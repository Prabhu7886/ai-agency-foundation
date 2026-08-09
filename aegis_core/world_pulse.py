"""Evidence-preserving World Pulse ingestion and source-quality labeling."""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from aegis_core.store import AegisStore


class WorldPulseService:
    """Convert approved public search results into traceable, non-overstated signals."""

    ESTABLISHED_DOMAINS = {
        "apnews.com", "bbc.com", "bloomberg.com", "cnbc.com", "economist.com", "ft.com",
        "reuters.com", "wsj.com", "nytimes.com", "theguardian.com", "npr.org",
    }

    def __init__(self, store: AegisStore) -> None:
        self.store = store

    def ingest(self, research: dict[str, Any], category: str, regions: list[str]) -> dict[str, Any]:
        accepted: list[dict[str, Any]] = []
        rejected = 0
        fingerprints: Counter[str] = Counter()
        parsed: list[dict[str, Any]] = []
        for finding in research.get("findings", []):
            source = self._source(finding)
            if not source:
                rejected += 1
                continue
            fingerprint = self._fingerprint(str(finding.get("title", "")))
            source["fingerprint"] = fingerprint
            fingerprints[fingerprint] += 1
            parsed.append({"finding": finding, "source": source})

        region = ", ".join(regions[:10]) if regions else "Global"
        for item in parsed:
            source = item["source"]
            if source["source_tier"] == "primary":
                verification = "primary_source"
                confidence = 0.78
            elif fingerprints[source["fingerprint"]] >= 2:
                verification = "corroborated"
                confidence = 0.7
            elif source["source_tier"] == "established":
                verification = "single_source"
                confidence = 0.58
            else:
                verification = "single_source"
                confidence = 0.4
            record = self.store.add_world_pulse(
                region=region,
                category=category,
                headline=str(item["finding"].get("title", ""))[:500],
                summary=str(item["finding"].get("summary", ""))[:4000],
                confidence=confidence,
                published_at=item["finding"].get("published_at"),
                source={**source, "verification_state": verification},
            )
            accepted.append(record)
        return {"accepted": len(accepted), "rejected": rejected, "signals": accepted}

    def _source(self, finding: dict[str, Any]) -> dict[str, Any] | None:
        url = str(finding.get("url", ""))
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        hostname = parsed.hostname.lower().rstrip(".")
        try:
            address = ipaddress.ip_address(hostname)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return None
        except ValueError:
            pass
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return None
        source_tier = self._tier(hostname)
        return {
            "url": url[:2000],
            "domain": hostname,
            "publisher": hostname.removeprefix("www.")[:200],
            "source_tier": source_tier,
            "published_at": finding.get("published_at"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _tier(cls, domain: str) -> str:
        clean = domain.removeprefix("www.")
        if clean.endswith(".gov") or clean.endswith(".mil") or clean in {"sec.gov", "federalreserve.gov", "imf.org", "worldbank.org", "un.org"}:
            return "primary"
        if clean in cls.ESTABLISHED_DOMAINS:
            return "established"
        return "other"

    @staticmethod
    def _fingerprint(title: str) -> str:
        words = re.findall(r"[a-z0-9]+", title.lower())
        return " ".join(words[:16])
