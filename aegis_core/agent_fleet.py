"""Authenticated local supervision for independently running Aegis agents."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from aegis_core.store import AegisStore
from utils.encryption import KeyManager


CONTRACT_VERSION = "1.0"
AUTOMATIC_CONTAINMENT_SEVERITIES = {"high", "critical"}
FULL_QUARANTINE_TERMS = {
    "approval_bypass",
    "credential_exposure",
    "credential_leak",
    "data_exfiltration",
    "data_leakage",
    "malware",
    "prompt_authority_bypass",
}
AUTHORITY_TERMS = {
    "ignore approval",
    "bypass approval",
    "disable security",
    "reveal secret",
    "credential",
    "password",
    "api key",
    "publish automatically",
    "delete files",
    "execute shell",
    "unrestricted access",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentBridgeError(RuntimeError):
    """Raised when an independent agent bridge fails closed."""


class AgentBridgeClient:
    """Small loopback-only client authenticated from the shared agency master key."""

    def __init__(self, endpoint: str, agent_id: str, timeout: float = 3.0) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or not parsed.hostname:
            raise AgentBridgeError("Agent bridges must use plain HTTP on loopback only")
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AgentBridgeError("Agent bridge URL is not a bounded loopback endpoint")
        self.endpoint = endpoint.rstrip("/")
        self.agent_id = agent_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False

    def _token(self) -> str:
        master = KeyManager().master_key()
        return hmac.new(master, f"agent-bridge-v1:{self.agent_id}".encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                f"{self.endpoint}{path}",
                json=payload,
                headers={"X-Aegis-Bridge": self._token(), "Accept": "application/json"},
                timeout=(1.0, self.timeout),
                allow_redirects=False,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AgentBridgeError(str(exc)) from exc
        if not isinstance(result, dict):
            raise AgentBridgeError("Agent bridge returned a non-object response")
        return result

    def snapshot(self) -> dict[str, Any]:
        return self._request("GET", "/v1/snapshot")

    def control(self, action: str, capability: str | None, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/control",
            {"action": action, "capability": capability, "reason": reason[:1000]},
        )

    def deploy_learning(self, update: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/learning",
            {
                "update_id": update["id"],
                "title": update["title"],
                "source": update["source"],
                "content": update["content"],
                "content_sha256": update["content_sha256"],
                "risk_level": update["risk_level"],
                "evaluation": update["evaluation"],
            },
        )

    def rollback_learning(self, update_id: str, reason: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/learning/{update_id}/rollback", {"reason": reason[:1000]})

    def containment_drill(self) -> dict[str, Any]:
        return self._request("POST", "/v1/drill/containment", {})


class AgentFleetService:
    """Polls agents, detects abnormal behavior, contains risk, and distributes learning."""

    def __init__(self, store: AegisStore) -> None:
        self.store = store

    def poll_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for endpoint in self.store.list_agent_endpoints():
            agent_id = endpoint["agent_id"]
            previous = self.store.latest_agent_snapshot(agent_id)
            client = AgentBridgeClient(endpoint["bridge_url"], agent_id)
            try:
                snapshot = client.snapshot()
                self._validate_snapshot(agent_id, snapshot)
                anomalies = self._detect_anomalies(agent_id, snapshot, (previous or {}).get("snapshot"))
                self.store.record_agent_snapshot(agent_id, snapshot)
                contained = [self._record_and_contain(client, agent_id, item) for item in anomalies]
                results.append({"agent_id": agent_id, "status": "connected", "anomalies": contained})
            except Exception as exc:
                self.store.mark_agent_unavailable(agent_id, str(exc))
                if endpoint.get("last_seen_at"):
                    anomaly = {
                        "fingerprint": hashlib.sha256(f"offline:{agent_id}".encode()).hexdigest(),
                        "severity": "medium",
                        "incident_type": "bridge_unavailable",
                        "title": f"{endpoint['name']} stopped reporting",
                        "capability": None,
                        "evidence": {"last_seen_at": endpoint.get("last_seen_at"), "error": str(exc)[:500]},
                        "action": None,
                        "solutions": [
                            "Confirm the independent agent process is running.",
                            "Verify its bridge remains bound to the configured loopback port.",
                            "Review its local logs before restarting it.",
                        ],
                    }
                    self._record_and_contain(client, agent_id, anomaly)
                results.append({"agent_id": agent_id, "status": "offline", "error": str(exc)[:500]})
        return results

    @staticmethod
    def _validate_snapshot(agent_id: str, snapshot: dict[str, Any]) -> None:
        if snapshot.get("contract_version") != CONTRACT_VERSION:
            raise AgentBridgeError("Unsupported Agent Bridge contract version")
        identity = snapshot.get("identity")
        if not isinstance(identity, dict) or identity.get("agent_id") != agent_id:
            raise AgentBridgeError("Agent Bridge identity does not match its registration")
        for field in ("health", "metrics", "controls", "skills"):
            if field not in snapshot:
                raise AgentBridgeError(f"Agent Bridge snapshot is missing {field}")

    def _detect_anomalies(
        self,
        agent_id: str,
        snapshot: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        events = snapshot.get("security_events", [])
        for event in events[:50]:
            if not isinstance(event, dict) or event.get("severity") not in AUTOMATIC_CONTAINMENT_SEVERITIES:
                continue
            event_type = str(event.get("event_type", "security_event")).lower()
            event_id = str(event.get("event_id") or hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest())
            full_stop = any(term in event_type for term in FULL_QUARANTINE_TERMS)
            capability = None if full_stop else str(event.get("capability") or "external_write")
            anomalies.append(
                {
                    "fingerprint": hashlib.sha256(f"{agent_id}:event:{event_id}".encode()).hexdigest(),
                    "severity": str(event["severity"]),
                    "incident_type": event_type,
                    "title": str(event.get("summary") or f"Security event reported by {agent_id}"),
                    "capability": capability,
                    "evidence": event,
                    "action": "quarantine" if full_stop else "pause_capability",
                    "solutions": [
                        "Review the originating task and the agent's security event evidence.",
                        "Correct the affected permission, tool, input, or policy before recovery.",
                        "Run the agent evaluation suite and resume only the contained capability first.",
                    ],
                }
            )

        metrics = snapshot.get("metrics", {})
        tasks_total = int(metrics.get("tasks_total", 0) or 0)
        failure_rate = float(metrics.get("failure_rate", 0) or 0)
        if tasks_total >= 5 and failure_rate >= 0.5:
            anomalies.append(
                {
                    "fingerprint": hashlib.sha256(f"{agent_id}:failure-rate:{tasks_total // 5}".encode()).hexdigest(),
                    "severity": "high",
                    "incident_type": "repeated_task_failures",
                    "title": f"{agent_id} crossed the repeated-failure threshold",
                    "capability": "task_execution",
                    "evidence": {"tasks_total": tasks_total, "failure_rate": failure_rate},
                    "action": "pause_capability",
                    "solutions": [
                        "Inspect the latest failed tasks without replaying sensitive inputs.",
                        "Verify model, storage, dependency, and data-freshness checks.",
                        "Run a sanitized successful task before resuming normal execution.",
                    ],
                }
            )

        resources = metrics.get("resources", {})
        memory_percent = float(resources.get("memory_percent", 0) or 0)
        if memory_percent >= 92:
            anomalies.append(
                {
                    "fingerprint": hashlib.sha256(f"{agent_id}:memory-pressure".encode()).hexdigest(),
                    "severity": "high",
                    "incident_type": "resource_pressure",
                    "title": f"{agent_id} reported unsafe memory pressure",
                    "capability": "model_inference",
                    "evidence": {"memory_percent": memory_percent},
                    "action": "pause_capability",
                    "solutions": [
                        "Allow the active local model to unload and check for duplicate agent processes.",
                        "Reduce concurrent model work or switch to the approved smaller local model.",
                        "Resume model inference after memory usage returns below the safety threshold.",
                    ],
                }
            )

        if previous:
            previous_version = str(previous.get("identity", {}).get("agent_version", ""))
            current_version = str(snapshot.get("identity", {}).get("agent_version", ""))
            previous_skills = self._skill_fingerprint(previous.get("skills", []))
            current_skills = self._skill_fingerprint(snapshot.get("skills", []))
            if (previous_version and current_version and previous_version != current_version) or previous_skills != current_skills:
                evidence = {
                    "previous_agent_version": previous_version,
                    "current_agent_version": current_version,
                    "skill_change": previous_skills != current_skills,
                }
                anomalies.append(
                    {
                        "fingerprint": hashlib.sha256(
                            f"{agent_id}:version:{previous_version}:{current_version}:{current_skills}".encode()
                        ).hexdigest(),
                        "severity": "medium",
                        "incident_type": "unreviewed_version_change",
                        "title": f"{agent_id} reported a version or skill change",
                        "capability": None,
                        "evidence": evidence,
                        "action": None,
                        "solutions": [
                            "Compare the reported version with Aegis learning and deployment history.",
                            "Run the agent's regression evaluation before accepting the new baseline.",
                            "Rollback the independent agent if the change was not authorized.",
                        ],
                    }
                )
        return anomalies

    @staticmethod
    def _skill_fingerprint(skills: Any) -> str:
        return hashlib.sha256(json.dumps(skills or [], sort_keys=True, default=str).encode()).hexdigest()

    def _record_and_contain(
        self,
        client: AgentBridgeClient,
        agent_id: str,
        anomaly: dict[str, Any],
    ) -> dict[str, Any]:
        action = anomaly.get("action")
        control_result: dict[str, Any] | None = None
        if action:
            try:
                control_result = client.control(action, anomaly.get("capability"), anomaly["title"])
                self.store.record_agent_control(
                    agent_id,
                    action,
                    anomaly.get("capability"),
                    anomaly["title"],
                    "automatic",
                    "completed",
                    control_result,
                )
            except Exception as exc:
                control_result = {"status": "failed", "error": str(exc)[:500]}
                self.store.record_agent_control(
                    agent_id,
                    action,
                    anomaly.get("capability"),
                    anomaly["title"],
                    "automatic",
                    "failed",
                    control_result,
                )
        report = {
            "summary": anomaly["title"],
            "evidence": anomaly["evidence"],
            "action_taken": control_result or {"status": "monitor_only"},
            "possible_solutions": anomaly["solutions"],
            "recovery_steps": [
                "Confirm the root cause and preserve relevant local evidence.",
                "Apply the smallest bounded correction.",
                "Run sanitized health and regression checks.",
                "Request owner-approved recovery for quarantined or major capabilities.",
                "Monitor the next operating cycle for recurrence.",
            ],
            "notification_state": "visible_in_aegis",
            "phone_notification_state": "not_connected",
        }
        incident = self.store.create_agent_incident(
            agent_id,
            anomaly["fingerprint"],
            anomaly["severity"],
            anomaly["incident_type"],
            anomaly["title"],
            report,
            anomaly.get("capability"),
            contained=bool(control_result and control_result.get("status") in {"paused", "quarantined"}),
        )
        return {"incident_id": incident["id"], "action": action, "control": control_result}

    def control_agent(
        self,
        agent_id: str,
        action: str,
        capability: str | None,
        reason: str,
        source: str = "owner",
    ) -> dict[str, Any]:
        endpoint = next((item for item in self.store.list_agent_endpoints(False) if item["agent_id"] == agent_id), None)
        if not endpoint:
            raise KeyError("Independent agent is not registered")
        result = AgentBridgeClient(endpoint["bridge_url"], agent_id).control(action, capability, reason)
        self.store.record_agent_control(agent_id, action, capability, reason, source, "completed", result)
        return result

    def run_containment_drill(self, agent_id: str) -> dict[str, Any]:
        endpoint = next((item for item in self.store.list_agent_endpoints(False) if item["agent_id"] == agent_id), None)
        if not endpoint:
            raise KeyError("Independent agent is not registered")
        drill = self.store.create_containment_drill(agent_id)
        try:
            result = AgentBridgeClient(endpoint["bridge_url"], agent_id).containment_drill()
            passed = result.get("status") == "passed" and result.get("business_capabilities_touched") is False
            report = {
                **result,
                "agent_id": agent_id,
                "bridge": endpoint["bridge_url"],
                "exercise_scope": "isolated diagnostic capability",
                "production_task_executed": False,
                "owner_recovery_gate_unchanged": True,
            }
            self.store.record_agent_control(
                agent_id,
                "containment_drill",
                "diagnostic_drill",
                "Authorized isolated containment and restoration exercise",
                "owner",
                "completed" if passed else "failed",
                report,
            )
            return self.store.finish_containment_drill(drill["id"], "passed" if passed else "failed", report)
        except Exception as exc:
            return self.store.finish_containment_drill(
                drill["id"],
                "failed",
                {"agent_id": agent_id, "error": str(exc)[:1000], "business_capabilities_touched": False},
            )

    def evaluate_learning(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload["content"])
        normalized = " ".join(content.casefold().split())
        authority_hits = sorted(term for term in AUTHORITY_TERMS if term in normalized)
        course = next(
            (item for item in self.store.list_academy_courses() if item["id"] == payload.get("course_id")),
            None,
        )
        checks = {
            "content_bounded": 40 <= len(content) <= 50_000,
            "content_hash_valid": bool(content.strip()),
            "no_authority_expansion": not authority_hits,
            "completed_course_linked": bool(course and course["status"] == "completed"),
            "low_risk_declared": payload["risk_level"] == "low",
        }
        auto = all(checks.values())
        return {
            "evaluated_at": utc_now(),
            "score": round(sum(checks.values()) / len(checks) * 100, 1),
            "passed": checks["content_bounded"] and checks["content_hash_valid"] and checks["no_authority_expansion"],
            "auto_deploy_allowed": auto,
            "checks": checks,
            "authority_terms_detected": authority_hits,
            "policy": "completed-course low-risk updates auto-deploy; all other updates require owner approval",
        }

    def create_learning_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        evaluation = self.evaluate_learning(payload)
        update = self.store.create_agent_learning_update(payload, evaluation)
        if evaluation["auto_deploy_allowed"]:
            return self.deploy_learning(update["id"])
        approval = self.store.create_approval(
            "agent_learning_deploy",
            f"Review major learning update for {payload['agent_id']}: {payload['title']}",
            payload["risk_level"],
            evidence={
                "learning_update_id": update["id"],
                "agent_id": payload["agent_id"],
                "content_sha256": update["content_sha256"],
                "evaluation": evaluation,
            },
            approval_queue="security_operations",
        )
        return {**update, "approval_id": approval["id"]}

    def deploy_learning(self, update_id: str) -> dict[str, Any]:
        update = self.store.get_agent_learning_update(update_id)
        if not update:
            raise KeyError("Learning update not found")
        endpoint = next(
            (item for item in self.store.list_agent_endpoints(False) if item["agent_id"] == update["agent_id"]),
            None,
        )
        if not endpoint:
            raise KeyError("Independent agent endpoint not found")
        try:
            result = AgentBridgeClient(endpoint["bridge_url"], update["agent_id"]).deploy_learning(update)
            return self.store.finish_agent_learning_update(update_id, "deployed", result)
        except Exception as exc:
            self.store.finish_agent_learning_update(update_id, "failed", {"error": str(exc)[:1000]})
            raise

    def rollback_learning(self, update_id: str, reason: str) -> dict[str, Any]:
        update = self.store.get_agent_learning_update(update_id)
        if not update:
            raise KeyError("Learning update not found")
        endpoint = next(
            (item for item in self.store.list_agent_endpoints(False) if item["agent_id"] == update["agent_id"]),
            None,
        )
        if not endpoint:
            raise KeyError("Independent agent endpoint not found")
        result = AgentBridgeClient(endpoint["bridge_url"], update["agent_id"]).rollback_learning(update_id, reason)
        return self.store.finish_agent_learning_update(update_id, "rolled_back", result)
