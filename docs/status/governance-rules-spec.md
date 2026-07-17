# Governance Rules Spec

Lifecycle state: Historical rules proposal; scheduling superseded by `HANDOFF.md`

Rule status: Accepted for phase-one planning, not yet a stable runtime contract.

Reader: DevFrame maintainers who need operational rules after reading the
unified object model.

Post-read action: use these rules to judge whether a proposed workflow,
document, runtime change, or RDCode projection respects the governance model.

Related docs: [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Contradiction Matrix](governance-contradiction-matrix.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md)

## Purpose

The object model says what the platform talks about. This rules spec says how
the platform should judge those objects during phase-one planning.

The rules are intentionally conservative. They protect the project from false
completion, authority drift, report-only proof, and UI-owned truth while the
first vertical slice is still unproven.

Phase one must not create new top-level authority objects for human approval,
policy activation, decision requests, attention requests, or user assets. If
one of those concepts is needed, represent it through `Decision`, `Artifact`,
`WorkItem` rationale, or projection payload until the object admission test is
passed.

## Rule Groups

Phase one uses ten rule groups:

1. work item status;
2. context snapshot;
3. run record;
4. artifact and evidence;
5. decision;
6. document authority;
7. evaluation and learning;
8. policy and escalation;
9. projection and RDCode.
10. human attention.

## Work Item Rules

### WORK-001: Work starts from intent, not from tools

A `WorkItem` must state the user or project intent before selecting an executor,
model, command, or client surface.

### WORK-002: A work item is not complete because a run completed

`Run.success` may support completion, but only a `Decision` can mark a
`WorkItem` completed.

### WORK-003: Missing required context blocks execution

If required context is missing, forbidden, stale, or unverifiable, the work item
must be `draft` or `blocked`, not `ready`.

### WORK-004: Status must explain user action

User-facing status should map to plain operational states:

| User-facing state | Governance meaning |
|---|---|
| `in_progress` | One or more runs are active |
| `waiting_for_you` | Human decision, consent, or input is required |
| `blocked` | Policy, evidence, context, tool, or environment prevents progress |
| `insufficient_evidence` | Output exists, but proof is not enough for a gate |
| `completed` | A decision accepted the result with sufficient evidence |

RDCode may localize these labels, but the backend must own the computed state.

## Context Snapshot Rules

### CTX-001: Serious work needs a context snapshot

Any governed run that may affect code, rules, release state, project memory, or
document authority must reference an input context snapshot.

### CTX-002: Context snapshots are artifacts

A context packet is stored as `Artifact(kind=context_snapshot)`, not as hidden
chat state.

### CTX-003: Context snapshots are immutable per run

A run cannot retroactively change the context it used. If context changes,
create a new artifact and a new run or review decision.

### CTX-004: Context snapshots must cite sources

Compressed or summarized context must cite source documents, files, evidence, or
memory records. Compression is not a source of truth.

### CTX-005: Context snapshots must support replay and comparison

`Artifact(kind=context_snapshot)` must carry enough payload to explain what was
selected, omitted, and relied on.

Minimum payload fields:

- `immutable`;
- `source_refs`;
- `selected_items`;
- `omitted_required_items`;
- `freshness`;
- `authority_level`;
- `redaction_summary`;
- `selection_rationale`;
- `token_budget`;
- `content_hash`.

## Run Rules

### RUN-001: A run must name its principal

Every run must identify the `Principal` that executed or controlled it.

### RUN-002: A run must name its tool boundary

Every run must record the model, tool, workflow, runtime, or command class used
well enough for a reviewer to understand the execution boundary.

### RUN-003: Claims require output artifacts or evidence

A run may claim success, failure, or blockage, but the claim is not trusted until
it is supported by artifacts or evidence.

### RUN-004: A failed run can still produce useful evidence

Failure is not discarded. A failed run may provide evidence for a blocker,
regression case, policy denial, or future evaluation.

## Artifact And Evidence Rules

### EVID-001: Evidence supports a specific claim

Evidence must say what claim it supports or rejects. A generic log dump is an
artifact until a claim is attached.

### EVID-002: Evidence has scope

Evidence must say which project, work item, run, branch, environment, or
document scope it applies to.

### EVID-003: Evidence has freshness

Evidence from an old context, old branch, old dependency set, or different
environment must not silently prove a current claim.

### EVID-004: Reports summarize evidence but do not replace it

A report can help a reviewer, but it cannot be the only proof for a gate unless
the report itself contains verifiable evidence references.

### EVID-005: Insufficient evidence is a first-class outcome

If output exists but proof is incomplete, the correct state is
`insufficient_evidence`, not success.

## Decision Rules

### DEC-001: Decisions are typed

Every decision must have a kind. Phase-one allowed kinds are:

- `review`;
- `gate`;
- `adopt`.

### DEC-002: Decisions cite evidence

A decision that accepts, blocks, or adopts a result must cite evidence or state
why evidence is unavailable and why the decision is still allowed.

