"""Create and verify the encrypted SQLCipher and ChromaDB stores."""

from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
from typing import Any, Iterator

from utils.encryption import EncryptionError, KeyManager, initialize_security_environment
from utils.logger import get_logger
from utils.monitor import SystemMonitor
from utils.paths import agency_root, ensure_runtime_directories


try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:  # pragma: no cover - explicit runtime error below
    sqlcipher = None  # type: ignore[assignment]


COLLECTIONS = (
    "aegis_brain",
    "etsy_knowledge",
    "ebay_knowledge",
    "shopify_knowledge",
    "resume_best_practices",
    "interview_knowledge",
    "web_design_patterns",
    "market_research",
    "competitor_analysis",
    "course_materials",
    "learning_content",
    "security_patterns",
    "open_source_learnings",
    "ai_industry_intel",
    "revenue_opportunities",
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0 CHECK(tokens_used >= 0),
    success BOOLEAN NOT NULL,
    response_time_ms INTEGER NOT NULL CHECK(response_time_ms >= 0),
    revenue_generated DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    user_satisfaction FLOAT,
    notes TEXT,
    security_flag BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_name_time ON agent_metrics(agent_name, start_time);

CREATE TABLE IF NOT EXISTS business_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    revenue DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    new_customers INTEGER NOT NULL DEFAULT 0,
    active_users INTEGER NOT NULL DEFAULT 0,
    agent_calls INTEGER NOT NULL DEFAULT 0,
    platform TEXT NOT NULL,
    security_incidents INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_business_metrics_date ON business_metrics(date);

CREATE TABLE IF NOT EXISTS knowledge_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    source TEXT NOT NULL,
    date_collected TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    confidence_score FLOAT NOT NULL CHECK(confidence_score BETWEEN 0 AND 1),
    needs_update BOOLEAN NOT NULL DEFAULT 0,
    source_type TEXT NOT NULL,
    security_level TEXT NOT NULL DEFAULT 'internal'
);
CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge_updates(topic);

CREATE TABLE IF NOT EXISTS aegis_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    agent_target TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT,
    security_check BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    check_type TEXT NOT NULL,
    result TEXT NOT NULL,
    severity TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_security_audit_time ON security_audit_log(timestamp);

CREATE TABLE IF NOT EXISTS open_source_intel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL,
    key_features TEXT NOT NULL,
    analyzed_date TEXT NOT NULL,
    implementation_ideas TEXT NOT NULL,
    code_quality_score FLOAT NOT NULL CHECK(code_quality_score BETWEEN 0 AND 100)
);

CREATE TABLE IF NOT EXISTS mobile_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    device_info TEXT,
    session_start TEXT NOT NULL,
    session_end TEXT,
    commands_issued INTEGER NOT NULL DEFAULT 0,
    security_verified BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS aegis_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    root_path TEXT NOT NULL,
    repository_url TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aegis_projects_status ON aegis_projects(status, updated_at);

CREATE TABLE IF NOT EXISTS aegis_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES aegis_projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK(status IN ('planned', 'awaiting_approval', 'running', 'completed', 'failed', 'cancelled')),
    risk_level TEXT NOT NULL DEFAULT 'low' CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
    assigned_agent TEXT,
    result_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aegis_tasks_project ON aegis_tasks(project_id, updated_at);

CREATE TABLE IF NOT EXISTS aegis_prompt_compilations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES aegis_tasks(id) ON DELETE CASCADE,
    original_prompt TEXT NOT NULL,
    compiled_prompt TEXT NOT NULL,
    objective TEXT NOT NULL,
    data_classification TEXT NOT NULL DEFAULT 'internal',
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
    approvals_json TEXT NOT NULL DEFAULT '[]',
    success_evidence_json TEXT NOT NULL DEFAULT '[]',
    compiler_mode TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aegis_prompt_task ON aegis_prompt_compilations(task_id, created_at);

