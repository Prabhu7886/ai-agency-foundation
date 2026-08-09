"""Local-only speech input and output for the Aegis Voice Lounge."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aegis_core.foundation import FoundationViolation


class LocalVoiceService:
    """Use an installed local Whisper engine and Windows SAPI; never a cloud service."""

    MAX_AUDIO_BYTES = 15 * 1024 * 1024
    ALLOWED_TYPES = {"audio/webm": ".webm", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"}

    def status(self) -> dict[str, Any]:
        return {
            "transcription_available": importlib.util.find_spec("faster_whisper") is not None,
            "transcription_engine": "faster-whisper (local)" if importlib.util.find_spec("faster_whisper") else None,
            "speech_available": True,
            "speech_engine": "Windows SAPI (local)",
            "cloud_audio": False,
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
        try:
            with tempfile.NamedTemporaryFile(prefix="aegis-voice-", suffix=self.ALLOWED_TYPES[media_type], delete=False) as handle:
                handle.write(audio)
                temporary = Path(handle.name)
            model = WhisperModel("small.en", device="auto", compute_type="int8")
            segments, info = model.transcribe(str(temporary), vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return {"text": text, "language": info.language, "engine": "faster-whisper", "local": True}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

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
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            input=clean,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise FoundationViolation("The local Windows speech engine failed")
        return {"spoken": True, "engine": "Windows SAPI", "local": True}
