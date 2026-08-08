"""Authenticated Telegram command and alert interface for Aegis."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from agents.base_agent import SecurityViolation
from agents.orchestrator import AegisOrchestrator
from utils.logger import get_logger
from utils.paths import agency_root


class MobileCommander:
    """Whitelist-only Telegram bot with sessions, rate limits, and confirmations."""

    COMMANDS = ("status", "etsy", "review", "learn", "security", "briefing", "github", "revenue", "agents", "deploy", "shutdown", "confirm")

    def __init__(self, aegis: AegisOrchestrator | None = None) -> None:
        load_dotenv(agency_root() / ".env", override=False)
        self.aegis = aegis or AegisOrchestrator()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.allowed_users = {
            int(value.strip()) for value in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if value.strip().isdigit()
        }
        self.session_timeout = timedelta(minutes=30)
        self.rate_limit = 15
        self.sessions: dict[int, dict[str, Any]] = {}
        self.request_times: dict[int, deque[float]] = defaultdict(deque)
        self.pending_confirmations: dict[int, dict[str, Any]] = {}
        self.logger = get_logger("mobile_commander")
        self._application: Application[Any, Any, Any, Any, Any, Any] | None = None
        if self.token and not self.allowed_users:
            raise RuntimeError("Telegram token is configured without a user ID whitelist")

    def build_application(self) -> Application[Any, Any, Any, Any, Any, Any]:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        application = Application.builder().token(self.token).build()
        for command in self.COMMANDS:
            application.add_handler(CommandHandler(command, self._handle_command))
        application.add_error_handler(self._handle_error)
        self._application = application
        return application

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        message = update.effective_message
        if user is None or message is None:
            return
        if not self._authenticate(user.id):
            self.logger.security_event("telegram_auth_failure", f"Denied Telegram user {user.id}", "high", "command blocked")
            await message.reply_text("Access denied.")
            return
        if not self._within_rate_limit(user.id):
            self.logger.security_event("telegram_rate_limit", f"Rate limit exceeded by {user.id}", "high", "temporarily blocked")
            await message.reply_text("Rate limit exceeded. Wait one minute and try again.")
            return
        self._touch_session(user.id, update)
        command = (message.text or "").strip()
        command_name = command.partition(" ")[0].split("@", 1)[0].lower()
        try:
            if command_name in {"/deploy", "/shutdown"}:
                response = self._request_confirmation(user.id, command_name)
            elif command_name == "/confirm":
                code = " ".join(context.args).strip()
                response = self._confirm_sensitive_action(user.id, code)
            else:
                response = self.aegis.process_telegram_command(command, user.id)
            await self._reply_chunks(message.reply_text, self._format_response(response))
            self._record_command(user.id, success=True)
        except Exception as exc:
            self.logger.error(f"Telegram command failed for authorized user {user.id}: {exc}")
            await message.reply_text(f"Command failed safely: {str(exc)[:500]}")
            self._record_command(user.id, success=False)

    def _authenticate(self, user_id: int) -> bool:
        return user_id in self.allowed_users

    def _within_rate_limit(self, user_id: int) -> bool:
        now = time.monotonic()
        window = self.request_times[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.rate_limit:
            return False
        window.append(now)
        return True

    def _touch_session(self, user_id: int, update: Update) -> None:
        now = datetime.now(timezone.utc)
        session = self.sessions.get(user_id)
        if session and now - session["last_active"] <= self.session_timeout:
            session["last_active"] = now
            return
        device = {
            "language_code": getattr(update.effective_user, "language_code", None),
            "chat_type": getattr(update.effective_chat, "type", None),
        }
        self.sessions[user_id] = {"started": now, "last_active": now, "commands": 0, "database_id": None}
        try:
            with self.aegis.database.connection() as connection:
                cursor = connection.execute(
                    """INSERT INTO mobile_sessions
                    (user_id, device_info, session_start, session_end, commands_issued, security_verified)
                    VALUES (?, ?, ?, NULL, 0, 1)""",
                    (str(user_id), json.dumps(device), now.isoformat()),
                )
                self.sessions[user_id]["database_id"] = cursor.lastrowid
        except Exception as exc:
            self.logger.error(f"Could not persist mobile session: {exc}")

    def _record_command(self, user_id: int, success: bool) -> None:
        session = self.sessions.get(user_id)
        if not session:
            return
        session["commands"] += 1
        session_id = session.get("database_id")
        if session_id:
            try:
                with self.aegis.database.connection() as connection:
                    connection.execute(
                        "UPDATE mobile_sessions SET commands_issued = ?, security_verified = ? WHERE id = ?",
                        (session["commands"], int(success), session_id),
                    )
            except Exception as exc:
                self.logger.error(f"Could not update mobile session: {exc}")

    def cleanup_expired_sessions(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [user_id for user_id, session in self.sessions.items() if now - session["last_active"] > self.session_timeout]
        for user_id in expired:
            session = self.sessions.pop(user_id)
            if session.get("database_id"):
                try:
                    with self.aegis.database.connection() as connection:
                        connection.execute(
                            "UPDATE mobile_sessions SET session_end = ? WHERE id = ?",
                            (now.isoformat(), session["database_id"]),
                        )
                except Exception as exc:
                    self.logger.error(f"Could not close mobile session: {exc}")
            self.pending_confirmations.pop(user_id, None)
        return len(expired)

    def _request_confirmation(self, user_id: int, command: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.pending_confirmations[user_id] = {
            "command": command,
            "code": code,
            "expires": datetime.now(timezone.utc) + timedelta(minutes=2),
        }
        return f"Security confirmation required for {command}. Reply `/confirm {code}` within two minutes."

    def _confirm_sensitive_action(self, user_id: int, code: str) -> str:
        pending = self.pending_confirmations.pop(user_id, None)
        if not pending or pending["expires"] < datetime.now(timezone.utc) or not secrets.compare_digest(pending["code"], code):
            raise PermissionError("Confirmation is missing, expired, or incorrect")
        if pending["command"] == "/shutdown":
            return json.dumps(self.aegis.shutdown_all_agents("confirmed Telegram emergency shutdown"), indent=2)
        if pending["command"] == "/deploy":
            return json.dumps(self._deploy_updates(), indent=2)
        raise ValueError("Unknown sensitive action")

    def _deploy_updates(self) -> dict[str, Any]:
        audit = self.aegis.daily_security_audit()
        if not audit.get("passed"):
            raise SecurityViolation("Deployment blocked because the security audit did not pass")
        completed = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=agency_root(), capture_output=True, text=True, timeout=120,
            check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise RuntimeError(f"git pull failed: {completed.stderr.strip()[:1000]}")
        return {"deployed": True, "output": completed.stdout.strip()[:1000], "audit_score": audit["security_score"]}

    async def send_alert(self, alert_type: str, message: str, severity: str = "info") -> dict[str, Any]:
        if self._application is None:
            raise RuntimeError("Telegram application is not running")
        safe_message = self._format_response(message)
        payload = f"AEGIS {severity.upper()} — {alert_type}\n{safe_message}"[:3900]
        delivered, failed = 0, 0
        for user_id in self.allowed_users:
            try:
                self.logger.outbound_event("https://api.telegram.org", f"{alert_type} alert", True, False)
                await self._application.bot.send_message(chat_id=user_id, text=payload)
                delivered += 1
            except Exception as exc:
                failed += 1
                self.logger.error(f"Telegram alert delivery failed: {exc}")
        return {"delivered": delivered, "failed": failed}

    async def send_daily_briefing(self) -> dict[str, Any]:
        briefing = self.aegis.daily_ai_briefing()
        return await self.send_alert("Daily briefing", json.dumps(briefing, ensure_ascii=False, default=str), "info")

    async def send_security_incident(self, incident: dict[str, Any]) -> dict[str, Any]:
        safe_summary = {key: incident.get(key) for key in ("type", "severity", "action")}
        return await self.send_alert("Security incident", json.dumps(safe_summary), str(incident.get("severity", "high")))

    async def send_revenue_milestone(self, milestone: str, amount: float) -> dict[str, Any]:
        return await self.send_alert("Revenue milestone", f"{milestone}: ${amount:,.2f}", "info")

    async def send_agent_failure(self, agent_name: str, failure_category: str) -> dict[str, Any]:
        return await self.send_alert("Agent failure", f"{agent_name}: {failure_category}", "high")

    @staticmethod
    async def _reply_chunks(reply: Callable[..., Any], text: str) -> None:
        for index in range(0, len(text), 3900):
            await reply(text[index:index + 3900])

    @staticmethod
    def _format_response(response: Any) -> str:
        text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False, default=str, indent=2)
        return text.replace("\x00", " ")[:15_000]

    async def _handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.logger.error(f"Telegram framework error: {context.error}")

    def run(self) -> None:
        application = self.build_application()
        self.logger.security_event("telegram_start", f"Starting whitelist-only bot for {len(self.allowed_users)} user(s)")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    MobileCommander().run()
