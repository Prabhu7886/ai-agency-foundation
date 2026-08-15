"""Reversible local CSV cleaning with provenance and quality reporting."""

from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis_core.foundation import FoundationGuard, FoundationViolation


class DataLabService:
    """Clean bounded local CSV inputs into new outputs without touching originals."""

    ALLOWED_OPERATIONS = {"trim_strings", "normalize_nulls", "deduplicate"}
    NULL_VALUES = {"n/a", "na", "null", "none", "nil", "-"}
    MAX_BYTES = 50 * 1024 * 1024

    def __init__(self, guard: FoundationGuard) -> None:
        self.guard = guard

    def plan(self, project: dict[str, Any], source_path: str, recipe: dict[str, Any]) -> dict[str, Any]:
        root = self.guard.validate_project_root(project["root_path"])
        source = Path(source_path).expanduser().resolve()
        if source != root and root not in source.parents:
            raise FoundationViolation("Data source must be inside the registered project root")
        if not source.is_file() or source.suffix.lower() != ".csv":
            raise FoundationViolation("Data Lab MVP accepts an existing CSV file")
        if source.stat().st_size > self.MAX_BYTES:
            raise FoundationViolation("Data Lab CSV limit is 50 MB")
        operations = [str(item) for item in recipe.get("operations", [])]
        if not operations or any(item not in self.ALLOWED_OPERATIONS for item in operations):
            raise FoundationViolation("Data Lab recipe contains an unsupported operation")
        return {
            "source_path": str(source),
            "source_sha256": self._sha256(source),
            "recipe": {"operations": operations, "required_columns": [str(item) for item in recipe.get("required_columns", [])]},
        }

    def execute(self, project: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        root = self.guard.validate_project_root(project["root_path"])
        source = Path(job["source_path"]).resolve()
        if source != root and root not in source.parents:
            raise FoundationViolation("Data source moved outside the registered project root")
        if self._sha256(source) != job["source_sha256"]:
            raise FoundationViolation("Data source changed after approval; create a new Data Lab job")
        recipe = job["recipe"]
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or any(not str(name).strip() for name in reader.fieldnames):
                raise FoundationViolation("CSV must have non-empty column headers")
            headers = [str(name) for name in reader.fieldnames]
            missing = [item for item in recipe.get("required_columns", []) if item not in headers]
            if missing:
                raise FoundationViolation(f"Required columns are missing: {', '.join(missing)}")
            rows = list(reader)

        input_rows = len(rows)
        normalized_nulls = 0
        if "trim_strings" in recipe["operations"] or "normalize_nulls" in recipe["operations"]:
            for row in rows:
                for key, value in list(row.items()):
                    clean = value.strip() if value and "trim_strings" in recipe["operations"] else (value or "")
                    if "normalize_nulls" in recipe["operations"] and clean.lower() in self.NULL_VALUES:
                        clean = ""
                        normalized_nulls += 1
                    row[key] = clean

        duplicates_removed = 0
        if "deduplicate" in recipe["operations"]:
            unique: list[dict[str, str]] = []
            seen: set[tuple[str, ...]] = set()
            for row in rows:
                fingerprint = tuple(row.get(header, "") for header in headers)
                if fingerprint in seen:
                    duplicates_removed += 1
                    continue
                seen.add(fingerprint)
                unique.append(row)
            rows = unique

        output_dir = root / "exports" / "aegis-data"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = output_dir / f"{source.stem}-cleaned-{timestamp}.csv"
        temporary = output.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        report = {
            "input_rows": input_rows,
            "output_rows": len(rows),
            "duplicates_removed": duplicates_removed,
            "nulls_normalized": normalized_nulls,
            "columns": headers,
            "source_unchanged": self._sha256(source) == job["source_sha256"],
        }
        return {"output_path": str(output), "output_sha256": self._sha256(output), "report": report}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
