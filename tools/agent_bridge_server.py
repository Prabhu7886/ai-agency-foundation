"""Run an authenticated loopback Agent Bridge for Commerce or Career Studio."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.fleet_bridge_state import FleetBridgeState
from utils.encryption import KeyManager


CONTRACT_VERSION = "1.0"


def bridge_master_key() -> bytes:
    """Load the supervision transport key without changing the agent data key."""
    auth_env = os.getenv("AEGIS_BRIDGE_AUTH_ENV_PATH", "").strip()
    if not auth_env:
        return KeyManager().master_key()
    env_path = Path(auth_env).expanduser().resolve(strict=True)
    encoded = str(dotenv_values(env_path).get(KeyManager.ENV_NAME, "")).strip()
    try:
        key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("The Agent Bridge authentication key is invalid") from exc
    if len(key) != 32:
        raise RuntimeError("The Agent Bridge authentication key must decode to 32 bytes")
    return key


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ControlRequest(BaseModel):
    action: str = Field(max_length=80)
    capability: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class LearningRequest(BaseModel):
    update_id: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=3, max_length=300)
    source: str = Field(min_length=2, max_length=1000)
    content: str = Field(min_length=40, max_length=50_000)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk_level: str = Field(max_length=20)
    evaluation: dict[str, Any]


class RollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RuntimeAdapter:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        if kind == "commerce":
            from agents.commerce.agent import CommerceAgent

            self.agent = CommerceAgent()
            self.agent.repository.database.setup_sqlcipher()
            self.agent_id = "aegis-commerce"
        elif kind == "career":
            from agents.career_agent import CareerAgent

            self.agent = CareerAgent()
            self.agent_id = "aegis-career-studio"
        else:
            raise ValueError("Agent Bridge kind must be commerce or career")
        self.state = FleetBridgeState(self.agent_id)

    def identity(self) -> dict[str, Any]:
        if self.kind == "commerce":
            identity = self.agent.identity.model_dump(mode="json")
            identity["prohibited_actions"] = ["unapproved_external_write", "credential_storage", "approval_bypass"]
            return identity
        identity = self.agent.fleet_identity()
        identity["agent_version"] = self.agent.report_status()["version"]
        identity["supervisor_agent_id"] = "aegis"
        identity["supported_platforms"] = ["local-career-studio"]
        identity["external_write_policy"] = "disabled"
        return identity

    def health(self) -> dict[str, Any]:
        raw = self.agent.fleet_health()
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json")
        if self.kind == "commerce":
            checks = [item for item in raw.get("checks", []) if item.get("name") not in {"local_model_endpoint", "etsy_connection", "erank_connection"}]
            endpoint = self.agent._verify_local_ollama()
            model_check: dict[str, Any]
            try:
                session = requests.Session()
                session.trust_env = False
                response = session.get(f"{endpoint}/api/tags", timeout=(0.5, 2.0), allow_redirects=False)
                response.raise_for_status()
                models = [str(item.get("name", "")) for item in response.json().get("models", [])]
                model_check = {
                    "name": "local_model_endpoint",
                    "status": "pass" if models else "fail",
                    "detail": f"Loopback Ollama reported {len(models)} installed model(s)." if models else "Ollama responded without an installed model.",
                    "observed_at": utc_now(),
                }
            except Exception as exc:
                models = []
                model_check = {
                    "name": "local_model_endpoint",
                    "status": "fail",
                    "detail": f"Loopback Ollama health check failed: {str(exc)[:180]}",
                    "observed_at": utc_now(),
                }
            marketplace_configured = bool(os.getenv("ETSY_API_KEY") and os.getenv("ETSY_SHOP_ID"))
            checks.extend([
                model_check,
                {
                    "name": "etsy_connection",
                    "status": "pass" if marketplace_configured else "unknown",
                    "detail": "Credential presence verified; no secret value exposed." if marketplace_configured else "Not configured. Local research and listing-package work remains available.",
                    "observed_at": utc_now(),
                    "required_for_local_cycle": False,
                },
                {
                    "name": "erank_connection",
                    "status": "unknown",
                    "detail": "Optional owner-provided CSV import; no live credential required.",
                    "observed_at": utc_now(),
                    "required_for_local_cycle": False,
                },
            ])
            raw = {**raw, "checks": checks, "model_inventory": models, "status": "healthy" if model_check["status"] == "pass" else "degraded"}
        state = str(raw.get("status") or raw.get("state") or "degraded")
        if self.state.public_status()["quarantined"]:
            state = "quarantined"
        return {**raw, "status": state, "observed_at": raw.get("observed_at") or raw.get("last_heartbeat") or utc_now()}

    def metrics(self) -> dict[str, Any]:
        if self.kind == "commerce":
            with self.agent.repository.database.connection() as connection:
                task_rows = connection.execute("SELECT status, COUNT(*) FROM commerce_tasks GROUP BY status").fetchall()
                tasks_by_status = {str(row[0]): int(row[1]) for row in task_rows}
                opportunities = int(connection.execute("SELECT COUNT(*) FROM commerce_opportunities").fetchone()[0])
                products = int(connection.execute("SELECT COUNT(*) FROM commerce_products").fetchone()[0])
                pending_approvals = int(
                    connection.execute("SELECT COUNT(*) FROM commerce_approvals WHERE status = 'pending'").fetchone()[0]
                )
            domain = {"opportunities": opportunities, "products": products, "pending_approvals": pending_approvals}
        else:
            workspace = self.agent.workspace()
            records = self.state.task_records(250)
            tasks_by_status: dict[str, int] = {}
            for record in records:
                state = str(record.get("status", "unknown"))
                tasks_by_status[state] = tasks_by_status.get(state, 0) + 1
            if not records:
                completed_outputs = len(workspace.get("jobs", [])) + len(workspace.get("resumes", [])) + len(workspace.get("interviews", []))
                if completed_outputs:
                    tasks_by_status["completed"] = completed_outputs
            domain = {
                "profile_facts": len(workspace.get("profile", {}).get("facts", [])),
                "jobs": len(workspace.get("jobs", [])),
                "resumes": len(workspace.get("resumes", [])),
                "interviews": len(workspace.get("interviews", [])),
            }
        total = sum(tasks_by_status.values())
        failed = tasks_by_status.get("failed", 0)
        # Duration and last-run timing come only from the encrypted bridge ledger.
        # Older database rows remain valid counts but are not given invented timings.
        task_records = self.state.task_records(250)
        durations = [int(item["duration_ms"]) for item in task_records if item.get("duration_ms") is not None]
        completed = tasks_by_status.get("completed", 0) + tasks_by_status.get("partial", 0)
        process = psutil.Process(os.getpid())
        return {
            "tasks_total": total,
            "tasks_by_status": tasks_by_status,
            "failure_rate": round(failed / total, 4) if total else 0,
            "success_rate": round(completed / total, 4) if total else 0,
            "average_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "last_success_at": next((item.get("updated_at") for item in task_records if item.get("status") == "completed"), None),
            "last_failure_at": next((item.get("updated_at") for item in task_records if item.get("status") == "failed"), None),
            "domain": domain,
            "resources": {
                "cpu_percent": process.cpu_percent(interval=None),
                "memory_percent": round(process.memory_percent(), 2),
                "rss_mb": round(process.memory_info().rss / 1024 / 1024, 1),
            },
        }

    def tasks(self) -> list[dict[str, Any]]:
        if self.kind == "commerce":
            with self.agent.repository.database.connection() as connection:
                rows = connection.execute(
                    """SELECT task_id, task_type, status, created_at, updated_at
                    FROM commerce_tasks ORDER BY updated_at DESC LIMIT 25"""
                ).fetchall()
            return [
                {"task_id": row[0], "task_type": row[1], "status": row[2], "created_at": row[3], "updated_at": row[4]}
                for row in rows
            ]
        workspace = self.agent.workspace()
        records = self.state.task_records(25)
        if records:
            return records
        items: list[dict[str, Any]] = []
        for category in ("jobs", "resumes", "interviews"):
            for item in reversed(workspace.get(category, [])):
                items.append(
                    {
                        "task_id": str(item.get("id", "")),
                        "task_type": category[:-1],
                        "status": "completed",
                        "created_at": item.get("created_at") or item.get("captured_at") or workspace.get("updated_at"),
                        "updated_at": item.get("updated_at") or item.get("created_at") or workspace.get("updated_at"),
                    }
                )
        return items[:25]

    def approvals(self) -> list[dict[str, Any]]:
        if self.kind != "commerce":
            return []
        with self.agent.repository.database.connection() as connection:
            rows = connection.execute(
                """SELECT approval_id, task_id, action_type, platform, target, summary, risk_level,
                requested_at, expires_at, status FROM commerce_approvals ORDER BY requested_at DESC LIMIT 25"""
            ).fetchall()
        keys = ["approval_id", "task_id", "action_type", "platform", "target", "summary", "risk_level", "requested_at", "expires_at", "status"]
        return [dict(zip(keys, row)) for row in rows]

    def security_events(self) -> list[dict[str, Any]]:
        if self.kind != "commerce":
            return self.state.load().get("security_events", [])[-25:]
        with self.agent.repository.database.connection() as connection:
            rows = connection.execute(
                """SELECT event_id, task_id, event_type, severity, occurred_at, summary, containment
                FROM commerce_security_events ORDER BY occurred_at DESC LIMIT 25"""
            ).fetchall()
        keys = ["event_id", "task_id", "event_type", "severity", "occurred_at", "summary", "containment"]
        return [dict(zip(keys, row)) for row in rows]

    def skills(self) -> list[dict[str, Any]]:
        if self.kind == "commerce":
            return [item.model_dump(mode="json") for item in self.agent.skill_versions()]
        report = self.agent.skill_report()
        return [{"skill_id": key, "version": value, "implementation": "career-studio"} for key, value in report["skills"].items()]

    def snapshot(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "observed_at": utc_now(),
            "identity": self.identity(),
            "health": self.health(),
            "metrics": self.metrics(),
            "tasks": self.tasks(),
            "approvals": self.approvals(),
            "security_events": self.security_events(),
            "skills": self.skills(),
            "controls": self.state.public_status(),
            "learning": self.state.learning_report(),
        }


def create_app(kind: str) -> FastAPI:
    runtime = RuntimeAdapter(kind)
    app = FastAPI(title=f"{runtime.agent_id} Agent Bridge", version=CONTRACT_VERSION, docs_url=None, redoc_url=None)

    async def authenticate(request: Request, x_aegis_bridge: str | None = Header(default=None)) -> None:
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="Agent Bridge accepts loopback clients only")
        expected = hmac.new(
            bridge_master_key(),
            f"agent-bridge-v1:{runtime.agent_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not x_aegis_bridge or not hmac.compare_digest(x_aegis_bridge, expected):
            raise HTTPException(status_code=401, detail="Authenticated Aegis bridge token required")

    @app.get("/v1/snapshot", dependencies=[Depends(authenticate)])
    async def snapshot() -> dict[str, Any]:
        return runtime.snapshot()

    @app.post("/v1/control", dependencies=[Depends(authenticate)])
    async def control(payload: ControlRequest) -> dict[str, Any]:
        return runtime.state.apply_control(payload.action, payload.capability, payload.reason)

    @app.post("/v1/learning", dependencies=[Depends(authenticate)])
    async def learning(payload: LearningRequest) -> dict[str, Any]:
        return runtime.state.deploy_learning(payload.model_dump())

    @app.post("/v1/learning/{update_id}/rollback", dependencies=[Depends(authenticate)])
    async def rollback(update_id: str, payload: RollbackRequest) -> dict[str, Any]:
        return runtime.state.rollback_learning(update_id, payload.reason)

    @app.post("/v1/drill/containment", dependencies=[Depends(authenticate)])
    async def containment_drill() -> dict[str, Any]:
        return runtime.state.run_containment_drill()

    app.state.runtime = runtime
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local authenticated Aegis Agent Bridge")
    parser.add_argument("--agent", choices=["commerce", "career"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Agent Bridge port must be between 1024 and 65535")
    uvicorn.run(create_app(args.agent), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
