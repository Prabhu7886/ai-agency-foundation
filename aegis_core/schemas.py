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
    conversation_id: str | None = Field(default=None, min_length=2, max_length=100)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=12)
    privacy_mode: Literal["standard", "private_incognito"] = "standard"


class ConversationCreate(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    title: str = Field(default="New conversation", max_length=120)


class ResponseFeedbackCreate(BaseModel):
    rating: Literal["helpful", "too_generic", "incorrect", "missed_intent"]
    correction: str = Field(default="", max_length=10_000)


class TrainingCandidateDecision(BaseModel):
    status: Literal["approved", "rejected"]


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
    schedule_id: str | None = Field(default=None, max_length=100)


class WorldPulseSourceCandidateCreate(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    niche: str = Field(min_length=2, max_length=80)
    source_type: Literal["publisher", "public_account", "public_data"]
    locator: str = Field(min_length=3, max_length=1000)
    reason: str = Field(min_length=5, max_length=2000)
    identity_verified: bool = False


class WorldPulseScheduleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    niche: str = Field(min_length=2, max_length=80)
    query: str = Field(min_length=3, max_length=500)
    cadence_hours: int = Field(ge=1, le=720)


class WorldPulseScheduleUpdate(BaseModel):
    status: Literal["planned", "paused"]


class OpportunityCycleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    niche: str = Field(min_length=2, max_length=80)
    query: str = Field(min_length=3, max_length=500)
    allocation: Literal["existing-80", "explore-20"] = "existing-80"
    cadence_hours: int = Field(default=168, ge=1, le=720)


class OpportunityCycleUpdate(BaseModel):
    status: Literal["active", "paused"]


class PluginChange(BaseModel):
    enabled: bool


class GitHubOperationRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)
    action: Literal["verify_auth", "inspect_governance", "create_branch", "stage_files", "commit", "push", "draft_pr"]
    branch: str | None = Field(default=None, max_length=120)
    paths: list[str] | None = Field(default=None, min_length=1, max_length=50)
    message: str | None = Field(default=None, max_length=160)
    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=20_000)
    base: str = Field(default="main", max_length=120)


class SecurityScanRequest(BaseModel):
    project_id: str = Field(min_length=2, max_length=100)


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
    opportunity_id: str | None = Field(default=None, max_length=100)


class SolutionTransitionRequest(BaseModel):
    target_stage: Literal["validate", "prototype", "pilot", "scale"]
    proof: str = Field(min_length=10, max_length=5_000)


class AcademyCourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    provider: str = Field(default="Independent", min_length=2, max_length=100)
    source_url: str | None = Field(default=None, max_length=1000)
    learning_goal: str = Field(default="", max_length=2000)


class AcademyCourseUpdate(BaseModel):
    status: Literal["planned", "active", "completed", "paused"]
    progress: float = Field(ge=0, le=100)


class AcademyMaterialCreate(BaseModel):
    module_title: str = Field(min_length=3, max_length=300)
    source_url: str | None = Field(default=None, max_length=1000)
    content: str = Field(min_length=40, max_length=50_000)
    owner_attested: bool = False


class AcademyAssessmentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    assessment_type: Literal["quiz", "exercise", "project"]
    score: float = Field(ge=0, le=100)
    evidence: dict[str, Any] = Field(default_factory=dict)


class LearningMemoryCreate(BaseModel):
    kind: Literal["explicit", "inferred"] = "explicit"
    category: Literal["communication", "workflow", "learning", "business"]
    statement: str = Field(min_length=3, max_length=2000)
    reason: str = Field(default="", max_length=2000)
    confidence: float = Field(default=1, ge=0, le=1)
    affects_authority: bool = False


class LearningMemoryDecision(BaseModel):
    status: Literal["confirmed", "disabled"]


class IdentityProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)
    role_title: str = Field(min_length=3, max_length=100)
    pronouns: str = Field(default="she/her", min_length=2, max_length=30)
    conversation_style: Literal["professional_warm", "concise_executive", "collaborative_deep_dive"]
    presentation_mode: Literal["executive", "study", "studio", "public_incognito"]
    traits: list[str] = Field(min_length=3, max_length=8)

    @field_validator("display_name", "role_title", "pronouns", mode="before")
    @classmethod
    def strip_identity_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("traits")
    @classmethod
    def validate_traits(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in value if item.strip()]
        if len(cleaned) < 3 or any(len(item) > 40 for item in cleaned):
            raise ValueError("Provide 3-8 concise identity traits")
        return list(dict.fromkeys(cleaned))


class CompanionSessionCreate(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    session_type: Literal["study", "task", "research", "creative"]
    privacy_mode: Literal["standard", "private_incognito"] = "standard"
    screen_access: Literal["none", "local_preview"] = "none"
    purpose: str = Field(min_length=3, max_length=1000)


class CompanionNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    learning_candidate: bool = False


class CompanionSessionComplete(BaseModel):
    status: Literal["completed", "aborted"] = "completed"
    summary: str = Field(default="", max_length=5_000)


class ScreenAnalysisRequest(BaseModel):
    session_id: str = Field(min_length=2, max_length=100)
    image_data_url: str = Field(min_length=32, max_length=2_100_000)
    question: str = Field(default="What is visible, and what should I pay attention to?", min_length=3, max_length=2_000)


class AgentControlRequest(BaseModel):
    action: Literal["pause_capability", "resume_capability", "quarantine", "recover"]
    capability: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class AgentLearningUpdateCreate(BaseModel):
    agent_id: str = Field(min_length=2, max_length=120)
    course_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=3, max_length=300)
    source: str = Field(min_length=2, max_length=1000)
    content: str = Field(min_length=40, max_length=50_000)
    risk_level: RiskLevel = "low"


class AgentLearningRollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
