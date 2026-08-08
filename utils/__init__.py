"""Shared secure utilities for AI Agency, loaded lazily for clean CLI execution."""

from __future__ import annotations

from typing import Any

__all__ = ["EncryptionManager", "KeyManager", "SecurityLogger", "agency_root", "get_logger"]


def __getattr__(name: str) -> Any:
    if name in {"EncryptionManager", "KeyManager"}:
        from utils.encryption import EncryptionManager, KeyManager

        return {"EncryptionManager": EncryptionManager, "KeyManager": KeyManager}[name]
    if name in {"SecurityLogger", "get_logger"}:
        from utils.logger import SecurityLogger, get_logger

        return {"SecurityLogger": SecurityLogger, "get_logger": get_logger}[name]
    if name == "agency_root":
        from utils.paths import agency_root

        return agency_root
    raise AttributeError(name)
