"""AES-256-GCM encryption and SQLCipher key derivation utilities."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from dotenv import load_dotenv

from utils.paths import agency_root, ensure_runtime_directories


class EncryptionError(RuntimeError):
    """Raised when secure encryption or key handling fails."""


@dataclass(frozen=True)
class EncryptedPayload:
    version: int
    nonce: str
    ciphertext: str

    def to_bytes(self) -> bytes:
        return json.dumps(self.__dict__, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, value: bytes) -> "EncryptedPayload":
        try:
            decoded = json.loads(value.decode("utf-8"))
            return cls(
                version=int(decoded["version"]),
                nonce=str(decoded["nonce"]),
                ciphertext=str(decoded["ciphertext"]),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise EncryptionError("Encrypted payload is invalid") from exc


class KeyManager:
    """Loads the agency master key and derives purpose-specific AES-256 keys."""

    ENV_NAME = "AI_AGENCY_MASTER_KEY"

    def __init__(self, env_path: Path | None = None) -> None:
        self.env_path = env_path or agency_root() / ".env"
        load_dotenv(self.env_path, override=False)

    @staticmethod
    def generate_master_key() -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

    def initialize_env(self, overwrite: bool = False) -> str:
        """Create a protected .env containing a new master key.

        Existing files are never replaced unless explicitly requested.
        """
        if self.env_path.exists() and not overwrite:
            raise EncryptionError(f"Refusing to overwrite existing {self.env_path}")
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        key = self.generate_master_key()
        lines = [
            f"{self.ENV_NAME}={key}",
            "OLLAMA_HOST=127.0.0.1:11434",
            "OLLAMA_BASE_URL=http://127.0.0.1:11434",
            "TELEGRAM_BOT_TOKEN=",
            "TELEGRAM_ALLOWED_USER_IDS=",
            "AI_AGENCY_OFFLINE_MODE=true",
            "AI_AGENCY_VECTOR_DB_ENCRYPTED_VOLUME_REQUIRED=true",
            "CHROMA_SERVER_ENABLED=false",
        ]
        flags = os.O_WRONLY | os.O_CREAT
        if not overwrite:
            flags |= os.O_EXCL
        else:
            flags |= os.O_TRUNC
        descriptor = os.open(self.env_path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        return key

    def master_key(self) -> bytes:
        encoded = os.getenv(self.ENV_NAME, "").strip()
        if not encoded:
            raise EncryptionError(
                f"{self.ENV_NAME} is missing. Run `python -m utils.encryption --init` locally."
            )
        try:
            raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise EncryptionError(f"{self.ENV_NAME} is not valid URL-safe base64") from exc
        if len(raw) != 32:
            raise EncryptionError(f"{self.ENV_NAME} must decode to exactly 32 bytes")
        return raw

    def derive_key(self, purpose: str) -> bytes:
        if not purpose or len(purpose) > 256:
            raise EncryptionError("A non-empty, bounded key purpose is required")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"AI_AGENCY_HKDF_V1",
            info=purpose.encode("utf-8"),
        ).derive(self.master_key())

    def sqlcipher_hex_key(self) -> str:
        return self.derive_key("sqlcipher:metrics.db").hex()


class EncryptionManager:
    """Authenticated AES-256-GCM encryption for files and structured data."""

    VERSION = 1

    def __init__(self, key_manager: KeyManager | None = None) -> None:
        self.keys = key_manager or KeyManager()

    def encrypt_bytes(self, data: bytes, purpose: str, associated_data: bytes | None = None) -> bytes:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self.keys.derive_key(purpose)).encrypt(nonce, data, associated_data)
        return EncryptedPayload(
            version=self.VERSION,
            nonce=base64.b64encode(nonce).decode("ascii"),
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        ).to_bytes()

    def decrypt_bytes(self, payload: bytes, purpose: str, associated_data: bytes | None = None) -> bytes:
        envelope = EncryptedPayload.from_bytes(payload)
        if envelope.version != self.VERSION:
            raise EncryptionError(f"Unsupported encrypted payload version: {envelope.version}")
        try:
            nonce = base64.b64decode(envelope.nonce, validate=True)
            ciphertext = base64.b64decode(envelope.ciphertext, validate=True)
            return AESGCM(self.keys.derive_key(purpose)).decrypt(nonce, ciphertext, associated_data)
        except Exception as exc:
            raise EncryptionError("Authentication or decryption failed") from exc

    def encrypt_json(self, data: Any, purpose: str) -> bytes:
        serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self.encrypt_bytes(serialized, purpose)

    def decrypt_json(self, payload: bytes, purpose: str) -> Any:
        return json.loads(self.decrypt_bytes(payload, purpose).decode("utf-8"))

    def encrypt_file(self, source: Path, destination: Path, purpose: str) -> Path:
        source_path = Path(source).resolve(strict=True)
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self.encrypt_bytes(source_path.read_bytes(), purpose, str(source_path.name).encode("utf-8"))
        destination_path.write_bytes(encrypted)
        return destination_path

    def decrypt_file(self, source: Path, destination: Path, purpose: str, original_name: str) -> Path:
        source_path = Path(source).resolve(strict=True)
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        plaintext = self.decrypt_bytes(source_path.read_bytes(), purpose, original_name.encode("utf-8"))
        destination_path.write_bytes(plaintext)
        return destination_path


def safe_identifier(value: str) -> str:
    """Convert untrusted identifiers into a safe directory component."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())[:80].strip("._")
    if not cleaned:
        raise ValueError("Identifier contains no safe characters")
    return cleaned


def initialize_security_environment() -> Path:
    ensure_runtime_directories()
    manager = KeyManager()
    manager.initialize_env()
    gitignore = agency_root() / ".gitignore"
    required = {".env", "*.db", "*.db-*", "databases/vector_db/", "databases/client_data/", "logs/", "runtime/", "backups/"}
    existing = set(gitignore.read_text(encoding="utf-8").splitlines()) if gitignore.exists() else set()
    gitignore.write_text("\n".join(sorted(existing | required)) + "\n", encoding="utf-8")
    return manager.env_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Agency encryption key management")
    parser.add_argument("--init", action="store_true", help="Create the private .env master key file")
    parser.add_argument("--verify", action="store_true", help="Verify encryption round-trip")
    args = parser.parse_args()
    if args.init:
        print(f"Created {initialize_security_environment()}")
    if args.verify:
        encryption = EncryptionManager()
        test_value = secrets.token_bytes(64)
        protected = encryption.encrypt_bytes(test_value, "self-test")
        if encryption.decrypt_bytes(protected, "self-test") != test_value:
            raise SystemExit("Encryption verification failed")
        print("AES-256-GCM verification succeeded")
