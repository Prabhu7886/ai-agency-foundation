"""Priority task queue and recurring secure job scheduler."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import schedule

from utils.logger import get_logger


@dataclass(order=True)
class QueuedTask:
    priority: int
    sequence: int
    name: str = field(compare=False)
    callback: Callable[..., Any] = field(compare=False)
    args: tuple[Any, ...] = field(default_factory=tuple, compare=False)
    kwargs: dict[str, Any] = field(default_factory=dict, compare=False)
    security_validated: bool = field(default=False, compare=False)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), compare=False)


class SecureTaskScheduler:
    def __init__(self) -> None:
        self.logger = get_logger("scheduler")
        self._queue: list[QueuedTask] = []
        self._condition = threading.Condition()
        self._counter = itertools.count()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._schedule_worker: threading.Thread | None = None

    def submit(
        self,
        name: str,
        callback: Callable[..., Any],
        *args: Any,
        priority: int = 50,
        security_validated: bool = False,
        **kwargs: Any,
    ) -> QueuedTask:
        if not callable(callback):
            raise TypeError("callback must be callable")
        if not 0 <= priority <= 100:
            raise ValueError("priority must be between 0 and 100")
        if not security_validated:
            raise PermissionError("Task must pass security validation before scheduling")
        task = QueuedTask(priority, next(self._counter), name, callback, args, kwargs, True)
        with self._condition:
            heapq.heappush(self._queue, task)
            self._condition.notify()
        self.logger.info(f"Queued task {name} at priority {priority}")
        return task

    def add_daily_job(self, at_time: str, callback: Callable[[], Any], tag: str) -> None:
        if not re_time(at_time):
            raise ValueError("Daily schedule time must use HH:MM 24-hour format")
        schedule.every().day.at(at_time).do(self._safe_run, tag, callback).tag(tag)

    def add_weekly_job(self, weekday: str, at_time: str, callback: Callable[[], Any], tag: str) -> None:
        weekday_name = weekday.lower()
        if weekday_name not in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
            raise ValueError("Invalid weekday")
        if not re_time(at_time):
            raise ValueError("Weekly schedule time must use HH:MM 24-hour format")
        getattr(schedule.every(), weekday_name).at(at_time).do(self._safe_run, tag, callback).tag(tag)

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run_queue, name="agency-task-worker", daemon=True)
        self._schedule_worker = threading.Thread(target=self._run_schedule, name="agency-schedule-worker", daemon=True)
        self._worker.start()
        self._schedule_worker.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        for worker in (self._worker, self._schedule_worker):
            if worker:
                worker.join(timeout=timeout)

    def pending(self) -> list[dict[str, Any]]:
        with self._condition:
            return [{"name": item.name, "priority": item.priority, "created_at": item.created_at} for item in sorted(self._queue)]

    def _run_queue(self) -> None:
        while not self._stop.is_set():
            with self._condition:
                while not self._queue and not self._stop.is_set():
                    self._condition.wait(timeout=1.0)
                if self._stop.is_set():
                    return
                task = heapq.heappop(self._queue)
            self._safe_run(task.name, task.callback, *task.args, **task.kwargs)

    def _run_schedule(self) -> None:
        while not self._stop.wait(1.0):
            schedule.run_pending()

    def _safe_run(self, name: str, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            result = callback(*args, **kwargs)
            self.logger.info(f"Completed scheduled task {name}")
            return result
        except Exception as exc:
            self.logger.error(f"Scheduled task {name} failed: {exc}", exc_info=True)
            return schedule.CancelJob if name.startswith("one-shot:") else None


def re_time(value: str) -> bool:
    try:
        parsed = time.strptime(value, "%H:%M")
        return 0 <= parsed.tm_hour <= 23 and 0 <= parsed.tm_min <= 59 and len(value) == 5
    except ValueError:
        return False


if __name__ == "__main__":
    scheduler = SecureTaskScheduler()
    scheduler.start()
    scheduler.submit("self-test", lambda: print("scheduler self-test passed"), priority=1, security_validated=True)
    time.sleep(0.5)
    scheduler.stop()
