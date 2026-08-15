"""Local system and security-focused resource monitoring."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from utils.logger import get_logger
from utils.paths import agency_root


@dataclass
class ResourceSnapshot:
    timestamp: str
    cpu_percent: float
    ram_percent: float
    ram_used_bytes: int
    disk_percent: float
    disk_free_bytes: int
    vram: dict[str, Any]
    outbound_connections: list[dict[str, Any]]
    monitored_processes: list[dict[str, Any]]


class SystemMonitor:
    def __init__(self) -> None:
        self.logger = get_logger("monitor")

    def snapshot(self) -> ResourceSnapshot:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(agency_root().anchor or Path.cwd().anchor))
        return ResourceSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            cpu_percent=psutil.cpu_percent(interval=0.1),
            ram_percent=float(memory.percent),
            ram_used_bytes=int(memory.used),
            disk_percent=float(disk.percent),
            disk_free_bytes=int(disk.free),
            vram=self._vram_metrics(),
            outbound_connections=self.outbound_connections(),
            monitored_processes=self.agent_processes(),
        )

    def outbound_connections(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            for connection in psutil.net_connections(kind="inet"):
                if connection.status != psutil.CONN_ESTABLISHED or not connection.raddr:
                    continue
                remote_ip = connection.raddr.ip
                if remote_ip.startswith("127.") or remote_ip == "::1":
                    continue
                results.append(
                    {
                        "pid": connection.pid,
                        "local": f"{connection.laddr.ip}:{connection.laddr.port}" if connection.laddr else "",
                        "remote": f"{remote_ip}:{connection.raddr.port}",
                        "process": self._process_name(connection.pid),
                    }
                )
        except (psutil.AccessDenied, OSError) as exc:
            self.logger.warning(f"Could not enumerate all network connections: {exc}")
        return results

    def agent_processes(self) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "cmdline", "memory_percent"]):
            try:
                command = " ".join(process.info.get("cmdline") or [])
                name = str(process.info.get("name") or "")
                if any(term in f"{name} {command}".lower() for term in ("ollama", "streamlit", "mobile_commander", "orchestrator")):
                    matches.append(
                        {
                            "pid": process.info["pid"],
                            "name": name,
                            "memory_percent": round(float(process.info.get("memory_percent") or 0.0), 2),
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return matches

    def verify_ollama_localhost(self, port: int = 11434) -> dict[str, Any]:
        listeners = []
        try:
            for connection in psutil.net_connections(kind="inet"):
                if connection.status == psutil.CONN_LISTEN and connection.laddr.port == port:
                    listeners.append(connection.laddr.ip)
        except psutil.AccessDenied as exc:
            return {"secure": False, "listeners": [], "reason": f"Access denied: {exc}"}
        secure = bool(listeners) and all(address in {"127.0.0.1", "::1"} for address in listeners)
        reason = "localhost only" if secure else ("not running" if not listeners else "non-local binding detected")
        return {"secure": secure, "listeners": sorted(set(listeners)), "reason": reason}

    def volume_encryption_status(self) -> dict[str, Any]:
        if os.name != "nt":
            return {"verified": False, "status": "automatic verification is Windows-only"}
        drive = agency_root().drive or "C:"
        try:
            completed = subprocess.run(
                ["manage-bde", "-status", drive],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = f"{completed.stdout}\n{completed.stderr}"
            direct = self._parse_bitlocker_output(output, drive)
            if completed.returncode == 0 or direct["verified"]:
                return direct
            return self._read_bitlocker_attestation(drive, direct["status"])
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            return self._read_bitlocker_attestation(drive, str(exc))

    @staticmethod
    def _parse_bitlocker_output(output: str, drive: str) -> dict[str, Any]:
        protection_on = bool(re.search(r"Protection Status:\s*Protection On", output, re.IGNORECASE))
        conversion_ok = bool(
            re.search(r"Conversion Status:\s*(?:Fully Encrypted|Used Space Only Encrypted)", output, re.IGNORECASE)
        )
        percentage_match = re.search(r"Percentage Encrypted:\s*([0-9]+(?:\.[0-9]+)?)%", output, re.IGNORECASE)
        percentage = float(percentage_match.group(1)) if percentage_match else None
        verified = protection_on and conversion_ok and percentage is not None and percentage >= 100.0
        return {
            "verified": verified,
            "status": "protected" if verified else "not verified",
            "drive": drive,
            "percentage": percentage,
            "source": "manage-bde",
        }

    @staticmethod
    def _read_bitlocker_attestation(drive: str, direct_error: str) -> dict[str, Any]:
        program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
        attestation_path = Path(
            os.getenv(
                "AI_AGENCY_BITLOCKER_ATTESTATION",
                str(program_data / "AI_Agency" / "Security" / "bitlocker_attestation.json"),
            )
        )
        try:
            attestation = json.loads(attestation_path.read_text(encoding="utf-8-sig"))
            checked_at = datetime.fromisoformat(str(attestation["checked_at"]).replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - checked_at.astimezone(timezone.utc)).total_seconds()
            verified = (
                bool(attestation.get("verified"))
                and str(attestation.get("drive", "")).upper() == drive.upper()
                and 0 <= age_seconds <= 108_000
            )
            return {
                "verified": verified,
                "status": "protected (administrator attestation)" if verified else "attestation invalid or stale",
                "drive": drive,
                "percentage": attestation.get("percentage"),
                "source": "administrator-attestation",
                "checked_at": attestation.get("checked_at"),
            }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {"verified": False, "status": direct_error, "drive": drive, "source": "unverified"}

    @staticmethod
    def ollama_firewall_status() -> dict[str, Any]:
        if os.name != "nt":
            return {"verified": False, "mode": "unsupported", "source": "Windows-only control"}
        program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
        attestation_path = Path(
            os.getenv(
                "AI_AGENCY_BITLOCKER_ATTESTATION",
                str(program_data / "AI_Agency" / "Security" / "bitlocker_attestation.json"),
            )
        )
        return SystemMonitor._read_ollama_firewall_attestation(attestation_path)

    @staticmethod
    def _read_ollama_firewall_attestation(attestation_path: Path) -> dict[str, Any]:
        """Validate a firewall attestation without bypassing platform enforcement."""
        try:
            attestation = json.loads(attestation_path.read_text(encoding="utf-8-sig"))
            checked_at = datetime.fromisoformat(str(attestation["checked_at"]).replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - checked_at.astimezone(timezone.utc)).total_seconds()
            firewall = attestation.get("ollama_firewall", {})
            verified = bool(firewall.get("verified")) and 0 <= age_seconds <= 108_000
            return {
                "verified": verified,
                "mode": firewall.get("mode", "unconfigured"),
                "rules": firewall.get("rules", []),
                "source": "administrator-attestation",
                "checked_at": attestation.get("checked_at"),
            }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {"verified": False, "mode": "unverified", "rules": [], "source": "unverified"}

    @staticmethod
    def _process_name(pid: int | None) -> str:
        if pid is None:
            return "unknown"
        try:
            return psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "unknown"

    @staticmethod
    def _vram_metrics() -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                return {"available": False}
            devices = []
            for line in completed.stdout.splitlines():
                name, total, used, utilization = [item.strip() for item in line.split(",", 3)]
                devices.append({"name": name, "total_mb": int(total), "used_mb": int(used), "utilization_percent": int(utilization)})
            return {"available": True, "devices": devices}
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            return {"available": False}


if __name__ == "__main__":
    print(asdict(SystemMonitor().snapshot()))
