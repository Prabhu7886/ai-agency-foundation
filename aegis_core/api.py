"""FastAPI application for the local-only Aegis executive workspace."""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from aegis_core.foundation import FoundationGuard, FoundationViolation
from aegis_core.codex_adapter import CodexAppServerAdapter
from aegis_core.data_lab import DataLabService
from aegis_core.github_adapter import GitHubAdapter
from aegis_core.model_gateway import LocalModelGateway
from aegis_core.prompt_compiler import PromptCompiler
from aegis_core.research import WebResearchService
from aegis_core.schemas import (
    AgentCreate,
    ApprovalDecision,
    ChatRequest,
    CodexTaskRequest,
    DataJobRequest,
    GitHubOperationRequest,
    PluginChange,
    OpportunityCreate,
    ProjectCreate,
    PromptCompileRequest,
    ResearchRequest,
    SkillEvaluationCreate,
    SkillReleaseRequest,
    SkillVersionCreate,
    SkillAssignment,
    SkillCreate,
    SolutionCreate,
    SolutionTransitionRequest,
    TaskCreate,
    TaskUpdate,
    VoiceSpeakRequest,
)
from aegis_core.store import AegisStore, slugify
from aegis_core.world_pulse import WorldPulseService
from aegis_core.voice import LocalVoiceService
from utils.paths import agency_root


WORKSPACES = [
    {"id": "executive-home", "label": "Executive Home", "description": "Priorities, projects, agents, and decisions."},
    {"id": "agent-fleet", "label": "Agent Fleet", "description": "Agents, reusable skills, and controlled plugins."},
    {"id": "world-pulse", "label": "World Pulse", "description": "Verified global intelligence and material impact."},
    {"id": "opportunity-engine", "label": "Opportunity Engine", "description": "80% compounding, 20% exploration."},
    {"id": "solution-factory", "label": "Solution Factory", "description": "Turn real problems into tested solutions."},
    {"id": "approval-center", "label": "Approval Center", "description": "Review evidence before consequential action."},
    {"id": "security-sentinel", "label": "Security Sentinel", "description": "Security, code, model, and runtime integrity."},
    {"id": "voice-lounge", "label": "Voice Lounge", "description": "Private push-to-talk collaboration."},
    {"id": "data-lab", "label": "Data Lab", "description": "Clean, validate, and analyze without losing raw data."},
]


class LoopbackOnlyMiddleware(BaseHTTPMiddleware):
    """Reject non-loopback clients before application routes execute."""

    def __init__(self, app: Any, guard: FoundationGuard) -> None:
        super().__init__(app)
        self.guard = guard

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        try:
            self.guard.assert_loopback(request.client.host if request.client else None)
        except FoundationViolation as exc:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})
        return await call_next(request)


