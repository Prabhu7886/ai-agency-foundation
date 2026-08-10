"""Source-backed executive reports for approved opportunity research."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
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
                "retrieved_at": item.get("retrieved_at") or item.get("collected_at"),
            }
            for index, item in enumerate(signals[:15], start=1)
        ]
        source_count = len(source_rows)
        independent_domains = len({source["domain"] for source in source_rows if source["domain"] != "unknown"})
        cross_referenced = independent_domains >= 2
        evidence_state = "cross-referenced public evidence" if cross_referenced else "early single-lane public evidence"
        findings = [
            {
                "headline": source["title"],
                "evidence": source["summary"],
                "source_ids": [source["id"]],
                "confidence": source["confidence"],
                "implication": "Validate whether this public signal maps to a painful, payable customer problem before investing.",
            }
            for source in source_rows[:6]
        ]
        return {
            "title": f"Opportunity research: {query[:120]}",
            "query": query,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classification": "public-only",
            "decision_state": "research_complete_validation_required",
            "executive_summary": [
                f"Research accepted {source_count} public discovery sources across {independent_domains} independent domains.",
                f"The current evidence is {evidence_state}; {tier_counts.get('primary', 0)} primary and {tier_counts.get('established', 0)} established sources were accepted.",
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
                "Search-result summaries are discovery evidence, not independently audited claims.",
                "Freshness depends on publisher metadata and the research timestamp.",
                "Source diversity does not prove customer demand or commercial viability.",
            ],
            "source_metrics": {
                "provider_result_count": int(research.get("source_count", source_count)),
                "source_count": source_count,
                "independent_domains": independent_domains,
                "cross_referenced": cross_referenced,
                "source_tiers": dict(tier_counts),
                "verification_states": dict(verification_counts),
            },
            "sources": source_rows,
        }
