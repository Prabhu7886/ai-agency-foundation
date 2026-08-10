"""Approved public-source research for Aegis World Pulse and project analysis."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ddgs import DDGS

from aegis_core.foundation import FoundationGuard, FoundationViolation
from utils.logger import get_logger


class WebResearchService:
    """Run a bounded public query only inside an explicitly enabled research session."""

    LIMITS = {"quick": 4, "standard": 8, "deep": 15}

    def __init__(self, guard: FoundationGuard) -> None:
        self.guard = guard
        self.logger = get_logger("aegis_web_research")

    def search(self, query: str, depth: str, *, approved_session: bool = False) -> dict[str, Any]:
        clean = self.guard.sanitize_public_query(query)
        offline = os.getenv("AI_AGENCY_OFFLINE_MODE", "true").lower() == "true"
        approved_exception = approved_session and self.guard.approved_public_research_enabled()
        if offline and not approved_exception:
            raise FoundationViolation(
                "Foundation offline mode is active and no approved public-research session was supplied."
            )
        limit = self.LIMITS[depth]
        self.logger.outbound_event("https://duckduckgo.com", f"approved public research: {clean}", True, False)
        findings: list[dict[str, Any]] = []
        with DDGS() as search:
            for item in search.text(clean, max_results=limit):
                findings.append(
                    {
                        "title": str(item.get("title", ""))[:500],
                        "url": str(item.get("href", ""))[:2000],
                        "summary": str(item.get("body", ""))[:4000],
                        "published_at": str(item.get("date", ""))[:100] or None,
                    }
                )
        if not findings:
            raise RuntimeError("The public search provider returned no usable results; no report was created.")
        domains = Counter(urlparse(item["url"]).netloc for item in findings if item["url"])
        return {
            "query": clean,
            "depth": depth,
            "findings": findings,
            "source_count": len(findings),
            "independent_domains": len(domains),
            "cross_referenced": len(domains) >= 2,
            "domains": dict(domains),
            "researched_at": datetime.now(timezone.utc).isoformat(),
            "classification": "public-only",
        }
