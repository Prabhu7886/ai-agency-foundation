"""Recurring, evidence-gated local opportunity discovery."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from aegis_core.store import AegisStore


class OpportunityEngineService:
    """Turn stored World Pulse evidence into deduplicated validation candidates."""

    def __init__(self, store: AegisStore) -> None:
        self.store = store

    def run_cycle(self, cycle_id: str) -> dict[str, Any]:
        cycle = next((item for item in self.store.list_opportunity_cycles() if item["id"] == cycle_id), None)
        if not cycle:
            raise KeyError("Opportunity cycle not found")
        if cycle["status"] != "active":
            raise ValueError("Opportunity cycle is paused")
        signals = self._matching_signals(cycle, self.store.list_world_pulse())
        domains = sorted({str(item.get("domain") or "") for item in signals if item.get("domain")})
        fingerprint = hashlib.sha256(
            (cycle_id + "|" + "|".join(sorted(str(item.get("headline", "")) for item in signals))).encode()
        ).hexdigest()
        if len(signals) < 2 or len(domains) < 2:
            self.store.mark_opportunity_cycle_run(cycle_id, fingerprint if signals else None)
            return {
                "status": "insufficient_evidence",
                "cycle_id": cycle_id,
                "signal_count": len(signals),
                "independent_domains": len(domains),
                "stop_reason": "At least two relevant signals from two independent domains are required.",
            }
        if fingerprint == cycle.get("last_candidate_fingerprint"):
            self.store.mark_opportunity_cycle_run(cycle_id, fingerprint)
            return {"status": "duplicate", "cycle_id": cycle_id, "fingerprint": fingerprint}
        average_confidence = sum(float(item.get("confidence", 0)) for item in signals) / len(signals)
        evidence_strength = min(90.0, round(average_confidence * 100 + min(15, len(domains) * 3), 1))
        evidence = [str(item.get("source_url")) for item in signals if item.get("source_url")][:20]
        thesis = (
            f"Recurring evidence for {cycle['query']} produced {len(signals)} relevant signals across "
            f"{len(domains)} independent domains. This is a discovery candidate, not proof of demand; "
            "customer interviews, willingness-to-pay, delivery cost, and competitor validation are still required."
        )
        opportunity = self.store.create_opportunity(
            {
                "title": f"Validate: {cycle['name']}",
                "thesis": thesis,
                "allocation": cycle["allocation"],
                "evidence": evidence,
                "evidence_strength": evidence_strength,
                "revenue_potential": 50.0,
                "strategic_fit": 70.0 if cycle["allocation"] == "existing-80" else 50.0,
                "speed_to_revenue": 45.0,
                "execution_risk": 55.0,
            }
        )
        self.store.mark_opportunity_cycle_run(cycle_id, fingerprint)
        return {
            "status": "candidate_created",
            "cycle_id": cycle_id,
            "fingerprint": fingerprint,
            "opportunity": opportunity,
            "signal_count": len(signals),
            "independent_domains": len(domains),
            "required_next_gate": "owner_review_and_customer_validation",
        }

    def run_due(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for cycle in self.store.due_opportunity_cycles():
            try:
                results.append(self.run_cycle(cycle["id"]))
            except Exception as exc:
                results.append({"cycle_id": cycle["id"], "status": "failed", "error": str(exc)[:500]})
        return results

    @staticmethod
    def _matching_signals(cycle: dict[str, Any], signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        terms = {
            item for item in re.findall(r"[a-z0-9]+", f"{cycle['niche']} {cycle['query']}".lower())
            if len(item) >= 3
        }
        cutoff = datetime.now(timezone.utc) - timedelta(days=45)
        matched: list[dict[str, Any]] = []
        for item in signals:
            collected = item.get("collected_at")
            if collected:
                try:
                    observed = datetime.fromisoformat(str(collected))
                    if observed.tzinfo is None:
                        observed = observed.replace(tzinfo=timezone.utc)
                    if observed < cutoff:
                        continue
                except ValueError:
                    continue
            text = f"{item.get('category', '')} {item.get('headline', '')} {item.get('summary', '')}".lower()
            if not terms or any(term in text for term in terms):
                matched.append(item)
        return matched[:20]
