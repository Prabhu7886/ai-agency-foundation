from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import yaml

from aegis_core.foundation import FoundationGuard, FoundationViolation
from aegis_core.codex_adapter import CodexAppServerAdapter
from aegis_core.data_lab import DataLabService
from aegis_core.github_adapter import GitHubAdapter
from aegis_core.model_gateway import LocalModelGateway
from aegis_core.model_router import LocalModelRouter
from aegis_core.opportunity_reports import OpportunityReportService
from aegis_core.prompt_compiler import PromptCompiler
from aegis_core.research import WebResearchService
from aegis_core.schemas import ChatRequest
from aegis_core.security_sentinel import SecuritySentinelService
from aegis_core.store import AegisStore
from aegis_core.world_pulse import WorldPulseService
from databases.setup_databases import DatabaseSetup
from tools.install_model_routing_policy import install as install_model_routing_policy


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


def test_approval_center_uses_two_audited_queues(store: AegisStore) -> None:
    security = store.create_approval("github_operation", "Inspect repository", "high")
    business = store.create_approval("solution_transition", "Validate offer", "medium")
    assert security["approval_queue"] == "security_operations"
    assert business["approval_queue"] == "business_creative"


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


def test_executive_prompt_does_not_turn_missing_measurements_into_low_risk() -> None:
    prompt = LocalModelGateway._executive_prompt("Assess concentration risk", {})
    assert "Never classify a risk as low merely because measurements are missing" in prompt


