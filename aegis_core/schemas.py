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


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    message: str = Field(min_length=1, max_length=50_000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=12)


class PromptCompileRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    message: str = Field(min_length=1, max_length=50_000)


class ResearchRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    query: str = Field(min_length=2, max_length=500)
    depth: Literal["quick", "standard", "deep"] = "standard"
    category: str = Field(default="general", min_length=2, max_length=80)
    regions: list[str] = Field(default_factory=lambda: ["Global"], max_length=20)
    purpose: Literal["world_pulse", "opportunity"] = "world_pulse"


class PluginChange(BaseModel):
    enabled: bool


class GitHubOperationRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    action: Literal["create_branch", "commit", "push", "draft_pr"]
    branch: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=160)
    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=20_000)
    base: str = Field(default="main", max_length=120)


class CodexTaskRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    message: str = Field(min_length=1, max_length=50_000)


class SkillVersionCreate(BaseModel):
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$", max_length=50)
    instructions: str = Field(min_length=20, max_length=50_000)


class SkillEvaluationCreate(BaseModel):
    evaluator: str = Field(min_length=2, max_length=100)
    score: float = Field(ge=0, le=100)
    passed: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


class SkillReleaseRequest(BaseModel):
    version_id: str = Field(min_length=2, max_length=100)
    action: Literal["promote", "rollback"]


class DataJobRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    source_path: str = Field(min_length=1, max_length=1000)
    operations: list[Literal["trim_strings", "normalize_nulls", "deduplicate"]] = Field(min_length=1, max_length=3)
    required_columns: list[str] = Field(default_factory=list, max_length=100)


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)


class OpportunityCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    thesis: str = Field(min_length=20, max_length=5_000)
    allocation: Literal["existing-80", "explore-20"]
    evidence: list[str] = Field(min_length=1, max_length=20)
    evidence_strength: float = Field(ge=0, le=100)
    revenue_potential: float = Field(ge=0, le=100)
    strategic_fit: float = Field(ge=0, le=100)
    speed_to_revenue: float = Field(ge=0, le=100)
    execution_risk: float = Field(ge=0, le=100)


class SolutionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    problem: str = Field(min_length=20, max_length=5_000)
    audience: str = Field(min_length=2, max_length=500)
    proof: str = Field(default="", max_length=5_000)
    owner_agent: str | None = Field(default=None, max_length=100)


class SolutionTransitionRequest(BaseModel):
    target_stage: Literal["validate", "prototype", "pilot", "scale"]
    proof: str = Field(min_length=10, max_length=5_000)
