# Reuse-First Constraint Governance Implementation Plan

Lifecycle state: Historical implementation plan; scheduling superseded by `HANDOFF.md`

Plan status: Accepted as the reuse-first planning layer for the review-first
governance kernel. Not yet an implementation claim.

Reader: DevFrame maintainers deciding how to turn project constraints into
reliable agent behavior without depending on model cleverness or hand-rolling a
large platform.

Post-read action: implement the review-first kernel with thin local contracts
first, reuse mature open-source patterns where they fit, and defer new
dependencies until the local fixtures prove the boundary.

Related docs: [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Review-First Governance Kernel Contraction Plan](review-first-governance-kernel-contraction-plan.md), [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Rules Spec](governance-rules-spec.md), [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md)

## Core Idea

Do not trust the model to be clever enough to stay correct.

Make the project strict enough that the model cannot easily create unreviewed
truth.

The target behavior is:

```text
Model proposes or executes
Project constraints validate
Evidence supports or rejects
Decision finalizes
Projection displays
```

This means DevFrame should not build a smarter agent first. It should build a
constraint system around ordinary agents.

## Reuse Survey

The market already has strong pieces, but no single project matches DevFrame's
whole need.

| Area | Reuse candidates | What to borrow | What not to borrow yet |
|---|---|---|---|
| Structured output | [Outlines](https://github.com/dottxt-ai/outlines), [Guardrails AI](https://github.com/guardrails-ai/guardrails), Guidance, LMQL | JSON/schema discipline, validators, constrained generation mindset | Do not make model output validity equal governance truth |
| Policy-as-code | [Open Policy Agent](https://github.com/open-policy-agent/opa), Cedar, OpenFGA | Explicit allow/deny decisions, policy inputs, auditability | Do not introduce a full authorization engine before phase-one decisions are proven |
| Durable workflow | [Temporal](https://github.com/temporalio/temporal), LangGraph | State machine thinking, retries, resumability, human checkpoints | Do not migrate the whole runtime before the review kernel works |
| Agent coding systems | SWE-agent, OpenHands | Tool execution and issue-solving patterns | Do not inherit their completion semantics without evidence gates |
| Evidence and supply-chain style proof | in-toto, SLSA, OpenLineage, MLMD | Provenance, artifact lineage, claim/evidence separation | Do not build a heavy ledger in phase one |

## Current Project Fit

DevFrame already has enough substrate to start without a major dependency:

- project contract concepts;
- rdgoal dispatch and report ingestion concepts;
- workflow and team runtime event concepts;
- evidence, review, gate, and final-verdict schemas;
- visual state and T3 projection surfaces;
- reviewer index and public snapshot verification discipline.

Therefore the first move should be local and thin:

1. define one review governance schema;
2. create success, blocked, insufficient-evidence, and missing-context fixtures;
3. write negative tests;
4. add a small derivation helper only if JSON Schema cannot express the rule;
5. postpone dependency adoption until a concrete gap appears.

## Reuse Decision Matrix

| Capability | Phase-one decision | Reason |
|---|---|---|
| JSON schema validation | Reuse existing Python/jsonschema-style testing if already available; otherwise add the smallest test dependency only if needed | The first slice is schema and fixture validation |
| Constrained decoding library | Do not adopt yet | No generation path exists in the first slice |
| Guardrails AI | Borrow validator concept, do not install yet | The current problem is governance packet validity, not live LLM re-asking |
| OPA/Cedar/OpenFGA | Borrow policy input/output shape, do not install yet | Phase one has only `Decision(kind=review|gate|adopt)` |
| Temporal/LangGraph | Borrow state-machine discipline, do not migrate yet | Existing workflow/team runtime can host early proof |
| in-toto/SLSA/OpenLineage/MLMD | Borrow provenance vocabulary, do not implement ledger yet | Phase one only needs artifact/evidence references |
| Existing DevFrame schemas | Reuse vocabulary selectively | Existing schemas may encode older boundaries; do not blindly compose them |

## Implementation Strategy

### Step 1: Local Contract First

Create the review governance kernel schema and fixtures described in the
implementation spec.

Why: local fixtures reveal whether the object model is coherent before external
libraries complicate the picture.

### Step 2: Negative Tests Before Runtime

Write tests for forbidden shortcuts:

- no context snapshot;
- run success without decision;
- report-only output;
- gate pass without evidence;
- projection claiming completion without gate pass;
- unknown decision kind;
- unexpected top-level object.

Why: this makes the system depend on project constraints instead of model
discipline.

### Step 3: Minimal Derivation Helper

If JSON Schema cannot express status derivation cleanly, add a tiny helper that
computes projection status from packet facts.

Why: computed status is the first proof that projection is not authority.

### Step 4: Evaluate Dependency Gaps

Only after tests exist, ask whether a dependency solves a real local problem:

| If the problem is... | Candidate |
|---|---|
| LLM output cannot reliably match the schema | Outlines or Guardrails AI |
| policy rules become too complex for local code | OPA or Cedar |
| review flow becomes long-running and resumable | Temporal or LangGraph |
| evidence lineage becomes multi-system and audit-heavy | in-toto, SLSA, OpenLineage, or MLMD-inspired records |

### Step 5: Add Dependency Behind An Adapter

If a dependency is adopted, put it behind a DevFrame-owned adapter. The object
model and governance rules remain the source of truth.

## Architecture Boundary

The boundary should look like this:

```text
DevFrame kernel schema and fixtures
  -> local validation and status derivation
  -> optional adapters
      -> constrained generation
      -> policy engine
      -> workflow engine
      -> provenance backend
  -> read-only projection
```

External projects should strengthen a boundary. They should not define the
boundary.

## What To Change First

The first real code change should be:

1. add `schemas/review_governance_kernel.schema.json`;
2. add four fixture files under a review-governance examples directory;
3. add one focused test file;
4. add a small helper only if needed for derived status;
5. update reviewer index/public snapshot references.

Do not start with:

- a new command;
- a new UI;
- a new coordinator runtime;
- a new policy engine;
- a new workflow engine;
- a new memory subsystem.

## Compatibility With Existing Modules

The first implementation should map to existing modules but avoid invasive
changes:

| Existing module area | Compatibility expectation |
|---|---|
| Project contracts | Project fixture should use compatible project identity language |
| rdgoal | Work item and run concepts should be able to reference rdgoal dispatch later |
| workflow engine | Review phase vocabulary should remain compatible |
| team runtime | Evidence and gate read-model lessons should inform fixture shape |
| visual state/T3 | Projection summary should be read-only and backend-derived |
| existing schemas | Vocabulary may be reused, but top-level object decisions come from the unified object model |

## Risk Controls

| Risk | Control |
|---|---|
| Dependency sprawl | Require a failing local test or documented gap before adding a dependency |
| Rule sprawl | Keep phase-one decision kinds to `review`, `gate`, and `adopt` |
| False completion | Test that run success never completes work alone |
| UI-owned truth | Test that projection cannot mark completion directly |
| Old schema drift | Reuse vocabulary, not old authority boundaries |
| Overbuilding policy | Delay OPA/Cedar/OpenFGA until local decisions outgrow simple rules |
| Overbuilding workflow | Delay Temporal/LangGraph until review flows need durable retries and resumability |

## Dependency Adoption Gate

Before adding any new third-party dependency, require:

1. the local fixture/test gap it solves;
2. why existing stdlib or current project dependency is insufficient;
3. license check;
4. public-repo suitability check;
5. adapter boundary;
6. fallback if the dependency is removed;
7. tests proving DevFrame rules still own the final decision.

## Success Criteria

This plan succeeds when the first implementation proves:

- project constraints reject invalid model-shaped outputs;
- evidence is required for gate pass;
- status is derived from facts and decisions;
- external libraries are optional accelerators, not the source of truth;
- the next dependency decision is evidence-based, not excitement-based.

## Immediate Next Task

Implement package one from the implementation spec:

```text
Schema + fixtures + negative contract tests.
```

That is the smallest useful move toward the user's goal: detailed research,
documented planning, then document-driven development.
