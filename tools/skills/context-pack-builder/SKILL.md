---
name: context-pack-builder
description: Context packet and handoff preparation workflow. Use when user says "@context-pack", "context pack", "context snapshot", "prepare context", "handoff context", "review package", "上下文包", "上下文快照", or when an agent must choose, compress, cite, and explain project context for another agent, reviewer, web AI, or governance fixture.
---

# context-pack-builder - Context Packet Discipline

Role: methodology skill, not a storage engine. Use it to choose and explain the
context that another agent or reviewer should rely on.

## Core Rule

Context preparation is reduction, not accumulation. A good packet says what was
selected, what was omitted, why it is current, and what cannot be inferred from
it.

## Workflow

1. Identify the reader and decision.
   Examples: coding agent, external web AI reviewer, evidence reviewer,
   release reviewer, or future handoff agent.

2. Start from navigation docs.
   Use `docs/README.md`, `docs/status/status-document-inventory.md`, and the
   task-specific active plan before reading broad historical material.

3. Classify candidate files.
   Separate stable contracts, active plans, recon receipts, evidence records,
   handoffs, historical stages, generated exports, and private runtime state.

4. Select the smallest sufficient set.
   Include only files that affect the requested decision. Prefer exact paths,
   schema files, tests, and current plans over narrative recaps.

5. Record omitted important context.
   If a relevant source is stale, private, too broad, conflicting, or excluded
   for scope, say so explicitly.

6. State freshness and authority.
   Mark whether each source is stable, active-plan, evidence-record, handoff,
   or historical. Do not treat the newest markdown file as automatically
   authoritative.

7. Keep generated bundles optional.
   Create a ZIP or copied packet only when the user asks for an uploadable or
   portable bundle. Otherwise provide paths and a concise coverage ledger.

## Minimal Context Ledger

Use this shape in reports or handoffs:

```text
Reader:
Decision needed:
Selected sources:
- path | authority | why included
Omitted relevant sources:
- path | reason omitted | risk
Known gaps:
Verification:
```

## Hard Stops

- Do not include secrets, browser profiles, raw private session transcripts, or
  local agent state in public or external context.
- Do not hide a missing high-impact source.
- Do not use cross-project memory as current project evidence without
  verification.
- Do not make a package larger just to look comprehensive.