def create_app(
    store: AegisStore | None = None,
    guard: FoundationGuard | None = None,
    model_gateway: LocalModelGateway | None = None,
) -> FastAPI:
    root = agency_root()
    load_dotenv(root / ".env", override=False)
    guard = guard or FoundationGuard()
    store = store or AegisStore()
    model_gateway = model_gateway or LocalModelGateway(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    prompt_compiler = PromptCompiler(model_gateway)
    research = WebResearchService(guard)
    github = GitHubAdapter(guard)
    codex = CodexAppServerAdapter(guard)
    world_pulse = WorldPulseService(store)
    data_lab = DataLabService(guard)
    voice = LocalVoiceService()
    session_token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        store.ensure_foundation_project(root, "https://github.com/Prabhu7886/ai-agency-foundation")
        try:
            yield
        finally:
            codex.close()

    app = FastAPI(
        title="Aegis Local Executive API",
        version="0.1.0",
        description="Local-first executive control plane built on the AI Agency security foundation.",
        lifespan=lifespan,
        docs_url="/api/docs" if os.getenv("AEGIS_ENABLE_API_DOCS", "false").lower() == "true" else None,
        redoc_url=None,
    )
    app.state.store = store
    app.state.guard = guard
    app.state.model_gateway = model_gateway
    app.add_middleware(LoopbackOnlyMiddleware, guard=guard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:4173", "http://localhost:4173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Aegis-Session"],
    )

    @app.exception_handler(FoundationViolation)
    async def foundation_error(_request: Request, exc: FoundationViolation) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    def require_session(request: Request) -> None:
        supplied = request.cookies.get("aegis_session") or request.headers.get("X-Aegis-Session")
        if not supplied or not secrets.compare_digest(supplied, session_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local Aegis session required")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "local_only": True, "service": "aegis", "version": "0.1.0"}

    @app.post("/api/session")
    async def create_session(response: Response) -> dict[str, Any]:
        response.set_cookie(
            "aegis_session",
            session_token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=8 * 60 * 60,
        )
        return {"authenticated": True, "expires_in_seconds": 8 * 60 * 60}

    @app.get("/api/bootstrap", dependencies=[Depends(require_session)])
    async def bootstrap() -> dict[str, Any]:
        return {
            "brand": {
                "name": "Aegis",
                "descriptor": "Local Executive AI",
                "motto": "See clearly. Act decisively.",
                "creed": "No BS. Find the path. Make it happen. Prove the result.",
            },
            "workspaces": WORKSPACES,
            "overview": store.overview(),
            "projects": store.list_projects(),
            "agents": store.list_agents(),
            "skills": store.list_skills(),
            "plugins": store.list_plugins(),
            "approvals": store.list_approvals(),
            "world_pulse": store.list_world_pulse(),
            "opportunities": store.list_opportunities(),
            "solutions": store.list_solutions(),
            "activity": store.list_activity(),
            "foundation": guard.status(),
            "local_model": model_gateway.health(),
            "integrations": {"github": github.status(), "codex": codex.status()},
        }

    @app.get("/api/projects", dependencies=[Depends(require_session)])
    async def projects() -> list[dict[str, Any]]:
        return store.list_projects()

    @app.post("/api/projects", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_session)])
    async def create_project(payload: ProjectCreate) -> dict[str, Any]:
        proposed_root = payload.root_path or str(root / "projects" / slugify(payload.name))
        validated_root = guard.validate_project_root(proposed_root)
        repository_url = guard.validate_repository_url(payload.repository_url)
        return store.create_project(payload.name, payload.description, validated_root, repository_url)

    @app.get("/api/projects/{project_id}", dependencies=[Depends(require_session)])
    async def project(project_id: str) -> dict[str, Any]:
        item = store.get_project(project_id)
        if not item:
            raise HTTPException(status_code=404, detail="Project not found")
        return item

    @app.post(
        "/api/projects/{project_id}/tasks",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_session)],
    )
    async def create_task(project_id: str, payload: TaskCreate) -> dict[str, Any]:
        try:
            return store.create_task(
                project_id,
                payload.title,
                payload.prompt,
                payload.risk_level,
                payload.assigned_agent,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/tasks/{task_id}", dependencies=[Depends(require_session)])
    async def update_task(task_id: str, payload: TaskUpdate) -> dict[str, Any]:
        try:
            return store.update_task(task_id, payload.status, payload.result_summary)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/agents", dependencies=[Depends(require_session)])
    async def agents() -> list[dict[str, Any]]:
        return store.list_agents()

    @app.post("/api/agents", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_session)])
    async def create_agent(payload: AgentCreate) -> dict[str, Any]:
        try:
            return store.create_agent(payload.model_dump())
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="Agent name already exists") from exc
            raise

    @app.get("/api/skills", dependencies=[Depends(require_session)])
    async def skills() -> list[dict[str, Any]]:
        return store.list_skills()

    @app.post("/api/skills", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_session)])
    async def create_skill(payload: SkillCreate) -> dict[str, Any]:
        try:
            return store.create_skill(payload.model_dump())
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="Skill name already exists") from exc
            raise

    @app.post("/api/agents/{agent_id}/skills", dependencies=[Depends(require_session)])
    async def assign_skill(agent_id: str, payload: SkillAssignment) -> dict[str, Any]:
        try:
            store.assign_skill(agent_id, payload.skill_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"assigned": True, "agent_id": agent_id, "skill_id": payload.skill_id}

    @app.get("/api/skills/{skill_id}/versions", dependencies=[Depends(require_session)])
    async def skill_versions(skill_id: str) -> list[dict[str, Any]]:
        return store.list_skill_versions(skill_id)

    @app.post("/api/skills/{skill_id}/versions", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_session)])
    async def create_skill_version(skill_id: str, payload: SkillVersionCreate) -> dict[str, Any]:
        try:
            return store.create_skill_version(skill_id, payload.version, payload.instructions)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="Skill version already exists") from exc
            raise

    @app.post("/api/skill-versions/{version_id}/evaluations", dependencies=[Depends(require_session)])
    async def evaluate_skill_version(version_id: str, payload: SkillEvaluationCreate) -> dict[str, Any]:
        try:
            return store.evaluate_skill_version(version_id, payload.evaluator, payload.score, payload.passed, payload.evidence)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/skills/{skill_id}/release-requests", dependencies=[Depends(require_session)])
    async def request_skill_release(skill_id: str, payload: SkillReleaseRequest) -> dict[str, Any]:
        versions = store.list_skill_versions(skill_id)
        target = next((item for item in versions if item["id"] == payload.version_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Skill version not found")
        approval = store.create_approval(
            action="skill_release",
            summary=f"{payload.action.title()} skill version {target['version']}",
            risk_level="high",
            evidence={"skill_id": skill_id, "version_id": payload.version_id, "release_action": payload.action},
        )
        return {"approval": approval}

    @app.post("/api/skills/release-requests/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_skill_release(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "skill_release":
            raise HTTPException(status_code=404, detail="Skill release approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Skill release must be approved first")
        evidence = approval.get("evidence", {})
        try:
            if evidence.get("release_action") == "rollback":
                return store.rollback_skill_version(evidence["skill_id"], evidence["version_id"])
            return store.promote_skill_version(evidence["skill_id"], evidence["version_id"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/plugins", dependencies=[Depends(require_session)])
    async def plugins() -> list[dict[str, Any]]:
        return store.list_plugins()

    @app.post("/api/plugins/{plugin_id}", dependencies=[Depends(require_session)])
    async def change_plugin(plugin_id: str, payload: PluginChange) -> dict[str, Any]:
        plugin = next((item for item in store.list_plugins() if item["id"] == plugin_id), None)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        if not payload.enabled:
            return {"plugin": store.set_plugin_status(plugin_id, "disabled"), "approval": None}
        approval = store.create_approval(
            action="enable_plugin",
            summary=f"Enable {plugin['name']} with {plugin['data_policy']} data policy",
            risk_level="medium" if plugin["data_policy"] == "local_only" else "high",
            evidence={"plugin_id": plugin_id, "capabilities": plugin["capabilities"], "data_policy": plugin["data_policy"]},
        )
        return {"plugin": plugin, "approval": approval}

    @app.get("/api/approvals", dependencies=[Depends(require_session)])
    async def approvals() -> list[dict[str, Any]]:
        return store.list_approvals()

    @app.post("/api/approvals/{approval_id}/decision", dependencies=[Depends(require_session)])
    async def decide_approval(approval_id: str, payload: ApprovalDecision) -> dict[str, Any]:
        try:
            decided = store.decide_approval(approval_id, payload.decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if payload.decision == "approved" and decided["action"] == "enable_plugin":
            plugin_id = decided.get("evidence", {}).get("plugin_id")
            if plugin_id:
                store.set_plugin_status(plugin_id, "enabled", "configured_pending_credentials")
        return decided

    @app.post("/api/chat", dependencies=[Depends(require_session)])
    async def chat(payload: ChatRequest) -> dict[str, Any]:
        project = store.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        task = store.create_task(
            payload.project_id,
            payload.message[:120],
            payload.message,
            "low",
            "Internal Engineering" if any(word in payload.message.lower() for word in ("code", "build", "test", "github")) else "Aegis",
            "running",
        )
        try:
            project_context = {key: project.get(key) for key in ("id", "name", "description", "repository_url", "root_path")}
            compilation = await asyncio.to_thread(prompt_compiler.compile, payload.message, project_context)
            store.save_prompt_compilation(task["id"], compilation)
            result = await asyncio.to_thread(
                model_gateway.chat,
                compilation["compiled_prompt"],
                {"project": project_context, "prompt_compiler": {"objective": compilation["objective"], "risk_level": compilation["risk_level"]}},
            )
            store.update_task(task["id"], "completed", result["answer"][:10_000])
            return {"task": store.get_task(task["id"]), "compilation": compilation, **result}
        except Exception as exc:
            message = f"Local model unavailable: {str(exc)[:500]}"
            store.update_task(task["id"], "failed", message)
            return {
                "task": store.get_task(task["id"]),
                "answer": "Aegis could not reach the approved local model. The task was recorded and no cloud fallback was used.",
                "provider": "none",
                "verified_local": True,
                "error": message,
            }

    @app.post("/api/prompts/compile", dependencies=[Depends(require_session)])
    async def compile_prompt(payload: PromptCompileRequest) -> dict[str, Any]:
        project = store.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        context = {key: project.get(key) for key in ("id", "name", "description", "repository_url", "root_path")}
        return await asyncio.to_thread(prompt_compiler.compile, payload.message, context)

    @app.post("/api/research/requests", dependencies=[Depends(require_session)])
    async def request_research(payload: ResearchRequest) -> dict[str, Any]:
        clean = guard.sanitize_public_query(payload.query)
        task_id = None
        if payload.project_id:
            task = store.create_task(
                payload.project_id,
                f"Research: {clean[:100]}",
                clean,
                "medium",
                "Aegis",
                "awaiting_approval",
            )
            task_id = task["id"]
        approval = store.create_approval(
            action="public_web_research",
            summary=f"Run approved public web research: {clean}",
            risk_level="medium",
            project_id=payload.project_id,
            task_id=task_id,
            evidence={
                "query": clean,
                "depth": payload.depth,
                "category": payload.category,
                "regions": payload.regions,
                "private_data_blocked": True,
            },
        )
        return {"approval": approval, "task_id": task_id}

    @app.post("/api/research/requests/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_research(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Research approval not found")
        if approval["action"] != "public_web_research" or approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Research request must be approved first")
        evidence = approval.get("evidence", {})
        try:
            result = await asyncio.to_thread(research.search, evidence.get("query", ""), evidence.get("depth", "standard"))
        except FoundationViolation:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Research provider failed: {str(exc)[:500]}") from exc
        pulse_result = world_pulse.ingest(
            result,
            str(evidence.get("category", "general")),
            [str(item) for item in evidence.get("regions", ["Global"])],
        )
        if approval.get("task_id"):
            store.update_task(
                approval["task_id"],
                "completed",
                f"Collected {result['source_count']} public sources and accepted {pulse_result['accepted']} traceable signals",
            )
        return {**result, "world_pulse": pulse_result}

    @app.get("/api/security/foundation", dependencies=[Depends(require_session)])
    async def foundation_status() -> dict[str, Any]:
        return {"policy": guard.status(), "local_model": model_gateway.health()}

    @app.get("/api/github/status/{project_id}", dependencies=[Depends(require_session)])
    async def github_status(project_id: str) -> dict[str, Any]:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return await asyncio.to_thread(github.status, project)

    @app.post("/api/github/requests", dependencies=[Depends(require_session)])
    async def request_github_operation(payload: GitHubOperationRequest) -> dict[str, Any]:
        project = store.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        guard.validate_project_root(project["root_path"])
        guard.validate_repository_url(project.get("repository_url"))
        parameters = payload.model_dump(exclude={"project_id", "action"}, exclude_none=True)
        approval = store.create_approval(
            action="github_operation",
            summary=f"Run GitHub {payload.action.replace('_', ' ')} for {project['name']}",
            risk_level="high",
            project_id=project["id"],
            evidence={"operation": payload.action, "parameters": parameters, "registered_root": project["root_path"]},
        )
        return {"approval": approval}

    @app.post("/api/github/requests/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_github_operation(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "github_operation":
            raise HTTPException(status_code=404, detail="GitHub approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="GitHub operation must be approved first")
        project = store.get_project(approval.get("project_id"))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        evidence = approval.get("evidence", {})
        return await asyncio.to_thread(github.execute, project, evidence.get("operation", ""), evidence.get("parameters", {}))

    @app.get("/api/codex/status", dependencies=[Depends(require_session)])
    async def codex_status() -> dict[str, Any]:
        return await asyncio.to_thread(codex.status, True)

    @app.post("/api/codex/login/device", dependencies=[Depends(require_session)])
    async def codex_device_login() -> dict[str, Any]:
        approval = store.create_approval(
            action="codex_device_login",
            summary="Start ChatGPT device login for the local Codex adapter",
            risk_level="high",
            evidence={"provider": "OpenAI Codex app-server", "credential_storage": "Codex-managed"},
        )
        return {"approval": approval}

    @app.post("/api/codex/login/device/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_codex_device_login(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "codex_device_login":
            raise HTTPException(status_code=404, detail="Codex login approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Codex login must be approved first")
        return await asyncio.to_thread(codex.start_device_login)

    @app.post("/api/codex/requests", dependencies=[Depends(require_session)])
    async def request_codex_task(payload: CodexTaskRequest) -> dict[str, Any]:
        project = store.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        context = {key: project.get(key) for key in ("id", "name", "description", "repository_url", "root_path")}
        compilation = await asyncio.to_thread(prompt_compiler.compile, payload.message, context)
        task = store.create_task(project["id"], payload.message[:120], payload.message, compilation["risk_level"], "Internal Engineering", "awaiting_approval")
        store.save_prompt_compilation(task["id"], compilation)
        approval = store.create_approval(
            action="codex_task",
            summary=f"Run approved Codex task in {project['name']}: {compilation['objective'][:200]}",
            risk_level="high",
            project_id=project["id"],
            task_id=task["id"],
            evidence={"compiled_prompt": compilation["compiled_prompt"], "network_access": False, "root_path": project["root_path"]},
        )
        return {"task": store.get_task(task["id"]), "approval": approval}

    @app.post("/api/codex/requests/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_codex_task(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "codex_task":
            raise HTTPException(status_code=404, detail="Codex task approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Codex task must be approved first")
        project = store.get_project(approval.get("project_id"))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        store.update_task(approval["task_id"], "running", "Codex app-server turn started")
        try:
            result = await asyncio.to_thread(codex.run_approved_turn, project, approval.get("evidence", {}).get("compiled_prompt", ""))
            store.update_task(approval["task_id"], "completed", result["answer"][:10_000])
            return {"task": store.get_task(approval["task_id"]), "result": result}
        except Exception as exc:
            store.update_task(approval["task_id"], "failed", str(exc)[:2000])
            raise

    @app.post("/api/data-lab/jobs", dependencies=[Depends(require_session)])
    async def request_data_job(payload: DataJobRequest) -> dict[str, Any]:
        project = store.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        plan = data_lab.plan(
            project,
            payload.source_path,
            {"operations": payload.operations, "required_columns": payload.required_columns},
        )
        job = store.create_data_job(project["id"], plan)
        approval = store.create_approval(
            action="data_lab_job",
            summary=f"Create a cleaned copy of {Path(plan['source_path']).name}",
            risk_level="medium",
            project_id=project["id"],
            evidence={"job_id": job["id"], "source_sha256": plan["source_sha256"], "recipe": plan["recipe"], "raw_overwrite": False},
        )
        return {"job": job, "approval": approval}

    @app.post("/api/data-lab/jobs/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_data_job(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "data_lab_job":
            raise HTTPException(status_code=404, detail="Data Lab approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Data Lab job must be approved first")
        project = store.get_project(approval.get("project_id"))
        job = store.get_data_job(approval.get("evidence", {}).get("job_id", ""))
        if not project or not job:
            raise HTTPException(status_code=404, detail="Data Lab job context is missing")
        result = await asyncio.to_thread(data_lab.execute, project, job)
        return store.complete_data_job(job["id"], result)

    @app.get("/api/voice/status", dependencies=[Depends(require_session)])
    async def voice_status() -> dict[str, Any]:
        return voice.status()

    @app.post("/api/voice/transcribe", dependencies=[Depends(require_session)])
    async def transcribe_voice(request: Request, audio: bytes = Body()) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "")
        return await asyncio.to_thread(voice.transcribe, audio, content_type)

    @app.post("/api/voice/speak", dependencies=[Depends(require_session)])
    async def speak_voice(payload: VoiceSpeakRequest) -> dict[str, Any]:
        return await asyncio.to_thread(voice.speak, payload.text)

    @app.post("/api/opportunities", dependencies=[Depends(require_session)])
    async def create_opportunity(payload: OpportunityCreate) -> dict[str, Any]:
        return store.create_opportunity(payload.model_dump())

    @app.post("/api/solutions", dependencies=[Depends(require_session)])
    async def create_solution(payload: SolutionCreate) -> dict[str, Any]:
        return store.create_solution(payload.model_dump())

    @app.post("/api/solutions/{solution_id}/transitions", dependencies=[Depends(require_session)])
    async def request_solution_transition(solution_id: str, payload: SolutionTransitionRequest) -> dict[str, Any]:
        solution = next((item for item in store.list_solutions() if item["id"] == solution_id), None)
        if not solution:
            raise HTTPException(status_code=404, detail="Solution not found")
        return store.create_approval(
            action="solution_transition",
            summary=f"Advance {solution['title']} from {solution['stage']} to {payload.target_stage}",
            risk_level="medium",
            evidence={"solution_id": solution_id, "target_stage": payload.target_stage, "proof": payload.proof},
        )

    @app.post("/api/solutions/transitions/{approval_id}/execute", dependencies=[Depends(require_session)])
    async def execute_solution_transition(approval_id: str) -> dict[str, Any]:
        approval = store.get_approval(approval_id)
        if not approval or approval["action"] != "solution_transition":
            raise HTTPException(status_code=404, detail="Solution transition approval not found")
        if approval["status"] != "approved":
            raise HTTPException(status_code=409, detail="Solution transition must be approved first")
        evidence = approval["evidence"]
        try:
            return store.transition_solution(evidence["solution_id"], evidence["target_stage"], evidence["proof"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="aegis-ui")
    else:
        @app.get("/")
        async def root_message() -> dict[str, str]:
            return {"message": "Aegis API is ready. Build frontend/ to enable the local workspace."}

    return app


app = create_app()
