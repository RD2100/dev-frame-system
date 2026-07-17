# Governance Spine And Document Coordination

Lifecycle state: Historical coordination record; scheduling superseded by `HANDOFF.md`

Reader: DevFrame maintainers turning the current planning documents into one coherent document-driven transformation path.

Post-read action: follow the governance spine, resolve the named contradictions, and write the next decision documents in order.

Related docs: [Status Document Inventory](status-document-inventory.md), [Workflow Consolidation and Command Plan](workflow-consolidation-and-command-plan.md), [Context Management Architecture Plan](context-management-architecture-plan.md), [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Model Knowledge Gap Governance Plan](model-knowledge-gap-governance-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Documentation Management Audit and Plan](documentation-management-audit-and-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md), [Browser Automation Transport Roadmap](browser-automation-transport-roadmap.md), [Paper Knowledge Base Iteration MVP Plan](paper-knowledge-base-iteration-mvp-plan.md), [Graph Projection And Knowledge Canvas Plan](graph-projection-knowledge-canvas-plan.md)

## Purpose

The current planning documents should not become a pile of parallel ideas. They
need one spine:

```text
Workflow and command consolidation
  -> Context management
  -> Context noise governance
  -> Model knowledge-gap governance
  -> Documentation governance
  -> Runtime governance and evidence closure
  -> Evaluation and feedback learning
  -> Project and cross-project memory harness
  -> Total-control policy and human escalation
  -> Unified object model
  -> Governance rules
  -> Document-driven transformation master plan
```

This document is the coordination layer before the final integrated plan. It
states how the existing documents fit together, what is still unresolved, and
what should be written next.

## Current Architecture Thesis

DevFrame should be the governance source of truth. RDCode, T3, dashboards,
browser surfaces, and future clients should be projection shells unless a
backend governance contract explicitly grants them mutation authority.

The platform should be modeled around durable facts, not around UI screens or
agent transcripts. The working minimum governance kernel is:

| Object | Plain role |
|---|---|
| `Project` | The bounded product or repository being governed |
| `WorkItem` | The goal, task, review request, or change unit being driven |
| `DocumentRevision` | A versioned written claim, plan, spec, rule, or guide |
| `Run` | An execution attempt by a principal through a tool/runtime |
| `Artifact` | A produced or captured file, context snapshot, report, diff, bundle, or package |
| `Evidence` | Proof that supports or rejects a claim about a run, artifact, or decision |
| `Decision` | A typed verdict, gate result, adoption, escalation, or policy outcome |
| `Principal` | A human, agent, service, or organization that acts or authorizes action |

This is not yet a stable runtime contract. It is the working synthesis captured
in `unified-object-model-decision-record.md`.

## How The Existing Plans Fit

| Layer | Current document | Contribution |
|---|---|---|
| Workflow surface | `workflow-consolidation-and-command-plan.md` | Separates user-facing commands from dispatch, adapters, gates, and views |
| Context | `context-management-architecture-plan.md` | Makes context explicit, bounded, cited, and auditable before dispatch |
| Context noise | `context-noise-governance-and-automation-plan.md` | Filters stale, disposable, irrelevant, duplicated, sensitive, or misleading material before dispatch |
| Knowledge gaps | `model-knowledge-gap-governance-plan.md` | Prevents model common sense from becoming unverified product, architecture, ecosystem, or acceptance judgment |
| Model performance | `context-led-model-performance-control-plan.md` | Treats model performance as controlled context, task shape, tools, evidence, memory, and routing |
| Memory harness | `project-and-cross-project-memory-harness-governance-plan.md` | Governs project memory, cross-project hints, memory isolation, retrieval evaluation, and promotion |
| Documentation | `documentation-management-audit-and-plan.md` and `documentation-management-detailed-rollout-plan.md` | Prevents authority drift and gives status docs lifecycle rules |
| Runtime and evidence | `runtime-governance-and-evidence-closure-transformation-plan.md` | Defines the target chain from intent to final verdict and read models |
| Evaluation and learning | `evaluation-feedback-learning-governance-plan.md` | Separates acceptance, evaluation, learning, and promotion |
| Authority | `total-control-policy-engine-and-human-escalation-governance-plan.md` | Defines policy decisions, human escalation, and blocked self-promotion |
| Object model | `unified-object-model-decision-record.md` | Unifies the nouns used by every layer |
| Contradictions | `governance-contradiction-matrix.md` | Names conflicts that must not be hidden in the master plan |
| Rules | `governance-rules-spec.md` | Turns the object model into phase-one operational rules |
| Master plan | `document-driven-transformation-master-plan.md` | Turns the unified model and rules into an implementation roadmap |
| Deferred modules | `browser-automation-transport-roadmap.md`, `paper-knowledge-base-iteration-mvp-plan.md`, `graph-projection-knowledge-canvas-plan.md` | Keeps later browser transport, paper knowledge-base iteration, and graph canvas work visible without moving them ahead of the review-first kernel |

## Decisions Already Strong Enough To Carry Forward

These points are now strong enough to be treated as working direction:

