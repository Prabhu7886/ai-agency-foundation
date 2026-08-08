"""Local secure agent runtime with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = ["AegisOrchestrator", "BaseAgent", "SecurityViolation"]


def __getattr__(name: str) -> Any:
    if name in {"BaseAgent", "SecurityViolation"}:
        from agents.base_agent import BaseAgent, SecurityViolation

        return {"BaseAgent": BaseAgent, "SecurityViolation": SecurityViolation}[name]
    if name == "AegisOrchestrator":
        from agents.orchestrator import AegisOrchestrator

        return AegisOrchestrator
    raise AttributeError(name)
