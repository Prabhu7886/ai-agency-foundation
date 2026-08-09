"""Read and enforce the security foundation inherited by every Aegis feature."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from utils.paths import agency_root


class FoundationViolation(PermissionError):
    """Raised when a proposed Aegis operation violates the foundation policy."""


class FoundationGuard:
    """Central policy gate shared by the API, agents, skills, and plugins."""

    LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
    SENSITIVE_PATTERNS = (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b(?:password|secret|token|api[ -]?key|private key)\b", re.IGNORECASE),
        re.compile(r"\b(?:client|customer)\s*(?:name|id|data|record)\b", re.IGNORECASE),
    )

    def __init__(self) -> None:
        root = agency_root()
        self.root = root
        self.security_path = root / "config" / "security.yaml"
        self.models_path = root / "config" / "models.yaml"
        self.security = self._read_yaml(self.security_path)
        self.models = self._read_yaml(self.models_path)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise RuntimeError(f"Required foundation configuration is missing: {path}")
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise RuntimeError(f"Foundation configuration must be a mapping: {path}")
        return value

    def assert_loopback(self, host: str | None) -> None:
        clean = (host or "").split("%", 1)[0]
        if clean not in self.LOOPBACK_HOSTS:
            raise FoundationViolation("Aegis accepts local loopback clients only")

    def sanitize_public_query(self, query: str) -> str:
        clean = " ".join(str(query).replace("\x00", " ").split())
        if not clean or len(clean) > 500:
            raise FoundationViolation("Public research queries must contain 1-500 characters")
        if any(pattern.search(clean) for pattern in self.SENSITIVE_PATTERNS):
            raise FoundationViolation("Sensitive or client data is prohibited in public research queries")
        return clean

    def allowed_project_roots(self) -> list[Path]:
        configured = [item.strip() for item in os.getenv("AEGIS_PROJECT_ROOTS", "").split(";") if item.strip()]
        roots = [Path(item).expanduser().resolve() for item in configured]
        roots.extend([self.root.resolve(), (self.root / "projects").resolve()])
        unique: list[Path] = []
        for path in roots:
            if path not in unique:
                unique.append(path)
        return unique

    def validate_project_root(self, proposed: str | Path) -> Path:
        target = Path(proposed).expanduser().resolve()
        for allowed in self.allowed_project_roots():
            if target == allowed or allowed in target.parents:
                return target
        raise FoundationViolation(
            "Project path is outside registered Aegis roots. Add an explicit root to AEGIS_PROJECT_ROOTS first."
        )

    def validate_repository_url(self, repository_url: str | None) -> str | None:
        if not repository_url:
            return None
        parsed = urlparse(repository_url)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
            raise FoundationViolation("MVP repositories must use an HTTPS github.com URL")
        if parsed.username or parsed.password:
            raise FoundationViolation("Credentials must never be embedded in repository URLs")
        return repository_url.rstrip("/")

    def status(self) -> dict[str, Any]:
        defaults = self.models.get("defaults", {})
        ollama = self.security.get("ollama", {})
        vector = self.security.get("vector_store", {})
        offline = os.getenv("AI_AGENCY_OFFLINE_MODE", str(defaults.get("offline_mode", True))).lower() == "true"
        return {
            "foundation_version": self.security.get("version", 1),
            "local_only": True,
            "api_bind": "127.0.0.1",
            "offline_mode": offline,
            "external_research": "approval_required" if offline else "approved_session_only",
            "sqlcipher_required": bool(self.security.get("encryption", {}).get("sqlcipher_required", True)),
            "vector_store_mode": vector.get("mode", "embedded_only"),
            "chroma_server_enabled": bool(vector.get("server_enabled", False)),
            "ollama_endpoint": f"{ollama.get('scheme', 'http')}://{ollama.get('host', '127.0.0.1')}:{ollama.get('port', 11434)}",
            "cloud_private_data": "blocked",
            "project_roots": [str(path) for path in self.allowed_project_roots()],
        }
