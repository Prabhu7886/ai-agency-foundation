"""Install the reviewed local model-routing policy into a protected Aegis runtime."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

import yaml


POLICY = {
    "enabled": True,
    "strategy": "content_aware",
    "one_model_at_a_time": True,
    "routes": {
        "general": {"model": "llama3.1:8b", "label": "Llama 3.1 8B"},
        "coding": {"model": "deepseek-coder-v2:16b", "label": "DeepSeek Coder V2 16B"},
        "analysis": {"model": "qwen2.5:14b", "label": "Qwen 2.5 14B"},
    },
}


def install(runtime_root: Path) -> Path:
    root = runtime_root.expanduser().resolve()
    models_path = root / "config" / "models.yaml"
    if not models_path.is_file():
        raise FileNotFoundError(f"Aegis model configuration is missing: {models_path}")
    payload = yaml.safe_load(models_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Aegis model configuration must be a mapping")
    models = payload.setdefault("models", {})
    if not isinstance(models, dict):
        raise ValueError("Aegis models configuration must be a mapping")
    aegis = models.setdefault("aegis", {})
    if not isinstance(aegis, dict):
        raise ValueError("Aegis model policy must be a mapping")
    aegis["routing"] = POLICY
    backup_path = models_path.with_suffix(".yaml.pre-model-routing")
    if not backup_path.exists():
        shutil.copy2(models_path, backup_path)
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    handle, temporary_name = tempfile.mkstemp(prefix="models-", suffix=".yaml", dir=models_path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, models_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return models_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args()
    installed = install(args.runtime_root)
    print(f"Installed content-aware local model policy: {installed}")


if __name__ == "__main__":
    main()
