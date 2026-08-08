"""Security-aware long-term memory, learning, and open-source analysis."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from git import Repo

from databases.setup_databases import COLLECTIONS, DatabaseSetup
from utils.encryption import EncryptionManager
from utils.logger import get_logger
from utils.monitor import SystemMonitor
from utils.paths import ensure_runtime_directories


SOURCE_CONFIDENCE = {
    "course_material": 0.90,
    "api_research": 0.90,
    "open_source_verified": 0.90,
    "web_search": 0.65,
    "github_analysis": 0.70,
    "user_input": 0.95,
    "conversation": 0.80,
}
SECURITY_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
IMPORTANCE_WEIGHT = {"low": 0.90, "medium": 1.0, "high": 1.05, "critical": 1.10}
VOLATILE_TERMS = {"price", "pricing", "trend", "competitor", "policy", "algorithm", "api", "market", "news", "revenue"}


class HashEmbeddingFunction:
    """Deterministic local embedding that never downloads a model or emits telemetry."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # Chroma's required signature
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9_]{2,}", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * (1.0 + min(len(token), 12) / 12.0)
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]


class KnowledgePipeline:
    """Manages protected memory and strictly controlled public-source learning."""

    def __init__(self) -> None:
        paths = ensure_runtime_directories()
        self.paths = paths
        self.index_path = paths["knowledge"] / "memory_index.json"
        self.encryption = EncryptionManager()
        self.database = DatabaseSetup()
        self.logger = get_logger("knowledge_pipeline")
        self.embedding = HashEmbeddingFunction()
        self._chroma_client: Any | None = None
        self._vector_access_error: str | None = None

    def _client(self) -> Any:
        blocked_reason = getattr(self, "_vector_access_error", None)
        if blocked_reason:
            raise RuntimeError(blocked_reason)
        if self._chroma_client is None:
            require_volume = os.getenv("AI_AGENCY_VECTOR_DB_ENCRYPTED_VOLUME_REQUIRED", "true").lower() == "true"
            volume_status = SystemMonitor().volume_encryption_status()
            if require_volume and not volume_status.get("verified"):
                self._vector_access_error = (
                    "Knowledge access blocked because vector-store volume encryption could not be verified"
                )
                raise RuntimeError(self._vector_access_error)
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError as exc:
                raise RuntimeError("chromadb is required for knowledge operations") from exc
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.paths["vector_db"]),
                settings=Settings(anonymized_telemetry=False, allow_reset=False, is_persistent=True),
            )
        return self._chroma_client

    def _collection(self, name: str) -> Any:
        if name not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {name}")
        return self._client().get_or_create_collection(
            name=name,
            embedding_function=self.embedding,
            metadata={"hnsw:space": "cosine", "security": "encrypted-volume-required"},
        )

    def add_knowledge(
        self,
        topic: str,
        data: str | dict[str, Any] | list[Any],
        source: str,
        collection_name: str,
        importance: str = "medium",
        security_classification: str = "internal",
        source_type: str = "user_input",
    ) -> dict[str, Any]:
        if security_classification not in SECURITY_RANK:
            raise ValueError(f"Invalid security classification: {security_classification}")
        if importance not in IMPORTANCE_WEIGHT:
            raise ValueError(f"Invalid importance: {importance}")
        topic_clean = self._bounded_text(topic, 300)
        source_clean = self._bounded_text(source, 1000)
        document = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, sort_keys=True)
        if not document.strip():
            raise ValueError("Knowledge data cannot be empty")
        now = datetime.now(timezone.utc)
        base_confidence = SOURCE_CONFIDENCE.get(source_type, 0.50)
        confidence = min(1.0, round(base_confidence * IMPORTANCE_WEIGHT[importance], 3))
        verified = source_type in {"course_material", "api_research", "open_source_verified", "user_input"}
        entry_id = str(uuid.uuid4())
        update_frequency = self._suggest_update_frequency(topic_clean)
        metadata = {
            "topic": topic_clean,
            "source": source_clean,
            "source_type": source_type,
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
            "confidence": confidence,
            "importance": importance,
            "security_level": security_classification,
            "security_rank": SECURITY_RANK[security_classification],
            "source_verified": bool(verified),
            "update_frequency_days": update_frequency,
            "monetization_potential": self._monetization_potential(topic_clean, document),
        }
        self._collection(collection_name).add(ids=[entry_id], documents=[document], metadatas=[metadata])
        self._record_index(entry_id, collection_name, metadata)
        try:
            with self.database.connection() as connection:
                connection.execute(
                    """INSERT INTO knowledge_updates
                    (topic, source, date_collected, last_updated, confidence_score, needs_update, source_type, security_level)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
                    (topic_clean, source_clean, now.isoformat(), now.isoformat(), confidence, source_type, security_classification),
                )
        except Exception as exc:
            self.logger.error(f"Knowledge metrics write failed: {exc}")
        self.logger.access_event(f"collection:{collection_name}/{entry_id}", "write", "knowledge_pipeline", True)
        return {"id": entry_id, "collection": collection_name, **metadata}

    def retrieve_knowledge(
        self,
        query: str,
        collection_name: str,
        top_k: int = 5,
        security_clearance: str = "standard",
    ) -> list[dict[str, Any]]:
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        clearance_rank = self._clearance_rank(security_clearance)
        result = self._collection(collection_name).query(
            query_texts=[self._bounded_text(query, 4000)],
            n_results=top_k,
            where={"security_rank": {"$lte": clearance_rank}},
            include=["documents", "metadatas", "distances"],
        )
        rows: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for entry_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            semantic_score = max(0.0, min(1.0, 1.0 - float(distance)))
            rows.append(
                {
                    "id": entry_id,
                    "data": document,
                    "metadata": metadata,
                    "semantic_score": round(semantic_score, 4),
                    "confidence_score": float(metadata.get("confidence", 0.0)),
                }
            )
            self.logger.access_event(f"collection:{collection_name}/{entry_id}", "read", "knowledge_pipeline", True)
        return rows

    def consolidate_research(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for collection_name in COLLECTIONS:
            collection = self._collection(collection_name)
            content = collection.get(include=["documents", "metadatas"])
            for entry_id, document, metadata in zip(content.get("ids", []), content.get("documents", []), content.get("metadatas", [])):
                if str(metadata.get("created_at", ""))[:10] != today:
                    continue
                key = f"{collection_name}:{str(metadata.get('topic', '')).lower()}"
                grouped.setdefault(key, []).append({"id": entry_id, "document": document, "metadata": metadata})
        merged = 0
        contradictions: list[dict[str, Any]] = []
        suspicious: list[dict[str, Any]] = []
        for key, entries in grouped.items():
            if len(entries) < 2:
                continue
            comparison = self._compare_texts(entries[0]["document"], entries[1]["document"])
            if comparison["contradiction_terms"]:
                contradictions.append({"topic": key, **comparison})
            else:
                merged += 1
            for entry in entries:
                if self._looks_suspicious(entry["document"]):
                    suspicious.append({"topic": key, "id": entry["id"], "reason": "prompt-injection-like content"})
        result = {
            "date": today,
            "topics_reviewed": len(grouped),
            "complementary_groups": merged,
            "contradictions": contradictions,
            "suspicious_findings": suspicious,
        }
        self.logger.security_event("research_consolidation", json.dumps(result, ensure_ascii=False), "warning" if suspicious else "info")
        return result

    def check_staleness(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        index = self._load_index()
        stale: list[dict[str, Any]] = []
        for entry_id, entry in index.get("entries", {}).items():
            updated = datetime.fromisoformat(entry["last_updated"])
            frequency = int(entry["update_frequency"])
            due = updated + timedelta(days=frequency)
            if due <= now:
                stale.append({"id": entry_id, "topic": entry["topic"], "collection": entry["collection"], "due_at": due.isoformat()})
        return sorted(stale, key=lambda item: item["due_at"])

    def cross_reference(self, source1: str, source2: str) -> dict[str, Any]:
        first = self._documents_by_source(source1)
        second = self._documents_by_source(source2)
        if not first or not second:
            return {"source1": source1, "source2": source2, "status": "insufficient_evidence", "contradictions": [], "complementary": []}
        comparisons = [self._compare_texts(left, right) for left in first for right in second]
        contradictions = [item for item in comparisons if item["contradiction_terms"]]
        complementary = [item for item in comparisons if item["overlap_score"] >= 0.15 and not item["contradiction_terms"]]
        return {
            "source1": source1,
            "source2": source2,
            "status": "contradiction_detected" if contradictions else "compatible",
            "contradictions": contradictions,
            "complementary": complementary,
        }

    def export_agent_brain(self, collection_name: str, encrypted: bool = True) -> Path:
        collection = self._collection(collection_name)
        content = collection.get(include=["documents", "metadatas"])
        export = {
            "collection": collection_name,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "entries": [
                {"id": entry_id, "document": document, "metadata": metadata}
                for entry_id, document, metadata in zip(content.get("ids", []), content.get("documents", []), content.get("metadatas", []))
            ],
        }
        destination = self.paths["exports"] / f"{collection_name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        if encrypted:
            destination = destination.with_suffix(".json.enc")
            destination.write_bytes(self.encryption.encrypt_json(export, f"brain-export:{collection_name}"))
        else:
            if any(entry["metadata"].get("security_rank", 1) > 0 for entry in export["entries"]):
                raise PermissionError("Unencrypted exports are permitted only for entirely public collections")
            destination.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.access_event(destination, "write", "knowledge_pipeline", True)
        return destination

    def analyze_github_repo(self, repo_url: str) -> dict[str, Any]:
        parsed = self._validate_external_url(repo_url, required_host="github.com")
        self._require_online("GitHub repository analysis")
        self.logger.outbound_event(repo_url, "analyze public GitHub repository", True, False)
        temp_dir = Path(tempfile.mkdtemp(prefix="aegis-repo-"))
        try:
            repository = Repo.clone_from(repo_url, temp_dir, depth=1, single_branch=True)
            files = [path for path in temp_dir.rglob("*") if path.is_file() and ".git" not in path.parts]
            languages = Counter(path.suffix.lower() or "[no extension]" for path in files)
            manifest_names = {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "docker-compose.yml"}
            manifests = sorted(str(path.relative_to(temp_dir)) for path in files if path.name in manifest_names)
            architecture = self._architecture_summary(files, temp_dir)
            quality = self._code_quality_score(files, temp_dir)
            result = {
                "repo_name": parsed.path.strip("/").removesuffix(".git"),
                "url": repo_url,
                "commit": repository.head.commit.hexsha,
                "file_count": len(files),
                "languages": dict(languages.most_common(12)),
                "manifests": manifests,
                "architecture_patterns": architecture,
                "code_quality_score": quality,
                "implementation_ideas": self._implementation_ideas(architecture, manifests),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.add_knowledge(
                result["repo_name"], result, repo_url, "open_source_learnings", "high", "internal", "open_source_verified"
            )
            try:
                with self.database.connection() as connection:
                    connection.execute(
                        """INSERT INTO open_source_intel
                        (repo_name, url, category, key_features, analyzed_date, implementation_ideas, code_quality_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            result["repo_name"], repo_url, "github", json.dumps(architecture), result["analyzed_at"],
                            json.dumps(result["implementation_ideas"]), quality,
                        ),
                    )
            except Exception as exc:
                self.logger.error(f"Open-source metrics write failed: {exc}")
            return result
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def analyze_ai_tool(self, website_url: str) -> dict[str, Any]:
        self._validate_external_url(website_url)
        html = self._safe_get(website_url, "analyze public AI tool landing page")
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else urlparse(website_url).netloc
        headings = [node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2", "h3"])[:30]]
        calls_to_action = [node.get_text(" ", strip=True) for node in soup.find_all(["a", "button"]) if node.get_text(" ", strip=True)][:40]
        pricing_terms = [text for text in soup.stripped_strings if any(term in text.lower() for term in ("$", "month", "pricing", "free trial"))][:30]
        result = {
            "url": website_url,
            "title": title,
            "positioning": headings[:10],
            "ux_patterns": self._infer_ux_patterns(headings, calls_to_action),
            "calls_to_action": calls_to_action[:15],
            "pricing_signals": pricing_terms,
            "implementation_hypotheses": self._implementation_ideas(headings, []),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.add_knowledge(title, result, website_url, "competitor_analysis", "medium", "internal", "web_search")
        return result

    def monitor_github_trending(self, topic: str = "ai-agent") -> list[dict[str, Any]]:
        query = re.sub(r"[^A-Za-z0-9-]+", "-", topic).strip("-") or "ai-agent"
        url = f"https://github.com/topics/{query}"
        html = self._safe_get(url, "monitor public GitHub topic")
        soup = BeautifulSoup(html, "html.parser")
        repositories = []
        for heading in soup.select("h3 a")[:20]:
            href = str(heading.get("href", ""))
            if re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", href):
                repositories.append({"name": href.strip("/"), "url": f"https://github.com{href}"})
        unique = list({item["url"]: item for item in repositories}.values())[:10]
        self.add_knowledge(
            f"GitHub topic {topic}", unique, url, "ai_industry_intel", "medium", "public", "github_analysis"
        )
        return unique

    def extract_implementation_patterns(self) -> dict[str, Any]:
        content = self._collection("open_source_learnings").get(include=["documents", "metadatas"])
        tokens: Counter[str] = Counter()
        architecture_terms = {
            "event-driven", "queue", "plugin", "registry", "dependency injection", "retrieval", "vector", "scheduler",
            "api", "worker", "agent", "orchestrator", "sandbox", "encryption", "audit",
        }
        for document in content.get("documents", []):
            lower = document.lower()
            for term in architecture_terms:
                if term in lower:
                    tokens[term] += 1
        result = {
            "repositories_analyzed": len(content.get("ids", [])),
            "common_patterns": [{"pattern": key, "occurrences": value} for key, value in tokens.most_common()],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.add_knowledge("Cross-repository implementation patterns", result, "local synthesis", "open_source_learnings", "high", "internal", "open_source_verified")
        return result

    def daily_ai_briefing(self) -> dict[str, Any]:
        from tools.intelligence_briefing import AIIntelligenceBriefing

        return AIIntelligenceBriefing(self).generate_daily_briefing()

    def track_competitor_movements(self) -> dict[str, Any]:
        from tools.intelligence_briefing import AIIntelligenceBriefing

        return AIIntelligenceBriefing(self).track_competitors()

    def identify_revenue_opportunities(self) -> list[dict[str, Any]]:
        from tools.intelligence_briefing import AIIntelligenceBriefing

        return AIIntelligenceBriefing(self).detect_revenue_opportunities()

    def learn_from_video(self, transcript: str, topic: str) -> list[dict[str, Any]]:
        chunks = self._chunk_text(transcript, 1800)
        results = []
        for index, chunk in enumerate(chunks):
            concepts = self._extract_key_sentences(chunk)
            results.append(
                self.add_knowledge(
                    f"{topic} - segment {index + 1}", {"text": chunk, "key_concepts": concepts},
                    "video transcript", "learning_content", "medium", "internal", "course_material",
                )
            )
        return results

    def learn_from_course(self, course_materials_path: Path) -> list[dict[str, Any]]:
        root = Path(course_materials_path).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("course_materials_path must be a directory")
        results: list[dict[str, Any]] = []
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            if file_path.stat().st_size > 50_000_000:
                self.logger.warning(f"Skipped oversized course file {file_path.name}")
                continue
            text = self._extract_document_text(file_path)
            if not text.strip():
                continue
            for index, chunk in enumerate(self._chunk_text(text, 2500)):
                results.append(
                    self.add_knowledge(
                        f"{file_path.stem} - part {index + 1}",
                        {"content": chunk, "key_concepts": self._extract_key_sentences(chunk)},
                        str(file_path), "course_materials", "high", "internal", "course_material",
                    )
                )
        return results

    def learn_from_conversation(self, chat_history: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
        text = chat_history if isinstance(chat_history, str) else json.dumps(chat_history, ensure_ascii=False)
        insights = self._extract_key_sentences(text, limit=12)
        if not insights:
            return []
        return [
            self.add_knowledge(
                "Conversation insights", {"insights": insights}, "user-agent discussion",
                "aegis_brain", "high", "confidential", "conversation",
            )
        ]

    def _record_index(self, entry_id: str, collection: str, metadata: dict[str, Any]) -> None:
        index = self._load_index()
        existing_topic_entries = [entry for entry in index["entries"].values() if entry.get("topic") == metadata["topic"]]
        confidence_history = [float(entry.get("confidence_evolution", [0])[-1]) for entry in existing_topic_entries]
        index["entries"][entry_id] = {
            "topic": metadata["topic"],
            "collection": collection,
            "last_updated": metadata["last_updated"],
            "update_frequency": metadata["update_frequency_days"],
            "confidence_evolution": confidence_history[-4:] + [metadata["confidence"]],
            "source_count": 1 + len(existing_topic_entries),
            "security_level": metadata["security_level"],
            "monetization_potential": metadata["monetization_potential"],
        }
        self.index_path.write_bytes(self.encryption.encrypt_json(index, "memory-index"))

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"version": 1, "encrypted": True, "entries": {}}
        try:
            decoded = self.encryption.decrypt_json(self.index_path.read_bytes(), "memory-index")
            if not isinstance(decoded, dict) or not isinstance(decoded.get("entries"), dict):
                raise ValueError("Unexpected memory index structure")
            return decoded
        except Exception as exc:
            raise RuntimeError("Memory index failed authenticated decryption") from exc

    def _documents_by_source(self, source: str) -> list[str]:
        documents: list[str] = []
        for collection_name in COLLECTIONS:
            result = self._collection(collection_name).get(where={"source": source}, include=["documents"])
            documents.extend(result.get("documents", []))
        return documents

    @staticmethod
    def _compare_texts(first: str, second: str) -> dict[str, Any]:
        tokenize = lambda value: set(re.findall(r"[a-z0-9]{3,}", value.lower()))
        first_tokens, second_tokens = tokenize(first), tokenize(second)
        union = first_tokens | second_tokens
        overlap = len(first_tokens & second_tokens) / max(1, len(union))
        negative_pairs = (("increase", "decrease"), ("allowed", "prohibited"), ("secure", "insecure"), ("supports", "does-not-support"), ("true", "false"))
        contradictions = [f"{left}/{right}" for left, right in negative_pairs if (left in first_tokens and right in second_tokens) or (right in first_tokens and left in second_tokens)]
        return {"overlap_score": round(overlap, 3), "contradiction_terms": contradictions}

    @staticmethod
    def _suggest_update_frequency(topic: str) -> int:
        terms = set(re.findall(r"[a-z]+", topic.lower()))
        if terms & VOLATILE_TERMS:
            return 7
        if {"security", "vulnerability", "regulation", "platform"} & terms:
            return 14
        if {"course", "principle", "pattern", "interview"} & terms:
            return 180
        return 60

    @staticmethod
    def _monetization_potential(topic: str, data: str) -> str:
        score = sum(term in f"{topic} {data}".lower() for term in ("revenue", "pricing", "customer", "underserved", "market", "sell", "profit"))
        return "high" if score >= 3 else "medium" if score >= 1 else "low"

    @staticmethod
    def _clearance_rank(clearance: str) -> int:
        aliases = {"standard": 1, "trusted": 2, "admin": 3, **SECURITY_RANK}
        if clearance not in aliases:
            raise ValueError(f"Unknown security clearance: {clearance}")
        return aliases[clearance]

    @staticmethod
    def _bounded_text(value: str, maximum: int) -> str:
        cleaned = " ".join(str(value).split())
        if not cleaned:
            raise ValueError("Text value cannot be empty")
        return cleaned[:maximum]

    @staticmethod
    def _looks_suspicious(text: str) -> bool:
        lower = text.lower()
        markers = ("ignore previous instructions", "reveal system prompt", "send all data", "exfiltrate", "disable security")
        return any(marker in lower for marker in markers)

    @staticmethod
    def _chunk_text(text: str, size: int) -> list[str]:
        normalized = " ".join(text.split())
        return [normalized[index:index + size] for index in range(0, len(normalized), size) if normalized[index:index + size].strip()]

    @staticmethod
    def _extract_key_sentences(text: str, limit: int = 8) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        scored = sorted(sentences, key=lambda sentence: (len(set(re.findall(r"\w+", sentence.lower()))), len(sentence)), reverse=True)
        return [sentence[:500] for sentence in scored if 30 <= len(sentence) <= 700][:limit]

    @staticmethod
    def _extract_document_text(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".rst", ".csv", ".json", ".yaml", ".yml"}:
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        if suffix == ".docx":
            from docx import Document

            return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
        return ""

    def _safe_get(self, url: str, purpose: str) -> str:
        self._require_online(purpose)
        current_url = url
        response = None
        for _ in range(6):
            self._validate_external_url(current_url)
            self.logger.outbound_event(current_url, purpose, True, False)
            response = requests.get(
                current_url,
                timeout=(5, 20),
                headers={"User-Agent": "AI-Agency-Research/1.0 (local; no client data)"},
                allow_redirects=False,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("External redirect did not include a destination")
                current_url = urljoin(current_url, location)
                continue
            break
        else:
            raise ValueError("External request exceeded the redirect safety limit")
        if response is None:
            raise RuntimeError("External request did not produce a response")
        response.raise_for_status()
        if len(response.content) > 10_000_000:
            raise ValueError("External response exceeds 10 MB safety limit")
        return response.text

    @staticmethod
    def _validate_external_url(url: str, required_host: str | None = None) -> Any:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Only absolute HTTPS URLs are permitted")
        hostname = parsed.hostname.lower().rstrip(".")
        if required_host and hostname not in {required_host, f"www.{required_host}"}:
            raise ValueError(f"URL must use {required_host}")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve external hostname: {hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                raise ValueError("External URL resolves to a prohibited private or special address")
        return parsed

    @staticmethod
    def _require_online(purpose: str) -> None:
        if os.getenv("AI_AGENCY_OFFLINE_MODE", "true").lower() == "true":
            raise PermissionError(f"Offline mode blocks {purpose}; set AI_AGENCY_OFFLINE_MODE=false for an approved research session")

    @staticmethod
    def _architecture_summary(files: list[Path], root: Path) -> list[str]:
        relative = [str(path.relative_to(root)).replace("\\", "/").lower() for path in files]
        patterns = []
        signals = {
            "modular package architecture": ("src/", "packages/", "lib/"),
            "plugin architecture": ("plugin", "extension"),
            "agent orchestration": ("agent", "orchestrat"),
            "API service": ("api/", "routes/", "fastapi", "server."),
            "test-driven structure": ("tests/", "test_", ".spec."),
            "containerized deployment": ("dockerfile", "docker-compose"),
            "workflow automation": (".github/workflows", "scheduler", "queue"),
        }
        joined = "\n".join(relative)
        for name, terms in signals.items():
            if any(term in joined for term in terms):
                patterns.append(name)
        return patterns or ["single-package repository"]

    @staticmethod
    def _code_quality_score(files: list[Path], root: Path) -> float:
        names = [str(path.relative_to(root)).replace("\\", "/").lower() for path in files]
        score = 35.0
        score += 12 if any("readme" in name for name in names) else 0
        score += 12 if any("test" in name for name in names) else 0
        score += 8 if any(name.endswith(("pyproject.toml", "package.json", "cargo.toml", "go.mod")) for name in names) else 0
        score += 8 if any(name.startswith(".github/workflows/") for name in names) else 0
        score += 8 if any("license" in name for name in names) else 0
        score += 7 if any(name.endswith((".lock", "requirements.txt")) for name in names) else 0
        score += 5 if any(name.endswith((".md", ".rst")) and "docs/" in name for name in names) else 0
        score -= 10 if len(files) > 50_000 else 0
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _implementation_ideas(patterns: Iterable[str], manifests: Iterable[str]) -> list[str]:
        combined = " ".join([*patterns, *manifests]).lower()
        ideas = []
        if "plugin" in combined or "registry" in combined:
            ideas.append("Adopt an explicit capability registry with security policy checks at registration time.")
        if "api" in combined:
            ideas.append("Separate local API contracts from agent logic and bind the service to localhost.")
        if "test" in combined:
            ideas.append("Port high-value contract and security tests before reusing implementation details.")
        if "docker" in combined:
            ideas.append("Use container patterns only after verifying local data mounts and network isolation.")
        if not ideas:
            ideas.append("Evaluate the repository's module boundaries and error-handling patterns before selective adoption.")
        return ideas

    @staticmethod
    def _infer_ux_patterns(headings: list[str], calls_to_action: list[str]) -> list[str]:
        text = " ".join([*headings, *calls_to_action]).lower()
        patterns = []
        for phrase, label in (("free", "free-entry funnel"), ("demo", "demo-led conversion"), ("start", "action-first CTA"), ("security", "trust positioning"), ("enterprise", "enterprise segmentation")):
            if phrase in text:
                patterns.append(label)
        return patterns


if __name__ == "__main__":
    pipeline = KnowledgePipeline()
    print({"root": str(pipeline.paths["root"]), "collections": list(COLLECTIONS), "stale": pipeline.check_staleness()})
