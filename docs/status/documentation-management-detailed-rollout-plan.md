# Documentation Management Detailed Rollout Plan

## Purpose

This document turns the documentation audit into an executable rollout plan.

Reader: a maintainer or coding agent preparing to reorganize DevFrame documentation without breaking public review paths, losing historical evidence, or promoting old status notes into current product truth.

Post-read action: execute the rollout phase by phase, stopping after each phase to verify discoverability, authority, and link integrity.

Lifecycle state: Historical plan; scheduling superseded by `HANDOFF.md`.

Related docs:

- `docs/README.md`
- `docs/status/documentation-management-audit-and-plan.md`
- `docs/status/reviewer-index.md`

## Scope

This plan covers only documentation management under `docs/` and links from repository-level documentation.

In scope:

- documentation entry points;
- status-document lifecycle labels;
- classification of existing status documents;
- rules for promotion from `status/` to stable docs;
- future archive structure;
- lightweight docs verification;
- reviewer-index alignment.

Out of scope for this plan:

- rewriting product behavior;
- moving code modules;
- changing schema contracts except for future docs metadata if needed;
- creating a full documentation website;
- deleting historical evidence.

## Current Baseline

Current observed shape:

```text
docs/
  README.md
  module-sources.md
  agent-runtime/
  assets/
  examples/
  status/
```

Current strengths:

- `agent-runtime/` already behaves like a stable reference area.
- `status/` preserves evidence, recon receipts, and planning decisions.
- `reviewer-index.md` gives reviewers a public-snapshot map.
- new context/workflow/model-performance planning docs are now discoverable from `docs/README.md`.

Current weaknesses:

- `status/` is still flat and mixes active plans, release state, evidence, recon receipts, historical stage reports, and prompts.
- most status documents do not declare lifecycle state.
- old stage reports can look as authoritative as current plans.
- no docs check exists to catch orphaned planning docs.
- no rule says when a document should move from `status/` to stable runtime docs.

## Target End State

The desired documentation system has these properties:

1. A new reader starts from `README.md` or `docs/README.md`.
2. Stable runtime rules live in `docs/agent-runtime/`.
3. Current planning and evidence stay in `docs/status/`.
4. Historical documents remain available but clearly marked.
5. Every active plan is linked from `docs/README.md`.
6. Every public-snapshot document relevant to review is linked from `reviewer-index.md`.
7. No document becomes authoritative just because it exists.
8. Documentation changes can be checked with a lightweight script or test.

## Document Type Taxonomy

Use these types for classification:

| Type | Meaning | Default Home |
|---|---|---|
| `product-entry` | user-facing start page and product overview | root README files |
| `docs-map` | navigation and authority map | `docs/README.md` |
| `stable-reference` | durable runtime concepts, contracts, policies | `docs/agent-runtime/` |
| `task-guide` | step-by-step user workflow | future `docs/guides/` |
| `active-plan` | approved direction, not yet implemented contract | `docs/status/` |
| `recon-receipt` | scoped pre-work, reuse assessment, decision record | `docs/status/` |
| `release-state` | current release readiness and review map | `docs/status/` |
| `evidence-record` | proof, audit note, live roundtrip evidence | `docs/status/` |
| `historical-stage` | old stage report kept for traceability | `docs/status/` now, archive later |
| `handoff` | next-agent or continuation prompt | `docs/status/` now, archive later |
| `fixture` | negative/positive machine-checkable example | `docs/agent-runtime/negative-test-fixtures/` or schemas |
| `example` | small reader-facing integration sample | `docs/examples/` |

## Phase 0: Freeze And Baseline

Goal: prevent accidental churn before the classification exists.

Actions:

1. Do not move any existing status files yet.
2. Record that `docs/README.md` is the documentation map.
3. Treat `documentation-management-audit-and-plan.md` as the policy document.
4. Treat this file as the rollout execution plan.
5. Run a scoped file listing of `docs/` before any future movement.

Exit criteria:

- `docs/README.md` links the active planning docs.
- `reviewer-index.md` links the active planning docs that affect the public snapshot.
- future agents know not to mass-move `docs/status/` in one pass.

Verification:

