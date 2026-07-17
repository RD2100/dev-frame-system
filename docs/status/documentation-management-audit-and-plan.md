# Documentation Management Audit and Plan

Lifecycle state: Historical plan; scheduling superseded by `HANDOFF.md`

## Purpose

This document records a critical review of the current `docs/` structure and proposes a document-driven management plan.

Reader: a future maintainer who needs to decide where a new document belongs, which document is authoritative, and how to prevent status notes from becoming permanent product documentation by accident.

Post-read action: classify every new or edited document as stable reference, task guide, explanation, planning/status, evidence, or example before writing it.

## Current Inventory

The current `docs/` directory has four visible areas:

| Area | Current Role | File Count Observed |
|---|---:|---:|
| `agent-runtime/` | durable runtime contracts, policies, explanations, fixtures | 51 |
| `status/` | recon receipts, plans, stage reports, release state, reviewer maps | 51 |
| `examples/` | small consumer examples | 1 |
| `assets/` | documentation images | 1 |

There is also one root-level document, `module-sources.md`.

The split is understandable, but incomplete. The repository has many useful documents, yet it does not clearly tell readers which ones are current, which ones are historical, and which ones are implementation plans.

## External Patterns Worth Reusing

This plan borrows selectively from established documentation systems:

- [Diataxis](https://diataxis.fr/) separates documentation by user need: tutorials, how-to guides, reference, and explanation.
- [GitHub Docs content model](https://docs.github.com/en/contributing/style-guide-and-content-model/about-the-content-model) uses a predictable hierarchy and warns against too many shallow or deep categories.
- [GitHub Docs best practices](https://docs.github.com/en/contributing/writing-for-github-docs/best-practices-for-github-docs) emphasizes audience, core purpose, readability, and scannability.
- [Kubernetes SIG Docs](https://github.com/kubernetes/community/blob/main/sig-docs/charter.md) separates standards/review/coordination from feature authorship.
- [The Good Docs Project](https://www.thegooddocsproject.dev/) is useful as a source of templates, not as a full information architecture to copy wholesale.

The practical lesson for this repo: use a simple content model and a small number of document types. Do not turn `docs/` into a dumping ground for every agent report.

## Critical Assessment

### What Is Good

The current docs already contain real governance value:

- `agent-runtime/` is a credible stable-docs area.
- `status/` preserves decisions, receipts, and evidence instead of leaving them in chat.
- release readiness and reviewer index documents make public-snapshot review easier.
- recon receipts fit this project's reuse-before-building rule.
- negative fixtures make acceptance behavior concrete.

This is better than a polished but empty documentation site. The repository has actual working memory.

### What Is Confusing

The main problem is not lack of content. It is weak information architecture:

- There was no `docs/README.md` entry point.
- `status/` contains current plans, old stage reports, prompts, evidence, roadmaps, and receipts at the same level.
- Several documents sound authoritative even if they are historical.
- New architecture plans are discoverable only if someone already knows their names.
- Stable runtime docs and current planning docs are not clearly separated in the reader's mind.
- There is no rule for when a status document should be promoted, archived, or marked superseded.
- The docs-manager skill expects `PRD.md`, `MVP.md`, and `process.md`, but this repo is not structured like a normal app repo. Applying that pattern literally would add noise.

### What Is Risky

The biggest risk is authority drift.

A future contributor may read an old stage document, a next-agent prompt, or a recon receipt and treat it as the current product contract. That can cause wrong implementation work even if each individual document is accurate in its original context.

The second risk is status-file accumulation. If every planning note stays forever in `docs/status/` without lifecycle labels, the folder becomes less useful as it grows.

## Proposed Documentation Model

Use six document types:

| Type | Purpose | Home |
|---|---|---|
| Product Entry | What this project is and how to start | root README files |
| Stable Runtime Reference | Durable contracts, policies, invariants, operating model | `docs/agent-runtime/` |
| Task Guide | How to complete a specific user task | future `docs/guides/` or package README files |
| Planning / Status | Current plans, recon receipts, roadmaps, release state | `docs/status/` |
| Evidence / Fixture | Testable examples, negative fixtures, evidence summaries | `docs/agent-runtime/negative-test-fixtures/` or `docs/status/` |
| Example | Small consumer examples | `docs/examples/` |

This is a Diataxis-inspired model, adapted to DevFrame's governance-heavy repo.

## Directory Policy

### Root README

The root README should remain product-facing:

- what DevFrame is;
- quick start;
- main command path;
- advanced entrypoints;
- high-level layout.

It should not become a full architecture handbook.

### `docs/README.md`

This should be the documentation map:

- read-first list;
- stable runtime docs;
- current planning docs;
- status/evidence rules;
- governance rules.

This file should stay short and navigational.

### `docs/agent-runtime/`

This is the home for stable concepts:

- operating model;
- runtime invariants;
- tool policy;
- verification gates;
- adapter contracts;
- visual control plane;
- methodology skills;
- durable workflow references.

Promotion rule: a status plan moves here only after the implementation exists and the contract is expected to remain stable.

### `docs/status/`

This is not a permanent manual. It is the project decision and evidence ledger.

Allowed content:

- current release state;
- reviewer index;
- recon receipts;
- active architecture plans;
- stage reports;
- scoped evidence summaries;
- roadmaps and cutover checklists.

Every new status document should include:

- purpose;
- reader;
- post-read action;
- current/superseded/archival status;
- related stable docs;
- review owner or review focus.

### Future `docs/guides/`

This folder should exist only when there are enough task-oriented documents.

Examples:

- set up a governed coding run;
- evaluate a model-output package;
- add a project-local methodology skill;
- bind a Web AI session safely;
- prepare a release evidence pack.

Do not create it just to move one file.

## Lifecycle Policy

Each document should have one lifecycle state:

| State | Meaning |
|---|---|
| Current | reader may rely on it for current work |
| Draft | planning direction, not implementation contract |
| Implemented | plan has been delivered and should be promoted or closed |
| Superseded | kept for history; newer doc owns the guidance |
| Archive | old evidence or stage report, useful only for traceability |

For now, state can be plain text in the document body. A later phase can add front matter if needed.

## Promotion Policy

A document can move from `status/` to stable docs only when:

1. implementation exists;
2. tests or review evidence exist;
3. the behavior is expected to remain part of the public contract;
4. the document has been rewritten for a fresh reader, not preserved as a work log;
5. `docs/README.md` and `reviewer-index.md` point to the promoted location.

This prevents stage reports and planning notes from hardening into accidental reference documentation.

## Template Policy

Use a small set of templates instead of inventing a new shape every time.

### Status Plan Template

Required sections:

- Purpose
- Current State
- Critical Assessment
- Target Model
- Rollout Plan
- Immediate Next Slice
- Review Checklist

### Recon Receipt Template

Required sections:

- Scope
- Existing Assets Reviewed
- Reuse Assessment
- Risks
- Decision
- Required Follow-up

### Stable Runtime Reference Template

Required sections:

- Purpose
- Concepts
- Invariants
- Inputs and Outputs
- Failure Modes
- Verification
- Related Docs

### Task Guide Template

Required sections:

- Goal
- Before You Start
- Steps
- Expected Output
- Troubleshooting
- Next Action

## Recommended Next Steps

### Step 1: Establish The Map

Add and maintain `docs/README.md`.

Exit criteria: a cold reader can find product docs, stable runtime docs, current plans, and evidence records without knowing filenames.

### Step 2: Mark Current Planning Docs

Add lifecycle labels to the newest planning documents:

- workflow consolidation;
- context management;
- context-led model performance;
- documentation management.

Exit criteria: a reader can tell these are active plans, not already-implemented product contracts.

### Step 3: Triage `docs/status/`

Classify status files into:

- active plan;
- current release evidence;
- recon receipt;
- historical stage report;
- next-agent handoff;
- archive candidate.

Exit criteria: `docs/status/` becomes a searchable ledger instead of a flat pile.

### Step 4: Create Archive Rules Before Moving Files

Do not mass-move old docs yet. First define whether archive paths should preserve old links.

Candidate future structure:

```text
docs/status/
  active/
  receipts/
  release/
  archive/
```

Exit criteria: no file movement happens without redirect or reviewer-index updates.

### Step 5: Promote Stable Plans

After implementation, rewrite stable parts into `docs/agent-runtime/`.

Exit criteria: stable docs explain current behavior; status docs explain how the decision was reached.

### Step 6: Add A Docs Check

Add a lightweight verification check later:

- `docs/README.md` exists;
- every current planning doc is linked from `docs/README.md`;
- `reviewer-index.md` links current public-snapshot docs;
- status docs include purpose and reader;
- no new status doc is orphaned.

Exit criteria: documentation discoverability becomes testable.

## What Not To Do

- Do not create many top-level docs folders before the content demands them.
- Do not move all historical files in one batch.
- Do not treat old next-agent prompts as stable docs.
- Do not duplicate root README content in `docs/README.md`.
- Do not apply generic PRD/MVP/process rules literally when this repo needs runtime and governance documentation.
- Do not promote a plan to stable docs before implementation proves it.

## Working Thesis

DevFrame docs should work like the product itself:

> one clear entry point, stable contracts separated from working state, evidence preserved but not confused with current truth, and every new document written for the next reader rather than the current chat.
