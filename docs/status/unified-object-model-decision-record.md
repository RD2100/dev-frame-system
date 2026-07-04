# Unified Object Model Decision Record

Lifecycle state: Draft active decision record

Decision status: Accepted for phase-one planning, not yet a stable runtime
contract.

Reader: DevFrame maintainers who need one shared vocabulary before changing
runtime, evidence, evaluation, policy, or RDCode projection behavior.

Post-read action: model new governance work with the phase-one objects below,
and do not introduce a new top-level object unless it passes the admission test.

Related docs: [Governance Spine And Document Coordination](governance-spine-and-document-coordination.md), [Governance Contradiction Matrix](governance-contradiction-matrix.md), [Governance Rules Spec](governance-rules-spec.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md)

## Purpose

The current planning set uses many useful nouns: goal, task spec, context
packet, run, report, review, verdict, policy decision, promotion, evidence,
agent, document authority, and RDCode conversation.

Those nouns cannot all become top-level platform objects. If they do, the
platform becomes hard to extend and harder to verify. This decision record
freezes a smaller object kernel for phase one.

The goal is not perfect ontology. The goal is a durable vocabulary that lets
documentation, runtime records, evidence, review, evaluation, policy, and UI
projections describe the same facts without competing source-of-truth claims.

## Decision

Phase one uses eight top-level governance objects:

| Object | Plain role | Why top-level |
|---|---|---|
| `Project` | The bounded repository, product, or workspace being governed | Owns scope, policy defaults, document set, and runtime records |
| `WorkItem` | The goal, review request, task, change unit, or investigation being driven | Connects intent to runs, evidence, decisions, and final status |
| `DocumentRevision` | A versioned written claim, plan, rule, guide, spec, or handoff | Gives documentation durable identity and reviewable history |
| `Run` | One execution attempt by a principal through a tool, model, workflow, or runtime | Captures what was attempted, by whom, with which inputs |
| `Artifact` | A produced or captured file, report, diff, bundle, context snapshot, or package | Gives outputs and inputs addressable identity |
| `Evidence` | Proof that supports or rejects a claim about a run, artifact, document, or decision | Separates facts from assertions |
| `Decision` | A typed verdict, gate result, adoption, escalation, or policy outcome | Makes authority explicit and auditable |
| `Principal` | A human, agent, service, model provider, or organization that acts or authorizes action | Unifies actors without making agents special |

These objects are the planning kernel. Implementation may use smaller internal
classes, tables, files, or schemas, but those internals should map back to this
kernel when exposed in governance docs or projections.

## Object Admission Test

A new top-level object is allowed only if all three conditions are true:

1. It has an independent lifecycle.
2. It has an independent fact source.
3. It has an independent authority boundary.

If one condition is missing, model it as a facet, payload, state, projection, or
artifact kind instead.

Examples:

| Candidate | Phase-one decision | Reason |
|---|---|---|
| `ContextPacket` | Not top-level | It is an immutable `Artifact(kind=context_snapshot)` referenced by a `Run` |
| `Review` | Not top-level | It is a `Decision(kind=review)` with evidence and reviewer payload |
| `Verdict` | Not top-level | It is a `Decision(kind=gate)` or final decision payload |
| `PolicyDecision` | Not separate top-level | It is a `Decision` kind with policy-specific payload |
| `PromotionDecision` | Not separate top-level | It is a `Decision` kind that adopts, supersedes, or rejects a change |
| `Agent` | Not top-level | It is `Principal(kind=agent)` |
| `DocumentAuthorityRecord` | Not top-level | It is derived from `DocumentRevision` plus `Decision(kind=adopt/supersede/archive)` |
| `Conversation` | Not governance top-level in phase one | It is a projection or artifact unless it becomes a governed work boundary |
| `Event` | Not platform top-level | Use events where replay or audit needs them; do not make events the main fact model |

## Core Relationships

The minimum relationship graph is:

```text
Project
  owns WorkItem
  owns DocumentRevision
  owns Principal scope

WorkItem
  uses DocumentRevision
  starts Run
  produces Artifact
  collects Evidence
  receives Decision

Run
  has Principal
  has input Artifact(kind=context_snapshot)
  produces Artifact
  emits Evidence
  may request Decision

DocumentRevision
  may be input to WorkItem
  may be cited by Evidence
  becomes authoritative through Decision

Decision
  is made by Principal or policy runtime
  cites Evidence
  targets Project, WorkItem, DocumentRevision, Run, Artifact, or Principal
```

The important boundary is that `Run.success` does not complete a `WorkItem`.
Completion requires a decision that cites sufficient evidence.

## Phase-One Decision Kinds

