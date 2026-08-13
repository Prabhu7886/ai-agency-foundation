# Aegis Capability Status

Last verified: 2026-08-12 · Aegis 0.9.0

This document separates working software from foundations, placeholders, and future intent. A capability is not called operational unless it has an implemented path and verification evidence.

## Working now

| Area | Current capability | Boundary |
|---|---|---|
| AI Workspace | Local Ollama chat, token streaming, encrypted conversation history, prompt compilation, and Llama/DeepSeek/Qwen routing | No automatic cloud fallback; current claims require approved research evidence |
| Approval Center | Security & Operations and Business & Creative queues using one encrypted, single-use execution ledger | Approval does not expand the registered action scope |
| GitHub and Codex | Approval-gated operations against the registered project | No merge, force push, delete, arbitrary shell, or unrestricted filesystem authority |
| World Pulse | Approval-gated public research, owner-approved source lanes, recurring schedules, source quality, freshness evidence, confidence labels, niche filtering, and an internal brief reader | Schedules create approval requests; they never silently open a network session, and social posts are not treated as verified facts |
| Opportunity Engine | Recurring local discovery over stored Pulse evidence, independent-domain checks, deduplication, conservative validation candidates, 80/20 allocation, and Solution Factory handoff | It does not claim demand or launch a business without customer validation and owner approval |
| Solution Factory | Linked solution records and evidence-gated stage transitions | Does not yet run complete build, launch, revenue, or performance programs |
| Aegis Hub | Owner-controlled digital identity, avatar, interruptible local voice states, Academy course plans, verified learning materials, assessments, completion gates, and visible preference memory | No external course credentials; voice depends on configured local speech engines, and raw audio is deleted after local transcription |
| Agent Fleet | Authenticated local bridges for independent Commerce and Career runtimes; actual runtime health, encrypted task timing/outcomes, 30-second monitoring, incident reports, isolated containment drills, capability-level containment, approval-gated recovery, and hashed learning deployment/rollback | Monitoring runs while Aegis is online; private payloads never cross the bridge; agents continue independently when Aegis is offline |
| Data Lab | Reversible CSV cleaning plans and approved clean-copy execution | Current operations are bounded to trimming, null normalization, and deduplication |
| Security Sentinel | Foundation status, secret-pattern scanning, risky-code checks, dependency posture, encrypted-backup approval flow, manifest verification, and non-destructive restore drills | A successful drill proves the selected backup can be decrypted and hash-verified; it is not a full disaster-recovery guarantee |
| Workspace operations | Dashboard-wide local search, hidden stack launcher, operations status, and controlled backup/recovery actions | The launcher does not auto-start Ollama and the application remains loopback-only |

## Not operational yet

- Direct course-platform synchronization or credentialed Coursera access. Materials can be added by public HTTPS reference or explicit owner attestation.
- Automatic feedback analysis and proposed skill improvements with evaluation and rollback.
- Always-listening/hotword voice, advanced avatar animation, and long-form duplex conversation.
- Business-phone notifications and long-duration reliability certification.
- Direct Aegis task dispatch into specialist agents. Live supervision is operational, but Aegis does not yet initiate their domain work.
- Production deployment or multi-user access; Aegis remains an owner-operated loopback application.

## Truth rule

UI visibility is not the same as operational automation. Every future capability must move through implementation, tests, runtime evidence, and—when consequential—owner approval before this document marks it working.
