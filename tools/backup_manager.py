"""Encrypted, verified backups for SQLCipher and the Chroma vector store."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from databases.setup_databases import DatabaseSetup
from utils.encryption import EncryptionManager
from utils.logger import get_logger
from utils.paths import ensure_runtime_directories


class EncryptedBackupManager:
    """Produces only AES-256-GCM backup artifacts and verifies every write."""

    def __init__(self) -> None:
        self.paths = ensure_runtime_directories()
        self.database = DatabaseSetup()
        self.encryption = EncryptionManager()
        self.logger = get_logger("backup_manager")
        self._lock = threading.Lock()

    def create_backup(self) -> dict[str, Any]:
        with self._lock:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            destination = self.paths["backups"] / f"ai-agency-{timestamp}.zip.enc"
            temporary_root = Path(tempfile.mkdtemp(prefix="aegis-backup-", dir=self.paths["runtime"]))
            archive_base = temporary_root / f"ai-agency-{timestamp}"
            try:
                source_root = temporary_root / "snapshot"
                source_root.mkdir()
                self._snapshot_sqlcipher(source_root)
                self._snapshot_vector_store(source_root)
                self._snapshot_configuration(source_root)
                manifest = self._manifest(source_root, timestamp)
                (source_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                archive_path = Path(shutil.make_archive(str(archive_base), "zip", source_root))
                purpose = f"backup:{timestamp}"
                destination.write_bytes(self.encryption.encrypt_bytes(archive_path.read_bytes(), purpose))
                verified = self._verify(destination, purpose, archive_path)
                if not verified:
                    destination.unlink(missing_ok=True)
                    raise RuntimeError("Encrypted backup verification failed")
                self.logger.security_event("encrypted_backup", f"Created {destination.name}", "info", "verified")
                return {"path": str(destination), "verified": True, "manifest": manifest}
            finally:
                shutil.rmtree(temporary_root, ignore_errors=True)

    def restore_to(self, backup_path: Path, destination: Path, timestamp: str) -> Path:
        source = Path(backup_path).resolve(strict=True)
        target = Path(destination).resolve()
        if target.exists() and any(target.iterdir()):
            raise FileExistsError("Restore destination must be empty")
        target.mkdir(parents=True, exist_ok=True)
        archive = self.encryption.decrypt_bytes(source.read_bytes(), f"backup:{timestamp}")
        temporary_zip = self.paths["runtime"] / f"restore-{timestamp}.zip"
        try:
            temporary_zip.write_bytes(archive)
            shutil.unpack_archive(temporary_zip, target, "zip")
        finally:
            temporary_zip.unlink(missing_ok=True)
        return target

    def prune(self, retain: int = 14) -> list[str]:
        if retain < 1:
            raise ValueError("At least one backup must be retained")
        backups = sorted(self.paths["backups"].glob("ai-agency-*.zip.enc"), key=lambda path: path.stat().st_mtime, reverse=True)
        removed = []
        for path in backups[retain:]:
            removed.append(path.name)
            path.unlink()
        return removed

    def _snapshot_sqlcipher(self, destination: Path) -> None:
        with self.database.connection() as connection:
            connection.execute("PRAGMA wal_checkpoint(FULL)")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Refusing backup because SQLCipher integrity is {integrity}")
        shutil.copy2(self.database.database_path, destination / "metrics.db")

    def _snapshot_vector_store(self, destination: Path) -> None:
        source = self.paths["vector_db"]
        if source.exists():
            shutil.copytree(source, destination / "vector_db")

    def _snapshot_configuration(self, destination: Path) -> None:
        config_destination = destination / "config"
        config_destination.mkdir()
        for path in self.paths["config"].glob("*"):
            if path.is_file() and path.name != ".env":
                shutil.copy2(path, config_destination / path.name)

    @staticmethod
    def _manifest(root: Path, timestamp: str) -> dict[str, Any]:
        files = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            files.append(
                {
                    "path": str(path.relative_to(root)).replace("\\", "/"),
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        return {"version": 1, "created_at": timestamp, "files": files}

    def _verify(self, encrypted_path: Path, purpose: str, original_archive: Path) -> bool:
        decrypted = self.encryption.decrypt_bytes(encrypted_path.read_bytes(), purpose)
        return hashlib.sha256(decrypted).digest() == hashlib.sha256(original_archive.read_bytes()).digest()


if __name__ == "__main__":
    print(json.dumps(EncryptedBackupManager().create_backup(), indent=2))