### DEC-003: Decisions name the decider

A decision must name the human, agent, service, or policy runtime that made it.

### DEC-004: Decision authority is scoped

A decision applies only to its target and scope. A decision for one work item
does not grant general authority to a model, workflow, or agent.

### DEC-005: Add decision kinds slowly

New decision kinds require a decision record that defines:

- valid targets;
- required payload;
- allowed outcomes;
- authority requirements;
- evidence requirements.

### DEC-006: Human approval is UI wording, not persistence

If a human approval, rejection, or exception unblocks work, it must be recorded
as a `Decision` or decision rationale. Do not add a `HumanApproval` object in
phase one.

### DEC-007: Policy-handled continuation is not an activation object

If policy and evidence allow routine continuation, record the result as a
`Decision(kind=gate)` with a policy-runtime decider or as work item rationale.
Do not add `PolicyActivation` or `AssetActivation` as phase-one objects.

### DEC-008: Decision requests are requests, not authority

A `DecisionRequest` may be submitted by a shell or UI, but it is not a source of
truth. Only the DevFrame governance backend may validate principal, target,
evidence, policy, and rationale, then produce the authoritative `Decision`.

## Document Authority Rules

### DOC-001: Documents do not become authoritative by being newer

A newer `DocumentRevision` is only newer. It is authoritative only after an
adoption decision.

### DOC-002: Status docs remain planning material until promoted

Documents in `docs/status` can guide architecture work, but they are not stable
runtime contracts until implementation and evidence support promotion.

### DOC-003: Handoff files expire as authority

Handoff files are for continuity. Their claims should be consumed into active
plans, decision records, stable docs, or implementation evidence.

### DOC-004: Contradictions must be named

If two documents conflict, the newer coordination or decision record must name
the conflict and record the provisional or final resolution.

## Evaluation And Learning Rules

### EVAL-001: Evaluation does not override acceptance

An evaluation score cannot turn a blocked, unsafe, or insufficient-evidence run
into an accepted result.

### EVAL-002: Fair comparisons require comparable context

Model or provider comparisons must use equivalent context snapshots or state
why comparison is limited.

### LEARN-001: Learning produces proposals, not defaults

A learning result may create an improvement proposal. It cannot update default
rules, skills, routes, tests, or memory without an adoption decision.

### LEARN-002: Promotion needs rollback

Any promoted learning change must have a rollback path or a documented reason
why rollback is not applicable.

## Policy And Escalation Rules

### POL-001: Confidence is not authority

Model confidence, test pass rate, or evaluator score does not grant permission
to mutate project state.

### POL-002: High-power actions require explicit authority

Actions that change release state, default rules, project memory, writeback
behavior, security posture, or document authority require a decision by an
authorized principal or policy runtime.

### POL-003: Self-promotion is blocked by default

An agent, coordinator, model route, or learning loop may not promote its own
authority or default behavior without independent decision.

### POL-004: Human escalation must be visible

If a human decision is required, the projection must show what decision is
needed, why it is needed, and what happens if the human declines.

## Human Attention Rules

### ATTN-001: Human attention must be actionable

Do not ask a human to inspect vague output. Ask for a specific decision, input,
approval, rejection, or policy exception.

### ATTN-002: Human attention must carry context

Every human-needed state must reference the work item, blocked reason, relevant
context snapshot, evidence summary, proposed decision, and consequence of
approval or rejection.

### ATTN-003: Human responses become decisions

Human responses that unblock governance work must be recorded as decisions or
decision rationale, not only as chat text.

### ATTN-004: Repeated human decisions become proposals, not rules

Repeated approvals may create an automation proposal. They must not silently
become adopted rules without evidence and adoption decision.

## Projection And RDCode Rules

### PROJ-001: Projections display facts; they do not own facts

RDCode, T3, dashboards, and browser views may display project, work item, run,
artifact, evidence, and decision summaries. DevFrame governance owns the facts.

### PROJ-002: Projection actions become governance requests

If a projection offers a button or command, the action must become a governed
request, not a direct bypass around policy.

RDCode may submit a request payload. It must not directly write `completed`,
`pass`, `adopted`, `enabled`, or other authority-bearing states.

### PROJ-003: Projection status is computed

User-facing labels must be derived from backend object state and decisions.
They must not be manually invented by the UI.

### PROJ-004: Writeback starts narrow

Phase-one projection writeback should be limited to review, gate, or adoption
requests needed by the first vertical slice.

The writeback output of RDCode is a request. The persisted decision must be
generated by DevFrame after validation.

## Phase-One Acceptance For The Rules

The rules are considered proven only after a review-first vertical slice can
show:

1. a work item with a context snapshot;
2. a run with named principal and tool boundary;
3. output artifacts;
4. evidence tied to claims;
5. a review decision;
6. a gate decision;
7. a projection that shows blocked, insufficient-evidence, or completed status
   from backend state.

Until then, these rules are planning authority, not implementation fact.
