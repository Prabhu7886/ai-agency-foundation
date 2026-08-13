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
        self.remove_invalid_empty_research_reports()

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
            ),
            (
                "aegis-commerce",
                "Aegis Commerce",
                "personal commerce specialist",
                "Runs the owner's commerce research and production cycle independently under Aegis supervision.",
                "local-auto",
                "offline",
                "commerce-v0.2.0",
                ["commerce", "research", "products", "listings", "pricing", "evidence"],
            ),
            (
                "aegis-career-studio",
                "Aegis Career Studio",
                "resume and interview specialist",
                "Runs the owner's evidence-backed career workspace independently under Aegis supervision.",
                "local-auto",
                "offline",
                "career-v0.1.0",
                ["career", "resume", "jobs", "interviews", "local-speech", "local-ocr"],
            ),
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
            ("plugin-web", "Web Research", "research", "Approved public-source search and website analysis.", "enabled", "approval_gated", 1, "public_queries_only", ["search", "website-analysis", "citations"]),
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
                """INSERT OR IGNORE INTO aegis_agent_endpoints
                (agent_id, bridge_url, dashboard_url, enabled, contract_version, last_status, updated_at)
                VALUES (?, ?, ?, 1, '1.0', 'offline', ?)""",
                [
                    ("aegis-commerce", "http://127.0.0.1:8511", "http://127.0.0.1:8501", now),
                    ("aegis-career-studio", "http://127.0.0.1:8512", "http://127.0.0.1:8502", now),
                ],
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
            connection.execute(
                """UPDATE aegis_plugin_registry
                SET status = 'enabled', connection_status = 'approval_gated', updated_at = ?
                WHERE id = 'plugin-web'""",
                (now,),
            )
            connection.execute(
                "UPDATE aegis_skill_registry SET status = 'testing', updated_at = ? WHERE id = 'skill-web-research'",
                (now,),
            )
            connection.execute(
                """INSERT OR IGNORE INTO aegis_identity_profiles
                (id, display_name, role_title, pronouns, embodiment, conversation_style,
                 presentation_mode, traits_json, truth_standard, authority_model, created_at, updated_at)
                VALUES ('aegis-primary', 'Aegis', 'Digital Executive Partner', 'she/her',
                        'always_digital', 'professional_warm', 'executive', ?, 'strict',
                        'owner_controlled', ?, ?)""",
                (
                    json.dumps(["professional", "friendly", "direct", "factual", "ambitious", "evidence-aware"]),
                    now,
                    now,
                ),
            )
            connection.executemany(
                """INSERT OR IGNORE INTO aegis_identity_assets
                (id, asset_type, label, public_path, content_sha256, status, identity_locked, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                [
                    (
                        "identity-portrait-v1",
                        "portrait",
                        "Executive portrait",
                        "/aegis-avatar.png",
                        "64bdfacd46dd9aae25a8caa5dec22c23cfd678b68047d32b7bcc28f128dc95f4",
                        "active",
                        now,
                        now,
                    ),
                    (
                        "identity-full-body-v1",
                        "full_body",
                        "Full-body video master",
                        "/aegis-full-body-v1.png",
                        "5b1eaec7f9286086a19f73a21bc4f90faf18ee051d0e5a1f09ce0da694d5a206",
                        "reference",
                        now,
                        now,
                    ),
                    (
                        "identity-motion-rig-v1",
                        "motion_rig",
                        "Motion and lip-sync rig",
                        None,
                        None,
                        "planned",
                        now,
                        now,
                    ),
                ],
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

    def list_conversations(self, project_id: str | None = None, *, include_archived: bool = False) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if project_id:
            conditions.append("c.project_id = ?")
            parameters.append(project_id)
        if not include_archived:
            conditions.append("c.status = 'active'")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connection() as connection:
            rows = self._rows(
                connection.execute(
                    f"""SELECT c.*, COUNT(m.id) AS message_count, MAX(m.created_at) AS last_message_at
                    FROM aegis_conversations c
                    LEFT JOIN aegis_conversation_messages m ON m.conversation_id = c.id
                    {where}
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC""",
                    parameters,
                )
            )
            for row in rows:
                preview = connection.execute(
                    """SELECT content FROM aegis_conversation_messages
                    WHERE conversation_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                    (row["id"],),
                ).fetchone()
                row["preview"] = str(preview[0])[:180] if preview else ""
                row["message_count"] = int(row["message_count"] or 0)
                row["encrypted_at_rest"] = True
        return rows

    def create_conversation(self, project_id: str, title: str = "New conversation") -> dict[str, Any]:
        if not self.get_project(project_id):
            raise KeyError("Project not found")
        conversation_id = new_id("conversation")
        now = utc_now()
        clean_title = re.sub(r"\s+", " ", title).strip()[:120] or "New conversation"
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_conversations
                (id, project_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)""",
                (conversation_id, project_id, clean_title, now, now),
            )
            self._activity(
                connection,
                "conversation_created",
                "Created encrypted local conversation",
                "conversation",
                conversation_id,
            )
        return self.get_conversation(conversation_id, message_limit=0) or {}

    def get_conversation(self, conversation_id: str, *, message_limit: int = 200) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            conversation = self._row(
                connection.execute("SELECT * FROM aegis_conversations WHERE id = ?", (conversation_id,))
            )
            if not conversation:
                return None
            conversation["encrypted_at_rest"] = True
            conversation["messages"] = self._conversation_messages(connection, conversation_id, message_limit)
            conversation["message_count"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM aegis_conversation_messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
        return conversation

    def _conversation_messages(self, connection: Any, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        bounded_limit = min(max(int(limit), 1), 500)
        messages = self._rows(
            connection.execute(
                """SELECT * FROM (
                    SELECT * FROM aegis_conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC, rowid DESC LIMIT ?
                ) ORDER BY created_at ASC""",
                (conversation_id, bounded_limit),
            )
        )
        for message in messages:
            message["compilation"] = self._decode(message.pop("compilation_json"), {}) or None
            message["token_count"] = int(message.get("token_count") or 0)
        return messages

    def conversation_context(self, conversation_id: str, *, limit: int = 12, max_characters: int = 60_000) -> list[dict[str, str]]:
        with self.database.connection() as connection:
            messages = self._conversation_messages(connection, conversation_id, limit)
        selected: list[dict[str, str]] = []
        used = 0
        for message in reversed(messages):
            content = str(message.get("content", ""))
            if used + len(content) > max_characters:
                remaining = max_characters - used
                if remaining <= 0:
                    break
                content = content[-remaining:]
            selected.append({"role": str(message["role"]), "content": content})
            used += len(content)
        return list(reversed(selected))

    def add_conversation_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        task_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        token_count: int = 0,
        compilation: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("Conversation role must be user or assistant")
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Conversation messages cannot be empty")
        message_id = new_id("message")
        now = utc_now()
        with self.database.connection() as connection:
            conversation = self._row(
                connection.execute("SELECT * FROM aegis_conversations WHERE id = ?", (conversation_id,))
            )
            if not conversation:
                raise KeyError("Conversation not found")
            if conversation["status"] != "active":
                raise ValueError("Archived conversations are read-only")
            connection.execute(
                """INSERT INTO aegis_conversation_messages
                (id, conversation_id, task_id, role, content, provider, model, token_count,
                 compilation_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    conversation_id,
                    task_id,
                    role,
                    clean_content[:100_000],
                    provider,
                    model,
                    max(int(token_count), 0),
                    json.dumps(compilation or {}),
                    str(error)[:2000] if error else None,
                    now,
                ),
            )
            if role == "user" and conversation["title"] == "New conversation":
                title = re.sub(r"\s+", " ", clean_content).strip()[:72]
                connection.execute(
                    "UPDATE aegis_conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, conversation_id),
                )
            else:
                connection.execute(
                    "UPDATE aegis_conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation_id),
                )
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise KeyError("Conversation not found")
        return next(item for item in conversation["messages"] if item["id"] == message_id)

    def archive_conversation(self, conversation_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_conversations SET status = 'archived', updated_at = ? WHERE id = ? AND status = 'active'",
                (now, conversation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Active conversation not found")
            self._activity(
                connection,
                "conversation_archived",
                "Archived encrypted local conversation",
                "conversation",
                conversation_id,
            )
        return self.get_conversation(conversation_id, message_limit=0) or {}

    def restore_conversation(self, conversation_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_conversations SET status = 'active', updated_at = ? WHERE id = ? AND status = 'archived'",
                (now, conversation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Archived conversation not found")
            self._activity(
                connection,
                "conversation_restored",
                "Restored encrypted local conversation",
                "conversation",
                conversation_id,
            )
        return self.get_conversation(conversation_id, message_limit=0) or {}

    def delete_conversation(self, conversation_id: str) -> None:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM aegis_conversations WHERE id = ? AND status = 'archived'",
                (conversation_id,),
            )
            if cursor.rowcount != 1:
                raise KeyError("Archived conversation not found")
            self._activity(
                connection,
                "conversation_deleted",
                "Permanently deleted encrypted local conversation",
                "conversation",
                conversation_id,
            )

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

    def list_agent_endpoints(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        query = """SELECT e.*, a.name, a.role FROM aegis_agent_endpoints e
        JOIN aegis_agent_registry a ON a.id = e.agent_id"""
        if enabled_only:
            query += " WHERE e.enabled = 1"
        query += " ORDER BY a.name"
        with self.database.connection() as connection:
            rows = self._rows(connection.execute(query))
        for row in rows:
            row["enabled"] = bool(row["enabled"])
        return rows

    def latest_agent_snapshot(self, agent_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = self._row(
                connection.execute(
                    """SELECT * FROM aegis_agent_snapshots
                    WHERE agent_id = ? ORDER BY observed_at DESC LIMIT 1""",
                    (agent_id,),
                )
            )
        if row:
            row["snapshot"] = self._decode(row.pop("snapshot_json"), {})
        return row

    def record_agent_snapshot(self, agent_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        endpoint_ids = {item["agent_id"] for item in self.list_agent_endpoints(enabled_only=False)}
        if agent_id not in endpoint_ids:
            raise KeyError("Agent endpoint is not registered")
        observed_at = str(snapshot.get("observed_at") or utc_now())
        status = str(snapshot.get("health", {}).get("status") or snapshot.get("health", {}).get("state") or "offline")
        normalized_status = {
            "healthy": "ready",
            "degraded": "ready",
            "unavailable": "offline",
            "quarantined": "paused",
            "paused": "paused",
        }.get(status, "ready")
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        snapshot_id = new_id("snapshot")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_agent_snapshots
                (id, agent_id, status, snapshot_json, snapshot_sha256, observed_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (snapshot_id, agent_id, status, encoded, digest, observed_at),
            )
            connection.execute(
                """UPDATE aegis_agent_endpoints SET last_seen_at = ?, last_status = ?, last_error = NULL,
                contract_version = ?, updated_at = ? WHERE agent_id = ?""",
                (observed_at, status, str(snapshot.get("contract_version", "1.0")), now, agent_id),
            )
            connection.execute(
                "UPDATE aegis_agent_registry SET status = ?, updated_at = ? WHERE id = ?",
                (normalized_status, now, agent_id),
            )
        return self.latest_agent_snapshot(agent_id) or {}

    def mark_agent_unavailable(self, agent_id: str, error: str) -> None:
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE aegis_agent_endpoints SET last_status = 'offline', last_error = ?, updated_at = ?
                WHERE agent_id = ?""",
                (error[:1000], now, agent_id),
            )
            connection.execute(
                "UPDATE aegis_agent_registry SET status = 'offline', updated_at = ? WHERE id = ?",
                (now, agent_id),
            )

    def list_agent_fleet(self) -> list[dict[str, Any]]:
        agents = {item["id"]: item for item in self.list_agents()}
        endpoints = {item["agent_id"]: item for item in self.list_agent_endpoints(enabled_only=False)}
        incidents = self.list_agent_incidents()
        incident_counts: dict[str, int] = {}
        for incident in incidents:
            if incident["status"] != "resolved":
                incident_counts[incident["agent_id"]] = incident_counts.get(incident["agent_id"], 0) + 1
        fleet: list[dict[str, Any]] = []
        for agent_id, endpoint in endpoints.items():
            agent = agents.get(agent_id, {"id": agent_id, "name": agent_id})
            latest = self.latest_agent_snapshot(agent_id)
            snapshot = (latest or {}).get("snapshot", {})
            fleet.append(
                {
                    **agent,
                    "bridge": {
                        "url": endpoint["bridge_url"],
                        "dashboard_url": endpoint.get("dashboard_url"),
                        "enabled": endpoint["enabled"],
                        "contract_version": endpoint["contract_version"],
                        "last_seen_at": endpoint.get("last_seen_at"),
                        "last_status": endpoint["last_status"],
                        "last_error": endpoint.get("last_error"),
                    },
                    "snapshot": snapshot,
                    "open_incidents": incident_counts.get(agent_id, 0),
                }
            )
        return fleet

    def create_agent_incident(
        self,
        agent_id: str,
        fingerprint: str,
        severity: str,
        incident_type: str,
        title: str,
        report: dict[str, Any],
        capability: str | None = None,
        contained: bool = False,
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            existing = self._row(
                connection.execute("SELECT * FROM aegis_agent_incidents WHERE fingerprint = ?", (fingerprint,))
            )
            if existing:
                existing["report"] = self._decode(existing.pop("report_json"), {})
                return existing
            incident_id = new_id("incident")
            now = utc_now()
            connection.execute(
                """INSERT INTO aegis_agent_incidents
                (id, agent_id, fingerprint, severity, incident_type, title, status, capability,
                 report_json, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incident_id,
                    agent_id,
                    fingerprint,
                    severity,
                    incident_type,
                    title[:300],
                    "contained" if contained else "open",
                    capability,
                    json.dumps(report, ensure_ascii=False, sort_keys=True, default=str),
                    now,
                ),
            )
            self._activity(
                connection,
                "agent_incident",
                f"{severity.upper()} {title}",
                "agent",
                agent_id,
                "critical" if severity == "critical" else "restricted",
            )
        return next(item for item in self.list_agent_incidents() if item["id"] == incident_id)

    def list_agent_incidents(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM aegis_agent_incidents"
        params: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            params = (agent_id,)
        query += " ORDER BY detected_at DESC"
        with self.database.connection() as connection:
            rows = self._rows(connection.execute(query, params))
        for row in rows:
            row["report"] = self._decode(row.pop("report_json"), {})
        return rows

    def resolve_agent_incident(self, incident_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_agent_incidents SET status = 'resolved', resolved_at = ?
                WHERE id = ?""",
                (now, incident_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Agent incident not found")
            self._activity(connection, "agent_incident_resolved", "Resolved agent incident", "incident", incident_id)
        return next(item for item in self.list_agent_incidents() if item["id"] == incident_id)

    def record_agent_control(
        self,
        agent_id: str,
        action: str,
        capability: str | None,
        reason: str,
        source: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control_id = new_id("control")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_agent_controls
                (id, agent_id, action, capability, reason, source, outcome, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (control_id, agent_id, action, capability, reason[:2000], source, outcome, json.dumps(details or {}), now),
            )
            self._activity(connection, "agent_control", f"{action}: {outcome}", "agent", agent_id, "restricted")
        return next(item for item in self.list_agent_controls(agent_id) if item["id"] == control_id)

    def list_agent_controls(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM aegis_agent_controls"
        params: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            params = (agent_id,)
        query += " ORDER BY created_at DESC"
        with self.database.connection() as connection:
            rows = self._rows(connection.execute(query, params))
        for row in rows:
            row["details"] = self._decode(row.pop("details_json"), {})
        return rows

    def create_agent_learning_update(self, payload: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        update_id = new_id("learning")
        now = utc_now()
        content = str(payload["content"])
        status = "evaluated" if evaluation.get("auto_deploy_allowed") else "approval_required"
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_agent_endpoints WHERE agent_id = ?", (payload["agent_id"],)).fetchone():
                raise KeyError("Independent agent is not registered")
            course_id = payload.get("course_id")
            if course_id and not connection.execute("SELECT 1 FROM aegis_academy_courses WHERE id = ?", (course_id,)).fetchone():
                raise KeyError("Academy course not found")
            connection.execute(
                """INSERT INTO aegis_agent_learning_updates
                (id, agent_id, course_id, title, source, content, content_sha256, risk_level,
                 status, evaluation_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    update_id,
                    payload["agent_id"],
                    course_id,
                    payload["title"],
                    payload["source"],
                    content,
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    payload["risk_level"],
                    status,
                    json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            self._activity(connection, "agent_learning_evaluated", f"Evaluated learning update: {payload['title']}", "agent", payload["agent_id"])
        return self.get_agent_learning_update(update_id) or {}

    def get_agent_learning_update(self, update_id: str, include_content: bool = True) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM aegis_agent_learning_updates WHERE id = ?", (update_id,)))
        if not row:
            return None
        row["evaluation"] = self._decode(row.pop("evaluation_json"), {})
        row["deployment"] = self._decode(row.pop("deployment_json"), {})
        if not include_content:
            row["content_preview"] = row["content"][:240]
            row.pop("content", None)
        return row

    def list_agent_learning_updates(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id FROM aegis_agent_learning_updates"
        params: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            params = (agent_id,)
        query += " ORDER BY created_at DESC"
        with self.database.connection() as connection:
            ids = [row[0] for row in connection.execute(query, params).fetchall()]
        return [item for item in (self.get_agent_learning_update(value, include_content=False) for value in ids) if item]

    def finish_agent_learning_update(self, update_id: str, status: str, deployment: dict[str, Any]) -> dict[str, Any]:
        if status not in {"deployed", "failed", "rolled_back"}:
            raise ValueError("Unsupported learning deployment status")
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_agent_learning_updates SET status = ?, deployment_json = ?, deployed_at = ?
                WHERE id = ?""",
                (status, json.dumps(deployment, ensure_ascii=False, sort_keys=True, default=str), now, update_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Learning update not found")
            row = self._row(connection.execute("SELECT agent_id, title FROM aegis_agent_learning_updates WHERE id = ?", (update_id,)))
            self._activity(connection, "agent_learning_deployment", f"{status}: {row['title']}", "agent", row["agent_id"])
        return self.get_agent_learning_update(update_id, include_content=False) or {}

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
        approval_queue: str | None = None,
    ) -> dict[str, Any]:
        approval_id = new_id("approval")
        now = utc_now()
        business_actions = {"solution_transition", "business_asset", "launch", "publish", "purchase"}
        queue = approval_queue or ("business_creative" if action in business_actions else "security_operations")
        if queue not in {"security_operations", "business_creative"}:
            raise ValueError("Unsupported approval queue")
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_approvals
                (id, project_id, task_id, action, approval_queue, summary, risk_level, status, evidence_json, requested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (approval_id, project_id, task_id, action, queue, summary, risk_level, json.dumps(evidence or {}), now),
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

    def list_world_pulse_source_candidates(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(
                connection.execute(
                    """SELECT c.*, a.status AS approval_status, a.decided_at
                    FROM aegis_world_pulse_source_candidates c
                    JOIN aegis_approvals a ON a.id = c.approval_id
                    ORDER BY c.created_at DESC"""
                )
            )
        for row in rows:
            row["identity_verified"] = bool(row["identity_verified"])
            row["status"] = "approved" if row["approval_status"] == "approved" else row["approval_status"]
        return rows

    def create_world_pulse_source_candidate(self, payload: dict[str, Any], approval_id: str) -> dict[str, Any]:
        candidate_id = new_id("pulse-source")
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_world_pulse_source_candidates
                (id, label, niche, source_type, locator, reason, identity_verified, approval_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate_id,
                    payload["label"],
                    payload["niche"],
                    payload["source_type"],
                    payload["locator"],
                    payload.get("reason", ""),
                    int(payload.get("identity_verified", False)),
                    approval_id,
                    utc_now(),
                ),
            )
            self._activity(connection, "pulse_source_proposed", f"Proposed World Pulse source: {payload['label']}", "pulse_source", candidate_id)
        return next(item for item in self.list_world_pulse_source_candidates() if item["id"] == candidate_id)

    def list_world_pulse_schedules(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(connection.execute("SELECT * FROM aegis_world_pulse_schedules ORDER BY updated_at DESC"))

    def create_world_pulse_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        schedule_id = new_id("pulse-schedule")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_world_pulse_schedules
                (id, name, niche, query, cadence_hours, execution_policy, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'approval_each_run', 'planned', ?, ?)""",
                (schedule_id, payload["name"], payload["niche"], payload["query"], payload["cadence_hours"], now, now),
            )
            self._activity(connection, "pulse_schedule_created", f"Created approval-gated research schedule: {payload['name']}", "pulse_schedule", schedule_id)
        return next(item for item in self.list_world_pulse_schedules() if item["id"] == schedule_id)

    def mark_world_pulse_schedule_requested(self, schedule_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_world_pulse_schedules SET last_requested_at = ?, updated_at = ? WHERE id = ?",
                (now, now, schedule_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("World Pulse schedule not found")
        return next(item for item in self.list_world_pulse_schedules() if item["id"] == schedule_id)

    def set_world_pulse_schedule_status(self, schedule_id: str, status: str) -> dict[str, Any]:
        if status not in {"planned", "paused"}:
            raise ValueError("Unsupported World Pulse schedule status")
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_world_pulse_schedules SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, schedule_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("World Pulse schedule not found")
            self._activity(connection, "pulse_schedule_status", f"World Pulse schedule set to {status}", "pulse_schedule", schedule_id)
        return next(item for item in self.list_world_pulse_schedules() if item["id"] == schedule_id)

    def due_world_pulse_schedules(self, now: datetime | None = None) -> list[dict[str, Any]]:
        anchor = now or datetime.now(timezone.utc)
        due: list[dict[str, Any]] = []
        for item in self.list_world_pulse_schedules():
            if item["status"] != "planned":
                continue
            last = item.get("last_requested_at")
            if not last or anchor - datetime.fromisoformat(str(last)) >= timedelta(hours=int(item["cadence_hours"])):
                due.append(item)
        return due

    def list_opportunity_cycles(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return self._rows(connection.execute("SELECT * FROM aegis_opportunity_cycles ORDER BY updated_at DESC"))

    def create_opportunity_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = new_id("opportunity-cycle")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_opportunity_cycles
                (id, name, niche, query, allocation, cadence_hours, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (cycle_id, payload["name"], payload["niche"], payload["query"], payload["allocation"], payload["cadence_hours"], now, now),
            )
            self._activity(connection, "opportunity_cycle_created", f"Created recurring opportunity cycle: {payload['name']}", "opportunity_cycle", cycle_id)
        return next(item for item in self.list_opportunity_cycles() if item["id"] == cycle_id)

    def set_opportunity_cycle_status(self, cycle_id: str, status: str) -> dict[str, Any]:
        if status not in {"active", "paused"}:
            raise ValueError("Unsupported opportunity cycle status")
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_opportunity_cycles SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, cycle_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Opportunity cycle not found")
            self._activity(connection, "opportunity_cycle_status", f"Opportunity cycle set to {status}", "opportunity_cycle", cycle_id)
        return next(item for item in self.list_opportunity_cycles() if item["id"] == cycle_id)

    def due_opportunity_cycles(self, now: datetime | None = None) -> list[dict[str, Any]]:
        anchor = now or datetime.now(timezone.utc)
        return [
            item for item in self.list_opportunity_cycles()
            if item["status"] == "active" and (
                not item.get("last_run_at")
                or anchor - datetime.fromisoformat(str(item["last_run_at"])) >= timedelta(hours=int(item["cadence_hours"]))
            )
        ]

    def mark_opportunity_cycle_run(self, cycle_id: str, fingerprint: str | None) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_opportunity_cycles SET last_run_at = ?, last_candidate_fingerprint = ?, updated_at = ?
                WHERE id = ?""",
                (now, fingerprint, now, cycle_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Opportunity cycle not found")
        return next(item for item in self.list_opportunity_cycles() if item["id"] == cycle_id)

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

    def list_research_reports(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            if project_id:
                rows = self._rows(
                    connection.execute(
                        "SELECT * FROM aegis_research_reports WHERE project_id = ? ORDER BY created_at DESC",
                        (project_id,),
                    )
                )
            else:
                rows = self._rows(connection.execute("SELECT * FROM aegis_research_reports ORDER BY created_at DESC"))
        for row in rows:
            row["report"] = self._decode(row.pop("report_json"), {})
        return rows

    def create_research_report(
        self,
        *,
        project_id: str | None,
        purpose: str,
        query: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        if purpose not in {"world_pulse", "opportunity"}:
            raise ValueError("Unsupported research report purpose")
        report_id = new_id("research-report")
        now = utc_now()
        metrics = report.get("source_metrics", {})
        source_count = int(metrics.get("source_count", 0))
        if source_count < 1:
            raise ValueError("A research report requires at least one accepted source")
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_research_reports
                (id, project_id, purpose, query, title, status, source_count, independent_domains, report_json, created_at)
                VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?)""",
                (
                    report_id,
                    project_id,
                    purpose,
                    query,
                    str(report.get("title", f"Research: {query}"))[:500],
                    source_count,
                    int(metrics.get("independent_domains", 0)),
                    json.dumps(report),
                    now,
                ),
            )
            self._activity(connection, "research_report_created", f"Created {purpose} research report: {query[:180]}", "research_report", report_id)
        return next(item for item in self.list_research_reports() if item["id"] == report_id)

    def remove_invalid_empty_research_reports(self) -> int:
        """Remove report artifacts that could not have contained source evidence."""
        with self.database.connection() as connection:
            invalid = self._rows(
                connection.execute("SELECT id FROM aegis_research_reports WHERE source_count = 0")
            )
            if invalid:
                connection.execute("DELETE FROM aegis_research_reports WHERE source_count = 0")
                for item in invalid:
                    self._activity(
                        connection,
                        "invalid_research_report_removed",
                        "Removed an empty research report that had no usable source evidence",
                        "research_report",
                        item["id"],
                    )
        return len(invalid)

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
                (id, title, problem, audience, stage, proof, owner_agent, opportunity_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'discover', ?, ?, ?, ?, ?)""",
                (solution_id, payload["title"], payload["problem"], payload["audience"], payload.get("proof", ""), payload.get("owner_agent"), payload.get("opportunity_id"), now, now),
            )
            self._activity(connection, "solution_created", f"Created solution program: {payload['title']}", "solution", solution_id)
        return next(item for item in self.list_solutions() if item["id"] == solution_id)

    def list_academy_courses(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            courses = self._rows(connection.execute("SELECT * FROM aegis_academy_courses ORDER BY updated_at DESC"))
            for course in courses:
                course["materials"] = self._rows(connection.execute(
                    """SELECT id, course_id, module_title, source_url, content_sha256, verification_state, created_at
                    FROM aegis_academy_materials WHERE course_id = ? ORDER BY created_at""",
                    (course["id"],),
                ))
                course["assessments"] = self._rows(connection.execute(
                    "SELECT * FROM aegis_academy_assessments WHERE course_id = ? ORDER BY created_at",
                    (course["id"],),
                ))
                for assessment in course["assessments"]:
                    assessment["passed"] = bool(assessment["passed"])
                    assessment["evidence"] = self._decode(assessment.pop("evidence_json"), {})
                course["completion_ready"] = (
                    float(course.get("progress", 0)) >= 100
                    and bool(course["materials"])
                    and any(item["passed"] for item in course["assessments"])
                )
        return courses

    def create_academy_course(self, payload: dict[str, Any]) -> dict[str, Any]:
        course_id = new_id("course")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_academy_courses
                (id, title, provider, source_url, status, progress, learning_goal, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'planned', 0, ?, ?, ?)""",
                (course_id, payload["title"], payload.get("provider", "Independent"), payload.get("source_url"), payload.get("learning_goal", ""), now, now),
            )
            self._activity(connection, "academy_course_added", f"Added course: {payload['title']}", "academy_course", course_id)
        return next(item for item in self.list_academy_courses() if item["id"] == course_id)

    def update_academy_course(self, course_id: str, status: str, progress: float) -> dict[str, Any]:
        if status not in {"planned", "active", "completed", "paused"}:
            raise ValueError("Unsupported course status")
        now = utc_now()
        with self.database.connection() as connection:
            if status == "completed":
                material_count = int(connection.execute(
                    "SELECT COUNT(*) FROM aegis_academy_materials WHERE course_id = ? AND verification_state != 'unverified'",
                    (course_id,),
                ).fetchone()[0])
                passed_count = int(connection.execute(
                    "SELECT COUNT(*) FROM aegis_academy_assessments WHERE course_id = ? AND passed = 1",
                    (course_id,),
                ).fetchone()[0])
                if progress < 100 or material_count < 1 or passed_count < 1:
                    raise ValueError("Course completion requires 100% progress, verified material, and a passed assessment")
            cursor = connection.execute(
                "UPDATE aegis_academy_courses SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
                (status, progress, now, course_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Course not found")
            self._activity(connection, "academy_progress_updated", f"Course progress updated to {progress:.0f}%", "academy_course", course_id)
        return next(item for item in self.list_academy_courses() if item["id"] == course_id)

    def add_academy_material(self, course_id: str, payload: dict[str, Any], verification_state: str) -> dict[str, Any]:
        material_id = new_id("course-material")
        content = str(payload["content"])
        now = utc_now()
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_academy_courses WHERE id = ?", (course_id,)).fetchone():
                raise KeyError("Course not found")
            connection.execute(
                """INSERT INTO aegis_academy_materials
                (id, course_id, module_title, source_url, content, content_sha256, verification_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (material_id, course_id, payload["module_title"], payload.get("source_url"), content, hashlib.sha256(content.encode()).hexdigest(), verification_state, now),
            )
            self._activity(connection, "academy_material_added", f"Added verified course material: {payload['module_title']}", "academy_course", course_id)
        return next(item for item in self.list_academy_courses() if item["id"] == course_id)

    def add_academy_assessment(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assessment_id = new_id("assessment")
        passed = float(payload["score"]) >= 80
        now = utc_now()
        with self.database.connection() as connection:
            if not connection.execute("SELECT 1 FROM aegis_academy_courses WHERE id = ?", (course_id,)).fetchone():
                raise KeyError("Course not found")
            connection.execute(
                """INSERT INTO aegis_academy_assessments
                (id, course_id, title, assessment_type, score, passed, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (assessment_id, course_id, payload["title"], payload["assessment_type"], payload["score"], int(passed), json.dumps(payload.get("evidence", {})), now),
            )
            self._activity(connection, "academy_assessment_recorded", f"Recorded Academy assessment: {payload['title']}", "academy_course", course_id)
        return next(item for item in self.list_academy_courses() if item["id"] == course_id)

    def create_containment_drill(self, agent_id: str) -> dict[str, Any]:
        drill_id = new_id("containment-drill")
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO aegis_containment_drills (id, agent_id, status, report_json, created_at) VALUES (?, ?, 'running', '{}', ?)",
                (drill_id, agent_id, now),
            )
        return {"id": drill_id, "agent_id": agent_id, "status": "running", "created_at": now}

    def finish_containment_drill(self, drill_id: str, status: str, report: dict[str, Any]) -> dict[str, Any]:
        if status not in {"passed", "failed"}:
            raise ValueError("Unsupported containment drill status")
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_containment_drills SET status = ?, report_json = ?, completed_at = ? WHERE id = ?",
                (status, json.dumps(report), now, drill_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Containment drill not found")
            self._activity(connection, "containment_drill", f"Containment drill {status}", "containment_drill", drill_id)
        return {"id": drill_id, "status": status, "report": report, "completed_at": now}

    def list_containment_drills(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(connection.execute("SELECT * FROM aegis_containment_drills ORDER BY created_at DESC LIMIT 20"))
        for row in rows:
            row["report"] = self._decode(row.pop("report_json"), {})
        return rows

    def list_learning_memory(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(connection.execute("SELECT * FROM aegis_learning_memory ORDER BY updated_at DESC"))
        for row in rows:
            row["affects_authority"] = bool(row["affects_authority"])
        return rows

    def create_learning_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = new_id("memory")
        now = utc_now()
        kind = payload.get("kind", "explicit")
        affects_authority = bool(payload.get("affects_authority", False))
        status = "proposed" if kind == "inferred" or affects_authority else "confirmed"
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO aegis_learning_memory
                (id, kind, category, statement, reason, confidence, status, affects_authority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, kind, payload["category"], payload["statement"], payload.get("reason", ""), payload.get("confidence", 1), status, int(affects_authority), now, now),
            )
            self._activity(connection, "learning_memory_created", f"Created {kind} memory proposal", "learning_memory", memory_id)
        return next(item for item in self.list_learning_memory() if item["id"] == memory_id)

    def set_learning_memory_status(self, memory_id: str, status: str) -> dict[str, Any]:
        if status not in {"confirmed", "disabled"}:
            raise ValueError("Unsupported memory status")
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE aegis_learning_memory SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), memory_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Memory not found")
        return next(item for item in self.list_learning_memory() if item["id"] == memory_id)

    def get_identity_profile(self) -> dict[str, Any]:
        with self.database.connection() as connection:
            profile = self._row(
                connection.execute("SELECT * FROM aegis_identity_profiles WHERE id = 'aegis-primary'")
            )
        if not profile:
            raise RuntimeError("Aegis identity profile is missing")
        profile["traits"] = self._decode(profile.pop("traits_json"), [])
        profile["identity_disclosure"] = "Aegis is an artificial digital executive partner, not a human."
        profile["authority_boundary"] = {
            "owner_retains_control": True,
            "self_permission_expansion": False,
            "external_actions_require_policy_check": True,
            "risky_or_sensitive_actions_require_approval": True,
        }
        return profile

    def update_identity_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE aegis_identity_profiles
                SET display_name = ?, role_title = ?, pronouns = ?, conversation_style = ?,
                    presentation_mode = ?, traits_json = ?, updated_at = ?
                WHERE id = 'aegis-primary'""",
                (
                    payload["display_name"],
                    payload["role_title"],
                    payload["pronouns"],
                    payload["conversation_style"],
                    payload["presentation_mode"],
                    json.dumps(payload["traits"]),
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Aegis identity profile is missing")
            self._activity(
                connection,
                "identity_profile_updated",
                "Updated owner-controlled Aegis presentation settings",
                "identity_profile",
                "aegis-primary",
            )
        return self.get_identity_profile()

    def list_identity_assets(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = self._rows(
                connection.execute(
                    "SELECT * FROM aegis_identity_assets ORDER BY asset_type, created_at"
                )
            )
        for row in rows:
            row["identity_locked"] = bool(row["identity_locked"])
        return rows

    def list_companion_sessions(self, limit: int = 25) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            sessions = self._rows(
                connection.execute(
                    "SELECT * FROM aegis_companion_sessions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                )
            )
            for session in sessions:
                session["notes"] = self._rows(
                    connection.execute(
                        """SELECT id, session_id, author, content, learning_candidate, created_at
                        FROM aegis_companion_notes WHERE session_id = ? ORDER BY created_at""",
                        (session["id"],),
                    )
                )
                for note in session["notes"]:
                    note["learning_candidate"] = bool(note["learning_candidate"])
        return sessions

    def start_companion_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = new_id("companion")
        now = utc_now()
        privacy_mode = payload.get("privacy_mode", "standard")
        retention_policy = "metadata_only" if privacy_mode == "private_incognito" else "notes_only"
        purpose = "" if privacy_mode == "private_incognito" else payload["purpose"]
        project_id = payload.get("project_id")
        with self.database.connection() as connection:
            if project_id and not connection.execute(
                "SELECT 1 FROM aegis_projects WHERE id = ?", (project_id,)
            ).fetchone():
                raise KeyError("Project not found")
            if connection.execute(
                "SELECT 1 FROM aegis_companion_sessions WHERE status = 'active'"
            ).fetchone():
                raise ValueError("Finish the active companion session before starting another")
            connection.execute(
                """INSERT INTO aegis_companion_sessions
                (id, project_id, session_type, privacy_mode, screen_access, retention_policy,
                 purpose, status, summary, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '', ?)""",
                (
                    session_id,
                    project_id,
                    payload["session_type"],
                    privacy_mode,
                    payload.get("screen_access", "none"),
                    retention_policy,
                    purpose,
                    now,
                ),
            )
            self._activity(
                connection,
                "companion_session_started",
                f"Started {privacy_mode.replace('_', ' ')} companion session",
                "companion_session",
                session_id,
            )
        return next(item for item in self.list_companion_sessions() if item["id"] == session_id)

    def add_companion_note(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        note_id = new_id("companion-note")
        memory_id = new_id("memory") if payload.get("learning_candidate") else None
        now = utc_now()
        with self.database.connection() as connection:
            session = self._row(
                connection.execute("SELECT * FROM aegis_companion_sessions WHERE id = ?", (session_id,))
            )
            if not session:
                raise KeyError("Companion session not found")
            if session["status"] != "active":
                raise ValueError("Companion session is not active")
            if session["privacy_mode"] == "private_incognito":
                raise ValueError("Private incognito sessions do not retain notes or learning candidates")
            connection.execute(
                """INSERT INTO aegis_companion_notes
                (id, session_id, author, content, learning_candidate, created_at)
                VALUES (?, ?, 'owner', ?, ?, ?)""",
                (note_id, session_id, payload["content"], int(bool(payload.get("learning_candidate"))), now),
            )
            if memory_id:
                connection.execute(
                    """INSERT INTO aegis_learning_memory
                    (id, kind, category, statement, reason, confidence, status, affects_authority, created_at, updated_at)
                    VALUES (?, 'inferred', 'learning', ?, ?, 0.7, 'proposed', 0, ?, ?)""",
                    (
                        memory_id,
                        payload["content"],
                        f"Owner marked a companion-session note as a learning candidate ({session_id})",
                        now,
                        now,
                    ),
                )
            self._activity(
                connection,
                "companion_note_added",
                "Added a local companion-session note",
                "companion_session",
                session_id,
            )
        return next(item for item in self.list_companion_sessions() if item["id"] == session_id)

    def finish_companion_session(self, session_id: str, status: str, summary: str = "") -> dict[str, Any]:
        if status not in {"completed", "aborted"}:
            raise ValueError("Unsupported companion session status")
        now = utc_now()
        with self.database.connection() as connection:
            session = self._row(
                connection.execute("SELECT * FROM aegis_companion_sessions WHERE id = ?", (session_id,))
            )
            if not session:
                raise KeyError("Companion session not found")
            if session["status"] != "active":
                raise ValueError("Companion session is already closed")
            retained_summary = "" if session["privacy_mode"] == "private_incognito" else summary
            connection.execute(
                """UPDATE aegis_companion_sessions
                SET status = ?, summary = ?, ended_at = ? WHERE id = ?""",
                (status, retained_summary, now, session_id),
            )
            self._activity(
                connection,
                "companion_session_closed",
                f"Companion session {status}",
                "companion_session",
                session_id,
            )
        return next(item for item in self.list_companion_sessions() if item["id"] == session_id)

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

    def search(self, query: str, limit: int = 40) -> list[dict[str, Any]]:
        clean = " ".join(query.split()).strip()
        if len(clean) < 2:
            return []
        pattern = f"%{clean}%"
        bounded = max(1, min(limit, 100))
        searches = (
            ("project", "SELECT id, name AS title, description AS summary, updated_at AS occurred_at FROM aegis_projects WHERE name LIKE ? OR description LIKE ? ORDER BY updated_at DESC LIMIT ?"),
            ("task", "SELECT id, title, COALESCE(result_summary, prompt) AS summary, updated_at AS occurred_at FROM aegis_tasks WHERE title LIKE ? OR prompt LIKE ? OR result_summary LIKE ? ORDER BY updated_at DESC LIMIT ?"),
            ("world_pulse", "SELECT id, headline AS title, summary, collected_at AS occurred_at FROM aegis_world_pulse WHERE headline LIKE ? OR summary LIKE ? ORDER BY collected_at DESC LIMIT ?"),
            ("opportunity", "SELECT id, title, thesis AS summary, updated_at AS occurred_at FROM aegis_opportunities WHERE title LIKE ? OR thesis LIKE ? ORDER BY updated_at DESC LIMIT ?"),
            ("solution", "SELECT id, title, problem AS summary, updated_at AS occurred_at FROM aegis_solutions WHERE title LIKE ? OR problem LIKE ? ORDER BY updated_at DESC LIMIT ?"),
            ("course", "SELECT id, title, learning_goal AS summary, updated_at AS occurred_at FROM aegis_academy_courses WHERE title LIKE ? OR learning_goal LIKE ? ORDER BY updated_at DESC LIMIT ?"),
        )
        results: list[dict[str, Any]] = []
        with self.database.connection() as connection:
            for kind, statement in searches:
                placeholders = statement.count("?")
                params = [pattern] * (placeholders - 1) + [bounded]
                for row in self._rows(connection.execute(statement, params)):
                    results.append({"kind": kind, **row})
        return sorted(results, key=lambda item: str(item.get("occurred_at", "")), reverse=True)[:bounded]

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
