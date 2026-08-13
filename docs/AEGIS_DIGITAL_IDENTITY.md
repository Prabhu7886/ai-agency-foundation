# Aegis Digital Identity Contract

Last verified: 2026-08-13 · Aegis 0.11.0

## Approved identity

Aegis is the owner's feminine, always-digital executive partner. Her default role is `Digital Executive Partner`, her default pronouns are `she/her`, and her operating style is professional, warm, direct, factual, ambitious, and evidence-aware.

Presentation does not grant authority. These controls are immutable outside reviewed code:

- Aegis discloses that she is artificial rather than presenting herself as human.
- The owner retains final authority.
- Aegis cannot expand her permissions.
- Risky, sensitive, external, financial, publishing, credentialed, or system-changing work remains policy- and approval-gated.
- Learned preferences may shape communication but cannot weaken the Truth Standard or security policy.

The editable profile is stored in SQLCipher. The dashboard can change the display name, role title, pronouns, conversation style, presentation mode, and descriptive traits. It cannot edit the authority model, truth standard, or always-digital embodiment.

## Presentation and privacy modes

| Mode | Intended use | Persistence | Identity disclosure |
|---|---|---|---|
| Executive | Private business planning and owner conversation | Encrypted local records | Aegis digital identity |
| Study | Courses, practice, review, and owner-guided learning | Encrypted local records | Aegis digital identity |
| Studio | Owner-approved videos and public content | Project records and approvals | Explicit AI identity |
| Public incognito | Neutral public presentation that removes owner and project identifiers | Governed content record | Still disclosed as AI |
| Private incognito | Sensitive one-on-one local conversation | No conversation, task, prompt, memory, or learning record | Local Aegis UI only |

Private incognito is technically enforced in the streaming chat path. It is local-only, has no cloud route, refuses saved conversation IDs, and returns only ephemeral UI messages. Companion-session incognito retains minimal timestamps and mode metadata for security audit but drops purpose, notes, learning candidates, and closing summaries.

## Visual identity assets

The encrypted asset registry currently tracks:

1. `identity-portrait-v1` — active face and upper-body identity reference.
2. `identity-full-body-v1` — versioned full-body reference for future video production.
3. `identity-motion-rig-v1` — browser motion preview active; offline render rig remains a separate planned package.

The portrait and full-body assets are identity-locked. A future production pipeline must preserve the face, hairstyle, digital circuitry, executive clothing language, and explicit non-human identity. It may create scene-specific renders without silently replacing the master identity.

## Laptop companion boundary

The Companion tab starts owner-consented study, task, research, or creative sessions. Screen access uses the browser's `getDisplayMedia` permission prompt every time.

Current data flow:

```text
Owner selects a screen/window
        |
        v
Browser-only live preview
        |
        +-- no frame upload
        +-- no frame recording
        +-- one owner-triggered frame at a time
        +-- raw frame validated, analyzed in memory, then discarded
        +-- no background watching or recording
        +-- owner may write explicit local notes
                    |
                    +-- ordinary encrypted note, or
                    +-- proposed learning candidate requiring review
```

The current release implements bounded local screen understanding with the configured `gemma3:4b` Ollama model. Availability remains false until that model is installed. The owner must start a screen-enabled companion session, grant browser permission, optionally crop private edges, capture one visible frame, and click Analyze. The frame is downscaled in the browser, limited to 1.5 MB, validated by media signature, sent only to the loopback API, processed in memory, and discarded. Aegis never samples automatically. Only the returned text can be saved, and private incognito blocks that save.

## Conversation improvement

Ordinary discussion receives a lightweight hidden conversational rewrite rather than a second model-generated execution contract. This reduces delay and keeps the response natural. Requests that can change state still use the full bounded compiler and risk classification.

The owner can mark a saved assistant answer Helpful, Too generic, Incorrect, or Missed intent. Each rating creates an encrypted local training candidate containing bounded excerpts. No model is fine-tuned automatically. A correction becomes a confirmed communication preference only after the owner approves it in Aegis Hub.

## Avatar motion boundary

The full-body identity has local idle, listening, and speaking presentation states rendered in the browser. This is motion-ready UI feedback, not phoneme-accurate lip sync. A production lip-sync renderer is deferred because the current master is not layered and the laptop has 8 GB VRAM; installing an unverified heavy renderer would compete with Ollama and is not justified yet.

## Learning governance

- Owner-written preferences may be confirmed directly when they affect presentation only.
- Inferred preferences and companion notes marked for learning enter `proposed` state.
- A learning candidate is not a trained model update.
- Authority-changing learning is always proposal-only.
- Private incognito blocks notes and learning candidates.
- Course knowledge still follows material verification, assessment, evaluation, deployment report, and rollback controls.

## Conversation behavior

The local model now receives the encrypted identity profile and confirmed non-authority owner preferences as bounded context. It is instructed to keep ordinary one-on-one discussion natural, disclose its digital identity when asked, and avoid promising memory in private incognito. Local response context is 8,192 tokens with a 1,024-token standard output budget; concise requests remain bounded separately.

## Deferred work

- OpenAI API and Smart Hybrid routing are deliberately deferred until the owner can complete Platform authentication.
- Offline motion rendering, repeatable phoneme lip sync, and reusable video poses.
- Local vision analysis for consented screen sessions.
- Public identity accounts and publishing adapters.
- Full conversational feedback/evaluation dataset and model fine-tuning.

No deferred item is represented as operational in the dashboard.
