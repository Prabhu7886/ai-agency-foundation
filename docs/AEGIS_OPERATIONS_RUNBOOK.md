# Aegis MVP Operations Runbook

Verified for Aegis 0.11.0 on 2026-08-15.

## Start and verify

Run `tools\windows\start_all_dashboards.ps1`. It starts the Aegis loopback service, the Commerce and Career supervision bridges, and both independent Streamlit dashboards. Existing healthy services are reused. It never starts Ollama or opens controlled maintenance.

Desktop access:

- `Aegis Executive Dashboard` opens `http://127.0.0.1:8000/`.
- `Aegis Commerce Dashboard` opens `http://127.0.0.1:8501/`.
- `Aegis Career Studio Dashboard` opens `http://127.0.0.1:8502/`.
- `Start All Aegis Dashboards` runs the bounded local launcher after a reboot.

Verify these loopback endpoints:

- Aegis: `http://127.0.0.1:8000/api/health`
- Commerce dashboard: `http://127.0.0.1:8501/_stcore/health`
- Career Studio dashboard: `http://127.0.0.1:8502/_stcore/health`
- Commerce bridge: authenticated `http://127.0.0.1:8511/v1/snapshot`
- Career bridge: authenticated `http://127.0.0.1:8512/v1/snapshot`

Bridge endpoints require their local bearer tokens. Use the dashboard instead of exposing those tokens in command history.

## Latest acceptance evidence

Verified on 2026-08-15:

- Aegis backend: 61 tests passed, including independent agent-data and supervision-key separation.
- Commerce Agent: 23 tests passed; encrypted SQLCipher storage and 17 collections verified during launch.
- Career Studio: 17 tests passed; the sidebar status-rendering defect was corrected and browser-retested.
- Aegis frontend: TypeScript and production Vite build passed.
- Browser acceptance: Aegis Executive Home, live Agent Fleet, Aegis Hub Companion, Commerce, and Career Studio rendered successfully.
- Agent Fleet: Commerce and Career reported healthy through authenticated loopback Bridge v1.0.
- Local vision: `gemma3:4b` completed a real image inference, discarded the raw frame, and unloaded after the request.
- Ollama containment: both outbound-block rules enabled, no external Ollama connections, and no model left occupying VRAM after validation.
- Desktop access: three dashboard shortcuts and one bounded all-dashboard launcher validated under the owner's Desktop folder.
- Interface system: Aegis uses a decision-first Executive Home, four-mode AI Workspace, Mission Control, and global Executive Partner popup. Commerce uses Command Center, Visual Studio, Operations, Intelligence, and AI Assistant. Career uses Career Journey, Application Board, Resume Studio, AI Coach, and Intelligence & Settings. All three rendered successfully with their current light product surfaces.
- Companion audit: `gemma3:4b` is ready; browser permission is required each session; no audio or recording is requested; one owner-triggered frame is analyzed locally and discarded. See `docs/LAPTOP_COMPANION_SECURITY_AUDIT.md`.
- Runtime isolation: Commerce and Career use separate encrypted data roots. Agent Bridge authentication uses the local protected Aegis supervision environment without embedding or copying the key into source or agent data.

## World Pulse schedules

A due schedule creates a pending Security & Operations approval. It does not perform network research by itself. On approval and execution, the adapter sanitizes the public query, adds valid owner-approved HTTPS domains or public handles as dedicated search lanes, verifies bounded public pages, and records source, date, retrieval, confidence, and methodology evidence.

Pause a schedule from World Pulse when a niche is no longer useful. Treat public-account claims as leads until independently corroborated.

## Opportunity cycles

Cycles run locally over stored Pulse signals. A candidate requires fresh evidence from at least two independent domains. Duplicate evidence fingerprints are skipped. Every candidate stops at customer validation; creation is not proof of demand, revenue, legality, or product-market fit.

## Agent containment drill

Use **Run safe drill** in Agent Fleet. The bridge pauses only the synthetic `diagnostic_drill` capability, verifies that a diagnostic task is blocked, and restores it in a `finally` path. Commerce and Career business capabilities remain enabled. Aegis stores the result in the containment-drill ledger.

For a real incident, capability pause and full quarantine follow the thresholds in `AGENT_FLEET_OPERATIONS.md`. Recovery remains approval-gated.

## Academy learning

Add course material only as a public HTTPS reference or with explicit owner attestation for local material. A course cannot be marked complete until progress is 100%, at least one material is verified, and an assessment is passed. Low-risk learning may deploy with a report; major capability or policy changes require approval and retain rollback hashes.

## Encrypted backup and restore drill

Creating a production backup is a Security & Operations action. Request it in Security Sentinel and approve it explicitly; do not bypass the ledger. A restore drill decrypts the selected backup into a temporary directory, verifies every manifest hash, reports the outcome, and deletes the temporary copy. It never overwrites the live system.

Keep the encryption master key in an independent trusted password manager. A backup without the key is not recoverable.

## Voice privacy

Voice is local-only. The service exposes idle, processing, and speaking states and supports interruption. Raw captured audio is deleted after local transcription. Transcripts follow the encrypted conversation-retention policy. Do not enable always-listening behavior for the MVP.

## Laptop companion privacy

Use the Executive Partner button from any Aegis workspace or open the full Companion tab in Aegis Hub. State a purpose, choose standard or private incognito, and select a screen, window, or browser tab in the permission prompt. The current engine never watches automatically: use **Observe this step** to capture one frame for local analysis. Stop sharing before exposing passwords, private messages, financial data, or unrelated windows. Continuous observation remains disabled until a separate policy is approved.

## Known boundaries

- Business-phone notifications are deferred until the owner has the phone available.
- Aegis monitors Commerce and Career but does not dispatch their domain work.
- Course-platform credentials and social posting remain disconnected.
- The application is single-owner and loopback-only, not a public or multi-user deployment.
- Passing tests and restore drills reduce risk; they do not replace OS hardening, endpoint protection, legal review, or a complete disaster-recovery exercise.
