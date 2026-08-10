# Aegis Working Queue

Queue created: 2026-08-10

The queue follows the approved order. Only one major workstream should be marked `RUNNING` at a time. Credentialed integrations and authority changes pause for owner approval.

| Order | Workstream | State | First functional milestone | Completion evidence |
|---:|---|---|---|---|
| 2 | Scheduled World Pulse and approved sources | RUNNING | Local schedule registry, approved-source registry, manual run-now control, and freshness status | Deterministic tests, encrypted persistence, approval checks, and live dashboard verification |
| 3 | Recurring Opportunity Engine | QUEUED | Convert approved Pulse/research evidence into recurring discovery runs and scored opportunity candidates | Source-backed candidates, deduplication, scoring tests, and stop criteria |
| 4 | Aegis Academy expansion | QUEUED | Modules, notes, quizzes, exercises, projects, and proposed skill updates | Local persistence, progress tests, skill-evaluation gate, and rollback path |
| 5 | AI feedback and controlled learning | QUEUED | Per-response feedback plus reviewable inferred preference proposals | Visible reason/confidence, confirmation/disable controls, evals, and no silent authority changes |
| 6 | Voice and avatar upgrade | QUEUED | Continuous local conversation state, interruption controls, and avatar states | Local-only audio test, permission checks, transcript deletion policy, and fallback behavior |
| 7 | Platform completion and hardening | QUEUED | Search, notifications, settings, backups, recovery, update controls, and endurance checks | Restore drill, security scan, browser QA, CI, and documented operational runbook |

## Agent Fleet integration contract

Every specialist agent connected to Aegis must implement the same bounded contract:

1. Identity: stable agent ID, purpose, owner, model policy, version, and declared capabilities.
2. Health: heartbeat, last successful run, current state, errors, and resource/cost indicators.
3. Task intake: explicit task envelope with project, scope, data classification, deadline, and required approvals.
4. Results: summary, artifacts, citations/evidence, confidence, freshness, limitations, and proposed next action.
5. Approval requests: exact action, risk, destination, data involved, cost, expiry, and rollback information.
6. Security events: permission failures, secret/PII detection, policy violations, and unsafe-output alerts.
7. Skill reporting: skill IDs and versions used, evaluation results, proposed improvements, and compatibility.

The E-commerce Agent and Resume & Interview Prep Agent will be designed in their dedicated Codex tasks. Their approved contracts will be registered here before either receives live authority.
