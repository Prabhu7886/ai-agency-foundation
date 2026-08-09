"""Pydantic contracts for the local Aegis control plane."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RiskLevel = Literal["low", "medium", "high", "critical"]
TaskStatus = Literal["planned", "awaiting_approval", "running", "completed", "failed", "cancelled"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    root_path: str | None = Field(default=None, max_length=500)
    repository_url: str | None = Field(default=None, max_length=500)

    @field_validator("name", "description", "root_path", "repository_url", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    prompt: str = Field(default="", max_length=50_000)
    risk_level: RiskLevel = "low"
    assigned_agent: str | None = Field(default=None, max_length=100)


class TaskUpdate(BaseModel):
    status: TaskStatus
    result_summary: str | None = Field(default=None, max_length=10_000)


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    model_policy: str = Field(default="local-auto", max_length=120)
    capabilities: list[str] = Field(default_factory=list, max_length=50)


class SkillCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    risk_level: RiskLevel = "low"
    capabilities: list[str] = Field(default_factory=list, max_length=50)


class SkillAssignment(BaseModel):
    skill_id: str = Field(min_length=2, max_length=100)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "declined"]


class ChatRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    message: str = Field(min_length=1, max_length=50_000)


class ResearchRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    query: str = Field(min_length=2, max_length=500)
    depth: Literal["quick", "standard", "deep"] = "standard"


class PluginChange(BaseModel):
    enabled: bool
