"""Create an encrypted backup and prove that it can be restored safely."""

from __future__ import annotations

import gc
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from databases.setup_databases import COLLECTIONS, DatabaseSetup
from tools.backup_manager import EncryptedBackupManager


def run_recovery_drill() -> dict[str, Any]:
    """Back up live stores, restore temporarily, and verify both database engines."""
    manager = EncryptedBackupManager()
    backup = manager.create_backup()
    runtime = manager.paths["runtime"].resolve()
    restored = Path(tempfile.mkdtemp(prefix="recovery-drill-", dir=runtime)).resolve()
    chroma_client = None
    try:
        manager.restore_to(Path(backup["path"]), restored)

        restored_database = DatabaseSetup(database_path=restored / "metrics.db")
        with restored_database.connection() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        if integrity != "ok":
            raise RuntimeError(f"Restored SQLCipher integrity check failed: {integrity}")

        required_tables = {
            "agent_metrics",
            "business_metrics",
            "knowledge_updates",
            "aegis_commands",
            "security_audit_log",
            "open_source_intel",
            "mobile_sessions",
        }
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            raise RuntimeError(f"Restored SQLCipher database is missing tables: {missing_tables}")

        vector_path = restored / "vector_db"
        if not vector_path.is_dir():
            raise RuntimeError("Restored Chroma vector store is missing")
        import chromadb
        from chromadb.config import Settings

        chroma_client = chromadb.PersistentClient(
            path=str(vector_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=False, is_persistent=True),
        )
        collection_names = sorted(collection.name for collection in chroma_client.list_collections())
        missing_collections = sorted(set(COLLECTIONS) - set(collection_names))
        if missing_collections:
            raise RuntimeError(f"Restored Chroma store is missing collections: {missing_collections}")

        return {
            "verified": True,
            "backup_path": backup["path"],
            "manifest_files": len(backup["manifest"]["files"]),
            "sqlcipher_integrity": integrity,
            "sqlcipher_tables": len(required_tables),
            "chroma_collections": len(collection_names),
            "temporary_restore_removed": True,
        }
    finally:
        if chroma_client is not None:
            chroma_client.close()
        chroma_client = None
        gc.collect()
        if restored.parent != runtime or not restored.name.startswith("recovery-drill-"):
            raise RuntimeError("Refusing to clean an unexpected recovery-drill path")
        if restored.exists():
            shutil.rmtree(restored)


if __name__ == "__main__":
    print(json.dumps(run_recovery_drill(), indent=2))
