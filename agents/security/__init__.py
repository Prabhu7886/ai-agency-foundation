"""Security guardian components with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = ["SecurityAuditor"]


def __getattr__(name: str) -> Any:
    if name == "SecurityAuditor":
        from agents.security.auditor import SecurityAuditor

        return SecurityAuditor
    raise AttributeError(name)
