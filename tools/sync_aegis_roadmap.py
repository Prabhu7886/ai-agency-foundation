"""Synchronize the approved Aegis implementation roadmap into encrypted tasks."""

from __future__ import annotations

from dotenv import load_dotenv

from aegis_core.store import AegisStore
from utils.paths import agency_root


ROADMAP = [
    (
        "Roadmap 2 · Scheduled World Pulse and approved sources",
        "Build local scheduling, approved-source curation, run-now controls, freshness status, and audit evidence. "
        "Credentialed social connections require owner approval.",
        "medium",
    ),
    (
        "Roadmap 3 · Recurring Opportunity Engine",
        "Create recurring evidence-backed market discovery, candidate deduplication, opportunity scoring, and stop criteria.",
        "medium",
    ),
    (
        "Roadmap 4 · Expand Aegis Academy",
        "Add modules, notes, quizzes, exercises, projects, and approval-gated skill proposals with evaluation and rollback.",
        "medium",
    ),
    (
        "Roadmap 5 · AI feedback and controlled learning",
        "Add per-response feedback and visible inferred preference proposals with reason, confidence, confirmation, "
        "disabling, evaluation, and rollback.",
        "medium",
    ),
    (
        "Roadmap 6 · Voice and avatar upgrade",
        "Add continuous local conversation states, interruption handling, avatar states, permissions, and local-audio "
        "privacy verification.",
        "medium",
    ),
    (
        "Roadmap 7 · Platform completion and hardening",
        "Complete search, notifications, settings, backups, recovery, updates, endurance checks, security verification, "
        "and operating runbooks.",
        "high",
    ),
]


def sync() -> list[dict[str, str]]:
    load_dotenv(agency_root() / ".env", override=False)
    store = AegisStore()
    store.initialize()
    projects = store.list_projects()
    if not projects:
        raise RuntimeError("Aegis has no registered project")
    project = projects[0]
    existing = {task["title"]: task for task in project.get("tasks", [])}

    for title, prompt, risk in ROADMAP:
        if title not in existing:
            task = store.create_task(project["id"], title, prompt, risk, "Internal Engineering")
            existing[title] = task

    first = existing[ROADMAP[0][0]]
    if first["status"] == "planned":
        existing[first["title"]] = store.update_task(
            first["id"],
            "running",
            "Implementation started: capability/status note and durable roadmap queue created.",
        )

    return [{"title": title, "status": existing[title]["status"]} for title, _, _ in ROADMAP]


if __name__ == "__main__":
    for item in sync():
        print(f"{item['status']:>9}  {item['title']}")
