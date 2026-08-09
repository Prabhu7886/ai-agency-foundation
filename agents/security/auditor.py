"""Fail-closed security audit engine used by Aegis and the dashboard."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from databases.setup_databases import DatabaseSetup
from utils.encryption import KeyManager
from utils.logger import get_logger
from utils.monitor import SystemMonitor
from utils.paths import agency_root, ensure_runtime_directories


@dataclass
class AuditCheck:
    name: str
    passed: bool
    severity: str
    result: str
    action: str


class SecurityAuditor:
    """Runs objective security checks and records every result."""

    SECRET_PATTERNS = {
        "OpenAI key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
        "Telegram token": re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
        "generic secret assignment": re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
    }
    PLAINTEXT_EXTENSIONS = {".txt", ".csv", ".json", ".xml", ".doc", ".docx", ".pdf", ".xlsx"}

    def __init__(self) -> None:
        self.paths = ensure_runtime_directories()
        self.database = DatabaseSetup()
        self.monitor = SystemMonitor()
        self.logger = get_logger("security_auditor")

    def run_full_audit(self) -> dict[str, Any]:
        checks: list[tuple[str, Callable[[], AuditCheck]]] = [
            ("master_key_present", self.check_master_key),
            ("sqlcipher_active", self.check_sqlcipher),
            ("secrets_protected", self.check_secret_storage),
            ("client_data_isolated", self.check_client_isolation),
            ("ollama_localhost_only", self.check_ollama_binding),
            ("ollama_outbound_firewall", self.check_ollama_firewall),
            ("outbound_connections", self.check_outbound_connections),
            ("telegram_whitelist", self.check_telegram_authentication),
            ("backup_encryption", self.check_backup_encryption),
            ("vector_volume_encryption", self.check_vector_volume_encryption),
            ("chromadb_embedded_only", self.check_chromadb_embedded_only),
            ("model_privacy", self.check_model_privacy),
        ]
        results: list[AuditCheck] = []
        for name, callback in checks:
            try:
                check = callback()
            except Exception as exc:
                check = AuditCheck(name, False, "critical", f"Check failed safely: {exc}", "Investigate before operating agents")
            results.append(check)
            self._record(check)
        critical_failures = [check for check in results if not check.passed and check.severity in {"high", "critical"}]
        passed_weight = sum(self._weight(check.severity) for check in results if check.passed)
        total_weight = sum(self._weight(check.severity) for check in results)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": not critical_failures,
            "security_score": round(100 * passed_weight / max(1, total_weight), 1),
            "checks": [asdict(check) for check in results],
            "critical_failures": [check.name for check in critical_failures],
        }
        report_path = self.paths["logs"] / "latest_security_audit.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    def check_master_key(self) -> AuditCheck:
        try:
            KeyManager().master_key()
            return AuditCheck("master_key_present", True, "critical", "Valid 256-bit master key loaded", "none")
        except Exception as exc:
            return AuditCheck("master_key_present", False, "critical", str(exc), "Initialize the local .env master key")

    def check_sqlcipher(self) -> AuditCheck:
        try:
            with self.database.connection() as connection:
                version = connection.execute("PRAGMA cipher_version").fetchone()
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
            passed = bool(version and version[0] and integrity and integrity[0] == "ok")
            return AuditCheck(
                "sqlcipher_active", passed, "critical",
                f"cipher={version[0] if version else 'missing'}, integrity={integrity[0] if integrity else 'unknown'}",
                "none" if passed else "Stop agents and repair encrypted database support",
            )
        except Exception as exc:
            return AuditCheck("sqlcipher_active", False, "critical", str(exc), "Install SQLCipher and verify the master key")

    def check_secret_storage(self) -> AuditCheck:
        root = agency_root()
        gitignore = root / ".gitignore"
        ignored = gitignore.exists() and ".env" in gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        findings = []
        excluded_parts = {".git", ".venv", "venv", "__pycache__", "vector_db", "client_data", "backups", "logs"}
        for path in root.rglob("*"):
            if not path.is_file() or path.name == ".env" or any(part in excluded_parts for part in path.parts):
                continue
            if path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for label, pattern in self.SECRET_PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{label} in {path.relative_to(root)}")
        passed = ignored and not findings
        result = "No plaintext secrets detected and .env is ignored" if passed else f"env_ignored={ignored}; findings={findings[:10]}"
        action = "none" if passed else ("Remove and rotate exposed credentials" if findings else "Add .env to .gitignore")
        return AuditCheck("secrets_protected", passed, "critical", result, action)

    def check_client_isolation(self) -> AuditCheck:
        client_root = self.paths["client_data"]
        plaintext = [
            str(path.relative_to(client_root)) for path in client_root.rglob("*")
            if path.is_file() and path.suffix.lower() in self.PLAINTEXT_EXTENSIONS and not path.name.endswith(".enc")
        ]
        root_files = [path.name for path in client_root.iterdir() if path.is_file()] if client_root.exists() else []
        passed = not plaintext and not root_files
        result = "Per-client containers contain no detected plaintext" if passed else f"plaintext={plaintext[:10]}, root_files={root_files[:10]}"
        return AuditCheck(
            "client_data_isolated", passed, "critical", result,
            "none" if passed else "Quarantine plaintext and encrypt it into a client container",
        )

    def check_ollama_binding(self) -> AuditCheck:
        result = self.monitor.verify_ollama_localhost()
        if result["reason"] == "not running":
            return AuditCheck("ollama_localhost_only", False, "medium", "Ollama is not currently listening", "Start Ollama with OLLAMA_HOST=127.0.0.1:11434")
        return AuditCheck(
            "ollama_localhost_only", bool(result["secure"]), "critical", json.dumps(result),
            "Stop Ollama immediately and bind it to 127.0.0.1" if not result["secure"] else "none",
        )

    def check_outbound_connections(self) -> AuditCheck:
        connections = self.monitor.outbound_connections()
        suspicious = [
            connection for connection in connections
            if any(term in connection.get("process", "").lower() for term in ("ollama", "aegis", "mobile_commander"))
        ]
        return AuditCheck(
            "outbound_connections", not suspicious, "high",
            f"{len(connections)} total external connections; {len(suspicious)} from protected processes",
            "Investigate and stop protected processes with external connections" if suspicious else "Review connection ledger regularly",
        )

    def check_ollama_firewall(self) -> AuditCheck:
        status = self.monitor.ollama_firewall_status()
        passed = bool(status.get("verified")) and status.get("mode") == "protected"
        return AuditCheck(
            "ollama_outbound_firewall",
            passed,
            "critical",
            json.dumps(status),
            "Exit Ollama maintenance mode and restore both outbound block rules" if not passed else "none",
        )

    def check_telegram_authentication(self) -> AuditCheck:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        ids = [value.strip() for value in raw_ids.split(",") if value.strip()]
        valid_ids = bool(ids) and all(value.isdigit() for value in ids)
        if not token:
            return AuditCheck("telegram_whitelist", True, "medium", "Telegram disabled because no bot token is configured", "none")
        passed = valid_ids
        return AuditCheck(
            "telegram_whitelist", passed, "critical",
            f"Telegram enabled with {len(ids)} numeric whitelisted user IDs" if passed else "Telegram token exists without a valid user ID whitelist",
            "Disable bot token or configure TELEGRAM_ALLOWED_USER_IDS" if not passed else "none",
        )

    def check_backup_encryption(self) -> AuditCheck:
        files = [path for path in self.paths["backups"].rglob("*") if path.is_file()]
        unencrypted = [str(path.relative_to(self.paths["backups"])) for path in files if not path.name.endswith(".enc")]
        passed = not unencrypted
        return AuditCheck(
            "backup_encryption", passed, "critical",
            "All backups encrypted" if passed else f"Unencrypted backups: {unencrypted[:10]}",
            "Remove or encrypt plaintext backups" if unencrypted else "none",
        )

    def check_vector_volume_encryption(self) -> AuditCheck:
        status = self.monitor.volume_encryption_status()
        return AuditCheck(
            "vector_volume_encryption", bool(status.get("verified")), "critical", json.dumps(status),
            "Enable BitLocker on the vector database volume" if not status.get("verified") else "none",
        )

    def check_chromadb_embedded_only(self) -> AuditCheck:
        listeners = []
        try:
            import psutil

            for connection in psutil.net_connections(kind="inet"):
                if connection.status != psutil.CONN_LISTEN or connection.laddr.port not in {8000, 8001}:
                    continue
                process_name = "unknown"
                command_line = ""
                if connection.pid:
                    try:
                        process = psutil.Process(connection.pid)
                        process_name = process.name()
                        command_line = " ".join(process.cmdline())
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if "chroma" in f"{process_name} {command_line}".lower():
                    listeners.append({"pid": connection.pid, "address": connection.laddr.ip, "port": connection.laddr.port})
        except (OSError, psutil.AccessDenied) as exc:
            return AuditCheck("chromadb_embedded_only", False, "critical", f"Could not verify listeners: {exc}", "Stop operation until listener state can be verified")
        enabled = os.getenv("CHROMA_SERVER_ENABLED", "false").lower() == "true"
        passed = not enabled and not listeners
        return AuditCheck(
            "chromadb_embedded_only", passed, "critical",
            f"server_enabled={enabled}, listeners={listeners}",
            "Stop Chroma HTTP server; use only in-process PersistentClient" if not passed else "none",
        )

    def check_model_privacy(self) -> AuditCheck:
        endpoint = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        parsed = urlparse(endpoint)
        local = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        server_binding = os.getenv("OLLAMA_HOST", "127.0.0.1:11434").strip()
        binding_local = server_binding in {"127.0.0.1:11434", "localhost:11434", "[::1]:11434"}
        offline = os.getenv("AI_AGENCY_OFFLINE_MODE", "true").lower() == "true"
        passed = local and binding_local and offline
        return AuditCheck(
            "model_privacy", passed, "critical",
            f"localhost_endpoint={local}, localhost_server_binding={binding_local}, offline_mode={offline}",
            "Set OLLAMA_HOST=127.0.0.1:11434, OLLAMA_BASE_URL=http://127.0.0.1:11434, and AI_AGENCY_OFFLINE_MODE=true" if not passed else "none",
        )

    def _record(self, check: AuditCheck) -> None:
        self.logger.security_event(check.name, check.result, check.severity, check.action)
        try:
            with self.database.connection() as connection:
                connection.execute(
                    """INSERT INTO security_audit_log
                    (timestamp, check_type, result, severity, action_taken, resolved)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (datetime.now(timezone.utc).isoformat(), check.name, check.result, check.severity, check.action, int(check.passed)),
                )
        except Exception as exc:
            self.logger.error(f"Security audit database write failed: {exc}")

    @staticmethod
    def _weight(severity: str) -> int:
        return {"info": 1, "low": 1, "medium": 2, "high": 4, "critical": 6}.get(severity, 1)


if __name__ == "__main__":
    print(json.dumps(SecurityAuditor().run_full_audit(), indent=2))