```powershell
Test-Path docs\README.md
Test-Path docs\status\documentation-management-audit-and-plan.md
Test-Path docs\status\documentation-management-detailed-rollout-plan.md
Select-String -Path docs\README.md -Pattern "Documentation Management"
Select-String -Path docs\status\reviewer-index.md -Pattern "documentation-management"
```

## Phase 1: Add Lifecycle Headers To Active Plans

Goal: make current planning documents visibly non-final.

Target documents:

- `workflow-consolidation-and-command-plan.md`
- `context-management-architecture-plan.md`
- `context-led-model-performance-control-plan.md`
- `documentation-management-audit-and-plan.md`
- `documentation-management-detailed-rollout-plan.md`

Required header fields:

```text
Lifecycle state:
Reader:
Post-read action:
Related docs:
Promotion target:
```

Rules:

- Do not add YAML front matter yet unless a parser needs it.
- Use plain Markdown fields to minimize tooling impact.
- Mark each plan as `Draft active plan` unless implementation has already landed.
- Add `Promotion target` only if there is a likely stable doc home.

Exit criteria:

- active planning docs cannot be mistaken for final product contracts;
- all active planning docs point to related docs;
- `docs/README.md` remains the map, not a duplicate of each plan.

Verification:

```powershell
Select-String -Path docs\status\*.md -Pattern "Lifecycle state:" |
  Select-String -Pattern "workflow-consolidation|context-management|context-led|documentation-management"
```

## Phase 2: Classify Existing Status Files

Goal: turn `docs/status/` from a flat pile into a known ledger.

Create a classification table in a new or existing status index.

Recommended file:

```text
docs/status/status-document-inventory.md
```

Required columns:

| Column | Meaning |
|---|---|
| Path | document path |
| Type | taxonomy type |
| Lifecycle | current, draft, implemented, superseded, archive |
| Current authority? | yes/no |
| Related stable doc | target stable doc if any |
| Suggested action | keep, label, promote later, archive later |

Initial classification rules:

- `release-readiness.md` -> `release-state`, current authority yes.
- `reviewer-index.md` -> `release-state`, current authority yes.
- `recon-receipt-*.md` -> `recon-receipt`, authority scoped to its receipt.
- `local-agent-control-plane-stage-*.md` -> `historical-stage`, authority no unless referenced by release readiness.
- `next-agent-*.md` and `continue-*.md` -> `handoff`, authority no after consumed.
- `*-plan.md` and `*-roadmap.md` -> usually `active-plan` or `historical-stage`; classify manually.
- `evidence-*.md` -> `evidence-record`, authority only for the exact evidence scope.

Exit criteria:

- every status file has one type;
- active plans are distinguishable from historical reports;
- no file movement has happened yet.

Verification:

```powershell
Test-Path docs\status\status-document-inventory.md
Select-String -Path docs\status\status-document-inventory.md -Pattern "release-readiness.md"
Select-String -Path docs\status\status-document-inventory.md -Pattern "recon-receipt"
Select-String -Path docs\status\status-document-inventory.md -Pattern "historical-stage"
```

## Phase 3: Define Archive Structure Without Moving Files

Goal: decide how archive paths will work before touching files.

Candidate future structure:

```text
docs/status/
  README.md
  release/
  active/
  receipts/
  evidence/
  archive/
```

Recommended first version:

- keep physical files in place;
- add classification and lifecycle labels;
- defer directory moves until links can be checked automatically.

Why not move immediately:

- old status docs may be linked from README, reviewer index, release notes, or external references;
- git history is easier to read before mass movement;
- current public-snapshot review expects known paths.

Exit criteria:

- a future archive structure is documented;
- no mass movement occurs without link checker support;
- reviewer index remains stable.

## Phase 4: Add Documentation Templates

Goal: reduce drift in new documents.

Recommended folder:

```text
docs/templates/
```

Initial templates:

- `status-plan-template.md`
- `recon-receipt-template.md`
- `stable-reference-template.md`
- `task-guide-template.md`

Template requirements:

- one-sentence purpose;
- named reader;
- post-read action;
- lifecycle state;
- related docs;
- verification or review checklist.

