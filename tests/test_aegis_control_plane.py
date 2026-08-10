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
from aegis_core.opportunity_reports import OpportunityReportService
from aegis_core.prompt_compiler import PromptCompiler
from aegis_core.research import WebResearchService
from aegis_core.schemas import ChatRequest
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


def test_approval_execution_is_single_use(store: AegisStore) -> None:
    approval = store.create_approval("bounded_action", "Run once", "high", evidence={"scope": "test"})
    store.decide_approval(approval["id"], "approved")
    claimed = store.claim_approval_execution(approval["id"], "bounded_action")
    assert claimed["execution"]["status"] == "running"
    store.finish_approval_execution(approval["id"], "completed", "done")
    with pytest.raises(ValueError, match="already consumed"):
        store.claim_approval_execution(approval["id"], "bounded_action")
    assert store.get_approval(approval["id"])["execution"]["status"] == "completed"


def test_stale_pending_approvals_expire(store: AegisStore) -> None:
    approval = store.create_approval("stale_action", "Do not keep forever", "medium")
    with store.database.connection() as connection:
        connection.execute(
            "UPDATE aegis_approvals SET requested_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", approval["id"]),
        )
    assert store.expire_stale_approvals() == 1
    assert store.get_approval(approval["id"])["status"] == "expired"


def test_task_state_machine_blocks_terminal_replay(store: AegisStore, tmp_path: Path) -> None:
    project = store.create_project("State Machine", "Test", tmp_path / "projects" / "states", None)
    task = store.create_task(project["id"], "One way", "Run safely", "low", status="running")
    store.update_task(task["id"], "completed", "finished")
    with pytest.raises(ValueError, match="Invalid task transition"):
        store.update_task(task["id"], "running", "replayed")


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


def test_prompt_compiler_keeps_owner_constraints_authoritative() -> None:
    class RewritingGateway:
        model = "test-local"

        def generate(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "response": """{
                    "objective": "List capabilities",
                    "deliverable": "A concise list",
                    "context": [],
                    "constraints": [],
                    "execution_steps": ["Read the snapshot"],
                    "risk_level": "low",
                    "approvals_required": [],
                    "success_evidence": ["Capabilities listed"],
                    "data_classification": "public",
                    "compiled_prompt": "List the available capabilities."
                }"""
            }

    original = "List exactly four capabilities and do not execute anything."
    compiled = PromptCompiler(RewritingGateway()).compile(original, {"name": "Aegis"})

    assert compiled["compiler_mode"] == "ollama-local"
    assert f"OWNER INTENT (authoritative; preserve every constraint): {original}" in compiled["compiled_prompt"]
    assert "REWRITTEN EXECUTION CONTRACT" in compiled["compiled_prompt"]


def test_chat_history_is_bounded_for_local_conversation_context() -> None:
    payload = ChatRequest(
        project_id="project-1",
        message="Continue the plan",
        history=[
            {"role": "user", "content": "Create a plan"},
            {"role": "assistant", "content": "Here is the plan"},
        ],
    )
    assert [item.role for item in payload.history] == ["user", "assistant"]
    with pytest.raises(ValueError):
        ChatRequest(
            project_id="project-1",
            message="Too much history",
            history=[{"role": "user", "content": str(index)} for index in range(13)],
        )


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


def test_approved_public_research_is_narrowly_allowed_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "security.yaml").write_text(
        yaml.safe_dump({"version": 1, "data_handling": {"approved_public_research_sessions": True}}),
        encoding="utf-8",
    )
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENCY_OFFLINE_MODE", "true")

    class FakeSearch:
        def __enter__(self) -> "FakeSearch":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def text(self, _query: str, max_results: int) -> list[dict[str, str]]:
            assert max_results == 4
            return [{"title": "Public market signal", "href": "https://example.com/report", "body": "Public evidence"}]

    monkeypatch.setattr("aegis_core.research.DDGS", FakeSearch)
    service = WebResearchService(FoundationGuard())
    with pytest.raises(FoundationViolation, match="no approved public-research session"):
        service.search("AI services for small businesses", "quick")
    result = service.search("AI services for small businesses", "quick", approved_session=True)
    assert result["source_count"] == 1
    assert result["classification"] == "public-only"


def test_public_research_fails_closed_when_provider_has_no_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "security.yaml").write_text(
        yaml.safe_dump({"version": 1, "data_handling": {"approved_public_research_sessions": True}}),
        encoding="utf-8",
    )
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENCY_OFFLINE_MODE", "true")

    class EmptySearch:
        def __enter__(self) -> "EmptySearch":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def text(self, _query: str, max_results: int) -> list[dict[str, str]]:
            assert max_results == 4
            return []

    monkeypatch.setattr("aegis_core.research.DDGS", EmptySearch)
    with pytest.raises(RuntimeError, match="no usable results"):
        WebResearchService(FoundationGuard()).search(
            "AI services for small businesses",
            "quick",
            approved_session=True,
        )


def test_opportunity_report_is_source_backed_and_encrypted_in_store(store: AegisStore, tmp_path: Path) -> None:
    project = store.create_project("Opportunity Lab", "Research", tmp_path / "projects" / "opportunity", None)
    research = {"source_count": 2, "independent_domains": 2, "cross_referenced": True}
    signals = [
        {
            "headline": "Primary demand signal",
            "summary": "A public agency reports growing adoption.",
            "source_url": "https://example.gov/report",
            "domain": "example.gov",
            "source_tier": "primary",
            "verification_state": "primary_source",
            "confidence": 0.78,
        },
        {
            "headline": "Established market signal",
            "summary": "An established publication describes buyer interest.",
            "source_url": "https://reuters.com/example",
            "domain": "reuters.com",
            "source_tier": "established",
            "verification_state": "single_source",
            "confidence": 0.58,
        },
    ]
    report = OpportunityReportService().build("AI workflow audits", research, signals)
    saved = store.create_research_report(
        project_id=project["id"],
        purpose="opportunity",
        query="AI workflow audits",
        report=report,
    )

    assert saved["source_count"] == 2
    assert saved["independent_domains"] == 2
    assert saved["report"]["decision_state"] == "research_complete_validation_required"
    assert saved["report"]["sources"][0]["id"] == "S1"
    with pytest.raises(ValueError, match="accepted public source"):
        OpportunityReportService().build("Unsupported idea", {"source_count": 4}, [])


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
