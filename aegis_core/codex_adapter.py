"""Official Codex app-server JSONL adapter with Aegis approval boundaries."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from aegis_core.foundation import FoundationGuard, FoundationViolation


class CodexAppServerAdapter:
    """Connect Aegis to Codex over the documented local stdio app-server protocol."""

    def __init__(self, guard: FoundationGuard, executable: str | None = None) -> None:
        self.guard = guard
        configured = executable or os.getenv("AEGIS_CODEX_EXECUTABLE")
        user_local = sorted(
            (Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        candidates = [Path(configured)] if configured else list(user_local)
        discovered = shutil.which("codex")
        if discovered and not configured:
            candidates.append(Path(discovered))
        self.executable = str(next((item for item in candidates if item.is_file()), "")) or None
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=2000)
        self._condition = threading.Condition()

    def status(self, check_account: bool = False) -> dict[str, Any]:
        if not self.executable:
            return {"installed": False, "connected": False, "protocol": "app-server-stdio"}
        if not check_account:
            running = bool(self._process and self._process.poll() is None)
            return {"installed": True, "connected": running, "protocol": "app-server-stdio", "account": None}
        try:
            self._ensure_started()
            account = self._request("account/read", {"refreshToken": False}, timeout=20)
            return {
                "installed": True,
                "connected": True,
                "protocol": "app-server-stdio",
                "account": account.get("account"),
                "requires_openai_auth": account.get("requiresOpenaiAuth"),
            }
        except Exception as exc:
            return {"installed": True, "connected": False, "protocol": "app-server-stdio", "error": str(exc)[:500]}

    def start_device_login(self) -> dict[str, Any]:
        self._ensure_started()
        return self._request("account/login/start", {"type": "chatgptDeviceCode"}, timeout=30)

    def run_approved_turn(self, project: dict[str, Any], compiled_prompt: str) -> dict[str, Any]:
        """Run one pre-approved Codex turn inside one registered root with network disabled."""
        root = self.guard.validate_project_root(project["root_path"])
        with self._turn_lock:
            self._ensure_started()
            account = self._request("account/read", {"refreshToken": False}, timeout=20)
            if account.get("requiresOpenaiAuth") and not account.get("account"):
                raise FoundationViolation("Codex requires ChatGPT authentication")
            event_cursor = self._event_count()
            thread_result = self._request(
                "thread/start",
                {
                    "cwd": str(root),
                    "approvalPolicy": "never",
                    "sandbox": "workspaceWrite",
                    "personality": "friendly",
                    "serviceName": "aegis_local_executive",
                },
                timeout=60,
            )
            thread_id = thread_result["thread"]["id"]
            turn_result = self._request(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": compiled_prompt}],
                    "cwd": str(root),
                    "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "workspaceWrite", "writableRoots": [str(root)], "networkAccess": False},
                    "summary": "concise",
                    "personality": "friendly",
                },
                timeout=60,
            )
            turn_id = turn_result["turn"]["id"]
            completed = self._wait_for_turn(thread_id, turn_id, event_cursor, timeout=1800)
            events = self._events_since(event_cursor)
            messages = [
                event.get("params", {}).get("item", {}).get("text", "")
                for event in events
                if event.get("method") == "item/completed"
                and event.get("params", {}).get("item", {}).get("type") == "agentMessage"
            ]
            diffs = [event.get("params", {}).get("diff", "") for event in events if event.get("method") == "turn/diff/updated"]
            return {
                "thread_id": thread_id,
                "turn_id": turn_id,
                "status": completed.get("params", {}).get("turn", {}).get("status", "unknown"),
                "answer": next((item for item in reversed(messages) if item), "Codex completed without a final text message."),
                "diff": next((item for item in reversed(diffs) if item), ""),
                "network_access": False,
                "project_root": str(root),
                "provider": "codex-app-server",
            }

    def close(self) -> None:
        process = self._process
        self._process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return
        if not self.executable:
            raise FoundationViolation("Codex executable is not installed or registered")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            [self.executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            creationflags=creation_flags,
        )
        self._reader = threading.Thread(target=self._read_loop, name="aegis-codex-events", daemon=True)
        self._reader.start()
        self._request(
            "initialize",
            {"clientInfo": {"name": "aegis_local_executive", "title": "Aegis", "version": "0.5.0"}},
            timeout=30,
        )
        self._notify("initialized", {})

    def _request(self, method: str, params: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[request_id] = response_queue
        self._send({"method": method, "id": request_id, "params": params})
        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"Codex app-server timed out during {method}") from exc
        if response.get("error"):
            raise RuntimeError(f"Codex {method} failed: {response['error']}")
        return response.get("result", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})

    def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.poll() is not None or not process.stdin:
            raise RuntimeError("Codex app-server is not running")
        with self._write_lock:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()

    def _read_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in message and "method" not in message:
                pending = self._pending.pop(int(message["id"]), None)
                if pending:
                    pending.put(message)
                continue
            if "id" in message and "method" in message:
                self._decline_server_request(message)
            with self._condition:
                self._events.append(message)
                self._condition.notify_all()

    def _decline_server_request(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if "requestApproval" in method:
            self._send({"id": message["id"], "result": {"decision": "decline"}})
        else:
            self._send({"id": message["id"], "error": {"code": -32000, "message": "Aegis does not auto-resolve server requests"}})

    def _event_count(self) -> int:
        with self._condition:
            return len(self._events)

    def _events_since(self, cursor: int) -> list[dict[str, Any]]:
        with self._condition:
            return list(self._events)[cursor:]

    def _wait_for_turn(self, thread_id: str, turn_id: str, cursor: int, *, timeout: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                for event in list(self._events)[cursor:]:
                    if event.get("method") != "turn/completed":
                        continue
                    turn = event.get("params", {}).get("turn", {})
                    if turn.get("id") == turn_id and (turn.get("threadId") in {None, thread_id}):
                        return event
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Codex turn did not complete before the Aegis timeout")
                self._condition.wait(timeout=min(remaining, 1.0))