def test_model_router_selects_specialists_and_unloads_previous_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    models_path = config / "models.yaml"
    models_path.write_text(yaml.safe_dump({"models": {"aegis": {"vram_limit_mb": 7168}}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    models = [
        {"name": "llama3.1:8b", "size": 4_900_000_000},
        {"name": "deepseek-coder-v2:16b", "size": 8_900_000_000},
        {"name": "qwen2.5:14b", "size": 8_700_000_000},
    ]

    def fake_get(url: str, **_kwargs: object) -> FakeResponse:
        if url.endswith("/api/tags"):
            return FakeResponse({"models": models})
        return FakeResponse({"models": [{"name": "llama3.1:8b", "size_vram": 4_900_000_000}]})

    unloaded: list[str] = []

    def fake_post(_url: str, **kwargs: object) -> FakeResponse:
        unloaded.append(str(kwargs["json"]["model"]))  # type: ignore[index]
        assert kwargs["json"]["keep_alive"] == 0  # type: ignore[index]
        return FakeResponse({})

    monkeypatch.setattr("aegis_core.model_router.requests.get", fake_get)
    monkeypatch.setattr("aegis_core.model_router.requests.post", fake_post)
    router = LocalModelRouter(config_path=models_path)

    coding = router.select("Debug this Python FastAPI endpoint and add pytest coverage")
    assert coding["model"] == "deepseek-coder-v2:16b"
    assert coding["category"] == "coding"
    assert coding["resource_fit"] == "hybrid_gpu_ram"
    assert router.select("Analyze the market and compare financial risks")["model"] == "qwen2.5:14b"
    assert router.select("Talk through this idea with me")["model"] == "llama3.1:8b"
    assert router.prepare(coding)["unloaded_models"] == ["llama3.1:8b"]
    assert unloaded == ["llama3.1:8b"]


def test_model_routing_policy_installer_preserves_existing_configuration(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    path = config / "models.yaml"
    path.write_text(yaml.safe_dump({"models": {"aegis": {"primary": "llama3.1:8b"}}}), encoding="utf-8")

    assert install_model_routing_policy(tmp_path) == path
    installed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert installed["models"]["aegis"]["primary"] == "llama3.1:8b"
    assert installed["models"]["aegis"]["routing"]["routes"]["coding"]["model"] == "deepseek-coder-v2:16b"
    assert path.with_suffix(".yaml.pre-model-routing").is_file()


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
    assert compiled["execution_steps"] == ["Answer the owner's question directly from supplied verified context"]
    assert "Follow the owner's requested length and format exactly" in compiled["constraints"]


def test_prompt_compiler_does_not_hide_destructive_actions_behind_informational_wording() -> None:
    class LowRiskGateway:
        model = "test-local"

        def generate(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "response": json.dumps(
                    {
                        "objective": "Explain and execute",
                        "deliverable": "Result",
                        "execution_steps": ["Delete files"],
                        "risk_level": "low",
                        "approvals_required": [],
                        "success_evidence": ["Done"],
                        "data_classification": "internal",
                    }
                )
            }

    compiler = PromptCompiler(LowRiskGateway())
    compiled = compiler.compile("Explain this plan and then delete every project file", {"project": "Aegis"})
    assert compiled["risk_level"] == "high"
    assert compiled["approvals_required"]


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


def test_encrypted_conversation_persists_bounded_history(store: AegisStore, tmp_path: Path) -> None:
    project = store.create_project("Conversation Lab", "Private chat", tmp_path / "projects" / "chat", None)
    conversation = store.create_conversation(project["id"])
    owner_text = "Design a private local agent workflow"
    store.add_conversation_message(conversation["id"], "user", owner_text, provider="owner")
    store.add_conversation_message(
        conversation["id"],
        "assistant",
        "Start with a bounded execution contract.",
        provider="ollama-local",
        model="test-local",
        token_count=8,
        compilation={"objective": "Design the workflow", "risk_level": "low"},
    )

    loaded = store.get_conversation(conversation["id"])
    assert loaded and loaded["encrypted_at_rest"] is True
    assert loaded["title"] == owner_text
    assert [item["role"] for item in loaded["messages"]] == ["user", "assistant"]
    assert loaded["messages"][1]["compilation"]["objective"] == "Design the workflow"
    assert store.conversation_context(conversation["id"], limit=1) == [
        {"role": "assistant", "content": "Start with a bounded execution contract."}
    ]
    assert owner_text.encode("utf-8") not in store.database.database_path.read_bytes()

    archived = store.archive_conversation(conversation["id"])
    assert archived["status"] == "archived"
    with pytest.raises(ValueError, match="read-only"):
        store.add_conversation_message(conversation["id"], "user", "Continue")
    assert store.restore_conversation(conversation["id"])["status"] == "active"
    store.archive_conversation(conversation["id"])
    store.delete_conversation(conversation["id"])
    assert store.get_conversation(conversation["id"]) is None


def test_model_gateway_streams_local_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self) -> list[bytes]:
            return [
                b'{"response":"Hello"}',
                b'{"response":" locally","done":true,"eval_count":2,"prompt_eval_count":5}',
            ]

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        assert url == "http://127.0.0.1:11434/api/generate"
        assert kwargs["json"]["stream"] is True  # type: ignore[index]
        return FakeResponse()

    monkeypatch.setattr("aegis_core.model_gateway.requests.post", fake_post)
    events = list(LocalModelGateway(model="test-local").stream_chat("Say hello", {"project": "test"}))
    assert "".join(item.get("content", "") for item in events) == "Hello locally"
    assert events[-1] == {"type": "done", "tokens": 2, "prompt_tokens": 5}


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


def test_github_controlled_maintenance_stages_only_explicit_registered_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "security.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "github": {"controlled_maintenance_enabled": True, "require_single_use_approval": True},
            }
        ),
        encoding="utf-8",
    )
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENCY_OFFLINE_MODE", "true")
    repository = tmp_path / "projects" / "repo"
    repository.mkdir(parents=True)
    GitHubAdapter._run(["git", "-C", str(repository), "init"], timeout=15)
    GitHubAdapter._run(["git", "-C", str(repository), "remote", "add", "origin", "https://github.com/example/repo"], timeout=15)
    GitHubAdapter._run(["git", "-C", str(repository), "switch", "-c", "codex/test"], timeout=15)
    (repository / "safe.txt").write_text("bounded", encoding="utf-8")
    guard = FoundationGuard()
    adapter = GitHubAdapter(guard, executable=str(tmp_path / "missing.exe"))
    project = {"id": "project-test", "root_path": str(repository), "repository_url": "https://github.com/example/repo"}

    result = adapter.execute(project, "stage_files", {"paths": ["safe.txt"]})
    assert result["returncode"] == 0
    staged = GitHubAdapter._run(["git", "-C", str(repository), "diff", "--cached", "--name-only"], timeout=15)
    assert staged["output"].strip() == "safe.txt"
    with pytest.raises(FoundationViolation, match="escapes"):
        adapter.execute(project, "stage_files", {"paths": ["../outside.txt"]})
    adapter._assert_online(approved_network=True)


