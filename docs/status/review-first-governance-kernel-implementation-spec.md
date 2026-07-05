# Review-First Governance Kernel Implementation Spec

Lifecycle state: Draft active implementation spec

Spec status: Implemented. Phase 1A kernel passed external GPT review (Round 7, GO).

Reader: DevFrame maintainers or coding agents extending the Phase 1A kernel.

Post-read action: implement the fixture and contract slice first, prove the
negative cases, and avoid expanding into coordinator autonomy, broad RDCode
writeback, model routing, or long-term memory.

Related docs: [Review-First Governance Kernel Contraction Plan](review-first-governance-kernel-contraction-plan.md), [Reuse-First Constraint Governance Implementation Plan](reuse-first-constraint-governance-implementation-plan.md), [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Rules Spec](governance-rules-spec.md), [Governance Contradiction Matrix](governance-contradiction-matrix.md), [Goal-Bound Evidence Gate Plan](goal-bound-evidence-gate-plan.md), [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md)

## Purpose

This spec is the bridge from planning documents to development.

The contraction plan says what to narrow to. This spec says what the first
developer should create, what to test, what to reuse, and where not to go.

The first implementation should prove contracts and fixtures before building a
full command, UI, coordinator behavior, or storage system.

## Development Thesis

Start with fixtures and validation, not a runtime migration.

The first useful deliverable is a small review governance packet that can prove:

```text
Project -> WorkItem(kind=review) -> Artifact(kind=context_snapshot) -> Run
-> Artifact(output) -> Evidence -> Decision(kind=review)
-> Decision(kind=gate) -> Projection(read-only status)
```

If this packet cannot represent success, blocked, and insufficient-evidence
cases, the platform is not ready for larger autonomy.

## Suggested Public Surface

These names are suggestions for the first implementation package. If the
developer chooses different names, the report must explain why.

| Surface | Suggested location | Purpose |
|---|---|---|
| Kernel schema | `schemas/review_governance_kernel.schema.json` | Validate the review-first packet |
| Positive fixture | `schemas/examples/review-governance/success.json` | Evidence-backed review and gate pass |
| Blocked fixture | `schemas/examples/review-governance/blocked.json` | Evidence-backed review failure or blocker |
| Insufficient fixture | `schemas/examples/review-governance/insufficient-evidence.json` | Report exists but evidence is not enough |
| Missing context fixture | `schemas/examples/review-governance/missing-context.json` | Work item cannot become ready |
| Goal-bound continuation fixture | `schemas/examples/review-governance/goal-bound-continuation.json` | Policy-handled low-risk continuation under the same goal |
| Contract tests | `packages/control-plane/tests/test_review_governance_kernel.py` | Validate fixtures and forbidden shortcuts |
| Optional helper module | `packages/control-plane/control_plane/review_governance_kernel.py` | Typed helper functions if schema-only validation becomes awkward |

The first package may be schema-plus-tests only. A helper module is optional and
should exist only if it reduces duplication or makes status derivation clearer.

## Reuse Targets

Use existing project concepts instead of inventing a parallel platform:

| Existing area | Reuse intent |
|---|---|
| project contract records | Reuse project identity and ownership concepts |
| rdgoal dispatch and digest concepts | Reuse the distinction between intent, dispatch, report, and digest |
| workflow engine records | Reuse plan, execute, review phase language where useful |
| team runtime records | Reuse event/read-model lessons, especially evidence and gate projections |
| visual state and T3 projection | Reuse projection-as-read-model discipline |
| existing agent-runtime schemas | Reuse evidence, review, gate, final-verdict vocabulary where compatible |
| public snapshot tests | Keep new files visible to release verification and reviewer index |

Do not copy an existing schema wholesale if it would blur the phase-one object
model. The kernel packet should be small and explicit.

## Kernel Packet Shape

The schema should validate one packet with these top-level keys:

```json
{
  "schema_version": "0.1",
  "project": {},
  "work_item": {},
  "document_revisions": [],
  "runs": [],
  "artifacts": [],
  "evidence": [],
  "decisions": [],
  "projection": {}
}
```

This packet is a fixture and contract boundary. It is not a storage design.

Do not add top-level keys for `decision_requests`, `human_approvals`,
`policy_activations`, `attention_requests`, `user_assets`, `goal_contracts`,
`supervision_plans`, `work_loops`, `checkpoints`, `evidence_reviews`,
`resumes`, or `goal_supervisors` in phase one. If a fixture needs those
concepts, represent them as an `Artifact`, `Decision`, `WorkItem` rationale, or
projection payload.

## Minimum Object Fields

### Project

Required:

- `id`
- `display_name`
- `scope`
- `owner_principal_id`

Optional in phase one:

- `policy_profile`
- `repository`
- `governance`

### WorkItem

Required:

