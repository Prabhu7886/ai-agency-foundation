"""Encrypted persistence layer with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = ["DatabaseSetup"]


def __getattr__(name: str) -> Any:
    if name == "DatabaseSetup":
        from databases.setup_databases import DatabaseSetup

        return DatabaseSetup
    raise AttributeError(name)
