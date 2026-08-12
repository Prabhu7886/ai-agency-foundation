# Aegis Capability Status

Last verified: 2026-08-11 · Aegis 0.8.0

This document separates working software from foundations, placeholders, and future intent. A capability is not called operational unless it has an implemented path and verification evidence.

## Working now

| Area | Current capability | Boundary |
|---|---|---|
| AI Workspace | Local Ollama chat, token streaming, encrypted conversation history, prompt compilation, and Llama/DeepSeek/Qwen routing | No automatic cloud fallback; current claims require approved research evidence |
| Approval Center | Security & Operations and Business & Creative queues using one encrypted, single-use execution ledger | Approval does not expand the registered action scope |
| GitHub and Codex | Approval-gated operations against the registered project | No merge, force push, delete, arbitrary shell, or unrestricted filesystem authority |
| World Pulse | Approval-gated public research, source quality, confidence labels, niche filtering, and an internal brief reader | Research runs on demand; social posts are not treated as verified facts |
| Opportunity Engine | Public research reports, evidence scoring, and handoff to Solution Factory | Discovery is initiated by the owner; no autonomous recurring scans yet |
| Solution Factory | Linked solution records and evidence-gated stage transitions | Does not yet run complete build, launch, revenue, or performance programs |
| Aegis Hub | Owner-controlled digital identity, avatar, local push-to-talk surface, Academy course plans, progress, and visible preference memory | No external course credentials; voice depends on configured local speech engines |
| Agent Fleet | Authenticated local bridges for independent Commerce and Career runtimes; 30-second health/metrics/task monitoring; incident reports; capability-level containment; approval-gated recovery; hashed controlled-learning deployment and rollback | Monitoring runs while Aegis is online; private agent payloads never cross the bridge; agents continue independently when Aegis is offline |
| Data Lab | Reversible CSV cleaning plans and approved clean-copy execution | Current operations are bounded to trimming, null normalization, and deduplication |
| Security Sentinel | Foundation status, secret-pattern scanning, risky-code checks, and dependency posture | Static checks support review but are not proof that software is vulnerability-free |

## Not operational yet

- Scheduled World Pulse refreshes and approved public-account monitoring.
- Continuous Opportunity Engine discovery across markets, forums, reviews, and customer complaints.
- Full course ingestion, shared notes, quizzes, exercises, and projects. Bounded completed-course learning updates are operational, but course-platform synchronization is not.
- Automatic feedback analysis and proposed skill improvements with evaluation and rollback.
- Continuous conversational voice, avatar animation, and interruption handling.
- Dashboard-wide search, notifications, settings, backup/recovery controls, and long-duration reliability monitoring.
- Direct Aegis task dispatch into specialist agents. Live supervision is operational, but Aegis does not yet initiate their domain work.
- Production deployment or multi-user access; Aegis remains an owner-operated loopback application.

## Truth rule

UI visibility is not the same as operational automation. Every future capability must move through implementation, tests, runtime evidence, and—when consequential—owner approval before this document marks it working.
