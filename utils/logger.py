"""Centralized, redacting application and security logging."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from utils.paths import ensure_runtime_directories


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{12,}\b"),
)


def redact(value: Any) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: match.group(0).split(match.group(1), 1)[0] + match.group(1) + "=[REDACTED]" if match.lastindex else "[REDACTED]", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class SecurityLogger:
    """Thread-safe logger with dedicated security, access, and outbound ledgers."""

    _configured: set[str] = set()
    _lock = threading.Lock()

    def __init__(self, name: str = "agency") -> None:
        paths = ensure_runtime_directories()
        self.logs_dir = paths["logs"]
        self.logger = logging.getLogger(f"ai_agency.{name}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        with self._lock:
            if self.logger.name not in self._configured:
                handler = RotatingFileHandler(
                    self.logs_dir / f"{name}.jsonl",
                    maxBytes=5_000_000,
                    backupCount=10,
                    encoding="utf-8",
                )
                handler.setFormatter(JsonFormatter())
                self.logger.addHandler(handler)
                self._configured.add(self.logger.name)

    def info(self, message: str, *args: Any) -> None:
        self.logger.info(redact(message), *args)

    def warning(self, message: str, *args: Any) -> None:
        self.logger.warning(redact(message), *args)

    def error(self, message: str, *args: Any, exc_info: bool = False) -> None:
        self.logger.error(redact(message), *args, exc_info=exc_info)

    def security_event(self, check_type: str, result: str, severity: str = "info", action: str = "none") -> None:
        self._append_ledger(
            "security_events.jsonl",
            {"check_type": check_type, "result": redact(result), "severity": severity, "action": redact(action)},
        )

    def access_event(self, resource: Path | str, operation: str, actor: str, allowed: bool) -> None:
        self._append_ledger(
            "data_access.jsonl",
            {"resource": redact(resource), "operation": operation, "actor": actor, "allowed": allowed},
        )

    def outbound_event(self, url: str, purpose: str, allowed: bool, contains_client_data: bool = False) -> None:
        parsed = urlsplit(url)
        destination = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        self._append_ledger(
            "outbound_connections.jsonl",
            {
                "destination": destination,
                "purpose": redact(purpose),
                "allowed": allowed,
                "contains_client_data": contains_client_data,
            },
        )

    def _append_ledger(self, filename: str, payload: dict[str, Any]) -> None:
        row = {"timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock:
            with (self.logs_dir / filename).open("a", encoding="utf-8") as handle:
                handle.write(line)


def get_logger(name: str) -> SecurityLogger:
    return SecurityLogger(name)


if __name__ == "__main__":
    test_logger = get_logger("logger_self_test")
    test_logger.info("Logger initialized")
    test_logger.security_event("logger_self_test", "passed")
    test_logger.access_event("self-test", "read", "logger", True)
    print(f"Logger self-test written to {test_logger.logs_dir}")