def test_security_sentinel_scans_only_tracked_text_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "security.yaml").write_text(yaml.safe_dump({"version": 1}), encoding="utf-8")
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    repository = tmp_path / "projects" / "repo"
    repository.mkdir(parents=True)
    GitHubAdapter._run(["git", "-C", str(repository), "init"], timeout=15)
    (repository / "safe.py").write_text("subprocess.run(command, shell=True)\n", encoding="utf-8")
    (repository / ".env").write_text("EXAMPLE_ONLY=true\n", encoding="utf-8")
    (repository / "untracked.py").write_text("eval('ignored')\n", encoding="utf-8")
    GitHubAdapter._run(["git", "-C", str(repository), "add", "--", "safe.py", ".env"], timeout=15)

    result = SecuritySentinelService(FoundationGuard()).scan(
        {"id": "project-test", "name": "Test", "root_path": str(repository)}
    )

    assert result["network_used"] is False
    assert result["file_source"] == "git_tracked"
    assert result["files_scanned"] == 1
    assert {item["rule"] for item in result["findings"]} == {"shell-execution", "tracked-env"}
    assert all(item["file"] != "untracked.py" for item in result["findings"])


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


def test_world_pulse_source_candidates_and_schedules_remain_approval_gated(store: AegisStore) -> None:
    approval = store.create_approval(
        "world_pulse_source",
        "Approve Federal Reserve public data",
        "medium",
        evidence={"monitoring_scope": "public_information_only"},
    )
    source = store.create_world_pulse_source_candidate(
        {
            "label": "Federal Reserve",
            "niche": "economy-trade",
            "source_type": "public_data",
            "locator": "https://www.federalreserve.gov/data.htm",
            "reason": "Primary public economic data",
            "identity_verified": True,
        },
        approval["id"],
    )
    assert source["status"] == "pending"
    store.decide_approval(approval["id"], "approved")
    assert store.list_world_pulse_source_candidates()[0]["status"] == "approved"

    schedule = store.create_world_pulse_schedule(
        {"name": "AI policy watch", "niche": "ai-technology", "query": "official AI policy updates", "cadence_hours": 24}
    )
    assert schedule["execution_policy"] == "approval_each_run"
    assert schedule["last_requested_at"] is None
    assert store.mark_world_pulse_schedule_requested(schedule["id"])["last_requested_at"]


def test_world_pulse_does_not_call_same_domain_duplicates_corroborated(store: AegisStore) -> None:
    result = WorldPulseService(store).ingest(
        {
            "findings": [
                {"title": "AI buyer demand rises", "url": "https://reuters.com/one", "summary": "First result."},
                {"title": "AI buyer demand rises", "url": "https://reuters.com/two", "summary": "Duplicate result."},
            ]
        },
        "markets",
        ["Global"],
    )

    assert {item["verification_state"] for item in result["signals"]} == {"single_source"}


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
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self) -> "FakeSearch":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def text(self, query: str, max_results: int) -> list[dict[str, str]]:
            self.calls += 1
            if "site:.gov" in query:
                assert max_results == 2
                return [{"title": "Official market signal", "href": "https://example.gov/report", "body": "Official evidence"}]
            assert max_results == 4
            return [{"title": "Public market signal", "href": "https://example.com/report", "body": "Public evidence"}]

    monkeypatch.setattr("aegis_core.research.DDGS", FakeSearch)
    service = WebResearchService(FoundationGuard())
    with pytest.raises(FoundationViolation, match="no approved public-research session"):
        service.search("AI services for small businesses", "quick")
    result = service.search("AI services for small businesses", "quick", approved_session=True, verify_pages=False)
    assert result["source_count"] == 2
    assert result["classification"] == "public-only"
    assert result["research_lanes"]["primary"]["accepted"] == 1


def test_full_page_verification_extracts_bounded_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "security.yaml").write_text(yaml.safe_dump({"version": 1}), encoding="utf-8")
    (config / "models.yaml").write_text(yaml.safe_dump({"defaults": {"offline_mode": True}}), encoding="utf-8")
    monkeypatch.setenv("AI_AGENCY_HOME", str(tmp_path))
    monkeypatch.setattr("aegis_core.research.socket.getaddrinfo", lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])

    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/html", "Content-Length": "500"}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            assert chunk_size == 65_536
            return [b'''<html><head><title>Official survey</title>
                <meta property="article:published_time" content="2026-07-01">
                <link rel="canonical" href="https://example.gov/report"></head>
                <body><h1>Official survey</h1><p>Methodology and sample size are documented.</p></body></html>''']

    monkeypatch.setattr("aegis_core.research.requests.get", lambda *_args, **_kwargs: FakeResponse())
    result = WebResearchService(FoundationGuard())._fetch_source(
        {"title": "Official survey", "url": "https://example.gov/report", "summary": "Search excerpt"}
    )
    assert result["page_verification_state"] == "verified_html"
    assert result["date_source"] == "page_metadata"
    assert result["published_at"] == "2026-07-01"
    assert result["methodology_terms"] == ["methodology", "sample size"]
    assert len(result["content_sha256"]) == 64


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
    assert saved["report"]["quality_gate"] == "mixed_quality_discovery"
    assert saved["report"]["source_metrics"]["high_trust_source_count"] == 2
    with pytest.raises(ValueError, match="accepted public source"):
        OpportunityReportService().build("Unsupported idea", {"source_count": 4}, [])


