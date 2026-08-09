from __future__ import annotations

import base64
from pathlib import Path

import pytest
import yaml

from aegis_core.foundation import FoundationGuard, FoundationViolation
from aegis_core.model_gateway import LocalModelGateway
from aegis_core.store import AegisStore
from databases.setup_databases import DatabaseSetup


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AegisStore:
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENCY_MASTER_KEY", base64.urlsafe_b64encode(b"a" * 32).decode("ascii"))
    database = DatabaseSetup(tmp_path / "databases" / "aegis.db")
    repository = AegisStore(database)
    repository.initialize()
    return repository


def test_registry_seeds_internal_engineering_agent_and_skills(store: AegisStore) -> None:
    agents = store.list_agents()
    assert [agent["name"] for agent in agents] == ["Internal Engineering"]
    assert {skill["name"] for skill in agents[0]["skills"]} == {"Secure Coding", "Security Review"}
    assert "Content Studio" in {skill["name"] for skill in store.list_skills()}


def test_project_task_and_approval_lifecycle(store: AegisStore, tmp_path: Path) -> None:
    project = store.create_project("Aegis Test", "Encrypted project", tmp_path / "projects" / "aegis", None)
    task = store.create_task(project["id"], "Review architecture", "Check the bounded design", "medium")
    approval = store.create_approval(
        "write_project_files",
        "Write the reviewed project files",
        "medium",
        project["id"],
        task["id"],
        {"files": 3},
    )
    decided = store.decide_approval(approval["id"], "approved")

    assert store.get_project(project["id"])["tasks"][0]["id"] == task["id"]
    assert decided["status"] == "approved"
    assert decided["evidence"] == {"files": 3}
    assert store.overview()["opportunity_allocation"] == {"existing": 80, "exploration": 20}


def test_foundation_guard_blocks_sensitive_research_and_unregistered_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "security.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "ollama": {"scheme": "http", "host": "127.0.0.1", "port": 11434},
                "encryption": {"sqlcipher_required": True},
                "vector_store": {"mode": "embedded_only", "server_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    guard = FoundationGuard()

    assert guard.validate_project_root(tmp_path / "projects" / "safe") == (tmp_path / "projects" / "safe").resolve()
    with pytest.raises(FoundationViolation, match="outside registered"):
        guard.validate_project_root(tmp_path.parent / "unregistered")
    with pytest.raises(FoundationViolation, match="Sensitive"):
        guard.sanitize_public_query("research customer data and API key")


def test_model_gateway_rejects_remote_ollama() -> None:
    with pytest.raises(FoundationViolation, match="loopback"):
        LocalModelGateway("http://example.com:11434")
