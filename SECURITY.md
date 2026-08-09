# Security Policy

## Dependency audit status

Dependencies are installed into an isolated virtual environment and audited with `pip-audit`. The current dependency set has one explicitly evaluated advisory:

- `PYSEC-2026-311` / `CVE-2026-45829` affects ChromaDB 1.0.0 and later when its unauthenticated HTTP server accepts a malicious model repository with `trust_remote_code=true`.
- This project does not start Chroma's HTTP server or expose its API. It uses only the in-process `PersistentClient` with a deterministic local embedding function.
- `CHROMA_SERVER_ENABLED=false` is required, the security audit checks for Chroma listeners, and the dashboard/runtime never import or invoke Chroma's server CLI.
- The latest unaffected pre-1.0 release requires a native `chroma-hnswlib` build that is unavailable on the supported Python 3.12 Windows runtime without adding a compiler toolchain.

The advisory waiver is limited to `PYSEC-2026-311`. No future or unrelated finding is automatically accepted. Run:

```powershell
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off --ignore-vuln PYSEC-2026-311
```

If Chroma publishes a fixed Windows-compatible release, remove this waiver and upgrade immediately.

## Windows volume-encryption attestation

The Aegis process must not run as administrator. Windows restricts live BitLocker inspection to elevated callers, so a narrow scheduled task performs that single check as `SYSTEM` and writes a non-secret status document under `C:\ProgramData\AI_Agency\Security`.

- The directory grants full control only to `SYSTEM` and local administrators; standard users receive read/execute access.
- The attestation contains status, percentage, method, timestamp, and protector-presence booleans. It never contains the recovery password.
- Aegis accepts the attestation only for its own drive and only for 30 hours.
- The verifier accepts Windows Device Encryption's `Used Space Only Encrypted` wording only when encryption is 100% and protection is on.
- Missing, stale, partial, or unprotected status blocks ChromaDB and runtime startup.

## Ollama controlled-maintenance policy

Normal operation uses two program-scoped Windows Firewall rules to block outbound internet connections from Ollama Desktop and the Ollama server. The API remains bound to `127.0.0.1`, so local inference continues normally.

- Maintenance mode is administrator-only and refuses to start while the Aegis runtime, dashboard, or project Python process is running.
- Entering and exiting maintenance mode is recorded in an administrator-protected JSONL ledger.
- Exiting maintenance mode restores both block rules and refreshes the security attestation.
- The daily audit requires a fresh administrator attestation showing both rules enabled as outbound blocks.
- Maintenance mode is only for approved application updates and model downloads. Sensitive workloads are prohibited until protected mode and the security audit are restored.

## Reporting and operating boundaries

Do not open a network listener for ChromaDB, Ollama, Streamlit, or internal services. Streamlit and Ollama must bind to `127.0.0.1`. Do not paste client data, credentials, or private business records into an issue or public GitHub discussion. Rotate any credential that is accidentally exposed.
