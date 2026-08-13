"""Local operational hardening, backup evidence, and non-destructive restore drills."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from tools.backup_manager import EncryptedBackupManager
from utils.paths import ensure_runtime_directories


class OperationsService:
    def __init__(self, backups: EncryptedBackupManager | None = None) -> None:
        self.backups = backups or EncryptedBackupManager()
        self.paths = ensure_runtime_directories()

    def status(self) -> dict[str, Any]:
        artifacts = sorted(self.paths["backups"].glob("ai-agency-*.zip.enc"), key=lambda item: item.stat().st_mtime, reverse=True)
        latest = artifacts[0] if artifacts else None
        return {
            "backup_count": len(artifacts),
            "latest_backup": latest.name if latest else None,
            "latest_backup_bytes": latest.stat().st_size if latest else 0,
            "encrypted_only": all(item.name.endswith(".enc") for item in self.paths["backups"].glob("*") if item.is_file()),
            "restore_policy": "non_destructive_drill_only",
            "production_restore": "manual_owner_approved",
            "startup_launcher": str((Path(__file__).resolve().parents[1] / "tools" / "windows" / "start_aegis_stack.ps1")),
        }

    def create_backup(self) -> dict[str, Any]:
        return self.backups.create_backup()

    def restore_drill(self, backup_name: str | None = None) -> dict[str, Any]:
        artifacts = sorted(self.paths["backups"].glob("ai-agency-*.zip.enc"), key=lambda item: item.stat().st_mtime, reverse=True)
        source = next((item for item in artifacts if item.name == backup_name), None) if backup_name else (artifacts[0] if artifacts else None)
        if not source:
            raise FileNotFoundError("No encrypted backup is available for a restore drill")
        timestamp = source.name.removeprefix("ai-agency-").removesuffix(".zip.enc")
        target = Path(tempfile.mkdtemp(prefix="aegis-restore-drill-", dir=self.paths["runtime"]))
        try:
            restored = self.backups.restore_to(source, target, timestamp)
            manifest_path = restored / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            mismatches: list[str] = []
            for entry in manifest.get("files", []):
                path = restored / str(entry["path"])
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                    mismatches.append(str(entry["path"]))
            return {
                "status": "passed" if not mismatches else "failed",
                "backup": source.name,
                "files_verified": len(manifest.get("files", [])) - len(mismatches),
                "mismatches": mismatches[:20],
                "production_data_changed": False,
                "temporary_restore_deleted": True,
            }
        finally:
            shutil.rmtree(target, ignore_errors=True)
