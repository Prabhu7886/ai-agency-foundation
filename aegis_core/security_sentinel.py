"""Bounded, local-only static security checks for registered Aegis projects."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from aegis_core.foundation import FoundationGuard


class SecuritySentinelService:
    """Inspect tracked source files without executing project code or using a network."""

    MAX_FILES = 2_000
    MAX_FILE_BYTES = 1_000_000
    TEXT_SUFFIXES = {
        ".cfg", ".css", ".env", ".html", ".ini", ".js", ".json", ".jsx", ".md",
        ".py", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
    }
    RULES = (
        ("critical", "private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "Private key material appears in a tracked file."),
        ("high", "hardcoded-secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"), "A secret-shaped value appears hardcoded in source."),
        ("high", "shell-execution", re.compile(r"\bshell\s*=\s*True\b"), "Shell execution can allow command injection; verify input boundaries."),
        ("high", "dynamic-execution", re.compile(r"(?<![\w.])(?:eval|exec)\s*\("), "Dynamic code execution requires manual review."),
        ("medium", "unsafe-yaml", re.compile(r"yaml\.load\s*\((?![^\n]*Loader\s*=)"), "Use a safe YAML loader for untrusted content."),
        ("medium", "wildcard-cors", re.compile(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]"), "Wildcard CORS weakens the local trust boundary."),
        ("medium", "public-bind", re.compile(r"(?:--host\s+0\.0\.0\.0|host\s*=\s*['\"]0\.0\.0\.0['\"])"), "A public network bind may expose the local service."),
    )

    def __init__(self, guard: FoundationGuard) -> None:
        self.guard = guard

    def scan(self, project: dict[str, Any]) -> dict[str, Any]:
        root = self.guard.validate_project_root(project["root_path"])
        files, source = self._project_files(root)
        findings: list[dict[str, Any]] = []
        scanned = 0
        skipped = 0

        for path in files[: self.MAX_FILES]:
            try:
                if path.suffix.lower() not in self.TEXT_SUFFIXES or path.stat().st_size > self.MAX_FILE_BYTES:
                    skipped += 1
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped += 1
                continue
            scanned += 1
            relative = path.relative_to(root).as_posix()
            for line_number, line in enumerate(text.splitlines(), start=1):
                for severity, rule, pattern, message in self.RULES:
                    if pattern.search(line):
                        findings.append(
                            {
                                "severity": severity,
                                "rule": rule,
                                "file": relative,
                                "line": line_number,
                                "message": message,
                            }
                        )
                        if len(findings) >= 200:
                            break
                if len(findings) >= 200:
                    break
            if len(findings) >= 200:
                break

        tracked_names = {path.relative_to(root).as_posix() for path in files}
        if ".env" in tracked_names:
            findings.append(
                {
                    "severity": "critical",
                    "rule": "tracked-env",
                    "file": ".env",
                    "line": None,
                    "message": "A .env file is tracked; remove it from version control and rotate exposed credentials.",
                }
            )
        dependency = self._dependency_posture(root, tracked_names)
        counts = {level: sum(item["severity"] == level for item in findings) for level in ("critical", "high", "medium", "low")}
        status = "critical" if counts["critical"] else "attention" if counts["high"] or counts["medium"] else "passed"
        return {
            "project_id": project["id"],
            "project_name": project["name"],
            "root": str(root),
            "mode": "local_static_read_only",
            "network_used": False,
            "file_source": source,
            "files_considered": min(len(files), self.MAX_FILES),
            "files_scanned": scanned,
            "files_skipped": skipped,
            "finding_limit_reached": len(findings) >= 200,
            "status": status,
            "counts": counts,
            "findings": findings,
            "dependency_posture": dependency,
            "limitations": [
                "Local pattern checks do not prove the absence of vulnerabilities.",
                "No external vulnerability database or package audit was contacted.",
                "Findings identify review targets and may include false positives.",
            ],
        }

    def _project_files(self, root: Path) -> tuple[list[Path], str]:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
        if result.returncode == 0:
            paths = self._bounded_paths(
                root,
                (item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item),
            )
            return paths, "git_tracked"
        fallback = (
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and not any(part in {".git", ".venv", "node_modules", "work", "dist"} for part in path.parts)
        )
        return self._bounded_paths(root, fallback), "bounded_walk"

    def _bounded_paths(self, root: Path, values: Iterable[str]) -> list[Path]:
        paths: list[Path] = []
        for value in values:
            target = (root / value).resolve()
            if target != root and root in target.parents and target.is_file():
                paths.append(target)
            if len(paths) >= self.MAX_FILES:
                break
        return paths

    @staticmethod
    def _dependency_posture(root: Path, tracked_names: set[str]) -> dict[str, Any]:
        python_manifest = next((name for name in ("requirements.lock", "requirements.txt", "pyproject.toml") if name in tracked_names), None)
        node_manifest = "frontend/package.json" if "frontend/package.json" in tracked_names else "package.json" if "package.json" in tracked_names else None
        node_lock = next((name for name in ("frontend/package-lock.json", "package-lock.json", "frontend/pnpm-lock.yaml", "pnpm-lock.yaml") if name in tracked_names), None)
        unpinned = 0
        requirements = root / "requirements.txt"
        if requirements.is_file():
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
                candidate = line.strip()
                if candidate and not candidate.startswith(("#", "-")) and "==" not in candidate:
                    unpinned += 1
        return {
            "python_manifest": python_manifest,
            "python_unpinned_requirements": unpinned,
            "node_manifest": node_manifest,
            "node_lockfile": node_lock,
            "external_advisory_check": "not_run_offline",
        }
