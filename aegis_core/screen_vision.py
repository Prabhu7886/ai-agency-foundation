"""Ephemeral local screen-frame understanding for owner-consented companion sessions."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from aegis_core.model_router import LocalModelRouter


SCREEN_PROMPT = """
You are Aegis viewing exactly one owner-consented screenshot during a local companion session.
Describe only what is visibly supported. Separate observations from inferences. Never claim to have
clicked, typed, watched continuously, or remembered earlier frames. Warn the owner if credentials,
personal data, financial data, private messages, or destructive controls appear visible. Answer the
owner's question first, then give at most five useful observations or next steps. Do not identify a
person from appearance and do not infer sensitive traits.
""".strip()


class ScreenVisionService:
    """Analyze one bounded frame in memory and return no image-derived persistence object."""

    MAX_FRAME_BYTES = 1_500_000
    DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\r\n]+)$")

    def __init__(self, router: LocalModelRouter) -> None:
        self.router = router

    def status(self) -> dict[str, Any]:
        try:
            route = self.router.select_vision()
            return {
                "available": True,
                "model": route["model"],
                "capture_mode": "owner_triggered_single_frame",
                "raw_frame_retention": "none",
                "transport": "loopback_only",
            }
        except Exception as exc:
            return {
                "available": False,
                "model": str(self.router.routes["vision"]["model"]),
                "capture_mode": "owner_triggered_single_frame",
                "raw_frame_retention": "none",
                "transport": "loopback_only",
                "error": str(exc)[:300],
            }

    def analyze(self, image_data_url: str, question: str, context: dict[str, Any]) -> dict[str, Any]:
        match = self.DATA_URL.fullmatch(image_data_url.strip())
        if not match:
            raise ValueError("Screen frame must be a JPEG, PNG, or WebP data URL")
        try:
            frame = base64.b64decode(match.group(2), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Screen frame is not valid base64 image data") from exc
        if not frame or len(frame) > self.MAX_FRAME_BYTES:
            raise ValueError("Screen frame must be between 1 byte and 1.5 MB")
        mime = match.group(1)
        if not self._matches_magic(frame, mime):
            raise ValueError("Screen frame content does not match its declared image type")

        route = self.router.select_vision()
        switch = self.router.prepare(route)
        gateway = self.router.gateway(route)
        prompt = (
            f"{SCREEN_PROMPT}\n\nSESSION CONTEXT:\n"
            f"type={context.get('session_type', 'unknown')}; purpose={context.get('purpose') or 'withheld'}; "
            f"privacy={context.get('privacy_mode', 'standard')}\n\nOWNER QUESTION:\n{question.strip()}"
        )
        try:
            payload = gateway.generate(
                prompt,
                images=[base64.b64encode(frame).decode("ascii")],
                timeout_seconds=180,
                options={"num_predict": 512, "temperature": 0.1, "num_ctx": 4096},
            )
            answer = str(payload.get("response", "")).strip()
            if not answer:
                raise RuntimeError("Local vision model returned an empty response")
            return {
                "analysis": answer[:20_000],
                "model": route["model"],
                "provider": "ollama-local",
                "verified_local": True,
                "raw_frame_retention": "discarded_after_inference",
                "recording": False,
                "route": {**route, **switch},
            }
        finally:
            self.router.release(str(route["model"]))

    @staticmethod
    def _matches_magic(frame: bytes, mime: str) -> bool:
        if mime == "image/png":
            return frame.startswith(b"\x89PNG\r\n\x1a\n")
        if mime == "image/jpeg":
            return frame.startswith(b"\xff\xd8\xff") and frame.endswith(b"\xff\xd9")
        if mime == "image/webp":
            return len(frame) >= 12 and frame[:4] == b"RIFF" and frame[8:12] == b"WEBP"
        return False
