from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from knowledge_pipeline.pipeline import HashEmbeddingFunction, KnowledgePipeline
from tools.backup_manager import EncryptedBackupManager
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


def test_bitlocker_parser_accepts_windows_device_encryption_at_100_percent() -> None:
    output = """
    Conversion Status:    Used Space Only Encrypted
    Percentage Encrypted: 100.0%
    Protection Status:    Protection On
    """
    result = SystemMonitor._parse_bitlocker_output(output, "C:")
    assert result["verified"] is True
    assert result["percentage"] == 100.0


def test_bitlocker_parser_rejects_partial_encryption() -> None:
    output = """
    Conversion Status:    Used Space Only Encrypted
    Percentage Encrypted: 99.9%
    Protection Status:    Protection On
    """
    assert SystemMonitor._parse_bitlocker_output(output, "C:")["verified"] is False


def test_ollama_firewall_requires_fresh_protected_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation = tmp_path / "security_attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "ollama_firewall": {
                    "verified": True,
                    "mode": "protected",
                    "rules": [{"name": "server", "verified": True}, {"name": "desktop", "verified": True}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_AGENCY_BITLOCKER_ATTESTATION", str(attestation))
    assert SystemMonitor._read_ollama_firewall_attestation(attestation)["verified"] is True

    payload = json.loads(attestation.read_text(encoding="utf-8"))
    payload["ollama_firewall"]["mode"] = "maintenance-or-unconfigured"
    payload["ollama_firewall"]["verified"] = False
    attestation.write_text(json.dumps(payload), encoding="utf-8")
    assert SystemMonitor._read_ollama_firewall_attestation(attestation)["verified"] is False


def test_scheduler_requires_security_validation() -> None:
    scheduler = SecureTaskScheduler()
    with pytest.raises(PermissionError):
        scheduler.submit("unsafe", lambda: None)


def _synthetic_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    files: dict[str, bytes],
    manifest_files: dict[str, bytes] | None = None,
) -> tuple[EncryptedBackupManager, Path, str]:
    timestamp = "20260809T120000Z"
    monkeypatch.setenv("AI_AGENCY_MASTER_KEY", base64.urlsafe_b64encode(b"r" * 32).decode("ascii"))
    encryption = EncryptionManager(KeyManager(tmp_path / "missing.env"))
    declared = manifest_files if manifest_files is not None else files
    manifest = {
        "version": 1,
        "created_at": timestamp,
        "files": [
            {
                "path": name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(declared.items())
        ],
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as backup_zip:
        for name, content in files.items():
            backup_zip.writestr(name, content)
        backup_zip.writestr("manifest.json", json.dumps(manifest))

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    backup_path = tmp_path / f"ai-agency-{timestamp}.zip.enc"
    backup_path.write_bytes(encryption.encrypt_bytes(archive.getvalue(), f"backup:{timestamp}"))
    manager = EncryptedBackupManager.__new__(EncryptedBackupManager)
    manager.paths = {"runtime": runtime}
    manager.encryption = encryption
    return manager, backup_path, timestamp


def test_synthetic_backup_restore_verifies_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = {"metrics.db": b"synthetic encrypted database", "config/security.yaml": b"offline: true\n"}
    manager, backup_path, _ = _synthetic_backup(monkeypatch, tmp_path, files)
    restored = manager.restore_to(backup_path, tmp_path / "restored")
    assert (restored / "metrics.db").read_bytes() == files["metrics.db"]
    assert (restored / "config" / "security.yaml").read_bytes() == files["config/security.yaml"]


def test_restore_rejects_manifest_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, backup_path, _ = _synthetic_backup(
        monkeypatch,
        tmp_path,
        {"metrics.db": b"tampered"},
        manifest_files={"metrics.db": b"expected"},
    )
    destination = tmp_path / "restored"
    with pytest.raises(RuntimeError, match="size does not match|hash does not match"):
        manager.restore_to(backup_path, destination)
    assert not destination.exists()


def test_restore_rejects_zip_path_traversal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, backup_path, _ = _synthetic_backup(
        monkeypatch,
        tmp_path,
        {"../outside.txt": b"escape"},
    )
    destination = tmp_path / "restored"
    with pytest.raises(RuntimeError, match="unsafe path"):
        manager.restore_to(backup_path, destination)
    assert not destination.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_restore_rejects_mismatched_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, backup_path, _ = _synthetic_backup(monkeypatch, tmp_path, {"metrics.db": b"data"})
    with pytest.raises(ValueError, match="does not match"):
        manager.restore_to(backup_path, tmp_path / "restored", "20260809T120001Z")
