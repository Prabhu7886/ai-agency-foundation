"""Local AI prompt compiler that clarifies requests without expanding authority."""

from __future__ import annotations

import json
import re
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
change the outcome.
""".strip()


class PromptCompiler:
    """Compile every owner request through the approved local model before execution."""

    HIGH_RISK = re.compile(
        r"\b(delete|erase|wipe|format|payment|purchase|transfer money|merge|production|deploy|"
        r"credential|password|token|private key|administrator|uac|firewall|bitlocker)\b",
        re.IGNORECASE,
    )
    MEDIUM_RISK = re.compile(
        r"\b(create|write|edit|commit|push|pull request|github|install|download|email|message|"
        r"publish|upload|web search|research|scrape|browser)\b",
        re.IGNORECASE,
    )

    def __init__(self, gateway: LocalModelGateway) -> None:
        self.gateway = gateway

    def compile(self, original_prompt: str, project_context: dict[str, Any]) -> dict[str, Any]:
        original = " ".join(original_prompt.replace("\x00", " ").split())
        minimum_risk = self._minimum_risk(original)
        prompt = (
            f"{PROMPT_COMPILER_INSTRUCTIONS}\n\n"
            f"PROJECT CONTEXT:\n{json.dumps(project_context, ensure_ascii=False, default=str)[:8000]}\n\n"
            f"OWNER REQUEST:\n{original}"
        )
        try:
            response = self.gateway.generate(prompt, json_mode=True, timeout_seconds=120)
            compiled = json.loads(str(response.get("response", "{}")))
            result = self._normalize(compiled, original, minimum_risk)
            result["compiler_mode"] = "ollama-local"
            result["model"] = self.gateway.model
            return result
        except Exception:
            result = self._fallback(original, project_context, minimum_risk)
            result["compiler_mode"] = "deterministic-fallback"
            result["model"] = None
            return result

    @classmethod
    def _minimum_risk(cls, prompt: str) -> str:
        if cls.HIGH_RISK.search(prompt):
            return "high"
        if cls.MEDIUM_RISK.search(prompt):
            return "medium"
        return "low"

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
        objective = str(value.get("objective") or original)[:1000]
        deliverable = str(value.get("deliverable") or "A factual response with evidence")[:1000]
        steps = self._string_list(value.get("execution_steps")) or ["Analyze the request", "Produce the deliverable", "Verify the result"]
        approvals = self._string_list(value.get("approvals_required"))
        if risk in {"high", "critical"} and not approvals:
            approvals = ["Owner approval before consequential execution"]
        evidence = self._string_list(value.get("success_evidence")) or ["Result addresses the stated objective", "Unknowns are labeled"]
        classification = str(value.get("data_classification", "internal")).lower()
        if classification not in {"public", "internal", "confidential", "restricted"}:
            classification = "internal"
        compiled_prompt = str(value.get("compiled_prompt") or "").strip()
        if not compiled_prompt:
            compiled_prompt = self._compiled_text(original, objective, deliverable, steps, approvals, evidence)
        return {
            "original_prompt": original,
            "objective": objective,
            "deliverable": deliverable,
            "context": self._string_list(value.get("context")),
            "constraints": self._string_list(value.get("constraints")),
            "execution_steps": steps,
            "risk_level": risk,
            "approvals_required": approvals,
            "success_evidence": evidence,
            "data_classification": classification,
            "compiled_prompt": compiled_prompt[:50_000],
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
            "compiled_prompt": self._compiled_text(original, objective, deliverable, steps, approvals, evidence),
        }

    @staticmethod
    def _compiled_text(original: str, objective: str, deliverable: str, steps: list[str], approvals: list[str], evidence: list[str]) -> str:
        return (
            f"OWNER INTENT (preserve exactly): {original}\n\nOBJECTIVE: {objective}\n"
            f"DELIVERABLE: {deliverable}\nEXECUTION STEPS:\n- " + "\n- ".join(steps)
            + ("\nAPPROVALS REQUIRED:\n- " + "\n- ".join(approvals) if approvals else "")
            + "\nSUCCESS EVIDENCE:\n- " + "\n- ".join(evidence)
            + "\nStop and ask the owner if a missing choice would materially change the outcome."
        )

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:1000] for item in value if str(item).strip()][:50]
