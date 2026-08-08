"""Public-source AI intelligence and revenue opportunity analysis."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from knowledge_pipeline.pipeline import KnowledgePipeline
from utils.logger import get_logger


class AIIntelligenceBriefing:
    """Generates bounded, attributable intelligence without transmitting client data."""

    SOURCES = {
        "github": "https://github.com/trending?since=daily&spoken_language_code=en",
        "hacker_news": "https://hn.algolia.com/api/v1/search?query=AI%20agent&tags=story&hitsPerPage=15",
        "reddit": "https://www.reddit.com/r/MachineLearning/hot.json?limit=15",
        "arxiv": "https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending",
        "product_hunt": "https://www.producthunt.com/topics/artificial-intelligence",
    }

    def __init__(self, pipeline: KnowledgePipeline | None = None) -> None:
        self.pipeline = pipeline or KnowledgePipeline()
        self.logger = get_logger("intelligence_briefing")

    def scan_sources(self) -> dict[str, list[dict[str, Any]]]:
        scanners = {
            "github": self._scan_github,
            "hacker_news": self._scan_hacker_news,
            "reddit": self._scan_reddit,
            "arxiv": self._scan_arxiv,
            "product_hunt": self._scan_product_hunt,
        }
        results: dict[str, list[dict[str, Any]]] = {}
        for name, scanner in scanners.items():
            try:
                results[name] = scanner()
            except Exception as exc:
                self.logger.error(f"Intelligence source {name} failed: {exc}")
                results[name] = [{"error": str(exc), "source": self.SOURCES[name]}]
        return results

    def generate_daily_briefing(self) -> dict[str, Any]:
        sources = self.scan_sources()
        all_items = [item for items in sources.values() for item in items if "error" not in item]
        ranked = sorted(all_items, key=self._relevance_score, reverse=True)
        developments = ranked[:3]
        opportunities = self.detect_revenue_opportunities(ranked)
        threats = [item for item in ranked if self._contains_any(item, {"launch", "pricing", "enterprise", "automation", "agent platform"})][:5]
        tools = [item for item in ranked if item.get("source_type") in {"github", "product_hunt"}][:5]
        action_items = self._action_items(developments, opportunities, threats)
        briefing = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "top_developments": developments,
            "revenue_opportunities": opportunities[:5],
            "competitive_threats": threats,
            "tools_to_investigate": tools,
            "recommended_actions": action_items,
            "source_status": {name: "error" if items and "error" in items[0] else "ok" for name, items in sources.items()},
        }
        self.pipeline.add_knowledge(
            "Daily AI briefing", briefing, "public intelligence sources", "ai_industry_intel",
            "high", "internal", "api_research",
        )
        return briefing

    def detect_revenue_opportunities(self, items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        if items is None:
            content = self.pipeline._collection("ai_industry_intel").get(include=["documents"])
            items = []
            for document in content.get("documents", []):
                try:
                    decoded = json.loads(document)
                    if isinstance(decoded, dict):
                        items.append(decoded)
                except json.JSONDecodeError:
                    items.append({"title": document[:200], "summary": document})
        opportunities: list[dict[str, Any]] = []
        business_models = {
            "workflow service": {"manual", "workflow", "automate", "time-consuming"},
            "vertical agent": {"agent", "industry", "specialized", "domain"},
            "monitoring subscription": {"monitor", "alert", "security", "compliance"},
            "API wrapper": {"api", "integration", "developer", "endpoint"},
            "data product": {"dataset", "benchmark", "analytics", "intelligence"},
        }
        for item in items:
            text = json.dumps(item, ensure_ascii=False).lower()
            for model, signals in business_models.items():
                matches = sorted(signal for signal in signals if signal in text)
                if len(matches) < 2:
                    continue
                title = str(item.get("title") or item.get("name") or "Emerging opportunity")[:180]
                score = min(100, 35 + 15 * len(matches) + (10 if any(term in text for term in ("pain", "problem", "need")) else 0))
                opportunities.append(
                    {
                        "opportunity": f"{model}: {title}",
                        "business_model": model,
                        "evidence": matches,
                        "profit_potential_score": score,
                        "validation_step": "Interview five target users and test a paid concierge version before building automation.",
                        "source_url": item.get("url", ""),
                    }
                )
        deduplicated = {opportunity["opportunity"]: opportunity for opportunity in opportunities}
        ranked = sorted(deduplicated.values(), key=lambda item: item["profit_potential_score"], reverse=True)
        if ranked:
            self.pipeline.add_knowledge(
                "Revenue opportunity scan", ranked[:20], "local intelligence synthesis", "revenue_opportunities",
                "high", "confidential", "api_research",
            )
        return ranked

    def track_competitors(self) -> dict[str, Any]:
        content = self.pipeline._collection("competitor_analysis").get(include=["documents", "metadatas"])
        competitors = []
        features: Counter[str] = Counter()
        prices: list[str] = []
        for document, metadata in zip(content.get("documents", []), content.get("metadatas", [])):
            try:
                decoded = json.loads(document)
            except json.JSONDecodeError:
                decoded = {"summary": document}
            competitors.append({"topic": metadata.get("topic"), "source": metadata.get("source"), "data": decoded})
            text = json.dumps(decoded, ensure_ascii=False).lower()
            for term in ("automation", "agent", "security", "analytics", "integration", "marketplace", "collaboration"):
                if term in text:
                    features[term] += 1
            prices.extend(re.findall(r"\$\s?\d+(?:\.\d{2})?(?:/\w+)?", text))
        gaps = [term for term in ("privacy", "local-first", "encrypted", "human approval", "audit trail") if features[term] == 0]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competitors_tracked": len(competitors),
            "common_features": dict(features.most_common()),
            "pricing_signals": sorted(set(prices)),
            "potential_gaps": gaps,
            "competitors": competitors[-20:],
        }

    def feature_comparison_matrix(self) -> list[dict[str, Any]]:
        tracking = self.track_competitors()
        rows = []
        for competitor in tracking["competitors"]:
            text = json.dumps(competitor["data"], ensure_ascii=False).lower()
            rows.append(
                {
                    "competitor": competitor["topic"],
                    "automation": "automation" in text,
                    "local_first": "local" in text,
                    "encryption": "encrypt" in text,
                    "integrations": "integration" in text,
                    "pricing_disclosed": "$" in text or "pricing" in text,
                }
            )
        return rows

    def _scan_github(self) -> list[dict[str, Any]]:
        soup = BeautifulSoup(self.pipeline._safe_get(self.SOURCES["github"], "daily GitHub trending scan"), "html.parser")
        rows = []
        for article in soup.select("article.Box-row")[:15]:
            link = article.select_one("h2 a")
            if not link:
                continue
            path = str(link.get("href", ""))
            description = article.select_one("p")
            rows.append(
                {
                    "title": " ".join(link.get_text(" ", strip=True).split()),
                    "summary": description.get_text(" ", strip=True) if description else "",
                    "url": f"https://github.com{path}",
                    "source_type": "github",
                }
            )
        return rows

    def _scan_hacker_news(self) -> list[dict[str, Any]]:
        payload = json.loads(self.pipeline._safe_get(self.SOURCES["hacker_news"], "daily Hacker News scan"))
        return [
            {
                "title": hit.get("title") or "Untitled",
                "summary": hit.get("story_text") or "",
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "points": hit.get("points", 0),
                "source_type": "hacker_news",
            }
            for hit in payload.get("hits", [])
        ]

    def _scan_reddit(self) -> list[dict[str, Any]]:
        payload = json.loads(self.pipeline._safe_get(self.SOURCES["reddit"], "daily public Reddit scan"))
        rows = []
        for child in payload.get("data", {}).get("children", []):
            data = child.get("data", {})
            rows.append(
                {
                    "title": data.get("title", "Untitled"),
                    "summary": str(data.get("selftext", ""))[:1000],
                    "url": f"https://www.reddit.com{data.get('permalink', '')}",
                    "score": data.get("score", 0),
                    "source_type": "reddit",
                }
            )
        return rows

    def _scan_arxiv(self) -> list[dict[str, Any]]:
        feed = feedparser.loads(self.pipeline._safe_get(self.SOURCES["arxiv"], "daily ArXiv scan"))
        return [
            {
                "title": " ".join(entry.get("title", "Untitled").split()),
                "summary": " ".join(entry.get("summary", "").split())[:1500],
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source_type": "arxiv",
            }
            for entry in feed.entries
        ]

    def _scan_product_hunt(self) -> list[dict[str, Any]]:
        soup = BeautifulSoup(self.pipeline._safe_get(self.SOURCES["product_hunt"], "daily Product Hunt scan"), "html.parser")
        rows = []
        for link in soup.select('a[href^="/posts/"]')[:20]:
            title = " ".join(link.get_text(" ", strip=True).split())
            if title:
                rows.append({"title": title[:200], "summary": "", "url": f"https://www.producthunt.com{link.get('href')}", "source_type": "product_hunt"})
        return list({item["url"]: item for item in rows}.values())[:10]

    @staticmethod
    def _contains_any(item: dict[str, Any], terms: set[str]) -> bool:
        text = json.dumps(item, ensure_ascii=False).lower()
        return any(term in text for term in terms)

    @staticmethod
    def _relevance_score(item: dict[str, Any]) -> int:
        text = json.dumps(item, ensure_ascii=False).lower()
        terms = ("agent", "automation", "local", "security", "small business", "revenue", "marketplace", "llm", "open source")
        score = sum(10 for term in terms if term in text)
        score += min(20, int(item.get("points") or item.get("score") or 0) // 10)
        return score

    @staticmethod
    def _action_items(developments: list[dict[str, Any]], opportunities: list[dict[str, Any]], threats: list[dict[str, Any]]) -> list[str]:
        actions = []
        if developments:
            actions.append(f"Review the highest-relevance development: {developments[0].get('title', 'untitled')}.")
        if opportunities:
            actions.append(f"Validate this opportunity with five prospects: {opportunities[0]['opportunity']}.")
        if threats:
            actions.append(f"Compare Aegis against the positioning in: {threats[0].get('title', 'competitor signal')}.")
        actions.append("Record outcomes in the encrypted knowledge base; do not submit client data to external sources.")
        return actions


if __name__ == "__main__":
    briefing = AIIntelligenceBriefing()
    print(json.dumps(briefing.generate_daily_briefing(), indent=2, ensure_ascii=False))