- `id`
- `project_id`
- `kind`
- `intent`
- `status`
- `input_context_artifact_id`

Allowed `kind` in phase one:

- `review`

Allowed `status` in phase one:

- `draft`
- `ready`
- `running`
- `reviewing`
- `blocked`
- `insufficient_evidence`
- `completed`

Rule: `completed` is valid only when a passing gate decision targets the work
item.

Optional `governance.goal_contract` may carry a `GoalContractPayload` for
goal-bound continuation tests. It is a payload on the work item, not a new
top-level object.

Recommended first fields:

- `goal`
- `non_goals`
- `project_scope_refs`
- `allowed_action_classes`
- `forbidden_action_classes`
- `autonomy_level`
- `evidence_required`
- `completion_criteria`
- `stop_lines`
- `owner`
- `expires_at`
- `resume_policy`

Rule: `resume_policy` must be `manual_only` in phase one.

### DocumentRevision

Required when present:

- `id`
- `project_id`
- `document_family`
- `revision_ref`
- `lifecycle_state`

Allowed `lifecycle_state` in phase one:

- `draft`
- `active_plan`
- `adopted`
- `superseded`

Rule: `adopted` requires an adoption decision unless the fixture explicitly
marks it as pre-existing context.

### Run

Required:

- `id`
- `project_id`
- `work_item_id`
- `principal_id`
- `tool_boundary`
- `input_context_artifact_id`
- `status`
- `claimed_result`

Allowed `status` in phase one:

- `prepared`
- `running`
- `succeeded`
- `failed`
- `blocked`

Rule: `status=succeeded` does not imply work item completion.

### Artifact

Required:

- `id`
- `project_id`
- `kind`
- `producer_ref`
- `content_ref`

Allowed `kind` in phase one:

- `context_snapshot`
- `review_report`
- `command_output`
- `diff_summary`
- `evidence_pack`

Additional requirement for `context_snapshot`:

- `immutable=true`
- `source_refs`
- `selected_items`
- `omitted_required_items`
- `freshness`
- `authority_level`
- `redaction_summary`
- `selection_rationale`
- `token_budget`
- `content_hash`
- `knowledge_gap_assessment`
- `required_knowledge`
- `assumption_claims`
- `checked_sources`
- `unresolved_gaps`

Rule: `context_snapshot` remains an artifact payload. Do not introduce
`ContextPacket` or `ContextRecord` as a top-level object in phase one.

### Evidence

Required:

- `id`
- `project_id`
- `claim`
- `supports`
- `source_artifact_id`
- `scope`
- `freshness`
- `observed_result`

Allowed `supports` values:

- `supports`
- `rejects`
- `inconclusive`

Rule: a report artifact is not evidence unless an evidence record cites it and
states the claim.

### Decision

Required:

- `id`
- `project_id`
- `kind`
- `target_ref`
- `decider_principal_id`
- `outcome`
- `evidence_ids`
- `rationale`

Allowed `kind` in phase one:

- `review`
- `gate`
- `adopt`

Allowed `outcome` for `review`:

- `pass`
- `fail`
- `blocked`
- `insufficient_evidence`

Allowed `outcome` for `gate`:

- `pass`
- `fail`
- `blocked`
- `insufficient_evidence`
- `human_required`
- `hard_stop`
- `pause`

Rule: `outcome=pass` requires at least one evidence record unless an explicit
exception field explains why evidence is unavailable and why the decision is
allowed.

Optional gate decisions may include `payload.decision_subtype =
goal_bound_continuation`.

Recommended payload fields:

- `run_id`
- `tick_seq`
- `goal_contract_version`
- `current_phase`
- `last_action_ref`
- `evidence_refs`
- `context_snapshot_ref`
- `policy_eval_result`
- `blocked_reasons`
- `open_risks`
- `continuation_decision`
- `decision_rationale`
- `human_question`
- `resume_ref`

Allowed `continuation_decision` values:

- `policy_continue`
- `blocked`
- `human_required`
- `hard_stop`
- `pause`

Rule: phase one must not allow `replan` as a continuation decision.

Rule: `policy_continue` requires current evidence refs, a context snapshot ref,
the policy version, and a pre-declared next step under the same goal contract.

### Principal

The first packet may model principals inline or in a `principals` array. If
principals are inline, every `principal_id` must still resolve to a declared
principal.

Required:

- `id`
- `kind`
- `display_name`
- `authority_scope`

Allowed `kind` in phase one:

- `human`
- `agent`
- `service`
- `policy_runtime`

### Projection

Required:

- `work_item_id`
- `computed_status`
- `blocked_reason`
- `evidence_summary`
- `decision_summary`
- `allowed_actions`

Rule: projection must be derivable from packet facts. It must not introduce a
completion state that the decisions do not support.

## Status Derivation Rules

Use these derivation rules for tests and projection:

