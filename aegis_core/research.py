"""Approved public-source research for Aegis World Pulse and project analysis."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urlparse

from ddgs import DDGS

from aegis_core.foundation import FoundationGuard, FoundationViolation
from utils.logger import get_logger


class WebResearchService:
    """Run a bounded public query only inside an explicitly enabled research session."""

    LIMITS = {"quick": 4, "standard": 8, "deep": 15}
    PRIMARY_LIMITS = {"quick": 2, "standard": 3, "deep": 5}

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
        seen_urls: set[str] = set()
        primary_query = (
            f"{clean} official data report statistics "
            "(site:.gov OR site:worldbank.org OR site:imf.org OR site:oecd.org OR site:un.org)"
        )
        lane_status: dict[str, dict[str, Any]] = {
            "primary": {"requested": self.PRIMARY_LIMITS[depth], "accepted": 0, "error": None},
            "discovery": {"requested": limit, "accepted": 0, "error": None},
        }
        with DDGS() as search:
            for lane, lane_query, lane_limit in (
                ("primary", primary_query, self.PRIMARY_LIMITS[depth]),
                ("discovery", clean, limit),
            ):
                try:
                    results = search.text(lane_query, max_results=lane_limit)
                    for item in results:
                        url = self._canonical_url(str(item.get("href", "")))
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        findings.append(
                            {
                                "title": str(item.get("title", ""))[:500],
                                "url": url[:2000],
                                "summary": str(item.get("body", ""))[:4000],
                                "published_at": str(item.get("date", ""))[:100] or None,
                                "search_lane": lane,
                            }
                        )
                        lane_status[lane]["accepted"] += 1
                        if len(findings) >= limit:
                            break
                except Exception as exc:
                    lane_status[lane]["error"] = str(exc)[:300]
                if len(findings) >= limit:
                    break
        if not findings:
            raise RuntimeError("The public search provider returned no usable results; no report was created.")
        domains = Counter(
            (urlparse(item["url"]).hostname or "").lower().removeprefix("www.")
            for item in findings
            if item["url"]
        )
        return {
            "query": clean,
            "depth": depth,
            "findings": findings,
            "source_count": len(findings),
            "independent_domains": len(domains),
            "cross_referenced": len(domains) >= 2,
            "domains": dict(domains),
            "research_lanes": lane_status,
            "researched_at": datetime.now(timezone.utc).isoformat(),
            "classification": "public-only",
        }

    @staticmethod
    def _canonical_url(value: str) -> str | None:
        url, _fragment = urldefrag(value.strip())
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        return url
