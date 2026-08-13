"""Local-only speech input and output for the Aegis Voice Lounge."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis_core.foundation import FoundationViolation


class LocalVoiceService:
    """Use an installed local Whisper engine and Windows SAPI; never a cloud service."""

    MAX_AUDIO_BYTES = 15 * 1024 * 1024
    ALLOWED_TYPES = {"audio/webm": ".webm", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"}

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._state = "idle"
        self._updated_at = datetime.now(timezone.utc).isoformat()

    def _set_state(self, state: str) -> None:
        with self._lock:
            self._state = state
            self._updated_at = datetime.now(timezone.utc).isoformat()

    def status(self) -> dict[str, Any]:
        return {
            "transcription_available": importlib.util.find_spec("faster_whisper") is not None,
            "transcription_engine": "faster-whisper (local)" if importlib.util.find_spec("faster_whisper") else None,
            "speech_available": True,
            "speech_engine": "Windows SAPI (local)",
            "cloud_audio": False,
            "session_state": self._state,
            "updated_at": self._updated_at,
            "interrupt_available": bool(self._process and self._process.poll() is None),
            "raw_audio_retention": "deleted_immediately_after_transcription",
            "transcript_retention": "not_saved_until_owner_submits_to_workspace",
        }

    def transcribe(self, audio: bytes, content_type: str) -> dict[str, Any]:
        media_type = content_type.split(";", 1)[0].lower()
        if media_type not in self.ALLOWED_TYPES:
            raise FoundationViolation("Voice Lounge accepts WebM, WAV, or MP3 audio")
        if not audio or len(audio) > self.MAX_AUDIO_BYTES:
            raise FoundationViolation("Voice recording must be between 1 byte and 15 MB")
        if importlib.util.find_spec("faster_whisper") is None:
            raise FoundationViolation("Local transcription is not installed; install faster-whisper to enable speech input")

        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        temporary: Path | None = None
        self._set_state("processing")
        try:
            with tempfile.NamedTemporaryFile(prefix="aegis-voice-", suffix=self.ALLOWED_TYPES[media_type], delete=False) as handle:
                handle.write(audio)
                temporary = Path(handle.name)
            model = WhisperModel("small.en", device="auto", compute_type="int8")
            segments, info = model.transcribe(str(temporary), vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return {"text": text, "language": info.language, "engine": "faster-whisper", "local": True, "raw_audio_deleted": True}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            self._set_state("idle")

    def speak(self, text: str) -> dict[str, Any]:
        clean = text.strip()
        if not clean or len(clean) > 5_000:
            raise FoundationViolation("Speech text must be between 1 and 5,000 characters")
        command = (
            "$text=[Console]::In.ReadToEnd(); "
            "Add-Type -AssemblyName System.Speech; "
            "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speaker.Speak($text)"
        )
        with self._lock:
            if self._process and self._process.poll() is None:
                raise FoundationViolation("Aegis is already speaking; interrupt the current response first")
            self._state = "speaking"
            self._updated_at = datetime.now(timezone.utc).isoformat()
            self._process = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            process = self._process
        try:
            _, _ = process.communicate(clean, timeout=120)
        except subprocess.TimeoutExpired as exc:
            process.terminate()
            raise FoundationViolation("The local Windows speech engine timed out") from exc
        finally:
            with self._lock:
                self._process = None
                self._state = "idle"
                self._updated_at = datetime.now(timezone.utc).isoformat()
        if process.returncode != 0:
            raise FoundationViolation("The local Windows speech engine failed")
        return {"spoken": True, "engine": "Windows SAPI", "local": True, "interrupted": False}

    def interrupt(self) -> dict[str, Any]:
        with self._lock:
            active = self._process
            if not active or active.poll() is not None:
                self._state = "idle"
                return {"interrupted": False, "state": "idle"}
            active.terminate()
            self._process = None
            self._state = "idle"
            self._updated_at = datetime.now(timezone.utc).isoformat()
            return {"interrupted": True, "state": "idle", "local": True}
