"""Restricted GitHub engineering adapter for registered Aegis projects."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aegis_core.foundation import FoundationGuard, FoundationViolation


class GitHubAdapter:
    """Expose a small, auditable Git/GitHub operation set without a shell."""

    BRANCH_PATTERN = re.compile(r"^codex/[a-z0-9][a-z0-9._/-]{0,119}$")
    ACTIONS = {"create_branch", "commit", "push", "draft_pr"}

    def __init__(self, guard: FoundationGuard, executable: str | None = None) -> None:
        self.guard = guard
        configured = executable or os.getenv("AEGIS_GH_EXECUTABLE")
        candidates = [configured, shutil.which("gh"), r"C:\Program Files\GitHub CLI\gh.exe"]
        self.executable = next((str(Path(item)) for item in candidates if item and Path(item).is_file()), None)

    def status(self, project: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "installed": bool(self.executable),
            "executable": self.executable,
            "remote_verification": "blocked_offline" if self._offline() else "not_checked",
        }
        if project:
            root = self.guard.validate_project_root(project["root_path"])
            result["project_root"] = str(root)
            result["repository_url"] = self.guard.validate_repository_url(project.get("repository_url"))
            result["git"] = self._run(["git", "-C", str(root), "status", "--short", "--branch"], timeout=15, check=False)
        if self.executable and not self._offline():
            auth = self._run([self.executable, "auth", "status"], timeout=20, check=False)
            result["authenticated"] = auth["returncode"] == 0
            result["remote_verification"] = "verified" if result["authenticated"] else "failed"
            result["auth_summary"] = auth["output"][-2000:]
        else:
            result["authenticated"] = None
        return result

    def execute(self, project: dict[str, Any], action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action not in self.ACTIONS:
            raise FoundationViolation("Unsupported GitHub operation")
        root = self.guard.validate_project_root(project["root_path"])
        repository_url = self.guard.validate_repository_url(project.get("repository_url"))
        if not repository_url:
            raise FoundationViolation("The registered project does not have a GitHub repository URL")

        if action == "create_branch":
            branch = self._validate_branch(parameters.get("branch"))
            result = self._run(["git", "-C", str(root), "switch", "-c", branch], timeout=30)
        elif action == "commit":
            message = self._bounded_text(parameters.get("message"), "commit message", 160)
            staged = self._run(["git", "-C", str(root), "diff", "--cached", "--quiet"], timeout=15, check=False)
            if staged["returncode"] == 0:
                raise FoundationViolation("No staged changes are available to commit")
            if staged["returncode"] != 1:
                raise RuntimeError(f"Unable to inspect staged changes: {staged['output'][-2000:]}")
            result = self._run(["git", "-C", str(root), "commit", "-m", message], timeout=60)
        elif action == "push":
            self._assert_online()
            branch = self._validate_branch(parameters.get("branch"))
            result = self._run(["git", "-C", str(root), "push", "-u", "origin", branch], timeout=180)
        else:
            self._assert_online()
            if not self.executable:
                raise FoundationViolation("GitHub CLI is not installed or registered")
            branch = self._validate_branch(parameters.get("branch"))
            title = self._bounded_text(parameters.get("title"), "pull request title", 160)
            body = self._bounded_text(parameters.get("body"), "pull request body", 20_000)
            base = str(parameters.get("base") or "main")
            if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", base):
                raise FoundationViolation("Invalid pull request base branch")
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
                handle.write(body)
                body_path = Path(handle.name)
            try:
                result = self._run(
                    [self.executable, "pr", "create", "--draft", "--base", base, "--head", branch, "--title", title, "--body-file", str(body_path)],
                    cwd=root,
                    timeout=180,
                )
            finally:
                body_path.unlink(missing_ok=True)
        return {"action": action, "project_id": project["id"], "repository_url": repository_url, **result}

    @classmethod
    def _validate_branch(cls, value: Any) -> str:
        branch = str(value or "")
        if not cls.BRANCH_PATTERN.fullmatch(branch) or ".." in branch or "//" in branch:
            raise FoundationViolation("Aegis branches must use a valid codex/ prefix")
        return branch

    @staticmethod
    def _bounded_text(value: Any, label: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum or "\x00" in text:
            raise FoundationViolation(f"Invalid {label}")
        return text

    def _assert_online(self) -> None:
        if self._offline():
            raise FoundationViolation("Foundation offline mode blocks GitHub network operations")

    @staticmethod
    def _offline() -> bool:
        return os.getenv("AI_AGENCY_OFFLINE_MODE", "true").lower() == "true"

    @staticmethod
    def _run(command: list[str], *, cwd: Path | None = None, timeout: int, check: bool = True) -> dict[str, Any]:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=creation_flags,
            check=False,
        )
        output = completed.stdout[-20_000:]
        if check and completed.returncode != 0:
            raise RuntimeError(f"Approved command failed ({completed.returncode}): {output[-2000:]}")
        return {"returncode": completed.returncode, "output": output, "command": command[:3]}
