# Goal-Bound Evidence Gate Plan

Lifecycle state: Historical phase plan; scheduling superseded by `HANDOFF.md`

Plan status: Accepted as a contraction of the Goal Supervisor idea, not as a
new autonomous coordinator mainline.

Reader: DevFrame maintainers deciding how goal-based continuation should enter
the review-first governance kernel without turning phase one into a workflow
runtime.

Post-read action: represent goal-bound continuation through existing
`WorkItem`, `Run`, `Artifact`, `Evidence`, and `Decision` records; reject
implementations that introduce a standalone Goal Supervisor, WorkLoop, or
resume runtime before the evidence gate is proven.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md)

## Core Decision

Do not make Goal Supervisor the next mainline capability.

The next useful slice is a goal-bound evidence gate:

```text
Given a WorkItem goal, a Run context snapshot, evidence refs, and policy,
produce an auditable continuation decision.
```

The mechanism answers a narrow governance question:

```text
Is the agent qualified to continue under the current goal, evidence,
permission, risk, and context boundaries?
```

It does not answer a workflow-runtime question:

```text
How should an autonomous agent keep working indefinitely?
```

That distinction matters because durable execution, agent orchestration, and
human-in-the-loop workflow engines are already mature external categories. The
DevFrame differentiation is not another coordinator. It is a governance ledger
that makes coding-agent continuation evidence-gated, policy-bounded, and
audit-replayable.

## Object Boundary

Phase one must not add these top-level objects:

- `GoalContract`;
- `SupervisionPlan`;
- `WorkLoop`;
- `Checkpoint`;
- `EvidenceReview`;
- `Resume`;
- `GoalSupervisor`.

Use payloads inside existing objects instead:

- `GoalContractPayload` belongs on `WorkItem.governance.goal_contract` or on a
  `Run` snapshot payload when the run needs to preserve the exact goal contract
  version it used.
- `SupervisionTickPayload` belongs inside `Decision(kind=gate)` with a
  `decision_subtype` such as `goal_bound_continuation`. Do not add a new
  decision kind until the phase-one decision-kind freeze is intentionally
  reopened.

This keeps the object model stable while preserving the future boundary for
goal-aware continuation.

## Minimal Goal Contract Payload

The first payload should stay small:

```text
GoalContractPayload
- goal
- non_goals
- project_scope_refs
- allowed_action_classes
- forbidden_action_classes
- autonomy_level
- evidence_required
- completion_criteria
- stop_lines
- owner
- expires_at
- resume_policy: manual_only
```

Do not require these in phase one:

- `timeout_policy`;
- `escalation_policy`;
- complex user-filled `risk_level`;
- `SupervisionPlan`;
- independent `Checkpoint`;
- independent `EvidenceReview`;
- automated resume policy.

Risk should be computed by policy from action class, evidence, scope, and stop
lines. It should not be a decorative field the agent fills in.

## Minimal Continuation Decision Payload

The first continuation payload should be a gate decision payload:

```text
SupervisionTickPayload
- run_id
- tick_seq
- goal_contract_version
- current_phase
- last_action_ref
- evidence_refs
- context_snapshot_ref
- policy_eval_result
- blocked_reasons
- open_risks
- continuation_decision: policy_continue | blocked | human_required | hard_stop | pause
- decision_rationale
- human_question
- resume_ref
```

Do not include `replan` in the first version. Replanning can change scope,
authority, or goal shape. In phase one, any need to replan should become
`human_required` or `hard_stop`.

## Policy Continue Boundary

`policy_continue` must never mean "the agent may keep working freely."

It means only this:

```text
Within the same WorkItem, same goal contract, same allowed action class, same
evidence recipe, and same context snapshot family, policy permits the next
pre-declared low-risk step.
```

Hard constraints:

1. It cannot change `goal`, `non_goals`, scope, or allowed actions.
2. It cannot create new authority.
3. It cannot use cross-project memory as gate evidence.
4. It cannot deploy, publish, push, delete, migrate, or call paid external
   services.
5. It cannot treat a worker completion claim as evidence.
6. It must cite at least one `EvidenceRef`.
7. It must cite a `ContextSnapshotRef`.
8. It must produce a persisted `Decision`; UI state alone is irrelevant.
9. It can continue only to a recipe-declared next step.
10. Missing required evidence means `blocked`, not continue.
11. The policy version must be written into the decision payload.

