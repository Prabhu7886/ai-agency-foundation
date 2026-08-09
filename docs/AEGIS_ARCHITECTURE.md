# Aegis Architecture and Delivery Contract

## Product definition

Aegis is the owner's local executive AI: a secure control plane for projects, specialist agents, reusable skills, evidence, approvals, and business decisions. It inherits the AI Agency Foundation security model instead of creating a parallel trust system.

The operating standard is:

- Tell the truth, label uncertainty, and cite current public evidence.
- Find a workable path without pretending that blocked or unverified work is complete.
- Keep primary inference and private data local.
- Require human approval for consequential, external, destructive, financial, credentialed, or privacy-sensitive actions.
- Record what was requested, what ran, what evidence was produced, and what changed.

## Why FastAPI and React

FastAPI plus React is the long-term default for Aegis.

FastAPI keeps the control plane in Python beside the existing agents, SQLCipher storage, Ollama runtime, schedulers, and security checks. Typed request contracts and explicit routes make approval and audit boundaries reviewable. React is a better fit than Streamlit for a durable Codex-style project interface, nested workspaces, task threads, real-time activity, plugin states, and future desktop packaging.

Streamlit remains useful as the existing operational dashboard and rapid diagnostic surface. It is not removed. The two interfaces can coexist while the React workspace becomes the main executive product.

The architecture should be reconsidered only if measured constraints justify it, such as a hard desktop distribution requirement, multi-user tenancy, or a need for a separately scaled event system. None of those require replacing FastAPI or React today.

## Product hierarchy

Workspaces are permanent executive surfaces:

1. Executive Home
2. Agent Fleet
3. World Pulse
4. Opportunity Engine
5. Solution Factory
6. Approval Center
7. Security Sentinel
8. Voice Lounge
9. Data Lab

Projects are Codex-style working contexts with a registered local root, optional GitHub repository, tasks, activity, and scoped agent work.

Agents are specialist workers managed by Aegis. The seeded Internal Engineering agent is the first controlled worker for code, tests, GitHub delivery, and technical review.

Skills are reusable capabilities assigned to agents. Content Studio is a skill, not a workspace. New skills can be versioned, evaluated, shared, and improved without changing the executive navigation.

Plugins are controlled connections or tools. The MVP catalog includes Ollama, GitHub, Codex, Gemini, public web research, and local voice. A catalog entry does not imply that credentials or a working adapter already exist.

## Runtime shape

```text
React workspace (127.0.0.1)
        |
        v
FastAPI control plane (loopback-only session)
        |
        +-- FoundationGuard
        |     +-- registered project roots
        |     +-- loopback Ollama endpoint
        |     +-- public-query data filter
        |     +-- offline-mode enforcement
        |
        +-- SQLCipher control database
        |     +-- projects and tasks
        |     +-- agents, skills, and plugins
        |     +-- approvals and activity
        |     +-- World Pulse, opportunities, and solutions
        |
        +-- Ollama local model gateway
        |
        +-- approved public research service
        |
        +-- future adapters: GitHub, Codex, Gemini, local speech
```

## Foundation compliance

The Aegis layer keeps these inherited controls active:

- SQLCipher is mandatory; there is no plaintext database fallback.
- The HTTP service binds to `127.0.0.1`, and middleware rejects non-loopback clients.
- Ollama must use a loopback URL. No cloud model fallback occurs when it is unavailable.
- New project paths must fall under `AI_AGENCY_HOME` or an explicit `AEGIS_PROJECT_ROOTS` entry.
- GitHub repository links must be HTTPS GitHub URLs.
- Public research rejects likely secrets and private/client data patterns.
- Approved research still cannot execute while `AI_AGENCY_OFFLINE_MODE=true`.
- API documentation is disabled unless `AEGIS_ENABLE_API_DOCS=true`.
- Voice is push-to-talk and local-only; the MVP does not upload or claim to transcribe audio.

## Model and integration policy

Local models own routine planning, analysis, private project context, and agent execution. Cloud specialists are exception paths for approved public or redacted work when they materially improve the result.

Codex should be integrated through an explicit adapter, using either its local SDK/app-server interface or a controlled GitHub handoff. A plugin toggle alone must never impersonate a Codex login or claim that a Codex task ran.

GitHub is the main external code launchpad. The intended policy is branch-based work, automated checks, draft pull requests, and human merge. The engineering adapter must remain limited to registered repositories and must never merge or change protection rules silently.

Gemini is optional. Subscription access and API access are separate products, so the adapter must verify an authorized API path and must not assume that a browser subscription supplies application credentials.

## World Pulse truth policy

World Pulse covers public information with material impact on global peace, economics, AI, IT, trade, gold, silver, and business conditions. Country priority is driven by material world impact rather than a permanent short list.

Every stored claim should retain source URL, publisher, publication time, retrieval time, confidence, affected regions, and verification state. Market and public-trade intelligence can include lawfully disclosed politician transactions, corporate insider filings, and institutional holdings. It must distinguish filing date, transaction date, reporting delay, and estimated value ranges.

No unverified headline belongs in an executive briefing. Conflicting sources should remain visible as a conflict, not be averaged into false certainty.

## Delivery status

Implemented in the first vertical slice:

- Encrypted control-plane schema and persistence.
- Exact nine-workspace navigation.
- Codex-style project creation and persistent task threads.
- Local Ollama chat with no cloud fallback.
- Agent, skill, and plugin registries.
- Approval-gated plugin and public-research requests.
- Foundation status and local model health.
- Opportunity 80/20 and solution-stage surfaces.
- Push-to-talk browser capture boundary.
- Aegis brand system, code-native mark, and three generated logo directions.
- Automated control-plane tests and browser acceptance coverage.

Next implementation slices:

1. GitHub adapter for registered repositories, branches, checks, and draft pull requests.
2. Codex engineering adapter with explicit login, per-task approval, redaction, and execution evidence.
3. World Pulse ingestion, source reconciliation, freshness scoring, and scheduled briefings.
4. Local speech-to-text and text-to-speech behind the existing push-to-talk boundary.
5. Data Lab provenance, reversible cleaning recipes, and quality reports.
6. Agent/skill package format, evaluation gates, version promotion, and rollback.
7. Opportunity and Solution workflows backed by evidence, experiments, budgets, and measured outcomes.

Each slice must add tests and pass Security Sentinel review before it can receive broader permissions.
