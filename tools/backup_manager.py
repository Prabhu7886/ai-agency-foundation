"""Encrypted, verified backups for SQLCipher and the Chroma vector store."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from databases.setup_databases import DatabaseSetup
from utils.encryption import EncryptionManager
from utils.logger import get_logger
from utils.paths import ensure_runtime_directories


class EncryptedBackupManager:
    """Produces only AES-256-GCM backup artifacts and verifies every write."""

    BACKUP_NAME = re.compile(r"^ai-agency-(\d{8}T\d{6}Z)\.zip\.enc$")
    MAX_ARCHIVE_MEMBERS = 50_000
    MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024

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

    def restore_to(self, backup_path: Path, destination: Path, timestamp: str | None = None) -> Path:
        source = Path(backup_path).resolve(strict=True)
        target = Path(destination).resolve()
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise FileExistsError("Restore destination must be an empty directory or not exist")

        backup_timestamp = self._backup_timestamp(source, timestamp)
        archive = self.encryption.decrypt_bytes(source.read_bytes(), f"backup:{backup_timestamp}")
        temporary_root = Path(tempfile.mkdtemp(prefix="aegis-restore-", dir=self.paths["runtime"]))
        staging = temporary_root / "verified"
        staging.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(archive), "r") as backup_zip:
                members = self._validated_members(backup_zip)
                for member, relative in members:
                    extracted = staging.joinpath(*relative.parts)
                    if member.is_dir():
                        extracted.mkdir(parents=True, exist_ok=True)
                        continue
                    extracted.parent.mkdir(parents=True, exist_ok=True)
                    with backup_zip.open(member, "r") as source_file, extracted.open("wb") as target_file:
                        shutil.copyfileobj(source_file, target_file)

            self._verify_restored_manifest(staging, backup_timestamp)
            if target.exists():
                target.rmdir()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(target))
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
        return target

    @classmethod
    def _backup_timestamp(cls, source: Path, supplied: str | None) -> str:
        match = cls.BACKUP_NAME.fullmatch(source.name)
        if not match:
            raise ValueError("Backup filename does not contain a valid UTC timestamp")
        inferred = match.group(1)
        if supplied is not None and supplied != inferred:
            raise ValueError("Supplied timestamp does not match the encrypted backup filename")
        return inferred

    @classmethod
    def _validated_members(cls, backup_zip: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
        members = backup_zip.infolist()
        if len(members) > cls.MAX_ARCHIVE_MEMBERS:
            raise RuntimeError("Backup archive contains too many members")

        validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        seen: set[str] = set()
        total_size = 0
        for member in members:
            name = member.filename
            relative = PurePosixPath(name)
            if (
                not name
                or "\\" in name
                or "\x00" in name
                or relative.is_absolute()
                or relative == PurePosixPath(".")
                or ".." in relative.parts
            ):
                raise RuntimeError(f"Backup archive contains an unsafe path: {name!r}")
            normalized = relative.as_posix().rstrip("/")
            if normalized in seen:
                raise RuntimeError(f"Backup archive contains a duplicate path: {normalized}")
            seen.add(normalized)

            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise RuntimeError(f"Backup archive contains a symbolic link: {name!r}")
            if member.flag_bits & 0x1:
                raise RuntimeError("Nested ZIP encryption is not supported")
            total_size += member.file_size
            if total_size > cls.MAX_ARCHIVE_BYTES:
                raise RuntimeError("Backup archive expands beyond the restore size limit")
            validated.append((member, relative))
        return validated

    @classmethod
    def _verify_restored_manifest(cls, root: Path, timestamp: str) -> None:
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("Backup manifest is missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Backup manifest is invalid") from exc
        if manifest.get("version") != 1 or manifest.get("created_at") != timestamp:
            raise RuntimeError("Backup manifest version or timestamp is invalid")
        entries = manifest.get("files")
        if not isinstance(entries, list):
            raise RuntimeError("Backup manifest file list is invalid")

        expected: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError("Backup manifest contains an invalid file entry")
            name = entry.get("path")
            if not isinstance(name, str):
                raise RuntimeError("Backup manifest contains an invalid path")
            relative = PurePosixPath(name)
            if (
                not name
                or "\\" in name
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() == "manifest.json"
            ):
                raise RuntimeError(f"Backup manifest contains an unsafe path: {name!r}")
            normalized = relative.as_posix()
            if normalized in expected:
                raise RuntimeError(f"Backup manifest contains a duplicate path: {normalized}")
            expected.add(normalized)
            restored = root.joinpath(*relative.parts)
            if not restored.is_file():
                raise RuntimeError(f"Backup file is missing after restore: {normalized}")
            if restored.stat().st_size != entry.get("size"):
                raise RuntimeError(f"Backup file size does not match its manifest: {normalized}")
            digest = hashlib.sha256(restored.read_bytes()).hexdigest()
            if digest != entry.get("sha256"):
                raise RuntimeError(f"Backup file hash does not match its manifest: {normalized}")

        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path != manifest_path
        }
        if actual != expected:
            unexpected = sorted(actual - expected)
            raise RuntimeError(f"Backup contains files not declared in its manifest: {unexpected[:10]}")

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
