from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from knowledge_pipeline.pipeline import HashEmbeddingFunction, KnowledgePipeline
from utils.encryption import EncryptionManager, KeyManager, safe_identifier
from utils.monitor import SystemMonitor
from utils.scheduler import SecureTaskScheduler


def test_aes_gcm_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
    monkeypatch.setenv("AI_AGENCY_MASTER_KEY", key)
    manager = EncryptionManager(KeyManager(tmp_path / ".env"))
    protected = manager.encrypt_bytes(b"private agency data", "test")
    assert b"private agency data" not in protected
    assert manager.decrypt_bytes(protected, "test") == b"private agency data"


def test_purpose_separation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_AGENCY_MASTER_KEY", base64.urlsafe_b64encode(b"z" * 32).decode("ascii"))
    manager = EncryptionManager(KeyManager(tmp_path / ".env"))
    protected = manager.encrypt_bytes(b"value", "purpose-a")
    with pytest.raises(Exception):
        manager.decrypt_bytes(protected, "purpose-b")


def test_safe_identifier_rejects_empty() -> None:
    assert safe_identifier("Client 123") == "Client_123"
    with pytest.raises(ValueError):
        safe_identifier("///")


def test_hash_embedding_is_local_and_deterministic() -> None:
    embedder = HashEmbeddingFunction(64)
    first = embedder(["local private agent"])[0]
    second = embedder(["local private agent"])[0]
    assert first == second
    assert len(first) == 64
    assert abs(sum(value * value for value in first) - 1.0) < 1e-8


def test_private_url_is_blocked() -> None:
    with pytest.raises(ValueError):
        KnowledgePipeline._validate_external_url("https://127.0.0.1/private")


def test_vector_store_fails_closed_without_verified_volume_encryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENCY_VECTOR_DB_ENCRYPTED_VOLUME_REQUIRED", "true")
    monkeypatch.setattr(SystemMonitor, "volume_encryption_status", lambda self: {"verified": False})
    pipeline = KnowledgePipeline.__new__(KnowledgePipeline)
    pipeline._chroma_client = None

    with pytest.raises(RuntimeError, match="volume encryption"):
        pipeline._client()


def test_scheduler_requires_security_validation() -> None:
    scheduler = SecureTaskScheduler()
    with pytest.raises(PermissionError):
        scheduler.submit("unsafe", lambda: None)