CREATE TABLE IF NOT EXISTS aegis_agent_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    model_policy TEXT NOT NULL DEFAULT 'local-auto',
    status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN ('ready', 'busy', 'paused', 'offline')),
    prompt_version TEXT NOT NULL DEFAULT 'proposal-v1',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_skill_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '0.1.0',
    status TEXT NOT NULL DEFAULT 'proposal' CHECK(status IN ('proposal', 'testing', 'active', 'disabled')),
    risk_level TEXT NOT NULL DEFAULT 'low' CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_agent_skills (
    agent_id TEXT NOT NULL REFERENCES aegis_agent_registry(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES aegis_skill_registry(id) ON DELETE CASCADE,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY(agent_id, skill_id)
);

CREATE TABLE IF NOT EXISTS aegis_skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES aegis_skill_registry(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    instructions TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate', 'testing', 'active', 'retired')),
    created_at TEXT NOT NULL,
    promoted_at TEXT,
    UNIQUE(skill_id, version)
);

CREATE TABLE IF NOT EXISTS aegis_skill_evaluations (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES aegis_skill_versions(id) ON DELETE CASCADE,
    evaluator TEXT NOT NULL,
    score FLOAT NOT NULL CHECK(score BETWEEN 0 AND 100),
    passed BOOLEAN NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aegis_skill_evals ON aegis_skill_evaluations(version_id, created_at);

CREATE TABLE IF NOT EXISTS aegis_plugin_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available', 'enabled', 'disabled', 'planned')),
    connection_status TEXT NOT NULL DEFAULT 'not_connected',
    requires_approval BOOLEAN NOT NULL DEFAULT 1,
    data_policy TEXT NOT NULL DEFAULT 'local_only',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_approvals (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES aegis_projects(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES aegis_tasks(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    summary TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'declined', 'expired')),
    evidence_json TEXT NOT NULL DEFAULT '{}',
    requested_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_aegis_approvals_status ON aegis_approvals(status, requested_at);

CREATE TABLE IF NOT EXISTS aegis_approval_executions (
    id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE REFERENCES aegis_approvals(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    result_summary TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_aegis_approval_executions_status
ON aegis_approval_executions(status, started_at);

CREATE TABLE IF NOT EXISTS aegis_world_pulse (
    id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    category TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT,
    confidence FLOAT NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    impact_level TEXT NOT NULL DEFAULT 'monitor',
    published_at TEXT,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_world_pulse_sources (
    id TEXT PRIMARY KEY,
    pulse_id TEXT NOT NULL REFERENCES aegis_world_pulse(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    publisher TEXT,
    source_tier TEXT NOT NULL CHECK(source_tier IN ('primary', 'established', 'other')),
    verification_state TEXT NOT NULL CHECK(verification_state IN ('primary_source', 'corroborated', 'single_source')),
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    UNIQUE(pulse_id, url)
);
CREATE INDEX IF NOT EXISTS idx_aegis_pulse_sources ON aegis_world_pulse_sources(pulse_id, domain);

CREATE TABLE IF NOT EXISTS aegis_research_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES aegis_projects(id) ON DELETE SET NULL,
    purpose TEXT NOT NULL CHECK(purpose IN ('world_pulse', 'opportunity')),
    query TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed', 'failed')),
    source_count INTEGER NOT NULL DEFAULT 0 CHECK(source_count >= 0),
    independent_domains INTEGER NOT NULL DEFAULT 0 CHECK(independent_domains >= 0),
    report_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aegis_research_reports_project
ON aegis_research_reports(project_id, created_at);

CREATE TABLE IF NOT EXISTS aegis_opportunities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    thesis TEXT NOT NULL,
    allocation TEXT NOT NULL CHECK(allocation IN ('existing-80', 'explore-20')),
    score FLOAT NOT NULL DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'watching',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_solutions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    problem TEXT NOT NULL,
    audience TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'discover',
    proof TEXT NOT NULL DEFAULT '',
    owner_agent TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    security_level TEXT NOT NULL DEFAULT 'internal',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aegis_data_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES aegis_projects(id) ON DELETE CASCADE,
    source_path TEXT NOT NULL,
    output_path TEXT,
    source_sha256 TEXT NOT NULL,
    output_sha256 TEXT,
    recipe_json TEXT NOT NULL,
    report_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('planned', 'running', 'completed', 'failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_aegis_activity_time ON aegis_activity(created_at);
"""


class DatabaseSetup:
    """Owns encrypted database initialization and connection policy."""

    def __init__(self, database_path: Path | None = None) -> None:
        paths = ensure_runtime_directories()
        self.database_path = (database_path or paths["databases"] / "metrics.db").resolve()
        self.vector_path = paths["vector_db"].resolve()
        self.logger = get_logger("database_setup")
        self.keys = KeyManager()

    def connect(self) -> Any:
        """Return a keyed SQLCipher connection and fail if encryption is unavailable."""
        if sqlcipher is None:
            raise RuntimeError("sqlcipher3 is required; unencrypted SQLite fallback is prohibited")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlcipher.connect(str(self.database_path))
        try:
            key_hex = self.keys.sqlcipher_hex_key()
            connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")
            connection.execute("PRAGMA cipher_page_size = 4096")
            connection.execute("PRAGMA kdf_iter = 256000")
            connection.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
            connection.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
            cipher_row = connection.execute("PRAGMA cipher_version").fetchone()
            if not cipher_row or not cipher_row[0]:
                raise RuntimeError("SQLCipher did not report an active cipher version")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except Exception:
            connection.close()
            raise

    @contextlib.contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def setup_sqlcipher(self) -> dict[str, Any]:
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            cipher_version = connection.execute("PRAGMA cipher_version").fetchone()[0]
        required = {
            "agent_metrics",
            "business_metrics",
            "knowledge_updates",
            "aegis_commands",
            "security_audit_log",
            "open_source_intel",
            "mobile_sessions",
            "aegis_projects",
            "aegis_tasks",
            "aegis_prompt_compilations",
            "aegis_agent_registry",
            "aegis_skill_registry",
            "aegis_agent_skills",
            "aegis_skill_versions",
            "aegis_skill_evaluations",
            "aegis_plugin_registry",
            "aegis_approvals",
            "aegis_approval_executions",
            "aegis_world_pulse",
            "aegis_world_pulse_sources",
            "aegis_research_reports",
            "aegis_opportunities",
            "aegis_solutions",
            "aegis_activity",
            "aegis_data_jobs",
        }
        missing = required - tables
        if missing:
            raise RuntimeError(f"Database schema is incomplete: {sorted(missing)}")
        if integrity != "ok":
            raise RuntimeError(f"SQLCipher integrity check failed: {integrity}")
        self.logger.security_event("sqlcipher_setup", f"active version {cipher_version}")
        return {"path": str(self.database_path), "cipher_version": cipher_version, "tables": sorted(required)}

    def setup_chromadb(self) -> dict[str, Any]:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RuntimeError("chromadb is required for the knowledge store") from exc
        self.vector_path.mkdir(parents=True, exist_ok=True)
        require_volume = os.getenv("AI_AGENCY_VECTOR_DB_ENCRYPTED_VOLUME_REQUIRED", "true").lower() == "true"
        volume_status = SystemMonitor().volume_encryption_status()
        if require_volume and not volume_status.get("verified"):
            raise RuntimeError(
                "Vector database requires an encrypted filesystem volume. Enable BitLocker or explicitly set "
                "AI_AGENCY_VECTOR_DB_ENCRYPTED_VOLUME_REQUIRED=false only for an isolated development environment."
            )
        client = chromadb.PersistentClient(
            path=str(self.vector_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=False, is_persistent=True),
        )
        created = []
        for name in COLLECTIONS:
            client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine", "security": "encrypted-volume-required"})
            created.append(name)
        self.logger.security_event("chromadb_setup", f"created {len(created)} collections")
        return {"path": str(self.vector_path), "collections": created, "volume_encryption": volume_status}

    def verify(self) -> dict[str, Any]:
        sql_result = self.setup_sqlcipher()
        vector_result = self.setup_chromadb()
        return {"sqlcipher": sql_result, "chromadb": vector_result, "verified": True}

    def setup_all(self) -> dict[str, Any]:
        result = self.verify()
        print(f"SQLCipher database ready: {self.database_path}")
        print(f"ChromaDB ready: {self.vector_path}")
        print(f"Collections verified: {len(result['chromadb']['collections'])}")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the secure AI Agency databases")
    parser.add_argument("--init-key", action="store_true", help="Create a new .env and master encryption key")
    args = parser.parse_args()
    if args.init_key:
        try:
            created = initialize_security_environment()
            print(f"Security environment created: {created}")
        except EncryptionError as exc:
            print(f"Security environment not changed: {exc}")
    DatabaseSetup().setup_all()
    print(f"AI Agency secure database setup succeeded under {agency_root()}")


if __name__ == "__main__":
    main()
