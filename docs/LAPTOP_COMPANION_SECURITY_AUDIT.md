# Laptop Companion Security Audit

Verified: 2026-08-15

## Current operating model

The Executive Partner popup and the full Aegis Hub companion use the same bounded local engine. The owner starts every session, chooses Research, Study, or Task, states the purpose, and chooses standard or private-incognito handling. A browser permission prompt then lets the owner select one screen, window, or tab.

The current MVP is not continuous surveillance. It provides a visible local preview and analyzes one owner-triggered frame per click. The frame is resized to a bounded JPEG, sent only to the loopback Aegis API, analyzed by local Ollama model `gemma3:4b`, and discarded after inference. Screen audio is never requested. The engine has no click, typing, file, browser-history, credential, or background-capture authority.

## Data flow and retention

1. Browser screen-share permission is requested for each session.
2. The selected stream stays inside the local browser preview.
3. A frame is created only after **Observe this step** or **Capture one frame**.
4. The frame travels over loopback to the local vision service.
5. The local model produces text analysis and unloads according to the model routing policy.
6. Raw pixels are discarded; the API reports `raw_frame_retention=discarded_after_inference`.
7. Standard mode saves analysis only after an explicit owner action. Private incognito blocks notes, summaries, and learning candidates and retains only minimal audit metadata.

## Controls verified

- Owner-started session and visible stop/abort/complete controls.
- Browser permission on every screen-sharing session.
- Loopback-only transport and local Ollama inference.
- No recording and no automatic frame sampling.
- One-frame-per-click capture boundary.
- Optional private-edge crop in the full companion workspace.
- Raw-frame deletion after inference.
- Encrypted notes only when explicitly requested in standard mode.
- Incognito blocks content retention and learning.
- Model availability is surfaced in the UI; failure is safe and does not fall back to cloud.

## Audit result

The configured project security scan passed with zero findings. Aegis, Commerce, and Career regression suites passed 61, 23, and 17 tests respectively. Both Agent Bridge v1.0 endpoints report healthy, with zero open incidents after the restart recovery was verified.

One real integration issue was found during the audit: giving Commerce and Career independent encrypted data roots changed the key used by their local supervision bridges, causing Aegis to reject the bridges. The fix separates the agent data key from the supervision transport key. Each agent now keeps its own runtime and database while the bridge reads the Aegis transport key from a local protected environment file path. No key is embedded in source, returned to the browser, or copied into an agent database. A regression test now verifies this separation.

## Remaining boundaries and decisions

- Continuous observation is disabled. Before adding it, the owner must choose capture scope, sampling interval, pause behavior, retention, and private-field masking.
- Recommended future policy: selected tab/window only, a visible session indicator, manual pause, analysis every 15–30 seconds, no raw-frame retention, encrypted text summaries in standard mode, and no content retention in incognito.
- The companion must never receive unrestricted mouse, keyboard, shell, credential, or filesystem authority.
- Sensitive material should be hidden before capture. Visual analysis can still misread a screen; consequential business, security, financial, medical, and legal decisions require verification.
- The active owner session remains active until the owner completes or aborts it; maintenance does not silently close it.
