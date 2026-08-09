from __future__ import annotations

import base64
from pathlib import Path

import pytest
import yaml

from aegis_core.foundation import FoundationGuard, FoundationViolation
from aegis_core.codex_adapter import CodexAppServerAdapter
from aegis_core.data_lab import DataLabService
from aegis_core.github_adapter import GitHubAdapter
from aegis_core.model_gateway import LocalModelGateway
from aegis_core.prompt_compiler import PromptCompiler
from aegis_core.store import AegisStore
from aegis_core.world_pulse import WorldPulseService
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
    store.save_prompt_compilation(
        task["id"],
        {
            "original_prompt": "Check the bounded design",
            "compiled_prompt": "Review the design and report evidence.",
            "objective": "Review architecture",
            "data_classification": "internal",
            "risk_level": "medium",
            "approvals_required": [],
            "success_evidence": ["Findings reported"],
            "compiler_mode": "ollama-local",
            "model": "test-model",
        },
    )

    assert store.get_project(project["id"])["tasks"][0]["id"] == task["id"]
    assert store.list_projects()[0]["task_count"] == 1
    assert store.list_projects()[0]["tasks"][0]["prompt_compilation"]["objective"] == "Review architecture"
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


def test_prompt_compiler_fails_closed_to_bounded_fallback() -> None:
    class OfflineGateway:
        model = "offline"

        def generate(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("offline")

    compiled = PromptCompiler(OfflineGateway()).compile(
        "Push the reviewed branch to GitHub",
        {"name": "Aegis"},
    )

    assert compiled["compiler_mode"] == "deterministic-fallback"
    assert compiled["risk_level"] == "medium"
    assert compiled["original_prompt"] == "Push the reviewed branch to GitHub"
    assert "Do not expand authority" in compiled["constraints"]


def test_engineering_adapters_enforce_bounded_identifiers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "security.yaml").write_text(yaml.safe_dump({"version": 1}), encoding="utf-8")
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENCY_OFFLINE_MODE", "true")
    guard = FoundationGuard()

    assert GitHubAdapter._validate_branch("codex/aegis-next") == "codex/aegis-next"
    with pytest.raises(FoundationViolation, match="codex/ prefix"):
        GitHubAdapter._validate_branch("main")
    with pytest.raises(FoundationViolation, match="offline mode"):
        GitHubAdapter(guard)._assert_online()
    assert CodexAppServerAdapter(guard, executable=str(tmp_path / "missing.exe")).status()["installed"] is False


def test_world_pulse_preserves_source_quality_and_rejects_local_urls(store: AegisStore) -> None:
    result = WorldPulseService(store).ingest(
        {
            "findings": [
                {"title": "Public filing update", "url": "https://www.sec.gov/example", "summary": "A public filing changed."},
                {"title": "Unsafe local result", "url": "https://127.0.0.1/private", "summary": "Must not be stored."},
            ]
        },
        "markets",
        ["United States"],
    )

    assert result["accepted"] == 1
    assert result["rejected"] == 1
    assert result["signals"][0]["source_tier"] == "primary"
    assert result["signals"][0]["verification_state"] == "primary_source"


def test_data_lab_preserves_raw_and_reports_transformations(store: AegisStore, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "security.yaml").write_text(yaml.safe_dump({"version": 1}), encoding="utf-8")
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    project = store.create_project("Data Project", "Test", tmp_path / "projects" / "data", None)
    source = Path(project["root_path"]) / "customers.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("name,email\n Alice ,N/A\n Alice ,N/A\n", encoding="utf-8")
    original = source.read_bytes()
    service = DataLabService(FoundationGuard())
    plan = service.plan(project, str(source), {"operations": ["trim_strings", "normalize_nulls", "deduplicate"]})
    result = service.execute(project, plan)

    assert source.read_bytes() == original
    assert Path(result["output_path"]).is_file()
    assert result["report"]["duplicates_removed"] == 1
    assert result["report"]["source_unchanged"] is True


def test_skill_promotion_requires_passing_evaluation(store: AegisStore) -> None:
    skill = store.list_skills()[0]
    candidate = store.create_skill_version(skill["id"], "0.2.0", "A bounded test instruction set with explicit evidence requirements.")
    with pytest.raises(ValueError, match="passing evaluation"):
        store.promote_skill_version(skill["id"], candidate["id"])
    store.evaluate_skill_version(candidate["id"], "pytest", 85, True, {"suite": "unit"})
    assert store.promote_skill_version(skill["id"], candidate["id"])["status"] == "active"


def test_opportunity_scoring_and_solution_stage_order(store: AegisStore) -> None:
    opportunity = store.create_opportunity({
        "title": "Local AI audits",
        "thesis": "Small businesses need private, bounded AI system audits.",
        "allocation": "explore-20",
        "evidence": ["public-source.example"],
        "evidence_strength": 80,
        "revenue_potential": 70,
        "strategic_fit": 90,
        "speed_to_revenue": 60,
        "execution_risk": 30,
    })
    assert opportunity["score"] == 75.5
    solution = store.create_solution({"title": "Audit kit", "problem": "Teams cannot verify private AI deployments safely.", "audience": "small businesses"})
    with pytest.raises(ValueError, match="one evidence-backed stage"):
        store.transition_solution(solution["id"], "prototype", "Skipped validation")
    assert store.transition_solution(solution["id"], "validate", "Five interviews recorded")["stage"] == "validate"