1. Context packets should be persisted and auditable, not only held in chat or
   UI state.
2. Context automation should reduce accidental noise before dispatch, not
   maximize retrieved material.
3. Runtime success is not the same thing as governance completion.
4. Evidence must support claims; reports alone are not final proof.
5. Evaluation can recommend improvements, but cannot promote them by itself.
6. Authority must be modeled separately from quality, confidence, and model
   preference.
7. RDCode is a shell around DevFrame governance, not the primary source of
   truth.
8. Document authority should come from versioned documents plus decisions, not
   from whichever markdown file is most recent or most visible.

## Contradictions To Resolve Before Integration

The final integrated plan should explicitly settle these contradictions:

| Conflict | Provisional resolution |
|---|---|
| `ContextPacket` as top-level object vs reusable artifact | Treat it as immutable `Artifact(kind=context_snapshot)` referenced by `Run.input_context_ref` unless a later decision proves an independent lifecycle and authority boundary |
| Context noise gate as a new object vs context-snapshot payload | Keep noise decisions inside context snapshots, ledgers, evidence, and decisions for phase one |
| Cross-project memory as authority vs low-authority candidate | Treat cross-project memory as hint or background until current project evidence and a decision prove applicability |
| Separate `Review`, `Verdict`, `PolicyDecision`, and `PromotionDecision` objects vs one `Decision` object | Use `Decision` as a typed envelope with kind-specific payloads; do not create an all-purpose table |
| `Goal`, `TaskSpec`, review request, and execution unit as separate first-class objects | Use `WorkItem` as the initial common object; keep task-spec versions as revisions or facets |
| `DocumentAuthorityRecord` as an independent source vs document-plus-decision projection | Use `DocumentRevision` plus `Decision(kind=adopt/supersede/archive)` and derive authority views |
| Event sourcing everywhere vs fact objects with events where useful | Keep fact objects primary; use append-only events only where replay, audit, or non-repudiation has clear value |
| Agent as top-level object vs unified actor model | Use `Principal`, with `Principal.kind=agent` for agents |
| RDCode conversation as source vs projection shell | Keep RDCode as a projection and command surface; DevFrame backend owns facts and decisions |

## Consolidation Writing Order

### 1. Unified Object Model Decision Record

Purpose: freeze the minimum nouns and relationships before writing the master
plan.

Status: written as `unified-object-model-decision-record.md`.

It answers:

- what are the top-level objects;
- what is intentionally not top-level;
- what object owns context snapshots;
- how decisions, evidence, and document authority relate;
- what phase-one constraints limit object and decision-kind growth.

### 2. Governance Contradiction Matrix

Purpose: make cross-plan conflicts explicit before integration.

Status: written as `governance-contradiction-matrix.md`.

It answers:

- where plans could be read against each other;
- which conflicts are P0 for false completion or unsafe authority;
- which provisional resolutions should guide the master plan.

### 3. Governance Rules Spec

Purpose: turn the object model into operational rules.

Status: written as `governance-rules-spec.md`.

It answers:

- when a run is blocked;
- when evidence is sufficient;
- when a document becomes authoritative;
- when a decision requires human escalation;
- when learning may become a promoted change;
- what projections RDCode may show or request.

### 4. Document-Driven Transformation Master Plan

Purpose: coordinate implementation without inventing a new architecture every
turn.

Status: written as `document-driven-transformation-master-plan.md`.

It answers:

- what vertical slice proves the model first;
- what docs move from active plan to stable reference after proof;
- what code paths consume the new objects;
- what review and evidence gates prove each phase;
- what is explicitly deferred.

## Recommended First Vertical Slice

The first proving slice should remain `/rdreview` or an equivalent review-first
workflow. It is narrow enough to avoid premature autonomous execution, but rich
enough to exercise:

- `WorkItem`;
- `DocumentRevision`;
- `Run`;
- `Artifact(kind=context_snapshot)`;
- `Evidence`;
- `Decision(kind=review|gate|adopt)`;
- RDCode or dashboard projection;
- human escalation boundaries.

This slice should prove the governance kernel before expanding into broad
Global Coordinator autonomy, long-term learning, or full RDCode writeback.

## Non-Goals For This Coordination Step

- Do not move or archive old status documents yet.
- Do not promote draft plans into `docs/agent-runtime/` yet.
- Do not implement the object model before writing its decision record.
- Do not make RDCode the source of truth.
- Do not introduce broad Zanzibar/OpenFGA-style authorization before the phase
  one object and decision model is proven.
- Do not treat long-term memory or model routing as more urgent than a working
  review/evidence/decision vertical slice.

## Completion Criteria

This coordination step is complete when:

1. `docs/README.md` points readers to the status inventory and governance spine.
2. `reviewer-index.md` includes the new coordination records.
3. Active planning documents are classified as current direction, not stable
   implementation truth.
4. The next writing order is explicit.
5. No old handoff, receipt, or stage report can easily be mistaken for the
   current whole-platform contract.
6. The master plan links the planning documents to a review-first vertical
   slice and explicit stop lines.
