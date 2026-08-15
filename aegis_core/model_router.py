"""Hardware-aware local Ollama model routing for Aegis conversations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests
import yaml

from aegis_core.model_gateway import LocalModelGateway
from utils.paths import agency_root


class LocalModelRouter:
    """Select one installed local model from the owner's request and unload the previous model."""

    CODE_PATTERN = re.compile(
        r"\b(python|javascript|typescript|react|fastapi|django|flask|sql|api|backend|frontend|"
        r"code|coding|debug|bug|refactor|function|class|pytest|unit test|compile|repository|"
        r"git|github|pull request|schema|database migration|security review|vulnerability)\b|"
        r"\b(build|implement|fix|edit|write)\b.{0,30}\b(app|website|api|script|code|feature|test|file)\b",
        re.IGNORECASE,
    )
    ANALYSIS_PATTERN = re.compile(
        r"\b(analyze|analysis|compare|strategy|business plan|market|opportunity|finance|financial|"
        r"economy|economic|forecast|statistics|dataset|data analysis|research|trade|gold|silver|"
        r"decision|risk|architecture|system design|reasoning|math|calculate|optimize|scenario)\b",
        re.IGNORECASE,
    )
    EXPLICIT_MODELS = {
        "deepseek": "coding",
        "qwen": "analysis",
        "llama": "general",
    }
    DEFAULT_ROUTES = {
        "general": {"model": "llama3.1:8b", "label": "Llama 3.1 8B"},
        "coding": {"model": "deepseek-coder-v2:16b", "label": "DeepSeek Coder V2 16B"},
        "analysis": {"model": "qwen2.5:14b", "label": "Qwen 2.5 14B"},
        "vision": {"model": "gemma3:4b", "label": "Gemma 3 4B Vision"},
    }

    def __init__(self, endpoint: str = "http://127.0.0.1:11434", config_path: Path | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        # Reuse gateway validation so routing can never broaden the approved Ollama endpoint.
        LocalModelGateway(self.endpoint)
        self.config_path = config_path or agency_root() / "config" / "models.yaml"
        self.routes, self.vram_limit_mb = self._load_policy()

    def select(self, prompt: str) -> dict[str, Any]:
        """Return the bounded route selected from content and actual installed models."""
        catalog, active = self._inventory()
        category, reason = self._category(prompt)
        requested = self.routes[category]
        selected = str(requested["model"])
        fallback_from = None
        if selected not in catalog:
            fallback_from = selected
            candidates = [
                str(self.routes["general"]["model"]),
                "llama3.1:8b",
                *catalog.keys(),
            ]
            selected = next((item for item in candidates if item in catalog), "")
            if not selected:
                raise RuntimeError("No approved local Ollama model is installed")
            category = next(
                (name for name, route in self.routes.items() if route["model"] == selected),
                "general",
            )
            reason = f"Requested specialist model is unavailable; safely fell back to installed {selected}"
        model_size = int(catalog.get(selected, {}).get("size", 0))
        resource_fit = "gpu" if not model_size or model_size <= self.vram_limit_mb * 1024 * 1024 else "hybrid_gpu_ram"
        return {
            "category": category,
            "model": selected,
            "label": str(self.routes.get(category, {}).get("label") or selected),
            "reason": reason,
            "resource_fit": resource_fit,
            "fallback_from": fallback_from,
            "installed": True,
            "already_loaded": selected in active,
            "one_model_at_a_time": True,
        }

    def prepare(self, route: dict[str, Any]) -> dict[str, Any]:
        """Unload every other Ollama model before the selected turn begins."""
        selected = str(route["model"])
        _catalog, active = self._inventory()
        unloaded: list[str] = []
        for model in active:
            if model == selected:
                continue
            response = requests.post(
                f"{self.endpoint}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=(3, 30),
            )
            response.raise_for_status()
            unloaded.append(model)
        return {"selected_model": selected, "unloaded_models": unloaded, "switched": bool(unloaded)}

    def select_vision(self) -> dict[str, Any]:
        """Select the dedicated image-capable model without falling back to a text-only model."""
        catalog, active = self._inventory()
        requested = self.routes["vision"]
        selected = str(requested["model"])
        if selected not in catalog:
            raise RuntimeError(
                f"Local vision model {selected} is not installed; screen analysis remains unavailable"
            )
        model_size = int(catalog[selected].get("size", 0))
        return {
            "category": "vision",
            "model": selected,
            "label": str(requested.get("label") or selected),
            "reason": "Owner requested analysis of one consented screen frame",
            "resource_fit": "gpu" if not model_size or model_size <= self.vram_limit_mb * 1024 * 1024 else "hybrid_gpu_ram",
            "fallback_from": None,
            "installed": True,
            "already_loaded": selected in active,
            "one_model_at_a_time": True,
        }

    def release(self, model: str) -> None:
        """Unload a model after an isolated media turn so scarce VRAM is returned."""
        response = requests.post(
            f"{self.endpoint}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=(3, 30),
        )
        response.raise_for_status()

    def gateway(self, route: dict[str, Any]) -> LocalModelGateway:
        return LocalModelGateway(self.endpoint, model=str(route["model"]))

    def status(self) -> dict[str, Any]:
        try:
            catalog, active = self._inventory()
            active_rows = list(active.values())
            active_model = str(active_rows[0].get("name")) if active_rows else None
            size_vram = sum(int(item.get("size_vram", 0)) for item in active_rows)
            return {
                "available": True,
                "endpoint": self.endpoint,
                "model": active_model or str(self.routes["general"]["model"]),
                "default_model": str(self.routes["general"]["model"]),
                "models": list(catalog),
                "active_models": list(active),
                "loaded": bool(active),
                "gpu_accelerated": size_vram > 0,
                "size_vram": size_vram,
                "routing_enabled": True,
                "one_model_at_a_time": True,
                "routes": {
                    category: {
                        **route,
                        "installed": str(route["model"]) in catalog,
                        "resource_fit": (
                            "gpu"
                            if int(catalog.get(str(route["model"]), {}).get("size", 0))
                            <= self.vram_limit_mb * 1024 * 1024
                            else "hybrid_gpu_ram"
                        ),
                    }
                    for category, route in self.routes.items()
                },
            }
        except Exception as exc:
            return {
                "available": False,
                "endpoint": self.endpoint,
                "model": str(self.routes["general"]["model"]),
                "routing_enabled": True,
                "error": str(exc)[:300],
            }

    def _load_policy(self) -> tuple[dict[str, dict[str, str]], int]:
        payload: dict[str, Any] = {}
        try:
            payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            payload = {}
        aegis = payload.get("models", {}).get("aegis", {}) if isinstance(payload, dict) else {}
        routing = aegis.get("routing", {}) if isinstance(aegis, dict) else {}
        configured = routing.get("routes", {}) if isinstance(routing, dict) else {}
        routes = {
            category: {
                "model": str(configured.get(category, {}).get("model") or defaults["model"]),
                "label": str(configured.get(category, {}).get("label") or defaults["label"]),
            }
            for category, defaults in self.DEFAULT_ROUTES.items()
        }
        return routes, int(aegis.get("vram_limit_mb", 7168))

    def _inventory(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        tags = requests.get(f"{self.endpoint}/api/tags", timeout=(1, 3))
        tags.raise_for_status()
        running = requests.get(f"{self.endpoint}/api/ps", timeout=(1, 3))
        running.raise_for_status()
        catalog = {
            str(item.get("name")): item
            for item in tags.json().get("models", [])
            if item.get("name")
        }
        active = {
            str(item.get("name")): item
            for item in running.json().get("models", [])
            if item.get("name")
        }
        return catalog, active

    @classmethod
    def _category(cls, prompt: str) -> tuple[str, str]:
        lowered = prompt.lower()
        for model_name, category in cls.EXPLICIT_MODELS.items():
            if re.search(rf"\b{re.escape(model_name)}\b", lowered):
                return category, f"Owner explicitly named {model_name}"
        if cls.CODE_PATTERN.search(prompt):
            return "coding", "Coding, debugging, repository, or implementation content detected"
        if cls.ANALYSIS_PATTERN.search(prompt):
            return "analysis", "Business, data, research, quantitative, or strategic analysis detected"
        return "general", "General conversation and executive assistance"
