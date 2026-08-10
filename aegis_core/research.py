"""Approved public-source research for Aegis World Pulse and project analysis."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pypdf import PdfReader

from aegis_core.foundation import FoundationGuard, FoundationViolation
from utils.logger import get_logger


class WebResearchService:
    """Run a bounded public query only inside an explicitly enabled research session."""

    LIMITS = {"quick": 4, "standard": 8, "deep": 15}
    PRIMARY_LIMITS = {"quick": 2, "standard": 3, "deep": 5}
    MAX_PAGE_BYTES = 1_500_000
    MAX_REDIRECTS = 3
    METHODOLOGY_TERMS = ("methodology", "methods", "sample size", "survey design", "data source")

    def __init__(self, guard: FoundationGuard) -> None:
        self.guard = guard
        self.logger = get_logger("aegis_web_research")

    def search(
        self,
        query: str,
        depth: str,
        *,
        approved_session: bool = False,
        verify_pages: bool = True,
    ) -> dict[str, Any]:
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
        if verify_pages:
            findings = self._enrich_findings(findings)
        domains = Counter(
            (urlparse(item["url"]).hostname or "").lower().removeprefix("www.")
            for item in findings
            if item["url"]
        )
        verification_counts = Counter(str(item.get("page_verification_state", "not_requested")) for item in findings)
        date_counts = Counter(str(item.get("date_source") or "unknown") for item in findings)
        return {
            "query": clean,
            "depth": depth,
            "findings": findings,
            "source_count": len(findings),
            "independent_domains": len(domains),
            "cross_referenced": len(domains) >= 2,
            "domains": dict(domains),
            "research_lanes": lane_status,
            "page_verification": {
                "requested": verify_pages,
                "verified": sum(count for state, count in verification_counts.items() if state.startswith("verified_")),
                "states": dict(verification_counts),
                "date_sources": dict(date_counts),
                "methodology_signals": sum(1 for item in findings if item.get("methodology_terms")),
            },
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

    def _enrich_findings(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        workers = min(4, len(findings))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="aegis-source") as executor:
            enriched = list(executor.map(self._fetch_source, findings))
        return enriched

    def _fetch_source(self, finding: dict[str, Any]) -> dict[str, Any]:
        original = dict(finding)
        current = str(finding.get("url", ""))
        try:
            for _attempt in range(self.MAX_REDIRECTS + 1):
                current = self._validated_public_url(current)
                with requests.get(
                    current,
                    headers={
                        "User-Agent": "AegisResearch/0.5 (+local owner-approved verification)",
                        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.2",
                    },
                    stream=True,
                    allow_redirects=False,
                    timeout=(3, 10),
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise RuntimeError("Redirect did not include a location")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    body = self._bounded_body(response)
                    if content_type in {"text/html", "application/xhtml+xml"} or body.lstrip().startswith(b"<"):
                        metadata = self._html_metadata(body, current)
                    elif content_type == "application/pdf" or body.startswith(b"%PDF"):
                        metadata = self._pdf_metadata(body)
                    else:
                        return {
                            **original,
                            "final_url": current,
                            "content_type": content_type or "unknown",
                            "page_verification_state": "unsupported_content",
                            "fetch_error": None,
                        }
                    published = metadata.get("published_at") or original.get("published_at")
                    date_source = metadata.get("date_source") or ("search_snippet" if original.get("published_at") else None)
                    canonical = str(metadata.get("canonical_url") or current)
                    try:
                        canonical = self._validated_public_url(canonical)
                    except Exception:
                        canonical = current
                    return {
                        **original,
                        **metadata,
                        "url": self._canonical_url(canonical) or original["url"],
                        "final_url": current,
                        "published_at": published,
                        "date_source": date_source,
                        "content_type": content_type or metadata.get("content_type"),
                        "content_sha256": hashlib.sha256(body).hexdigest(),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "fetch_error": None,
                    }
            raise RuntimeError("Source exceeded the redirect limit")
        except Exception as exc:
            return {
                **original,
                "page_verification_state": "fetch_failed",
                "fetch_error": str(exc)[:300],
                "date_source": "search_snippet" if original.get("published_at") else None,
            }

    @classmethod
    def _bounded_body(cls, response: requests.Response) -> bytes:
        size_header = response.headers.get("Content-Length")
        if size_header and int(size_header) > cls.MAX_PAGE_BYTES:
            raise RuntimeError("Source exceeded the bounded download size")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            total += len(chunk)
            if total > cls.MAX_PAGE_BYTES:
                raise RuntimeError("Source exceeded the bounded download size")
            chunks.append(chunk)
        return b"".join(chunks)

    @classmethod
    def _html_metadata(cls, body: bytes, current_url: str) -> dict[str, Any]:
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = urljoin(current_url, str(canonical.get("href", ""))) if canonical else None
        description = ""
        published_at = None
        date_source = None
        for tag in soup.find_all("meta"):
            key = str(tag.get("property") or tag.get("name") or tag.get("itemprop") or "").lower()
            content = str(tag.get("content") or "").strip()
            if not content:
                continue
            if key in {"description", "og:description", "twitter:description"} and not description:
                description = content[:1500]
            if key in {
                "article:published_time", "datepublished", "date", "dc.date", "dcterms.date",
                "citation_publication_date", "citation_date", "publishdate", "pubdate",
            } and not published_at:
                published_at = content[:100]
                date_source = "page_metadata"
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.get_text(" ", strip=True))
            except Exception:
                continue
            json_date = cls._find_json_date(payload)
            if json_date and not published_at:
                published_at = json_date[:100]
                date_source = "structured_data"
        if not published_at:
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                published_at = str(time_tag.get("datetime"))[:100]
                date_source = "time_element"
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())
        methodology = [term for term in cls.METHODOLOGY_TERMS if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
        return {
            "page_title": title[:500],
            "page_description": description,
            "text_excerpt": text[:6000],
            "canonical_url": canonical_url,
            "published_at": published_at,
            "date_source": date_source,
            "methodology_terms": methodology,
            "page_verification_state": "verified_html",
            "content_type": "text/html",
        }

    @classmethod
    def _pdf_metadata(cls, body: bytes) -> dict[str, Any]:
        reader = PdfReader(BytesIO(body))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:8])
        text = " ".join(text.split())
        methodology = [term for term in cls.METHODOLOGY_TERMS if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
        return {
            "page_title": str((reader.metadata or {}).get("/Title") or "")[:500],
            "page_description": "",
            "text_excerpt": text[:6000],
            "canonical_url": None,
            "published_at": None,
            "date_source": None,
            "methodology_terms": methodology,
            "page_verification_state": "verified_pdf",
            "content_type": "application/pdf",
        }

    @classmethod
    def _find_json_date(cls, value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("datePublished", "dateCreated", "uploadDate"):
                if value.get(key):
                    return str(value[key])
            for child in value.values():
                result = cls._find_json_date(child)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = cls._find_json_date(child)
                if result:
                    return result
        return None

    @staticmethod
    def _validated_public_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise FoundationViolation("Source verification requires a public HTTPS URL")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise FoundationViolation("Local addresses are blocked from source verification")
        for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(result[4][0].split("%", 1)[0])
            if not address.is_global:
                raise FoundationViolation("Non-public addresses are blocked from source verification")
        return value
