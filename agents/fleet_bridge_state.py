"""Encrypted enforcement state shared by independent Agent Bridge processes."""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.encryption import EncryptionManager, safe_identifier
from utils.paths import ensure_runtime_directories


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FleetContainmentError(PermissionError):
    """Raised when Aegis has contained a requested operation."""


class FleetBridgeState:
    """Persist quarantine, capability, and learning state using authenticated encryption."""

    VERSION = 1
    CONTROL_ACTIONS = {"pause_capability", "resume_capability", "quarantine", "recover"}

    def __init__(self, agent_id: str, path: Path | None = None) -> None:
        self.agent_id = safe_identifier(agent_id)
        runtime = ensure_runtime_directories()["runtime"]
        self.path = path or runtime / f"{self.agent_id}.bridge-state.enc"
        self.encryption = EncryptionManager()
        self.purpose = f"agent-bridge-state:{self.agent_id}:v{self.VERSION}"
        self._lock = threading.RLock()

    def _default(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "agent_id": self.agent_id,
            "quarantined": False,
            "quarantine_reason": None,
            "paused_capabilities": [],
            "controls": [],
            "learning_updates": [],
            "security_events": [],
            "task_records": [],
            "updated_at": utc_now(),
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return self._default()
            state = self.encryption.decrypt_json(self.path.read_bytes(), self.purpose)
            if not isinstance(state, dict) or state.get("agent_id") != self.agent_id:
                raise RuntimeError("Agent Bridge state identity mismatch")
            return state

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = dict(state)
            state["version"] = self.VERSION
            state["agent_id"] = self.agent_id
            state["updated_at"] = utc_now()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(self.encryption.encrypt_json(state, self.purpose))
            os.replace(temporary, self.path)
            return state

    def public_status(self) -> dict[str, Any]:
        state = self.load()
        return {
            "quarantined": bool(state["quarantined"]),
            "quarantine_reason": state.get("quarantine_reason"),
            "paused_capabilities": list(state.get("paused_capabilities", [])),
            "last_control": state.get("controls", [])[-1] if state.get("controls") else None,
            "updated_at": state["updated_at"],
        }

    def apply_control(self, action: str, capability: str | None, reason: str) -> dict[str, Any]:
        if action not in self.CONTROL_ACTIONS:
            raise ValueError("Unsupported Agent Bridge control action")
        if action in {"pause_capability", "resume_capability"} and not capability:
            raise ValueError("A bounded capability is required")
        state = self.load()
        paused = set(state.get("paused_capabilities", []))
        if action == "pause_capability":
            paused.add(safe_identifier(str(capability)))
        elif action == "resume_capability":
            paused.discard(safe_identifier(str(capability)))
        elif action == "quarantine":
            state["quarantined"] = True
            state["quarantine_reason"] = reason[:1000]
        elif action == "recover":
            state["quarantined"] = False
            state["quarantine_reason"] = None
        state["paused_capabilities"] = sorted(paused)
        event = {
            "action": action,
            "capability": capability,
            "reason": reason[:1000],
            "occurred_at": utc_now(),
        }
        state.setdefault("controls", []).append(event)
        state["controls"] = state["controls"][-100:]
        state = self.save(state)
        return {
            "status": "quarantined" if state["quarantined"] else "paused" if state["paused_capabilities"] else "active",
            **self.public_status(),
        }

    def assert_task_allowed(self, task_type: str, capabilities: list[str] | None = None) -> None:
        state = self.load()
        if state["quarantined"]:
            raise FleetContainmentError("Agent is quarantined by Aegis; owner-approved recovery is required")
        paused = set(state.get("paused_capabilities", []))
        requested = {safe_identifier(task_type), "task_execution", *(safe_identifier(item) for item in capabilities or [])}
        blocked = sorted(paused & requested)
        if blocked:
            raise FleetContainmentError(f"Aegis paused capability: {blocked[0]}")

    def record_task_start(self, task_id: str, task_type: str) -> None:
        state = self.load()
        now = utc_now()
        safe_id = safe_identifier(task_id)
        records = [item for item in state.get("task_records", []) if item.get("task_id") != safe_id]
        records.append({
            "task_id": safe_id,
            "task_type": safe_identifier(task_type),
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "duration_ms": None,
            "warning_count": 0,
        })
        state["task_records"] = records[-250:]
        self.save(state)

    def record_task_finish(self, task_id: str, status: str, duration_ms: int, warning_count: int = 0) -> None:
        state = self.load()
        safe_id = safe_identifier(task_id)
        record = next((item for item in state.get("task_records", []) if item.get("task_id") == safe_id), None)
        if record is None:
            record = {
                "task_id": safe_id,
                "task_type": "unknown",
                "created_at": utc_now(),
            }
            state.setdefault("task_records", []).append(record)
        record.update({
            "status": status if status in {"completed", "partial", "failed", "blocked"} else "failed",
            "updated_at": utc_now(),
            "duration_ms": max(0, int(duration_ms)),
            "warning_count": max(0, int(warning_count)),
        })
        state["task_records"] = state.get("task_records", [])[-250:]
        self.save(state)

    def task_records(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self.load().get("task_records", [])))[0:max(1, min(limit, 250))]

    def run_containment_drill(self) -> dict[str, Any]:
        """Exercise an isolated diagnostic capability and always restore it."""
        capability = "diagnostic_drill"
        blocked = False
        restored = False
        self.apply_control("pause_capability", capability, "Authorized non-business containment drill")
        try:
            try:
                self.assert_task_allowed("diagnostic_task", [capability])
            except FleetContainmentError:
                blocked = True
        finally:
            self.apply_control("resume_capability", capability, "Containment drill cleanup")
            restored = capability not in self.public_status()["paused_capabilities"]
        return {
            "status": "passed" if blocked and restored else "failed",
            "capability": capability,
            "blocked_while_paused": blocked,
            "restored_after_drill": restored,
            "business_capabilities_touched": False,
            "completed_at": utc_now(),
        }

    def deploy_learning(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content", ""))
        expected = str(payload.get("content_sha256", ""))
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not content.strip() or actual != expected:
            raise ValueError("Learning update content hash verification failed")
        evaluation = payload.get("evaluation", {})
        if not isinstance(evaluation, dict) or not evaluation.get("passed"):
            raise PermissionError("Learning update did not pass Aegis evaluation")
        state = self.load()
        update_id = safe_identifier(str(payload["update_id"]))
        existing = next((item for item in state.get("learning_updates", []) if item["update_id"] == update_id), None)
        if existing and existing.get("status") == "active":
            return {"status": "already_active", "update_id": update_id, "activated_at": existing["activated_at"]}
        record = {
            "update_id": update_id,
            "title": str(payload.get("title", ""))[:300],
            "source": str(payload.get("source", ""))[:1000],
            "content": content[:50_000],
            "content_sha256": actual,
            "risk_level": str(payload.get("risk_level", "low")),
            "status": "active",
            "activated_at": utc_now(),
            "rolled_back_at": None,
        }
        updates = [item for item in state.get("learning_updates", []) if item["update_id"] != update_id]
        updates.append(record)
        state["learning_updates"] = updates[-100:]
        self.save(state)
        return {
            "status": "deployed",
            "update_id": update_id,
            "content_sha256": actual,
            "activated_at": record["activated_at"],
            "rollback_available": True,
        }

    def rollback_learning(self, update_id: str, reason: str) -> dict[str, Any]:
        state = self.load()
        found = None
        for item in state.get("learning_updates", []):
            if item["update_id"] == update_id:
                item["status"] = "rolled_back"
                item["rolled_back_at"] = utc_now()
                item["rollback_reason"] = reason[:1000]
                found = item
                break
        if not found:
            raise KeyError("Agent learning update not found")
        self.save(state)
        return {"status": "rolled_back", "update_id": update_id, "rolled_back_at": found["rolled_back_at"]}

    def active_learning_context(self, limit: int = 8_000) -> str:
        state = self.load()
        active = [item for item in state.get("learning_updates", []) if item.get("status") == "active"]
        chunks = [
            f"SOURCE: {item['source']}\nTITLE: {item['title']}\nREFERENCE MATERIAL:\n{item['content']}"
            for item in active
        ]
        return "\n\n---\n\n".join(chunks)[-limit:]

    def learning_report(self) -> list[dict[str, Any]]:
        state = self.load()
        return [
            {key: value for key, value in item.items() if key != "content"}
            for item in reversed(state.get("learning_updates", []))
        ]
