# Aegis MVP Operations Runbook

Verified for Aegis 0.9.0 on 2026-08-12.

## Start and verify

Run `tools\windows\start_aegis_stack.ps1`. It starts the Aegis loopback service with the virtual environment's no-console Python launcher and starts the Commerce and Career supervision bridges only when their ports are not already listening. It never starts Ollama or opens controlled maintenance.

Verify these loopback endpoints:

- Aegis: `http://127.0.0.1:8000/api/health`
- Commerce bridge: authenticated `http://127.0.0.1:8511/v1/snapshot`
- Career bridge: authenticated `http://127.0.0.1:8512/v1/snapshot`

Bridge endpoints require their local bearer tokens. Use the dashboard instead of exposing those tokens in command history.

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

## Known boundaries

- Business-phone notifications are deferred until the owner has the phone available.
- Aegis monitors Commerce and Career but does not dispatch their domain work.
- Course-platform credentials and social posting remain disconnected.
- The application is single-owner and loopback-only, not a public or multi-user deployment.
- Passing tests and restore drills reduce risk; they do not replace OS hardening, endpoint protection, legal review, or a complete disaster-recovery exercise.