| Condition | Computed status |
|---|---|
| Work item lacks `input_context_artifact_id` or referenced context artifact is missing | `blocked` |
| Run succeeded but no review decision exists | `reviewing` |
| Review decision is `insufficient_evidence` | `insufficient_evidence` |
| Gate decision is `blocked` or `fail` | `blocked` |
| Gate decision is `pass` and cites evidence | `completed` |
| Human decision is required but absent | `waiting_for_you` if the projection layer supports it; otherwise `blocked` with explicit reason |

The schema can validate shape. A helper function or test utility may validate
derivation rules.

## Required Fixtures

### `success.json`

Must show:

- one review work item;
- one immutable context snapshot artifact;
- one succeeded run;
- one output artifact;
- evidence supporting the review claim;
- `Decision(kind=review, outcome=pass)`;
- `Decision(kind=gate, outcome=pass)`;
- projection status `completed`.

### `blocked.json`

Must show one of:

- evidence-backed review failure;
- policy or environment blocker;
- gate decision outcome `blocked` or `fail`.

Projection status must be `blocked`.

### `insufficient-evidence.json`

Must show:

- output artifact exists;
- review report exists;
- evidence is missing or inconclusive;
- review or gate decision outcome `insufficient_evidence`;
- projection status `insufficient_evidence`.

### `missing-context.json`

Must show:

- work item exists;
- no valid context snapshot artifact is linked;
- no run can be considered ready;
- projection status `blocked`.

### Optional `policy-handled-continuation.json`

May show:

- policy and evidence are sufficient for routine continuation;
- no human approval object exists;
- continuation is recorded as `Decision(kind=gate)` with a `policy_runtime`
  principal or work item rationale;
- projection explains the policy rationale.

This fixture is optional. It must not block the first schema package.

### Optional `goal-bound-continuation.json`

May show:

- a review work item with `governance.goal_contract`;
- one immutable context snapshot;
- evidence records satisfying the declared evidence requirement;
- a `Decision(kind=gate)` payload with
  `decision_subtype=goal_bound_continuation`;
- `continuation_decision=policy_continue`;
- a pre-declared next step that is low-risk, read-only, or validation-only.

This fixture must not add a supervisor object, work loop, automated resume
runtime, or scheduler.

### Optional `asset-placeholder.json`

May show one imported `evidence_recipe` or `review_checklist` placeholder.

It must be represented through existing phase-one objects and must not add an
asset registry, asset lifecycle service, MCP execution path, or marketplace
surface.

## Required Negative Tests

The first test file should include these cases:

| Case | Expected failure or derived status |
|---|---|
| Work item references missing context artifact | Validation failure or blocked status |
| Context artifact is not immutable | Validation failure |
| Run has `succeeded` but no review decision | Not completed |
| Gate pass has no evidence IDs | Validation failure |
| Context artifact lacks `source_refs`, `selected_items`, `selection_rationale`, or `content_hash` | Validation failure |
| Knowledge-dependent claim lacks `checked_sources` or lists unresolved required gaps | Validation failure or blocked status |
| Report artifact exists without evidence record | Insufficient evidence |
| Projection says completed without gate pass | Validation failure |
| Decision kind outside `review`, `gate`, `adopt` | Validation failure |
| New top-level object appears in packet | Validation failure unless schema explicitly allows extension metadata |
| Human-needed state lacks exact requested decision | Validation failure or blocked status with explicit reason |
| RDCode request writes `completed`, `pass`, `adopted`, or `enabled` directly | Validation failure |
| Human approval, policy activation, decision request, or attention request appears as a top-level object | Validation failure |
| Asset placeholder expands into registry, lifecycle service, MCP execution, or team enablement | Validation failure |
| Goal contract, supervision plan, work loop, checkpoint, evidence review, resume, or goal supervisor appears as a top-level object | Validation failure |
| Goal-bound continuation lacks evidence refs | Validation failure or blocked status |
| Goal-bound continuation lacks context snapshot ref | Validation failure or blocked status |
| Cross-project memory ref is used as gate-passing evidence | Validation failure or blocked status |
| Worker completion claim is used as completion evidence | Validation failure or insufficient evidence |
| Projection or UI state is used as policy input for continuation | Validation failure |
| Continuation decision uses `replan` in phase one | Validation failure |
| `policy_continue` targets a free-form next step outside the declared recipe | Validation failure or blocked status |

## Package Plan

### Package 1: Schema And Fixtures

Create the kernel schema and four fixtures.

Acceptance:

- all positive fixtures validate shape;
- invalid variants fail as expected;
- no runtime module is required yet.

### Package 2: Status Derivation Helper

Add a small helper only if tests need logic beyond JSON Schema.

Acceptance:

- helper derives `blocked`, `reviewing`, `insufficient_evidence`, and
  `completed`;
- helper never treats run success alone as completed.

