"""Install the reviewed controlled-maintenance policy into a protected Aegis runtime."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

import yaml


POLICY = {
    "controlled_maintenance_enabled": True,
    "require_single_use_approval": True,
    "branch_prefix": "codex/",
    "allowed_actions": ["verify_auth", "create_branch", "stage_files", "commit", "push", "draft_pr"],
}


def install(runtime_root: Path) -> Path:
    root = runtime_root.expanduser().resolve()
    security_path = root / "config" / "security.yaml"
    if not security_path.is_file():
        raise FileNotFoundError(f"Aegis security configuration is missing: {security_path}")
    payload = yaml.safe_load(security_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Aegis security configuration must be a mapping")
    payload["github"] = POLICY
    backup_path = security_path.with_suffix(".yaml.pre-github-maintenance")
    if not backup_path.exists():
        shutil.copy2(security_path, backup_path)
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    handle, temporary_name = tempfile.mkstemp(prefix="security-", suffix=".yaml", dir=security_path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, security_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return security_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args()
    installed = install(args.runtime_root)
    print(f"Installed controlled GitHub maintenance policy: {installed}")


if __name__ == "__main__":
    main()