Responsible first examples:

- rerun an already declared validation command;
- read logs or generated reports;
- produce a review note from existing evidence;
- advance to a read-only final review tick after the evidence checklist passes.

Explicit non-examples:

- continue coding because the worker says it is nearly done;
- push, release, deploy, migrate, delete, or publish;
- widen the task after discovering a nearby issue;
- use cross-project memory as the reason the current project gate passes;
- mark a work item complete from dashboard or shell state.

## Human Required Boundary

`human_required` is not a general approval prompt. It is a scarce interruption.

Use it only when all three are true:

1. policy cannot decide safely;
2. the answer changes the next path;
3. the question is concrete enough for a human to answer quickly.

Rules:

- one open human gate per goal;
- same-class questions are deduplicated;
- routine uncertainty becomes `blocked` or `pause`, not repeated prompts;
- every human question includes a recommended option and a safe default;
- no continuation happens without an explicit resume command or a new decision;
- the human answer is recorded as a decision payload, not only chat text.

Bad question:

```text
Should the agent continue?
```

Good question:

```text
The task now requires editing policy documents, but the goal contract forbids
rule changes. Choose one path: keep the task stopped, allow a read-only change
proposal, or sign a new goal contract with expanded scope.
```

## Minimal Fixture Slice

Name: Goal-Bound Evidence Gate Slice.

Goal: prove that the system can produce a stable continuation decision from
goal constraints, context snapshot, evidence, and policy.

Minimum fixture set:

1. one `GoalContractPayload`;
2. one `Decision(kind=gate)` payload for `policy_continue`;
3. one gate decision for `blocked`;
4. one gate decision for `human_required`;
5. one gate decision for `hard_stop`.

Required assertions:

- no evidence refs means never continue;
- no context snapshot ref means never continue;
- cross-project memory refs cannot support a gate pass;
- worker claims cannot satisfy completion evidence;
- projection or UI state cannot decide policy;
- `replan` cannot appear in the first continuation fixture;
- top-level Goal Supervisor objects are rejected;
- `policy_continue` can only target a pre-declared next step.

The first consumer should be the review-first `/rdreview` lifecycle, not a broad
autonomous coordinator.

## Phase Order

### Phase 0: Lock Governance Facts

Confirm that the kernel facts remain:

```text
Project -> WorkItem -> Artifact(context_snapshot) -> Run -> Evidence -> Decision -> Projection
```

No separate supervision fact system is allowed.

### Phase 1: Policy And Permission Gate

Define action classes, forbidden actions, stop lines, and deny-by-default
behavior before real continuation.

Memory, model confidence, and worker claims cannot grant authority.

### Phase 2: Read-Only Gate Fixtures

Add the goal contract and continuation decision payloads to fixtures.

The output is a decision, not execution.

### Phase 3: Memory As Advisory Input

Project memory may help explain context. Cross-project memory may suggest a
candidate risk or pattern. Neither can pass a gate without current-project
evidence.

### Phase 4: Manual Resume

Resume rereads prior decision, evidence refs, context snapshot refs, and policy
version. It does not continue from a natural-language summary.

### Phase 5: Narrow Policy Continue

Allow only low-risk, read-only, or validation steps that are already declared in
the evidence recipe.

### Phase 6: Runtime Evaluation

Only after the gate is stable should the project evaluate whether it needs a
durable scheduler or workflow engine.

## Stop Lines

Do not implement in phase one:

- persistent autonomous coordinator;
- automatic multi-agent dispatch from a goal;
- automated cross-session resume;
- dashboard-owned supervision state;
- cross-project memory-driven execution;
- broad durable workflow migration;
- automatic publishing, deployment, push, deletion, or migration;
- generated rules that self-promote into authority.

## Product Framing

The public framing should avoid promising a self-running agent operating
system.

Preferred framing:

```text
DevFrame decides whether a coding agent is qualified to continue under current
project constraints, evidence, permissions, and context.
```

Avoid:

```text
DevFrame is a Goal Supervisor that keeps agents working continuously.
```

The former is testable and differentiated. The latter competes with workflow
runtimes and risks swallowing the current governance spine.
