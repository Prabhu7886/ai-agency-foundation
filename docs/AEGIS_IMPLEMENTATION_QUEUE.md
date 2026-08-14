# Aegis Working Queue

Queue created: 2026-08-10

The queue follows the approved order. Only one major workstream should be marked `RUNNING` at a time. Credentialed integrations and authority changes pause for owner approval.

| Order | Workstream | State | First functional milestone | Completion evidence |
|---:|---|---|---|---|
| 2 | Scheduled World Pulse and approved sources | COMPLETE | Local schedules create single-use research approvals and dedicated owner-approved source lanes | 53-test control-plane suite, encrypted persistence, approval checks, and source-lane tests |
| 3 | Recurring Opportunity Engine | COMPLETE | Stored Pulse evidence becomes deduplicated validation candidates on owner-configured cycles | Independent-domain/freshness gates, deduplication tests, and explicit customer-validation stop |
| 4 | Aegis Academy expansion | COMPLETE | Verified materials and passed assessments gate course completion and learning proposals | Encrypted persistence, evidence/assessment tests, existing eval and rollback path |
| 5 | AI feedback and controlled learning | COMPLETE | Explicit feedback and completed-course learning remain visible and reversible | No silent authority changes; major updates remain approval-gated |
| 6 | Voice and avatar upgrade | COMPLETE FOR MVP | Local processing/speaking states, interruption, fallback, and raw-audio deletion | Local-only service controls and dashboard state surface |
| 7 | Platform completion and hardening | COMPLETE FOR MVP | Search, encrypted backup approvals, restore drills, stack startup, all-dashboard launcher, Desktop access, and operations status | Production build, 60 backend tests, 23 Commerce tests, 17 Career tests, browser acceptance, and operations runbook |
| 8 | Digital identity control plane | COMPLETE FOR LOCAL MVP | Encrypted identity profile, locked portrait/full-body registry, consented companion sessions, and private incognito chat | 60 backend tests, TypeScript validation, production build, local vision inference, and digital identity contract |
| 9 | Smart Hybrid API conversation | DEFERRED BY OWNER | Secure Platform key, $10 hard budget, public/sanitized routing, feedback ledger, and local fallback | Resume only after owner can authenticate to OpenAI Platform |
| 10 | Local screen understanding | COMPLETE FOR LOCAL MVP | One owner-triggered frame, optional edge crop, loopback-only in-memory vision, zero raw retention | `gemma3:4b` installed through controlled maintenance; local visual inference passed; model unloaded after use; outbound blocking restored |
| 11 | Conversational learning | IMPLEMENTED | Natural low-risk prompt wrapper, encrypted ratings/corrections, owner-reviewed training candidates | Collect real owner feedback; do not fine-tune automatically |
| 12 | Digital embodiment | PARTIAL | Full-body identity and browser idle/listening/speaking motion preview | Choose layered 2D asset or evaluate offline renderer before true lip sync |

## Agent Fleet integration contract

Every specialist agent connected to Aegis must implement the same bounded contract:

1. Identity: stable agent ID, purpose, owner, model policy, version, and declared capabilities.
2. Health: heartbeat, last successful run, current state, errors, and resource/cost indicators.
3. Task intake: explicit task envelope with project, scope, data classification, deadline, and required approvals.
4. Results: summary, artifacts, citations/evidence, confidence, freshness, limitations, and proposed next action.
5. Approval requests: exact action, risk, destination, data involved, cost, expiry, and rollback information.
6. Security events: permission failures, secret/PII detection, policy violations, and unsafe-output alerts.
7. Skill reporting: skill IDs and versions used, evaluation results, proposed improvements, and compatibility.

Commerce and Career Studio now implement the approved local bridge contract and remain independent runtimes. Aegis monitors sanitized telemetry, enforces capability or full-agent containment, records incident reports, and distributes evaluated learning updates. Direct task dispatch remains a later authority decision.

## Agent Fleet supervision delivery

| Step | Result | State |
|---:|---|---|
| 1 | Reconciled Commerce and Career behind a common bridge without merging private stores | COMPLETE |
| 2 | Versioned authenticated loopback Agent Bridge | COMPLETE |
| 3 | Live Agent Fleet status, domain metrics, tasks, approvals, skills, and studio links | COMPLETE |
| 4 | Threshold-based abnormal-behavior detection | COMPLETE |
| 5 | Capability pause, severe-threat quarantine, incident reports, and recovery approvals | COMPLETE |
| 6 | Completed-course low-risk auto-deployment plus major-update approvals and rollback | COMPLETE |
| 7 | Agent Fleet performance, task, skill, security, incident, control, and learning views | COMPLETE |
| 8 | Failure-path and policy tests | COMPLETE |
| 9 | Operational and recovery documentation | COMPLETE |
| 10 | Business-phone notification channel | DEFERRED UNTIL OWNER HAS PHONE |
