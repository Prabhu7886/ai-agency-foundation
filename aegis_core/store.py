"""Encrypted persistence for Aegis workspaces, projects, agents, skills, and approvals."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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
        return projects

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            project = self._row(connection.execute("SELECT * FROM aegis_projects WHERE id = ?", (project_id,)))
            if project:
                project["tasks"] = self._rows(
                    connection.execute("SELECT * FROM aegis_tasks WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))
                )
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
            return self._row(connection.execute("SELECT * FROM aegis_tasks WHERE id = ?", (task_id,)))

    def update_task(self, task_id: str, status: str, result_summary: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_tasks SET status = ?, result_summary = ?, updated_at = ? WHERE id = ?",
                (status, result_summary, now, task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Task not found")
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
        with self.database.connection() as connection:
            approvals = self._rows(
                connection.execute(
                    "SELECT * FROM aegis_approvals ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, requested_at DESC"
                )
            )
        for approval in approvals:
            approval["evidence"] = self._decode(approval.pop("evidence_json"), {})
        return approvals

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            approval = self._row(connection.execute("SELECT * FROM aegis_approvals WHERE id = ?", (approval_id,)))
        if approval:
            approval["evidence"] = self._decode(approval.pop("evidence_json"), {})
        return approval

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
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

    def list_world_pulse(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(connection.execute("SELECT * FROM aegis_world_pulse ORDER BY collected_at DESC LIMIT 100"))

    def list_opportunities(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(connection.execute("SELECT * FROM aegis_opportunities ORDER BY score DESC, updated_at DESC"))
        for row in rows:
            row["evidence"] = self._decode(row.pop("evidence_json"), [])
        return rows

    def list_solutions(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(connection.execute("SELECT * FROM aegis_solutions ORDER BY updated_at DESC"))

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
