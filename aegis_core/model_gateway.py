"""Local-first model gateway used by the Aegis workspace."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import requests

from aegis_core.foundation import FoundationViolation
from utils.paths import agency_root


AEGIS_EXECUTIVE_PROMPT = """
You are Aegis, the owner's local executive AI and chief of staff. Follow the Truth Standard:
separate verified facts, assumptions, estimates, and unknowns. Be ambitious, direct, practical,
and constructive. No empty hype and no defeatist answers. When a goal is difficult, identify the
constraint, the safest workable path, the cheapest useful test, and the evidence required to proceed.
Never claim an action ran, a security control passed, or current data was verified without evidence.
Never request that private client data be sent to a cloud service. Consequential actions require the
owner's approval.
""".strip()


class LocalModelGateway:
    """Call only the approved localhost Ollama endpoint and fail closed otherwise."""

    def __init__(self, endpoint: str = "http://127.0.0.1:11434", model: str | None = None) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise FoundationViolation("Local model endpoint must use HTTP on loopback")
        if parsed.port not in {None, 11434}:
            raise FoundationViolation("Local model endpoint must use the approved Ollama port 11434")
        self.endpoint = endpoint.rstrip("/")
        self.model = model or self._configured_model()

    @staticmethod
    def _configured_model() -> str:
        import yaml

        config_path = agency_root() / "config" / "models.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return str(config.get("models", {}).get("aegis", {}).get("primary", "llama3.1:8b"))

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=(1, 2))
            response.raise_for_status()
            models = [item.get("name") for item in response.json().get("models", [])]
            return {"available": True, "endpoint": self.endpoint, "model": self.model, "models": models}
        except Exception as exc:
            return {"available": False, "endpoint": self.endpoint, "model": self.model, "error": str(exc)[:300]}

    def chat(self, message: str, project_context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = json.dumps(project_context or {}, ensure_ascii=False, default=str)[:8000]
        prompt = f"{AEGIS_EXECUTIVE_PROMPT}\n\nPROJECT CONTEXT:\n{context}\n\nOWNER:\n{message.strip()}"
        payload = self.generate(prompt)
        answer = str(payload.get("response", "")).strip()
        if not answer:
            raise RuntimeError("Ollama returned an empty response")
        return {
            "answer": answer[:100_000],
            "model": self.model,
            "provider": "ollama-local",
            "verified_local": True,
            "tokens": int(payload.get("eval_count", 0)),
        }

    def generate(self, prompt: str, *, json_mode: bool = False, timeout_seconds: int = 180) -> dict[str, Any]:
        """Generate locally, optionally requiring Ollama's JSON output mode."""
        body: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False, "keep_alive": -1}
        if json_mode:
            body["format"] = "json"
        response = requests.post(
            f"{self.endpoint}/api/generate",
            json=body,
            timeout=(3, timeout_seconds),
        )
        response.raise_for_status()
        return response.json()
