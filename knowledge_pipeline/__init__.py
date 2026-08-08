"""AI Agency secure knowledge pipeline with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = ["KnowledgePipeline"]


def __getattr__(name: str) -> Any:
    if name == "KnowledgePipeline":
        from knowledge_pipeline.pipeline import KnowledgePipeline

        return KnowledgePipeline
    raise AttributeError(name)