Exit criteria:

- future planning docs stop inventing their own structure;
- `documentation-management-audit-and-plan.md` can point to reusable templates;
- new docs become easier to review.

Verification:

```powershell
Test-Path docs\templates\status-plan-template.md
Test-Path docs\templates\recon-receipt-template.md
Test-Path docs\templates\stable-reference-template.md
Test-Path docs\templates\task-guide-template.md
```

## Phase 5: Add A Lightweight Docs Check

Goal: make discoverability testable.

Recommended script:

```text
scripts/verify-docs-map.ps1
```

Initial checks:

1. `docs/README.md` exists.
2. `docs/status/reviewer-index.md` exists.
3. active planning docs listed in `docs/README.md` exist.
4. public-snapshot status docs listed in reviewer index exist.
5. active planning docs contain `Lifecycle state:`.
6. no `docs/status/*-plan.md` file is orphaned from `docs/README.md` unless explicitly marked archive or superseded.

Exit criteria:

- documentation map drift is caught before release;
- the check can be added to existing public snapshot verification later.

Verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-docs-map.ps1
```

## Phase 6: Promote Stable Content

Goal: move proven architecture from status plans into durable runtime docs.

Promotion candidates after implementation:

| Plan | Stable Destination |
|---|---|
| workflow consolidation | `docs/agent-runtime/command-model.md` or update existing operating docs |
| context management | `docs/agent-runtime/context-management.md` |
| context-led model performance | `docs/agent-runtime/model-performance-control.md` |
| documentation management | `docs/agent-runtime/documentation-governance.md` only if needed |

Promotion criteria:

1. implementation exists;
2. tests or reviewer evidence exist;
3. behavior is expected to remain stable;
4. the stable doc is rewritten for a cold reader;
5. status doc is marked implemented or superseded;
6. links are updated in `docs/README.md` and `reviewer-index.md`.

Exit criteria:

- stable docs explain current behavior;
- status docs preserve decision history without competing for authority.

## Phase 7: Optional Physical Reorganization

Goal: move files only after classification and link checks are reliable.

Candidate movement rules:

- `recon-receipt-*.md` -> `docs/status/receipts/`
- active plans -> `docs/status/active/`
- release docs -> `docs/status/release/`
- consumed handoffs -> `docs/status/archive/handoffs/`
- old stage reports -> `docs/status/archive/stages/`

Hard stop conditions:

- do not move files if reviewer index cannot be updated in the same change;
- do not move files if public snapshot verification assumes old paths;
- do not move files if external docs reference them;
- do not mix physical movement with content rewriting in one large batch.

Exit criteria:

- file movement is mechanical and reviewable;
- old authority relationships remain clear.

## Ownership Model

Borrowing from mature open-source docs governance, feature authors own feature content, while docs governance owns structure, standards, and review.

For DevFrame:

- implementation owner writes or updates feature docs;
- reviewer checks whether the doc type and lifecycle state are correct;
- release reviewer checks `reviewer-index.md`;
- docs governance check keeps `docs/README.md` and status inventory current.

This avoids a bottleneck where one "docs owner" must understand every feature, while still preventing documentation sprawl.

## Review Checklist For Each Phase

Before closing a phase, answer:

1. Did this make current guidance easier to find?
2. Did this reduce authority drift?
3. Did this preserve historical evidence?
4. Did this avoid unnecessary file movement?
5. Did this keep public reviewer paths intact?
6. Did this create a reusable rule rather than a one-off cleanup?
7. Did this leave the next phase obvious?

## Immediate Next Slice

The next useful implementation slice is Phase 1 plus a small part of Phase 2:

1. add lifecycle headers to active planning docs;
2. create `docs/status/status-document-inventory.md`;
3. classify only the current active plans, release docs, and recon receipt pattern first;
4. do not move files yet;
5. add a reviewer note explaining that physical reorganization is intentionally deferred.

This gives the project better document authority with minimal risk.

## Working Thesis

The right cleanup is not a dramatic folder shuffle. It is a controlled lifecycle system:

> map first, label second, inventory third, verify fourth, promote only after implementation, and archive only when links are protected.
