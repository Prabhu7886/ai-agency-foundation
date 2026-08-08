"""Long-running local Aegis service with audits, research, backups, and Telegram."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import threading
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv

from agents.orchestrator import AegisOrchestrator
from databases.setup_databases import DatabaseSetup
from tools.backup_manager import EncryptedBackupManager
from tools.mobile_commander import MobileCommander
from utils.logger import get_logger
from utils.paths import agency_root, ensure_runtime_directories
from utils.scheduler import SecureTaskScheduler


class AgencyRuntime:
    """Wires secure services and scheduled operations into one local process."""

    def __init__(self) -> None:
        load_dotenv(agency_root() / ".env", override=False)
        ensure_runtime_directories()
        self.logger = get_logger("agency_runtime")
        self.database = DatabaseSetup()
        self.aegis = AegisOrchestrator()
        self.backups = EncryptedBackupManager()
        self.scheduler = SecureTaskScheduler()
        self.mobile = MobileCommander(self.aegis)
        self._stop = threading.Event()

    def initialize(self) -> dict[str, Any]:
        database_result = self.database.setup_all()
        audit = self.aegis.daily_security_audit()
        if not audit["passed"]:
            raise RuntimeError(f"Startup blocked by security controls: {audit['critical_failures']}")
        self._configure_schedule()
        return {"database": database_result, "security": audit}

    def run(self) -> None:
        result = self.initialize()
        self.logger.info(f"Aegis runtime initialized with security score {result['security']['security_score']}")
        self.scheduler.start()
        self._install_signal_handlers()
        try:
            if self.mobile.token:
                self.mobile.run()
            else:
                self.logger.warning("Telegram is disabled; runtime is operating locally only")
                while not self._stop.wait(1.0):
                    self.mobile.cleanup_expired_sessions()
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        self.scheduler.stop()
        self.aegis.shutdown_all_agents("agency runtime stopped")

    def _configure_schedule(self) -> None:
        schedule_path = agency_root() / "config" / "schedule.yaml"
        config = yaml.safe_load(schedule_path.read_text(encoding="utf-8"))
        self.scheduler.add_daily_job(config["security"]["audit"]["at"], self._scheduled_audit, "daily-security-audit")
        self.scheduler.add_daily_job(config["research"]["ai_briefing"]["at"], self._scheduled_briefing, "daily-ai-briefing")
        self.scheduler.add_daily_job(config["research"]["github_trending"]["at"], self._scheduled_github_scan, "daily-github-scan")
        self.scheduler.add_daily_job(config["research"]["knowledge_consolidation"]["at"], self.aegis.pipeline.consolidate_research, "knowledge-consolidation")
        self.scheduler.add_daily_job(config["backups"]["encrypted_daily"]["at"], self._scheduled_backup, "encrypted-daily-backup")
        weekly = config["research"]["competitor_scan"]
        self.scheduler.add_weekly_job(weekly["weekday"], weekly["at"], self.aegis.monitor_competitors, "weekly-competitor-scan")
        oss = config.get("research", {}).get("open_source_scan", {"weekday": "sunday", "at": "08:00"})
        self.scheduler.add_weekly_job(oss["weekday"], oss["at"], self.aegis.weekly_oss_scan, "weekly-oss-scan")

    def _scheduled_audit(self) -> dict[str, Any]:
        audit = self.aegis.daily_security_audit()
        if not audit["passed"] and self.mobile.token:
            self._notify("Security audit failure", {"score": audit["security_score"], "failures": audit["critical_failures"]}, "critical")
        return audit

    def _scheduled_briefing(self) -> dict[str, Any]:
        try:
            briefing = self.aegis.daily_ai_briefing()
            if self.mobile.token:
                self._notify("Daily briefing", briefing, "info")
            return briefing
        except PermissionError as exc:
            self.logger.info(f"Daily briefing skipped in offline mode: {exc}")
            return {"skipped": True, "reason": str(exc)}

    def _scheduled_github_scan(self) -> dict[str, Any]:
        try:
            return {"repositories": self.aegis.pipeline.monitor_github_trending("ai-agent")}
        except PermissionError as exc:
            return {"skipped": True, "reason": str(exc)}

    def _scheduled_backup(self) -> dict[str, Any]:
        result = self.backups.create_backup()
        result["pruned"] = self.backups.prune(retain=14)
        return result

    def _notify(self, alert_type: str, payload: dict[str, Any], severity: str) -> None:
        try:
            asyncio.run(self.mobile.send_alert(alert_type, json.dumps(payload, ensure_ascii=False, default=str), severity))
        except Exception as exc:
            self.logger.error(f"Mobile notification failed: {exc}")

    def _install_signal_handlers(self) -> None:
        def handler(_signum: int, _frame: Any) -> None:
            self._stop.set()

        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signal_name, handler)
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    AgencyRuntime().run()
