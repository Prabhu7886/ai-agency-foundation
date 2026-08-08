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

## Reporting and operating boundaries

Do not open a network listener for ChromaDB, Ollama, Streamlit, or internal services. Streamlit and Ollama must bind to `127.0.0.1`. Do not paste client data, credentials, or private business records into an issue or public GitHub discussion. Rotate any credential that is accidentally exposed.
