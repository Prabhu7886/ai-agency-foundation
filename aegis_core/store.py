"""Encrypted persistence for Aegis workspaces, projects, agents, skills, and approvals."""

from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from databases.setup_databases import DatabaseSetup


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "project"


class AegisStore:
    """Small SQLCipher repository; plaintext database fallbacks are prohibited."""

    def __init__(self, database: DatabaseSetup | None = None) -> None:
        self.database = database or DatabaseSetup()

    def initialize(self) -> None:
        self.database.setup_sqlcipher()
        self._seed_registry()
        self.expire_stale_approvals()

    @staticmethod
    def _decode(value: Any, default: Any) -> Any:
        if value in {None, ""}:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    @staticmethod
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        columns = [item[0] for item in cursor.description or []]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _row(cursor: Any) -> dict[str, Any] | None:
        rows = AegisStore._rows(cursor)
        return rows[0] if rows else None

    def _seed_registry(self) -> None:
        now = utc_now()
        agents = [
            (
                "agent-engineering",
                "Internal Engineering",
                "engineering and platform integrity",
                "Builds, tests, reviews, and prepares GitHub delivery under approval controls.",
                "local-auto",
                "ready",
                "proposal-v1",
                ["code", "tests", "security-review", "git-draft", "architecture"],
            )
        ]
        skills = [
            ("skill-secure-coding", "Secure Coding", "engineering", "Plan, implement, test, and review bounded code changes.", "testing", "medium", ["code", "tests", "diff-review"]),
            ("skill-github-delivery", "GitHub Delivery", "engineering", "Prepare a branch, commit, push, and draft PR after approval.", "proposal", "high", ["branch", "commit", "push", "draft-pr"]),
            ("skill-web-research", "Verified Web Research", "research", "Search public sources with citations, freshness, and confidence labels.", "proposal", "medium", ["web-search", "citations", "source-quality"]),
            ("skill-data-quality", "Data Quality", "data", "Profile, validate, standardize, deduplicate, and report without overwriting raw data.", "testing", "medium", ["profile", "validate", "clean", "qa-report"]),
            ("skill-content-studio", "Content Studio", "creative", "Research and prepare multi-platform ideas, scripts, storyboards, and content packages.", "proposal", "medium", ["ideas", "scripts", "storyboards", "platform-adaptation"]),
            ("skill-security-review", "Security Review", "security", "Check secrets, dependencies, permissions, tests, and risky changes.", "active", "high", ["secrets", "dependencies", "permissions", "runtime-health"]),
        ]
        plugins = [
            ("plugin-ollama", "Ollama Local Models", "models", "Primary local inference runtime.", "enabled", "configured", 0, "local_only", ["chat", "routing", "local-inference"]),
            ("plugin-github", "GitHub", "engineering", "External source control, checks, branches, and draft pull requests.", "available", "not_connected", 1, "registered_projects_only", ["repositories", "branches", "pull-requests", "checks"]),
            ("plugin-codex", "Codex", "engineering", "Escalation specialist for difficult engineering and independent review.", "available", "not_connected", 1, "redacted_or_approved", ["coding", "review", "tests"]),
            ("plugin-gemini", "Gemini", "intelligence", "Optional cloud specialist for approved research and model improvement tasks.", "available", "not_connected", 1, "redacted_or_approved", ["analysis", "multimodal", "research"]),
            ("plugin-web", "Web Research", "research", "Approved public-source search and website analysis.", "disabled", "approval_required", 1, "public_queries_only", ["search", "website-analysis", "citations"]),
            ("plugin-voice", "Local Voice", "experience", "Push-to-talk conversation through a future local transcription engine.", "planned", "not_connected", 1, "local_audio_only", ["record", "transcribe", "speak"]),
        ]
        with self.database.connection() as connection:
            connection.executemany(
                """INSERT OR IGNORE INTO aegis_agent_registry
                (id, name, role, description, model_policy, status, prompt_version, capabilities_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(*row[:7], json.dumps(row[7]), now, now) for row in agents],
            )
            connection.executemany(
                """INSERT OR IGNORE INTO aegis_skill_registry
                (id, name, category, description, version, status, risk_level, capabilities_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, '0.1.0', ?, ?, ?, ?, ?)""",
                [(row[0], row[1], row[2], row[3], row[4], row[5], json.dumps(row[6]), now, now) for row in skills],
            )
            connection.executemany(
                """INSERT OR IGNORE INTO aegis_skill_versions
                (id, skill_id, version, instructions, checksum_sha256, status, created_at, promoted_at)
                VALUES (?, ?, '0.1.0', ?, ?, ?, ?, ?)""",
                [
                    (
                        f"{row[0]}-v0.1.0",
                        row[0],
                        row[3],
                        hashlib.sha256(row[3].encode("utf-8")).hexdigest(),
                        "active" if row[4] == "active" else "candidate",
                        now,
                        now if row[4] == "active" else None,
                    )
                    for row in skills
                ],
            )
            connection.executemany(
                """INSERT OR IGNORE INTO aegis_plugin_registry
                (id, name, category, description, status, connection_status, requires_approval, data_policy, capabilities_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], json.dumps(row[8]), now) for row in plugins],
            )
            for skill_id in ("skill-secure-coding", "skill-security-review"):
                connection.execute(
                    "INSERT OR IGNORE INTO aegis_agent_skills (agent_id, skill_id, assigned_at) VALUES (?, ?, ?)",
                    ("agent-engineering", skill_id, now),
                )

    def ensure_foundation_project(self, root: Path, repository_url: str) -> dict[str, Any]:
        existing = self.get_project("project-foundation")
        if existing:
            return existing
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_projects
                (id, name, description, root_path, repository_url, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    "project-foundation",
                    "AI Agency Foundation",
                    "Secure local-first foundation and the home of Aegis.",
                    str(root),
                    repository_url,
                    now,
                    now,
                ),
            )
            self._activity(connection, "project_registered", "Registered the AI Agency Foundation project", "project", "project-foundation")
        return self.get_project("project-foundation") or {}

    def list_projects(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            projects = self._rows(connection.execute("SELECT * FROM aegis_projects ORDER BY updated_at DESC"))
            for project in projects:
                project["task_count"] = connection.execute(
                    "SELECT COUNT(*) FROM aegis_tasks WHERE project_id = ?", (project["id"],)
                ).fetchone()[0]
                project["tasks"] = self._rows(
                    connection.execute(
                        "SELECT * FROM aegis_tasks WHERE project_id = ? ORDER BY updated_at DESC LIMIT 20",
                        (project["id"],),
                    )
                )
                self._attach_compilations(connection, project["tasks"])
        return projects

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            project = self._row(connection.execute("SELECT * FROM aegis_projects WHERE id = ?", (project_id,)))
            if project:
                project["tasks"] = self._rows(
                    connection.execute("SELECT * FROM aegis_tasks WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))
                )
                self._attach_compilations(connection, project["tasks"])
        return project

    def create_project(
        self, name: str, description: str, root_path: Path, repository_url: str | None
    ) -> dict[str, Any]:
        project_id = new_id("project")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_projects
                (id, name, description, root_path, repository_url, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (project_id, name, description, str(root_path), repository_url, now, now),
            )
            self._activity(connection, "project_created", f"Created project workspace: {name}", "project", project_id)
        return self.get_project(project_id) or {}

    def create_task(
        self,
        project_id: str,
        title: str,
        prompt: str,
        risk_level: str = "low",
        assigned_agent: str | None = None,
        status: str = "planned",
    ) -> dict[str, Any]:
        if not self.get_project(project_id):
            raise KeyError("Project not found")
        task_id = new_id("task")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_tasks
                (id, project_id, title, prompt, status, risk_level, assigned_agent, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, project_id, title, prompt, status, risk_level, assigned_agent, now, now),
            )
            connection.execute("UPDATE aegis_projects SET updated_at = ? WHERE id = ?", (now, project_id))
            self._activity(connection, "task_created", f"Created task: {title}", "task", task_id)
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            task = self._row(connection.execute("SELECT * FROM aegis_tasks WHERE id = ?", (task_id,)))
            if task:
                self._attach_compilations(connection, [task])
            return task

    def save_prompt_compilation(self, task_id: str, value: dict[str, Any]) -> dict[str, Any]:
        compilation_id = new_id("prompt")
        now = utc_now()
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_tasks WHERE id = ?", (task_id,)).fetchone():
                raise KeyError("Task not found")
            connection.execute(
                """INSERT INTO aegis_prompt_compilations
                (id, task_id, original_prompt, compiled_prompt, objective, data_classification,
                 risk_level, approvals_json, success_evidence_json, compiler_mode, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  original_prompt = excluded.original_prompt,
                  compiled_prompt = excluded.compiled_prompt,
                  objective = excluded.objective,
                  data_classification = excluded.data_classification,
                  risk_level = excluded.risk_level,
                  approvals_json = excluded.approvals_json,
                  success_evidence_json = excluded.success_evidence_json,
                  compiler_mode = excluded.compiler_mode,
                  model = excluded.model,
                  created_at = excluded.created_at""",
                (
                    compilation_id,
                    task_id,
                    value["original_prompt"],
                    value["compiled_prompt"],
                    value["objective"],
                    value["data_classification"],
                    value["risk_level"],
                    json.dumps(value.get("approvals_required", [])),
                    json.dumps(value.get("success_evidence", [])),
                    value["compiler_mode"],
                    value.get("model"),
                    now,
                ),
            )
            connection.execute(
                "UPDATE aegis_tasks SET risk_level = ?, updated_at = ? WHERE id = ?",
                (value["risk_level"], now, task_id),
            )
            self._activity(connection, "prompt_compiled", f"Compiled task prompt: {value['objective'][:180]}", "task", task_id)
        task = self.get_task(task_id)
        return (task or {}).get("prompt_compilation", {})

    def update_task(self, task_id: str, status: str, result_summary: str | None = None) -> dict[str, Any]:
        now = utc_now()
        transitions = {
            "planned": {"awaiting_approval", "running", "cancelled"},
            "awaiting_approval": {"running", "failed", "cancelled"},
            "running": {"completed", "failed", "cancelled"},
            "completed": set(),
            "failed": set(),
            "cancelled": set(),
        }
        with self.database.connection() as connection:
            current = self._row(connection.execute("SELECT * FROM aegis_tasks WHERE id = ?", (task_id,)))
            if not current:
                raise KeyError("Task not found")
            if status != current["status"] and status not in transitions.get(current["status"], set()):
                raise ValueError(f"Invalid task transition from {current['status']} to {status}")
            cursor = connection.execute(
                "UPDATE aegis_tasks SET status = ?, result_summary = ?, updated_at = ? WHERE id = ?",
                (status, result_summary, now, task_id),
            )
            self._activity(connection, "task_updated", f"Task moved to {status}", "task", task_id)
        return self.get_task(task_id) or {}

    def list_agents(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            agents = self._rows(connection.execute("SELECT * FROM aegis_agent_registry ORDER BY name"))
            for agent in agents:
                agent["capabilities"] = self._decode(agent.pop("capabilities_json"), [])
                agent["skills"] = self._rows(
                    connection.execute(
                        """SELECT s.id, s.name, s.category, s.version, s.status
                        FROM aegis_agent_skills a JOIN aegis_skill_registry s ON s.id = a.skill_id
                        WHERE a.agent_id = ? ORDER BY s.name""",
                        (agent["id"],),
                    )
                )
        return agents

    def create_agent(self, values: dict[str, Any]) -> dict[str, Any]:
        agent_id = new_id("agent")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_agent_registry
                (id, name, role, description, model_policy, status, prompt_version, capabilities_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'ready', 'proposal-v1', ?, ?, ?)""",
                (
                    agent_id,
                    values["name"],
                    values["role"],
                    values.get("description", ""),
                    values.get("model_policy", "local-auto"),
                    json.dumps(values.get("capabilities", [])),
                    now,
                    now,
                ),
            )
            self._activity(connection, "agent_created", f"Created agent proposal: {values['name']}", "agent", agent_id)
        return next(agent for agent in self.list_agents() if agent["id"] == agent_id)

    def list_skills(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            skills = self._rows(connection.execute("SELECT * FROM aegis_skill_registry ORDER BY category, name"))
        for skill in skills:
            skill["capabilities"] = self._decode(skill.pop("capabilities_json"), [])
        return skills

    def create_skill(self, values: dict[str, Any]) -> dict[str, Any]:
        skill_id = new_id("skill")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_skill_registry
                (id, name, category, description, version, status, risk_level, capabilities_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, '0.1.0', 'proposal', ?, ?, ?, ?)""",
                (
                    skill_id,
                    values["name"],
                    values["category"],
                    values.get("description", ""),
                    values.get("risk_level", "low"),
                    json.dumps(values.get("capabilities", [])),
                    now,
                    now,
                ),
            )
            self._activity(connection, "skill_created", f"Created skill proposal: {values['name']}", "skill", skill_id)
        return next(skill for skill in self.list_skills() if skill["id"] == skill_id)

    def list_skill_versions(self, skill_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            versions = self._rows(
                connection.execute(
                    "SELECT * FROM aegis_skill_versions WHERE skill_id = ? ORDER BY created_at DESC",
                    (skill_id,),
                )
            )
            for version in versions:
                version["evaluations"] = self._rows(
                    connection.execute(
                        "SELECT * FROM aegis_skill_evaluations WHERE version_id = ? ORDER BY created_at DESC",
                        (version["id"],),
                    )
                )
                for evaluation in version["evaluations"]:
                    evaluation["passed"] = bool(evaluation["passed"])
                    evaluation["evidence"] = self._decode(evaluation.pop("evidence_json"), {})
        return versions

    def create_skill_version(self, skill_id: str, version: str, instructions: str) -> dict[str, Any]:
        now = utc_now()
        version_id = new_id("skill-version")
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_skill_registry WHERE id = ?", (skill_id,)).fetchone():
                raise KeyError("Skill not found")
            connection.execute(
                """INSERT INTO aegis_skill_versions
                (id, skill_id, version, instructions, checksum_sha256, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'candidate', ?)""",
                (version_id, skill_id, version, instructions, hashlib.sha256(instructions.encode("utf-8")).hexdigest(), now),
            )
            self._activity(connection, "skill_version_created", f"Created skill candidate {version}", "skill", skill_id)
        return next(item for item in self.list_skill_versions(skill_id) if item["id"] == version_id)

    def evaluate_skill_version(
        self, version_id: str, evaluator: str, score: float, passed: bool, evidence: dict[str, Any]
    ) -> dict[str, Any]:
        evaluation_id = new_id("evaluation")
        now = utc_now()
        with self.database.connection() as connection:
            version = self._row(connection.execute("SELECT * FROM aegis_skill_versions WHERE id = ?", (version_id,)))
            if not version:
                raise KeyError("Skill version not found")
            connection.execute(
                """INSERT INTO aegis_skill_evaluations
                (id, version_id, evaluator, score, passed, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (evaluation_id, version_id, evaluator, score, int(passed), json.dumps(evidence), now),
            )
            connection.execute("UPDATE aegis_skill_versions SET status = 'testing' WHERE id = ? AND status = 'candidate'", (version_id,))
            self._activity(connection, "skill_evaluated", f"Skill evaluation score {score:.1f}; passed={passed}", "skill", version["skill_id"])
        return next(
            item
            for item in self.list_skill_versions(version["skill_id"])
            if item["id"] == version_id
        )

    def promote_skill_version(self, skill_id: str, version_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            candidate = self._row(
                connection.execute("SELECT * FROM aegis_skill_versions WHERE id = ? AND skill_id = ?", (version_id, skill_id))
            )
            if not candidate:
                raise KeyError("Skill version not found")
            passed = connection.execute(
                "SELECT 1 FROM aegis_skill_evaluations WHERE version_id = ? AND passed = 1 AND score >= 70 LIMIT 1",
                (version_id,),
            ).fetchone()
            if not passed:
                raise ValueError("Skill version needs a passing evaluation score of at least 70")
            connection.execute("UPDATE aegis_skill_versions SET status = 'retired' WHERE skill_id = ? AND status = 'active'", (skill_id,))
            connection.execute("UPDATE aegis_skill_versions SET status = 'active', promoted_at = ? WHERE id = ?", (now, version_id))
            connection.execute(
                "UPDATE aegis_skill_registry SET version = ?, status = 'active', updated_at = ? WHERE id = ?",
                (candidate["version"], now, skill_id),
            )
            self._activity(connection, "skill_promoted", f"Promoted skill version {candidate['version']}", "skill", skill_id)
        return next(item for item in self.list_skill_versions(skill_id) if item["id"] == version_id)

    def rollback_skill_version(self, skill_id: str, version_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            target = self._row(
                connection.execute(
                    "SELECT * FROM aegis_skill_versions WHERE id = ? AND skill_id = ? AND status IN ('retired', 'active')",
                    (version_id, skill_id),
                )
            )
            if not target:
                raise ValueError("Rollback target must be a previously active skill version")
            connection.execute("UPDATE aegis_skill_versions SET status = 'retired' WHERE skill_id = ? AND status = 'active'", (skill_id,))
            connection.execute("UPDATE aegis_skill_versions SET status = 'active', promoted_at = ? WHERE id = ?", (now, version_id))
            connection.execute(
                "UPDATE aegis_skill_registry SET version = ?, status = 'active', updated_at = ? WHERE id = ?",
                (target["version"], now, skill_id),
            )
            self._activity(connection, "skill_rolled_back", f"Rolled back skill to {target['version']}", "skill", skill_id)
        return next(item for item in self.list_skill_versions(skill_id) if item["id"] == version_id)

    def assign_skill(self, agent_id: str, skill_id: str) -> None:
        now = utc_now()
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_agent_registry WHERE id = ?", (agent_id,)).fetchone():
                raise KeyError("Agent not found")
            if not connection.execute("SELECT 1 FROM aegis_skill_registry WHERE id = ?", (skill_id,)).fetchone():
                raise KeyError("Skill not found")
            connection.execute(
                "INSERT OR IGNORE INTO aegis_agent_skills (agent_id, skill_id, assigned_at) VALUES (?, ?, ?)",
                (agent_id, skill_id, now),
            )
            self._activity(connection, "skill_assigned", "Assigned skill to agent", "agent", agent_id)

    def list_plugins(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            plugins = self._rows(connection.execute("SELECT * FROM aegis_plugin_registry ORDER BY category, name"))
        for plugin in plugins:
            plugin["capabilities"] = self._decode(plugin.pop("capabilities_json"), [])
            plugin["requires_approval"] = bool(plugin["requires_approval"])
        return plugins

    def set_plugin_status(self, plugin_id: str, status: str, connection_status: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            current = self._row(connection.execute("SELECT * FROM aegis_plugin_registry WHERE id = ?", (plugin_id,)))
            if not current:
                raise KeyError("Plugin not found")
            connection.execute(
                "UPDATE aegis_plugin_registry SET status = ?, connection_status = ?, updated_at = ? WHERE id = ?",
                (status, connection_status or current["connection_status"], now, plugin_id),
            )
            self._activity(connection, "plugin_updated", f"Plugin {current['name']} moved to {status}", "plugin", plugin_id)
        return next(plugin for plugin in self.list_plugins() if plugin["id"] == plugin_id)

    def create_approval(
        self,
        action: str,
        summary: str,
        risk_level: str,
        project_id: str | None = None,
        task_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        approval_id = new_id("approval")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_approvals
                (id, project_id, task_id, action, summary, risk_level, status, evidence_json, requested_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (approval_id, project_id, task_id, action, summary, risk_level, json.dumps(evidence or {}), now),
            )
            self._activity(connection, "approval_requested", summary, "approval", approval_id)
        return self.get_approval(approval_id) or {}

    def list_approvals(self) -> list[dict[str, Any]]:
        self.expire_stale_approvals()
        with self.database.connection() as connection:
            approvals = self._rows(
                connection.execute(
                    "SELECT * FROM aegis_approvals ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, requested_at DESC"
                )
            )
            for approval in approvals:
                approval["evidence"] = self._decode(approval.pop("evidence_json"), {})
                approval["execution"] = self._row(
                    connection.execute("SELECT * FROM aegis_approval_executions WHERE approval_id = ?", (approval["id"],))
                )
        return approvals

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            approval = self._row(connection.execute("SELECT * FROM aegis_approvals WHERE id = ?", (approval_id,)))
        if approval:
            approval["evidence"] = self._decode(approval.pop("evidence_json"), {})
            with self.database.connection() as connection:
                approval["execution"] = self._row(
                    connection.execute("SELECT * FROM aegis_approval_executions WHERE approval_id = ?", (approval_id,))
                )
        return approval

    def claim_approval_execution(self, approval_id: str, expected_action: str) -> dict[str, Any]:
        """Atomically consume one approved action so it cannot be replayed."""
        execution_id = new_id("execution")
        now = utc_now()
        with self.database.connection() as connection:
            approval = self._row(connection.execute("SELECT * FROM aegis_approvals WHERE id = ?", (approval_id,)))
            if not approval:
                raise KeyError("Approval not found")
            if approval["action"] != expected_action:
                raise ValueError("Approval action does not match this operation")
            if approval["status"] != "approved":
                raise ValueError("Action must be approved before execution")
            existing = self._row(
                connection.execute("SELECT * FROM aegis_approval_executions WHERE approval_id = ?", (approval_id,))
            )
            if existing:
                raise ValueError(f"Approval was already consumed with status {existing['status']}")
            connection.execute(
                """INSERT INTO aegis_approval_executions
                (id, approval_id, action, status, started_at) VALUES (?, ?, ?, 'running', ?)""",
                (execution_id, approval_id, expected_action, now),
            )
            self._activity(connection, "approval_execution_started", f"Started approved action: {expected_action}", "approval", approval_id)
        result = self.get_approval(approval_id) or {}
        result["execution"] = {"id": execution_id, "status": "running", "started_at": now}
        return result

    def finish_approval_execution(self, approval_id: str, status: str, result_summary: str = "") -> dict[str, Any]:
        if status not in {"completed", "failed"}:
            raise ValueError("Execution status must be completed or failed")
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_approval_executions
                SET status = ?, result_summary = ?, finished_at = ?
                WHERE approval_id = ? AND status = 'running'""",
                (status, result_summary[:2000], now, approval_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Approval execution is not running")
            self._activity(connection, "approval_execution_finished", f"Approved action {status}", "approval", approval_id)
            execution = self._row(
                connection.execute("SELECT * FROM aegis_approval_executions WHERE approval_id = ?", (approval_id,))
            )
        return execution or {}

    def get_approval_execution(self, approval_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            return self._row(
                connection.execute("SELECT * FROM aegis_approval_executions WHERE approval_id = ?", (approval_id,))
            )

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        self.expire_stale_approvals()
        now = utc_now()
        with self.database.connection() as connection:
            current = self._row(connection.execute("SELECT * FROM aegis_approvals WHERE id = ?", (approval_id,)))
            if not current:
                raise KeyError("Approval not found")
            if current["status"] != "pending":
                raise ValueError("Approval has already been decided")
            connection.execute(
                "UPDATE aegis_approvals SET status = ?, decided_at = ? WHERE id = ?",
                (decision, now, approval_id),
            )
            self._activity(connection, "approval_decided", f"Approval {decision}: {current['summary']}", "approval", approval_id)
        return self.get_approval(approval_id) or {}

    def expire_stale_approvals(self, hours: int = 8) -> int:
        threshold = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat()
        now = utc_now()
        with self.database.connection() as connection:
            stale = self._rows(
                connection.execute(
                    "SELECT id, summary FROM aegis_approvals WHERE status = 'pending' AND requested_at < ?",
                    (threshold,),
                )
            )
            if stale:
                connection.execute(
                    "UPDATE aegis_approvals SET status = 'expired', decided_at = ? WHERE status = 'pending' AND requested_at < ?",
                    (now, threshold),
                )
                for approval in stale:
                    self._activity(
                        connection,
                        "approval_expired",
                        f"Approval expired: {approval['summary']}",
                        "approval",
                        approval["id"],
                    )
        return len(stale)

    def list_world_pulse(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(
                connection.execute(
                    """SELECT p.*, s.domain, s.publisher, s.source_tier, s.verification_state, s.retrieved_at
                    FROM aegis_world_pulse p
                    LEFT JOIN aegis_world_pulse_sources s ON s.pulse_id = p.id
                    ORDER BY p.collected_at DESC LIMIT 100"""
                )
            )

    def add_world_pulse(
        self,
        *,
        region: str,
        category: str,
        headline: str,
        summary: str,
        confidence: float,
        published_at: str | None,
        source: dict[str, Any],
    ) -> dict[str, Any]:
        pulse_id = new_id("pulse")
        source_id = new_id("source")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_world_pulse
                (id, region, category, headline, summary, source_url, confidence, impact_level, published_at, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'monitor', ?, ?)""",
                (pulse_id, region, category, headline, summary, source["url"], confidence, published_at, now),
            )
            connection.execute(
                """INSERT INTO aegis_world_pulse_sources
                (id, pulse_id, url, domain, publisher, source_tier, verification_state, published_at, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id,
                    pulse_id,
                    source["url"],
                    source["domain"],
                    source.get("publisher"),
                    source["source_tier"],
                    source["verification_state"],
                    source.get("published_at"),
                    source["retrieved_at"],
                ),
            )
            self._activity(connection, "world_pulse_ingested", f"World Pulse signal: {headline[:180]}", "pulse", pulse_id)
        return next(item for item in self.list_world_pulse() if item["id"] == pulse_id)

    def list_opportunities(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(connection.execute("SELECT * FROM aegis_opportunities ORDER BY score DESC, updated_at DESC"))
        for row in rows:
            row["evidence"] = self._decode(row.pop("evidence_json"), [])
        return rows

    def create_opportunity(self, payload: dict[str, Any]) -> dict[str, Any]:
        opportunity_id = new_id("opportunity")
        now = utc_now()
        score = round(
            payload["evidence_strength"] * 0.30
            + payload["revenue_potential"] * 0.25
            + payload["strategic_fit"] * 0.20
            + payload["speed_to_revenue"] * 0.15
            + (100 - payload["execution_risk"]) * 0.10,
            1,
        )
        evidence = {
            "sources": payload["evidence"],
            "dimensions": {key: payload[key] for key in ("evidence_strength", "revenue_potential", "strategic_fit", "speed_to_revenue", "execution_risk")},
            "score_formula": "30% evidence + 25% revenue + 20% fit + 15% speed + 10% inverse risk",
        }
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_opportunities
                (id, title, thesis, allocation, score, status, evidence_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'scored', ?, ?, ?)""",
                (opportunity_id, payload["title"], payload["thesis"], payload["allocation"], score, json.dumps(evidence), now, now),
            )
            self._activity(connection, "opportunity_scored", f"Scored opportunity: {payload['title']}", "opportunity", opportunity_id)
        return next(item for item in self.list_opportunities() if item["id"] == opportunity_id)

    def list_solutions(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(connection.execute("SELECT * FROM aegis_solutions ORDER BY updated_at DESC"))

    def create_solution(self, payload: dict[str, Any]) -> dict[str, Any]:
        solution_id = new_id("solution")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_solutions
                (id, title, problem, audience, stage, proof, owner_agent, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'discover', ?, ?, ?, ?)""",
                (solution_id, payload["title"], payload["problem"], payload["audience"], payload.get("proof", ""), payload.get("owner_agent"), now, now),
            )
            self._activity(connection, "solution_created", f"Created solution program: {payload['title']}", "solution", solution_id)
        return next(item for item in self.list_solutions() if item["id"] == solution_id)

    def transition_solution(self, solution_id: str, target_stage: str, proof: str) -> dict[str, Any]:
        stages = ["discover", "validate", "prototype", "pilot", "scale"]
        now = utc_now()
        with self.database.connection() as connection:
            current = self._row(connection.execute("SELECT * FROM aegis_solutions WHERE id = ?", (solution_id,)))
            if not current:
                raise KeyError("Solution not found")
            if stages.index(target_stage) != stages.index(current["stage"]) + 1:
                raise ValueError("Solutions can advance only one evidence-backed stage at a time")
            connection.execute(
                "UPDATE aegis_solutions SET stage = ?, proof = ?, updated_at = ? WHERE id = ?",
                (target_stage, proof, now, solution_id),
            )
            self._activity(connection, "solution_advanced", f"Advanced {current['title']} to {target_stage}", "solution", solution_id)
        return next(item for item in self.list_solutions() if item["id"] == solution_id)

    def create_data_job(self, project_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        job_id = new_id("data-job")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_data_jobs
                (id, project_id, source_path, source_sha256, recipe_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'planned', ?)""",
                (job_id, project_id, plan["source_path"], plan["source_sha256"], json.dumps(plan["recipe"]), now),
            )
            self._activity(connection, "data_job_planned", f"Planned reversible cleaning for {Path(plan['source_path']).name}", "data_job", job_id)
        return self.get_data_job(job_id) or {}

    def get_data_job(self, job_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            job = self._row(connection.execute("SELECT * FROM aegis_data_jobs WHERE id = ?", (job_id,)))
        if job:
            job["recipe"] = self._decode(job.pop("recipe_json"), {})
            job["report"] = self._decode(job.pop("report_json"), {})
        return job

    def complete_data_job(self, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_data_jobs SET output_path = ?, output_sha256 = ?, report_json = ?,
                status = 'completed', completed_at = ? WHERE id = ?""",
                (result["output_path"], result["output_sha256"], json.dumps(result["report"]), now, job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Data job not found")
            self._activity(connection, "data_job_completed", "Completed reversible Data Lab job", "data_job", job_id)
        return self.get_data_job(job_id) or {}

    def list_activity(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(
                connection.execute("SELECT * FROM aegis_activity ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),))
            )

    def overview(self) -> dict[str, Any]:
        with self.database.connection() as connection:
            counts = {
                "projects": connection.execute("SELECT COUNT(*) FROM aegis_projects WHERE status = 'active'").fetchone()[0],
                "agents": connection.execute("SELECT COUNT(*) FROM aegis_agent_registry WHERE status != 'offline'").fetchone()[0],
                "pending_approvals": connection.execute("SELECT COUNT(*) FROM aegis_approvals WHERE status = 'pending'").fetchone()[0],
                "open_tasks": connection.execute(
                    "SELECT COUNT(*) FROM aegis_tasks WHERE status IN ('planned', 'awaiting_approval', 'running')"
                ).fetchone()[0],
            }
        return {**counts, "opportunity_allocation": {"existing": 80, "exploration": 20}}

    def _activity(
        self,
        connection: Any,
        event_type: str,
        summary: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        security_level: str = "internal",
    ) -> None:
        connection.execute(
            """INSERT INTO aegis_activity
            (event_type, summary, entity_type, entity_id, security_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, summary[:2000], entity_type, entity_id, security_level, utc_now()),
        )

    def _attach_compilations(self, connection: Any, tasks: list[dict[str, Any]]) -> None:
        for task in tasks:
            compilation = self._row(
                connection.execute("SELECT * FROM aegis_prompt_compilations WHERE task_id = ?", (task["id"],))
            )
            if not compilation:
                task["prompt_compilation"] = None
                continue
            compilation["approvals_required"] = self._decode(compilation.pop("approvals_json"), [])
            compilation["success_evidence"] = self._decode(compilation.pop("success_evidence_json"), [])
            task["prompt_compilation"] = compilation
