"""Source-backed executive reports for approved opportunity research."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


class OpportunityReportService:
    """Turn accepted public signals into a bounded, decision-ready report."""

    def build(self, query: str, research: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
        if not signals:
            raise ValueError("An opportunity report requires at least one accepted public source")
        tier_counts = Counter(str(item.get("source_tier", "other")) for item in signals)
        verification_counts = Counter(str(item.get("verification_state", "single_source")) for item in signals)
        source_rows = [
            {
                "id": f"S{index}",
                "title": str(item.get("headline", "Untitled source"))[:500],
                "summary": str(item.get("summary", ""))[:1500],
                "url": str(item.get("source_url", ""))[:2000],
                "domain": str(item.get("domain", "unknown"))[:200],
                "source_tier": str(item.get("source_tier", "other")),
                "verification_state": str(item.get("verification_state", "single_source")),
                "confidence": round(float(item.get("confidence", 0.0)), 2),
                "published_at": item.get("published_at"),
                "freshness_state": self._freshness_state(item.get("published_at")),
                "retrieved_at": item.get("retrieved_at") or item.get("collected_at"),
                "page_verification_state": str(item.get("page_verification_state", "not_requested")),
                "date_source": item.get("date_source"),
                "methodology_terms": list(item.get("methodology_terms") or [])[:10],
                "content_sha256": item.get("content_sha256"),
                "page_title": item.get("page_title"),
            }
            for index, item in enumerate(signals[:15], start=1)
        ]
        source_count = len(source_rows)
        independent_domains = len({source["domain"] for source in source_rows if source["domain"] != "unknown"})
        cross_referenced = independent_domains >= 2
        evidence_state = "cross-referenced public evidence" if cross_referenced else "early single-lane public evidence"
        freshness_counts = Counter(str(source["freshness_state"]) for source in source_rows)
        dated_source_count = source_count - freshness_counts.get("unknown", 0)
        high_trust_source_count = tier_counts.get("primary", 0) + tier_counts.get("established", 0)
        page_counts = Counter(str(source["page_verification_state"]) for source in source_rows)
        verified_page_count = sum(count for state, count in page_counts.items() if state.startswith("verified_"))
        verified_primary_count = sum(
            1
            for source in source_rows
            if source["source_tier"] == "primary" and source["page_verification_state"].startswith("verified_")
        )
        verified_date_count = sum(
            1 for source in source_rows if source.get("date_source") in {"page_metadata", "structured_data", "time_element"}
        )
        methodology_source_count = sum(1 for source in source_rows if source["methodology_terms"])
        if verified_primary_count >= 2 and verified_date_count >= 1 and methodology_source_count >= 1:
            quality_gate = "supported_discovery"
        elif high_trust_source_count:
            quality_gate = "mixed_quality_discovery"
        else:
            quality_gate = "discovery_only"
        primary_lane = research.get("research_lanes", {}).get("primary", {})
        findings = [
            {
                "headline": source["title"],
                "evidence": source["summary"],
                "source_ids": [source["id"]],
                "confidence": source["confidence"],
                "implication": (
                    "The full source page was fetched and exposed methodology signals; review the actual method and definitions before treating the claim as decision-grade."
                    if source["source_tier"] == "primary" and source["page_verification_state"].startswith("verified_") and source["methodology_terms"]
                    else "Review the linked primary source and its methodology before treating the excerpt as decision-grade."
                    if source["source_tier"] == "primary"
                    else "Validate whether this public signal maps to a painful, payable customer problem before investing."
                ),
            }
            for source in source_rows[:6]
        ]
        return {
            "title": f"Opportunity research: {query[:120]}",
            "query": query,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classification": "public-only",
            "decision_state": "research_complete_validation_required",
            "quality_gate": quality_gate,
            "executive_summary": [
                f"Research accepted {source_count} public discovery sources across {independent_domains} independent domains.",
                f"The current evidence is {evidence_state}; {tier_counts.get('primary', 0)} primary and {tier_counts.get('established', 0)} established sources were accepted.",
                f"Publication-date coverage is {dated_source_count}/{source_count}; {freshness_counts.get('current', 0)} current, {freshness_counts.get('recent', 0)} recent, {freshness_counts.get('stale', 0)} stale, {freshness_counts.get('future_dated', 0)} future-dated, and {freshness_counts.get('unknown', 0)} unknown-date sources.",
                f"Full-page verification succeeded for {verified_page_count}/{source_count} sources; {verified_date_count} sources exposed page date metadata and {methodology_source_count} sources exposed methodology signals.",
                f"Verification mix: {verification_counts.get('primary_source', 0)} primary-source, {verification_counts.get('corroborated', 0)} corroborated, and {verification_counts.get('single_source', 0)} single-source signals.",
                "Revenue, willingness to pay, market size, and execution cost remain unverified and must not be treated as facts.",
            ],
            "key_findings": findings,
            "recommended_next_steps": [
                "Define the narrowest customer segment and the expensive problem this opportunity would solve.",
                "Run at least five evidence-recorded customer interviews before assigning a revenue score.",
                "Draft one paid-pilot offer, success metric, maximum test budget, and explicit stop criteria.",
                "Score the opportunity only after customer, pricing, delivery-cost, and competitive evidence is attached.",
            ],
            "further_questions": [
                "Who experiences this problem frequently enough to pay for a solution?",
                "What existing workaround or competitor already receives the budget?",
                "Can a useful paid pilot be delivered with current agents and skills?",
                "Which new evidence would materially increase or decrease confidence?",
            ],
            "caveats": [
                "Search-result summaries remain discovery evidence; a successful full-page fetch verifies source identity and metadata, not the truth of every claim.",
                "The official-source search lane is a discovery aid; the accepted domain tier, publication date, and linked methodology determine trust.",
                "Missing or unparsable publication dates are labeled unknown rather than assumed current.",
                "Source diversity does not prove customer demand or commercial viability.",
            ],
            "source_metrics": {
                "provider_result_count": int(research.get("source_count", source_count)),
                "source_count": source_count,
                "independent_domains": independent_domains,
                "cross_referenced": cross_referenced,
                "quality_gate": quality_gate,
                "high_trust_source_count": high_trust_source_count,
                "dated_source_count": dated_source_count,
                "primary_lane_candidates": int(primary_lane.get("accepted", 0)),
                "source_tiers": dict(tier_counts),
                "verification_states": dict(verification_counts),
                "freshness_states": dict(freshness_counts),
                "page_verification_states": dict(page_counts),
                "verified_page_count": verified_page_count,
                "verified_primary_count": verified_primary_count,
                "verified_date_count": verified_date_count,
                "methodology_source_count": methodology_source_count,
            },
            "sources": source_rows,
        }

    @staticmethod
    def _freshness_state(value: Any) -> str:
        if not value:
            return "unknown"
        text = str(value).strip()
        parsed: datetime | None = None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                for pattern in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
                    try:
                        parsed = datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
        if not parsed:
            return "unknown"
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days
        if age_days < -2:
            return "future_dated"
        if age_days <= 120:
            return "current"
        if age_days <= 365:
            return "recent"
        return "stale"
