"""Start the local-only Aegis executive workspace."""

from __future__ import annotations

import os

import uvicorn


def configured_port() -> int:
    """Return a safe unprivileged local port."""
    raw = os.getenv("AEGIS_PORT", "8000")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit("AEGIS_PORT must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise SystemExit("AEGIS_PORT must be between 1024 and 65535")
    return port


if __name__ == "__main__":
    uvicorn.run(
        "aegis_core.api:app",
        host="127.0.0.1",
        port=configured_port(),
        reload=False,
        access_log=True,
    )