Phase one allows only these `Decision.kind` values:

| Kind | Purpose |
|---|---|
| `review` | Records an independent review outcome against a run, artifact, document, or work item |
| `gate` | Records pass, fail, blocked, or insufficient-evidence status for a required gate |
| `adopt` | Makes a document revision, rule, context policy, workflow default, or improvement authoritative |

The next two likely kinds are `escalate` and `supersede`, but they should not be
added until the first vertical slice proves the initial three.

## Required Fields By Concept

This is not a storage schema. It is the minimum conceptual shape each object
must expose to governance readers and projections.

### `Project`

- identity;
- owner or controlling principal;
- scope boundary;
- active document set;
- default policy profile;
- current work items;
- projection state.

### `WorkItem`

- identity;
- project;
- intent;
- status;
- priority or risk;
- required documents;
- input context snapshot reference;
- runs;
- artifacts;
- evidence;
- decisions.

### `DocumentRevision`

- identity;
- document family;
- revision or content address;
- lifecycle state;
- authority state;
- supersedes or superseded-by links;
- cited decisions;
- cited evidence.

### `Run`

- identity;
- project;
- work item;
- principal;
- tool, model, workflow, or runtime;
- input context snapshot;
- start and end state;
- output artifacts;
- evidence;
- claimed result;
- governing decisions.

### `Artifact`

- identity;
- kind;
- location or content reference;
- producer;
- produced-at or captured-at time;
- integrity information where relevant;
- visibility and privacy boundary;
- linked work item or run.

### `Evidence`

- identity;
- evidence kind;
- claim being supported or rejected;
- source artifact or command;
- observed result;
- freshness;
- scope;
- verifier or reviewer;
- trust limits.

### `Decision`

- identity;
- kind;
- target object;
- deciding principal or policy runtime;
- outcome;
- rationale;
- evidence references;
- effective time;
- expiry or review condition where relevant.

### `Principal`

- identity;
- kind;
- authority scope;
- authentication or provenance reference when applicable;
- policy role;
- allowed action class;
- audit trail.

## Lifecycle Rules

### Work Item Status

Use a small status set:

| Status | Meaning |
|---|---|
| `draft` | Intent exists, but required context or authority is incomplete |
| `ready` | Required inputs are present and a run may be prepared |
| `running` | At least one run is in progress |
| `blocked` | A gate, policy, missing evidence, or human decision prevents progress |
| `reviewing` | Output exists and is waiting for review or gate decision |
| `completed` | A decision accepted the result with sufficient evidence |
| `archived` | Work is retained for traceability but no longer active |

### Document Revision Authority

A document revision becomes authoritative only through a decision. A newer file
is not automatically more authoritative than an older one.

### Context Snapshot Ownership

A context packet is stored as `Artifact(kind=context_snapshot)`. It is immutable
for the run that used it. A later run may create a new snapshot.

### Evidence Freshness

Evidence must carry scope and freshness. A passing command from an old branch,
old dependency set, or different project scope cannot silently prove a current
claim.

## Projection Rules

RDCode, T3, dashboards, and other clients may display:

- project list and active work items;
- run state;
- evidence summaries;
- decision summaries;
- blocked reasons;
- human-required actions.

They must not become the primary source of truth for:

- evidence validity;
- document authority;
- final verdicts;
- policy grants;
- promotion decisions.

If a projection initiates a mutation, the mutation must return to the DevFrame
governance backend as a decision request, work item update, or run request.

## Phase-One Vertical Slice

The first proving slice should be `/rdreview` or an equivalent review-first
workflow.

It should exercise:

- one `Project`;
- one `WorkItem`;
- at least one `DocumentRevision`;
- one `Run`;
- one `Artifact(kind=context_snapshot)`;
- at least one output `Artifact`;
- at least one `Evidence` record;
- one `Decision(kind=review)` and one `Decision(kind=gate)`;
- a projection that shows status without owning authority.

This is enough to test the object model without enabling broad autonomous
execution.

## Deferred Questions

These questions are intentionally deferred:

- exact database, file, or schema representation;
- event-sourcing design;
- long-term memory object shape;
- Zanzibar/OpenFGA-style authorization graph;
- multi-project organization model;
- model-provider score history;
- full RDCode writeback authority.

They should not block phase one.

## Reader Test

A fresh maintainer should now be able to answer:

1. Which objects are top-level?
2. Why is `ContextPacket` not top-level?
3. Why does `Run.success` not equal completion?
4. How does a document become authoritative?
5. Why is RDCode a projection shell in phase one?

If a future document cannot answer those questions consistently, it should link
back here and state the intended exception.
