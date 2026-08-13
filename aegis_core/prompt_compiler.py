"""Local AI prompt compiler that clarifies requests without expanding authority."""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from aegis_core.model_gateway import LocalModelGateway


PROMPT_COMPILER_INSTRUCTIONS = """
You are the Aegis Prompt Compiler. Rewrite the owner's request into a precise execution contract.
Do not execute the task. Preserve the owner's intent and never add authority, credentials, targets,
recipients, spending, destructive actions, or external disclosure that the owner did not request.
Clearly state unknowns instead of guessing. Return one JSON object with exactly these fields:
objective (string), deliverable (string), context (array of strings), constraints (array of strings),
execution_steps (array of strings), risk_level (low|medium|high|critical), approvals_required
(array of strings), success_evidence (array of strings), data_classification
(public|internal|confidential|restricted), and compiled_prompt (string). The compiled_prompt must be
self-contained, concise, factual, and tell the executor to stop for missing choices that materially
change the outcome. Keep the entire JSON response under 300 words: at most 5 execution steps, 5
constraints, 4 context items, and 4 success-evidence items.
""".strip()


class PromptCompiler:
    """Compile every owner request through the approved local model before execution."""

    HIGH_RISK = re.compile(
        r"\b(delete|erase|wipe|format|payment|purchase|transfer money|merge|production|deploy|"
        r"credential|password|token|private key|administrator|uac|firewall|bitlocker)\b",
        re.IGNORECASE,
    )
    MEDIUM_RISK = re.compile(
        r"\b(create|write|edit|commit|push|pull request|install|download|email|message|"
        r"publish|upload|web search|research|scrape|browser)\b",
        re.IGNORECASE,
    )
    INFORMATIONAL = re.compile(
        r"^(reply|answer|confirm|explain|summarize|describe|list|compare|what|why|how|when|where|who|is|are|can|could|would)\b",
        re.IGNORECASE,
    )
    EXECUTION_REQUEST = re.compile(
        r"\b(build|create|implement|change|edit|delete|install|download|deploy|publish|push|commit|"
        r"send|upload|run|execute|fix|write|move|rename|connect|authorize|purchase|pay)\b",
        re.IGNORECASE,
    )

    def __init__(self, gateway: LocalModelGateway) -> None:
        self.gateway = gateway

    def compile(self, original_prompt: str, project_context: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        original = " ".join(original_prompt.replace("\x00", " ").split())
        minimum_risk = self._minimum_risk(original)
        if not self.EXECUTION_REQUEST.search(original) and minimum_risk == "low":
            return self._conversation_rewrite(original, started)
        prompt = (
            f"{PROMPT_COMPILER_INSTRUCTIONS}\n\n"
            f"PROJECT CONTEXT:\n{json.dumps(project_context, ensure_ascii=False, default=str)[:4000]}\n\n"
            f"OWNER REQUEST:\n{original}"
        )
        try:
            response = self.gateway.generate(
                prompt,
                json_mode=True,
                timeout_seconds=75,
                options={"num_predict": 320, "temperature": 0.0, "num_ctx": 3072},
            )
            compiled = json.loads(str(response.get("response", "{}")))
            result = self._normalize(compiled, original, minimum_risk)
            result["compiler_mode"] = "ollama-local"
            result["model"] = self.gateway.model
            result["rewrite_duration_ms"] = round((perf_counter() - started) * 1000)
            return result
        except Exception:
            result = self._fallback(original, project_context, minimum_risk)
            result["compiler_mode"] = "deterministic-fallback"
            result["model"] = None
            result["rewrite_duration_ms"] = round((perf_counter() - started) * 1000)
            return result

    @staticmethod
    def _conversation_rewrite(original: str, started: float) -> dict[str, Any]:
        """Silently wrap ordinary conversation without an expensive or rigid compiler turn."""
        objective = "Respond directly and naturally to the owner's message"
        compiled_prompt = (
            f"OWNER MESSAGE (authoritative): {original}\n\n"
            "Respond as Aegis in a professional, warm, realistic conversation. Answer the actual question "
            "first; use relevant confirmed context; label uncertainty; do not invent current facts or claim "
            "actions. Keep the depth proportional to the request and avoid an execution-plan format unless asked."
        )
        return {
            "original_prompt": original,
            "objective": objective,
            "deliverable": "A direct, useful conversational response",
            "context": [],
            "constraints": ["Preserve owner intent", "Label uncertainty", "Do not invent execution"],
            "execution_steps": ["Answer the owner's message naturally"],
            "risk_level": "low",
            "approvals_required": [],
            "success_evidence": ["The response directly addresses the owner's message"],
            "data_classification": "internal",
            "compiled_prompt": compiled_prompt,
            "compiler_mode": "conversational-direct",
            "model": None,
            "rewrite_duration_ms": round((perf_counter() - started) * 1000),
        }

    @classmethod
    def _minimum_risk(cls, prompt: str) -> str:
        if cls.HIGH_RISK.search(prompt):
            return "high"
        if cls.MEDIUM_RISK.search(prompt):
            return "medium"
        return "low"

    @classmethod
    def _is_informational(cls, prompt: str) -> bool:
        return bool(
            cls.INFORMATIONAL.search(prompt)
            and not cls.HIGH_RISK.search(prompt)
            and not cls.MEDIUM_RISK.search(prompt)
        )

    @staticmethod
    def _risk_rank(value: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(value, 0)

    def _normalize(self, value: Any, original: str, minimum_risk: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Prompt compiler response must be an object")
        risk = str(value.get("risk_level", "low")).lower()
        if risk not in {"low", "medium", "high", "critical"}:
            risk = minimum_risk
        if self._risk_rank(risk) < self._risk_rank(minimum_risk):
            risk = minimum_risk
        objective = str(value.get("objective") or original)[:500]
        deliverable = str(value.get("deliverable") or "A factual response with evidence")[:500]
        context = self._string_list(value.get("context"), 4)
        constraints = self._string_list(value.get("constraints"), 5)
        steps = self._string_list(value.get("execution_steps"), 5) or ["Analyze the request", "Produce the deliverable", "Verify the result"]
        approvals = self._string_list(value.get("approvals_required"))
        if risk in {"high", "critical"} and not approvals:
            approvals = ["Owner approval before consequential execution"]
        evidence = self._string_list(value.get("success_evidence"), 4) or ["Result addresses the stated objective", "Unknowns are labeled"]
        classification = str(value.get("data_classification", "internal")).lower()
        if classification not in {"public", "internal", "confidential", "restricted"}:
            classification = "internal"
        if self._is_informational(original):
            risk = "low"
            approvals = []
            steps = ["Answer the owner's question directly from supplied verified context"]
            format_constraint = "Follow the owner's requested length and format exactly"
            if format_constraint not in constraints:
                constraints.append(format_constraint)
        # The local model supplies the structured rewrite, while Aegis renders the final
        # contract deterministically. This keeps owner intent authoritative and avoids a
        # second model call receiving a long, repetitive free-form compiler response.
        compiled_prompt = self._compiled_text(original, objective, deliverable, steps, approvals, evidence, constraints)
        return {
            "original_prompt": original,
            "objective": objective,
            "deliverable": deliverable,
            "context": context,
            "constraints": constraints,
            "execution_steps": steps,
            "risk_level": risk,
            "approvals_required": approvals,
            "success_evidence": evidence,
            "data_classification": classification,
            "compiled_prompt": compiled_prompt[:8_000],
        }

    def _fallback(self, original: str, project: dict[str, Any], risk: str) -> dict[str, Any]:
        objective = original[:1000]
        deliverable = "Complete the requested work and provide verifiable results"
        steps = ["Confirm the request scope from the supplied context", "Perform only authorized work", "Verify and report the outcome"]
        approvals = ["Owner approval before consequential execution"] if risk in {"high", "critical"} else []
        evidence = ["Requested deliverable exists", "Relevant checks pass", "Changes and unresolved risks are reported"]
        return {
            "original_prompt": original,
            "objective": objective,
            "deliverable": deliverable,
            "context": [f"Project: {project.get('name', 'Unspecified')}"] if project else [],
            "constraints": ["Do not expand authority", "Do not claim unverified work", "Protect private data"],
            "execution_steps": steps,
            "risk_level": risk,
            "approvals_required": approvals,
            "success_evidence": evidence,
            "data_classification": "internal",
            "compiled_prompt": self._compiled_text(
                original,
                objective,
                deliverable,
                steps,
                approvals,
                evidence,
                ["Do not expand authority", "Do not claim unverified work", "Protect private data"],
            ),
        }

    @staticmethod
    def _compiled_text(
        original: str,
        objective: str,
        deliverable: str,
        steps: list[str],
        approvals: list[str],
        evidence: list[str],
        constraints: list[str] | None = None,
    ) -> str:
        return (
            f"OWNER INTENT (authoritative; preserve every constraint): {original}\n\n"
            f"REWRITTEN EXECUTION CONTRACT:\nOBJECTIVE: {objective}\n"
            f"DELIVERABLE: {deliverable}\nEXECUTION STEPS:\n- " + "\n- ".join(steps)
            + ("\nCONSTRAINTS:\n- " + "\n- ".join(constraints) if constraints else "")
            + ("\nAPPROVALS REQUIRED:\n- " + "\n- ".join(approvals) if approvals else "")
            + "\nSUCCESS EVIDENCE:\n- " + "\n- ".join(evidence)
            + "\nAsk the owner only if a genuinely missing choice would materially change the requested outcome; otherwise proceed with labeled assumptions."
        )

    @staticmethod
    def _string_list(value: Any, maximum_items: int = 8) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:300] for item in value if str(item).strip()][:maximum_items]
