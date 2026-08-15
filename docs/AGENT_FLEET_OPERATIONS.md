# Independent Agent Fleet Operations

## Approved operating model

Aegis is the owner's private executive control plane. Commerce, Career Studio, and future specialist agents remain independent local applications with their own runtime, database, dashboard, and development cycle. Aegis supervises them through an authenticated loopback Agent Bridge instead of merging their code or private records.

The bridge contract is version `1.0`. Authentication is derived from the agency master key for the registered agent ID; bridge secrets are not stored in source or returned to the browser. Requests and bridge servers are restricted to loopback.

## Data crossing the bridge

- Stable identity, purpose, version, capabilities, and declared restrictions.
- Health, current state, heartbeat, and sanitized dependency checks.
- Aggregate task counts, success/failure rates, domain KPIs, and process resource use.
- Task IDs, types, states, and timestamps without prompts or private task payloads.
- Pending approval metadata without credentials.
- Security events, skill versions, containment status, and learning-update hashes.

Customer records, resume text, profile facts, prompts, credentials, files, and marketplace payloads remain inside the owning agent.

## Monitoring and containment

Aegis polls registered bridges every 30 seconds while the Aegis control plane is running. Agents remain operational when Aegis is offline.

Automatic policy:

1. Critical credential exposure, data leakage/exfiltration, malware, or approval bypass quarantines the whole agent.
2. Other high/critical events pause the reported dangerous capability. Safe capabilities continue.
3. A failure rate of at least 50% after five recorded tasks pauses task execution.
4. Agent-process memory pressure of at least 92% pauses model inference.
5. Unexpected agent or skill version changes create a review incident without automatic containment.
6. Bridge loss creates an availability incident only after the agent was previously seen.

Every incident stores evidence, action taken, possible solutions, recovery steps, and notification state in the encrypted Aegis database. Resume and recovery actions require an owner approval. Incident resolution does not silently recover a contained capability.

## Controlled learning

Aegis training initially means verified knowledge, prompt/skill references, and versioned operating guidance—not autonomous weight changes or self-modifying code.

A low-risk learning update auto-deploys only when all conditions pass:

- It is linked to an Academy course marked completed.
- It is between 40 and 50,000 characters.
- It contains no authority-expanding security terms.
- It is explicitly classified low risk.
- Its SHA-256 content hash is verified by the receiving bridge.

Every other update creates a Security & Operations approval. Active learning is stored with authenticated encryption by the independent agent, visibly reported to Aegis, and reversible through an owner-approved rollback.

## Local ports

| Service | Bridge | Dashboard |
|---|---:|---:|
| Commerce | `127.0.0.1:8511` | `127.0.0.1:8501` |
| Career Studio | `127.0.0.1:8512` | `127.0.0.1:8502` |
| Aegis | — | `127.0.0.1:8000` |

Start both independent bridges with `tools/windows/start_agent_bridges.ps1`. The script refuses missing roots or runtimes and opens hidden background processes bound by each server to loopback.

## Recovery drill

1. Review the incident evidence and local agent logs.
2. Correct the smallest affected permission, tool, model, input, or skill version.
3. Run the independent agent's sanitized tests and health snapshot.
4. Request recovery or capability resume in Aegis Approval Center.
5. Approve the single bounded recovery action.
6. Monitor the next operating cycle for recurrence, then mark the incident resolved.
