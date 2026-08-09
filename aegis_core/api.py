"""FastAPI application for the local-only Aegis executive workspace."""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from aegis_core.foundation import FoundationGuard, FoundationViolation
from aegis_core.model_gateway import LocalModelGateway
from aegis_core.research import WebResearchService
from aegis_core.schemas import (
    AgentCreate,
    ApprovalDecision,
    ChatRequest,
    PluginChange,
    ProjectCreate,
    ResearchRequest,
    SkillAssignment,
    SkillCreate,
    TaskCreate,
    TaskUpdate,
)
from aegis_core.store import AegisStore, slugify
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
    research = WebResearchService(guard)
    session_token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        store.ensure_foundation_project(root, "https://github.com/Prabhu7886/ai-agency-foundation")
        yield

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
            result = await asyncio.to_thread(
                model_gateway.chat,
                payload.message,
                {"project": {key: project.get(key) for key in ("id", "name", "description", "repository_url")}},
            )
            store.update_task(task["id"], "completed", result["answer"][:10_000])
            return {"task": store.get_task(task["id"]), **result}
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
            evidence={"query": clean, "depth": payload.depth, "private_data_blocked": True},
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
        if approval.get("task_id"):
            store.update_task(approval["task_id"], "completed", f"Collected {result['source_count']} public sources")
        return result

    @app.get("/api/security/foundation", dependencies=[Depends(require_session)])
    async def foundation_status() -> dict[str, Any]:
        return {"policy": guard.status(), "local_model": model_gateway.health()}

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="aegis-ui")
    else:
        @app.get("/")
        async def root_message() -> dict[str, str]:
            return {"message": "Aegis API is ready. Build frontend/ to enable the local workspace."}

    return app


app = create_app()