def test_opportunity_report_requires_verified_page_evidence_for_supported_gate() -> None:
    signals = [
        {
            "headline": f"Primary source {index}",
            "summary": "Official methodology-backed evidence.",
            "source_url": f"https://agency{index}.gov/report",
            "domain": f"agency{index}.gov",
            "source_tier": "primary",
            "verification_state": "primary_source",
            "confidence": 0.78,
            "published_at": "2026-07-01",
            "page_verification_state": "verified_html",
            "date_source": "page_metadata",
            "methodology_terms": ["methodology"],
            "content_sha256": "a" * 64,
        }
        for index in range(2)
    ]
    report = OpportunityReportService().build("Verified market", {"source_count": 2}, signals)
    assert report["quality_gate"] == "supported_discovery"
    assert report["source_metrics"]["verified_page_count"] == 2
    assert report["source_metrics"]["verified_date_count"] == 2


def test_opportunity_report_flags_conflicting_numeric_claims_for_reconciliation() -> None:
    signals = [
        {
            "headline": "Small-business AI adoption rose in 2026",
            "summary": "The survey estimates AI adoption at 41 percent among small businesses.",
            "source_url": "https://agency-a.gov/adoption",
            "domain": "agency-a.gov",
            "source_tier": "primary",
            "verification_state": "primary_source",
            "confidence": 0.78,
            "published_at": "2026-07-01",
            "page_verification_state": "verified_html",
            "date_source": "page_metadata",
            "methodology_terms": ["survey"],
        },
        {
            "headline": "Small-business AI adoption rose in 2026",
            "summary": "The survey estimates AI adoption at 63 percent among small businesses.",
            "source_url": "https://agency-b.gov/adoption",
            "domain": "agency-b.gov",
            "source_tier": "primary",
            "verification_state": "primary_source",
            "confidence": 0.78,
            "published_at": "2026-07-02",
            "page_verification_state": "verified_html",
            "date_source": "page_metadata",
            "methodology_terms": ["survey"],
        },
    ]

    report = OpportunityReportService().build("AI adoption", {"source_count": 2}, signals)
    assert report["claim_assessments"][0]["status"] == "needs_reconciliation"
    assert report["claim_assessments"][0]["metric_values"] == ["41 percent", "63 percent"]
    assert report["source_metrics"]["unresolved_claim_count"] == 1
    assert report["quality_gate"] == "mixed_quality_discovery"


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
    solution = store.create_solution({"title": "Audit kit", "problem": "Teams cannot verify private AI deployments safely.", "audience": "small businesses", "opportunity_id": opportunity["id"]})
    assert solution["opportunity_id"] == opportunity["id"]
    with pytest.raises(ValueError, match="one evidence-backed stage"):
        store.transition_solution(solution["id"], "prototype", "Skipped validation")
    assert store.transition_solution(solution["id"], "validate", "Five interviews recorded")["stage"] == "validate"


def test_academy_and_controlled_learning_are_local_and_reviewable(store: AegisStore) -> None:
    course = store.create_academy_course({
        "title": "AI Product Strategy",
        "provider": "Coursera",
        "source_url": "https://www.coursera.org/learn/example",
        "learning_goal": "Turn verified customer problems into scoped offers.",
    })
    assert course["status"] == "planned"
    assert store.update_academy_course(course["id"], "active", 10)["progress"] == 10

    explicit = store.create_learning_memory({"kind": "explicit", "category": "communication", "statement": "Lead with the executive summary."})
    inferred = store.create_learning_memory({"kind": "inferred", "category": "workflow", "statement": "Prefer visual reviews.", "reason": "Repeated UI review requests", "confidence": 0.7})
    assert explicit["status"] == "confirmed"
    assert inferred["status"] == "proposed"
    assert store.set_learning_memory_status(inferred["id"], "disabled")["status"] == "disabled"
