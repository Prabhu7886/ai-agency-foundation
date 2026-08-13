"""Verified, owner-controlled Aegis Academy ingestion and completion gates."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

from aegis_core.store import AegisStore


class AcademyService:
    """Accept bounded learning material without impersonating a course platform."""

    def __init__(self, store: AegisStore) -> None:
        self.store = store

    def add_material(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        source_url = str(payload.get("source_url") or "").strip()
        if source_url:
            self._validate_public_https(source_url)
            verification = "public_source"
        elif payload.get("owner_attested"):
            verification = "owner_attested"
        else:
            raise ValueError("Material needs a permitted public source URL or explicit owner attestation")
        return self.store.add_academy_material(course_id, payload, verification)

    @staticmethod
    def _validate_public_https(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Course material source must be a public HTTPS URL")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("Course material source must not target localhost")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Course material source must not target a private address")
