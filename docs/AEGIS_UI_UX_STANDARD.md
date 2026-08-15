# Aegis UI/UX Standard

## Product rule

Aegis and every supervised agent use one cohesive application shell with specialized workspaces inside it. A workspace is designed around a user job, not around a reusable dashboard template.

## Five-second test

Every screen must make these points clear within five seconds:

1. Where am I?
2. What changed?
3. What needs my attention?
4. What is the safest useful next action?
5. What will happen if I take that action?

## Aegis workspace map

- **Executive Home:** daily briefing, owner attention queue, agent health, priorities, World Pulse, and quick actions.
- **AI Workspace:** projects, conversations, research, code, learning, files, generated artifacts, prompt rewrite preview, and approval boundaries.
- **Mission Control:** independent-agent health, current mission, progress, incidents, business approvals, system approvals, and containment controls.
- **Opportunity Engine:** evidence discovery, verification, scoring, proposal generation, and approval handoff.
- **World Pulse:** niche briefings, source transparency, confidence, freshness, and same-window reading.
- **Approval Center:** separate Business and System queues with scope, evidence, risk, cost, and consequences.
- **Security Sentinel:** security posture, incidents, reports, backups, recovery, and owner-controlled remediation.
- **Learning Hub:** courses, practice, evaluation, proposed learning, and controlled release to agents.
- **Data Lab:** preserve, profile, validate, standardize, deduplicate, approve, and report.
- **Aegis Hub:** identity, voice, avatar, companion sessions, privacy, and controlled learning.

## Independent-agent pattern

- Commerce is one agent with Command Center, Visual Studio, and Operations workspaces.
- Career is one agent with Career Journey, Application Board, and AI Coach Studio workspaces.
- Aegis supervises them; it does not absorb their public-facing product experiences.

## Interaction rules

- One visually dominant action per section.
- Use plain language and verbs: Review, Approve, Open agent, Continue, Research, Practice.
- Summaries lead; supporting detail is progressively disclosed.
- Status color is never the only status signal.
- Alerts include cause, impact, evidence, and a next action.
- Empty states explain how to begin; loading states explain what is happening.
- Preserve user context when switching workspaces.
- Search and command access remain globally available.
- Owner approval boundaries remain visible at the action point.

## Visual rules

- Contemporary product UI, not a themed developer dashboard.
- Warm neutral surfaces for thinking and decision work; dark slate only for dense operational monitoring.
- Restrained violet, cobalt, cyan, emerald, amber, and red accents with semantic meaning.
- Strong typography, spacing, alignment, and hierarchy before decorative effects.
- No ornamental KPI walls, fake holograms, cyberpunk HUDs, excessive glow, glassmorphism, decorative grids, or tiny text.
- Responsive layouts at desktop, tablet, and mobile widths.
- Meet WCAG AA contrast, visible keyboard focus, meaningful labels, and reduced-motion preferences.

## Executive Partner observation policy

- Aegis never starts screen access silently.
- The owner chooses the shared screen, window, or tab through the browser permission dialog for every session.
- A persistent visible indicator and Stop control are required while sharing.
- The initial safe mode is local preview plus owner-triggered single-frame analysis.
- Raw frames are discarded after local analysis.
- Standard sessions may save an encrypted text note only when the owner requests it.
- Incognito sessions retain metadata only and cannot save analysis or learning.
- Continuous or timed observation requires a separately approved capture frequency and retention policy.
- Screen observation never grants permission to click, type, submit, purchase, publish, or change files.

## Change-control rule

Interface changes may improve presentation, navigation, accessibility, and task flow. They must not silently change agent logic, permissions, approval gates, security boundaries, data contracts, or retention policy.
