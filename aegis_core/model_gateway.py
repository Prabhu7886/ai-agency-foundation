"""Local-first model gateway used by the Aegis workspace."""

from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.parse import urlparse

import requests

from aegis_core.foundation import FoundationViolation
from utils.paths import agency_root


AEGIS_EXECUTIVE_PROMPT = """
You are Aegis, the owner's local executive AI and chief of staff. Follow the Truth Standard:
separate verified facts, assumptions, estimates, and unknowns. Be ambitious, direct, practical,
and constructive. Write with the professional, friendly, natural quality of an excellent human
collaborator: answer first, cover the topic, explain unfamiliar ideas plainly, and use structure only
when it improves clarity. No empty hype and no defeatist answers. When a goal is difficult, identify the
constraint, the safest workable path, the cheapest useful test, and the evidence required to proceed.
Never claim an action ran, a security control passed, or current data was verified without evidence.
For time-sensitive questions, state the date of the newest supplied evidence and never present model
memory as "latest". If current evidence is absent, say that fresh approved research is needed and offer
the exact public query to run. Cite source titles or URLs when verified research context supplies them.
Never classify a risk as low merely because measurements are missing. State well-established qualitative
risk direction separately from unknown likelihood, magnitude, or current-data estimates.
Never request that private client data be sent to a cloud service. Consequential actions require the
owner's approval. Answer the owner's actual question first. Follow requested length and format exactly.
Do not narrate the prompt compiler, invent extra steps, or ask for clarification when the supplied
verified context already resolves the question. When the owner requests one sentence, return only
that sentence with no heading, preamble, bullets, or follow-up; include every requested fact in the
same sentence by joining clauses with "and" or a semicolon.
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
            active: dict[str, Any] = {}
            try:
                running = requests.get(f"{self.endpoint}/api/ps", timeout=(1, 2))
                running.raise_for_status()
                active = next(
                    (item for item in running.json().get("models", []) if item.get("name") == self.model),
                    {},
                )
            except Exception:
                active = {}
            size_vram = int(active.get("size_vram", 0))
            return {
                "available": True,
                "endpoint": self.endpoint,
                "model": self.model,
                "models": models,
                "loaded": bool(active),
                "gpu_accelerated": size_vram > 0,
                "size_vram": size_vram,
            }
        except Exception as exc:
            return {"available": False, "endpoint": self.endpoint, "model": self.model, "error": str(exc)[:300]}

    def chat(self, message: str, project_context: dict[str, Any] | None = None) -> dict[str, Any]:
        prompt = self._executive_prompt(message, project_context)
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

    def stream_chat(
        self,
        message: str,
        project_context: dict[str, Any] | None = None,
        *,
        timeout_seconds: int = 180,
    ) -> Iterator[dict[str, Any]]:
        """Yield local Ollama tokens and a final usage event without buffering the answer."""
        lowered = message.lower()
        concise = "short sentence" in lowered or "one sentence" in lowered or "brief answer" in lowered
        options: dict[str, Any] = {"num_predict": 64 if concise else 512, "temperature": 0.2, "num_ctx": 4096}
        if concise:
            options["stop"] = ["\n", ". "]
        body = {
            "model": self.model,
            "prompt": self._executive_prompt(message, project_context),
            "stream": True,
            "keep_alive": -1,
            "options": options,
        }
        with requests.post(
            f"{self.endpoint}/api/generate",
            json=body,
            stream=True,
            timeout=(3, timeout_seconds),
        ) as response:
            response.raise_for_status()
            saw_done = False
            emitted_parts: list[str] = []
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                payload = json.loads(raw_line.decode("utf-8"))
                if payload.get("error"):
                    raise RuntimeError(str(payload["error"])[:500])
                token = str(payload.get("response", ""))
                if token:
                    emitted_parts.append(token)
                    yield {"type": "token", "content": token}
                if payload.get("done"):
                    saw_done = True
                    final_text = "".join(emitted_parts).rstrip()
                    if concise and final_text and not final_text.endswith((".", "!", "?")):
                        yield {"type": "token", "content": "."}
                    yield {
                        "type": "done",
                        "tokens": int(payload.get("eval_count", 0)),
                        "prompt_tokens": int(payload.get("prompt_eval_count", 0)),
                    }
            if not saw_done:
                raise RuntimeError("Ollama stream ended before the completion event")

    @staticmethod
    def _executive_prompt(message: str, project_context: dict[str, Any] | None) -> str:
        context = json.dumps(project_context or {}, ensure_ascii=False, default=str)[:60_000]
        return f"{AEGIS_EXECUTIVE_PROMPT}\n\nPROJECT CONTEXT:\n{context}\n\nOWNER:\n{message.strip()}"

    def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        timeout_seconds: int = 180,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate locally, optionally requiring Ollama's JSON output mode."""
        body: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False, "keep_alive": -1}
        if json_mode:
            body["format"] = "json"
        if options:
            body["options"] = options
        response = requests.post(
            f"{self.endpoint}/api/generate",
            json=body,
            timeout=(3, timeout_seconds),
        )
        response.raise_for_status()
        return response.json()
