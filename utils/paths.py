"""Canonical filesystem paths for the AI Agency runtime."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ROOT = Path(r"C:\AI_AGENCY")


def agency_root() -> Path:
    """Return the configured absolute agency root."""
    configured = os.getenv("AI_AGENCY_HOME")
    root = Path(configured).expanduser() if configured else DEFAULT_ROOT
    return root.resolve()


def ensure_runtime_directories() -> dict[str, Path]:
    """Create private runtime directories and return them by logical name."""
    root = agency_root()
    paths = {
        "root": root,
        "dashboard": root / "dashboard",
        "agents": root / "agents",
        "knowledge": root / "knowledge_pipeline",
        "databases": root / "databases",
        "vector_db": root / "databases" / "vector_db",
        "client_data": root / "databases" / "client_data",
        "exports": root / "databases" / "exports",
        "tools": root / "tools",
        "config": root / "config",
        "utils": root / "utils",
        "logs": root / "logs",
        "backups": root / "backups",
        "runtime": root / "runtime",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


if __name__ == "__main__":
    for name, path in ensure_runtime_directories().items():
        print(f"{name}: {path}")