### Package 3: Contract Tests

Add focused tests for fixture validation and status derivation.

Acceptance:

- tests cover every required negative case;
- tests are narrow enough to run without external services.

### Package 4: Optional Prepare-Only CLI Or Driver

Only after packages 1-3 pass, consider a prepare-only local driver that emits a
sample review governance packet.

Acceptance:

- generated packet validates;
- driver does not execute autonomous coordinator work;
- driver does not write public-repo runtime state unless explicitly requested.

## Non-Goals For The First Implementation

Do not implement:

- full `/rdreview` command UX;
- full RDCode writeback;
- direct RDCode authority writes;
- human approval, policy activation, decision request, or attention request as
  top-level objects;
- goal contract, supervision plan, work loop, checkpoint, evidence review,
  resume, or goal supervisor as top-level objects;
- user asset registry or lifecycle service;
- persistent coordinator runtime;
- persistent Goal Supervisor runtime;
- automated cross-session resume;
- model scoring or auto-routing;
- long-term memory update logic;
- new authorization graph;
- broad event ledger;
- stable runtime documentation promotion.
- knowledge-gap registry, research-task system, or long-term memory promotion.

These remain blocked until fixture, contract, and negative-test evidence exists.

## Verification Commands

The first implementation report should include exact commands. Expected command
shape:

```powershell
python -m pytest packages/control-plane/tests/test_review_governance_kernel.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

If JSON Schema validation uses an existing test utility or dependency, name it
in the implementation report.

## Reviewer Index Requirements

The implementation report must include:

- changed files;
- generated fixtures;
- schema file;
- tests run;
- negative cases covered;
- known gaps;
- whether any helper module was added;
- whether any runtime command was added.

If the implementation adds a schema or fixture, update the public surface or
reviewer index so reviewers can find it.

## Success Definition

The first implementation is successful only when a reviewer can inspect the
fixtures and tests and confirm:

1. context is an immutable artifact;
2. run success does not complete work;
3. reports do not replace evidence;
4. gate decisions cite evidence;
5. projection status is derived, not invented;
6. no deferred feature was smuggled in.
7. human-needed states are actionable, scoped, and resumable.

That is the first real proof that document-driven development has crossed from
planning into enforceable governance.

## Implementation Status (Phase 1A — Completed 2026-07-05)

The Phase 1A kernel is implemented and passed external GPT review (Round 7, GO).

### Delivered

| Surface | Location | Notes |
|---|---|---|
| Kernel schema | `schemas/review_governance_kernel.schema.json` | 44 static constraints under draft-07 |
| Success fixture | `schemas/examples/review-governance/success.json` | Evidence-backed review + gate pass |
| Blocked fixture | `schemas/examples/review-governance/blocked.json` | Tool boundary violation → blocked |
| Insufficient-evidence fixture | `schemas/examples/review-governance/insufficient-evidence.json` | Inconclusive evidence → insufficient_evidence |
| Missing-context fixture | `schemas/examples/review-governance/missing-context.json` | No context snapshot → blocked |
| Contract tests | `packages/control-plane/tests/test_review_governance_kernel.py` | 55 tests, all passing |
| Semantic validator | `packages/control-plane/control_plane/review_governance_validator.py` | 12 cross-object constraints |

### Semantic validator constraints (12 total)

1. `work_item.status=completed` requires a gate decision with `outcome=pass` and `target_ref=work_item.id`
2. Gate/review pass requires `evidence_ids` that resolve to existing evidence with `supports ∈ {supports, confirm}`
3. Gate pass must cite at least one non-`review_report` artifact
4. `work_item.input_context_artifact_id` must resolve if status is `ready`/`completed`
5. `evidence.source_artifact_id` must resolve to existing artifacts
6. All principal references must resolve to declared principals
7. `projection.computed_status=completed` requires gate pass for this work item
8. `projection.computed_status=completed` must match `work_item.status=completed`
9. `projection.computed_status=ready` must not match `work_item.status=completed` (reverse inconsistency)
10. `projection.computed_status=insufficient_evidence` requires a decision with matching `outcome` and `target_ref`
11. `projection.computed_status=blocked` requires a blocked/human_required decision for this work item
12. Projection reference consistency: `work_item_id`, `latest_decision_id` (must exist in decisions AND target the current work item), `review_outcome`, and `gate_outcome`

### Deviations from spec

None. The spec suggested "optionally a small helper" — the semantic validator
serves this role as `validate_packet()`.

### Post-Phase 1A additions (from GPT feedback)

Two non-blocking suggestions from the Round 7 GO review were addressed after
closure:

- `latest_decision_id` now validates that the referenced decision's
  `target_ref` matches the current `work_item.id` (not just existence).
- Reverse inconsistency check: `projection.computed_status="ready"` with
  `work_item.status="completed"` is now rejected.
