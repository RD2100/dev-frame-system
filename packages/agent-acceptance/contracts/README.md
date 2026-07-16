# Contracts

Normative JSON schemas consumed by dev-frame-opencode and any automation agent.

## Schema Index

| Schema | Purpose | Key Rules |
|--------|---------|-----------|
| `FLOW_OUTCOME.schema.json` | Three-layer bounded-flow state (transport/business/dispatch) | `terminal=false` requires `next_task_spec_path` or `required_next_action`; `ready_to_dispatch` ≠ `dispatched`; later project milestones are out of scope |
| `TASKSPEC.schema.json` | Machine-readable task specification | Must be JSON, not Markdown-only; `high_risk=true` triggers `human_required` |
| `DISPATCH_RESULT.schema.json` | Dispatch operation result | Distinguishes 6 dispatch states; `ready_to_dispatch` and `taskspec_generated` are non-terminal |

## Usage

These schemas are the single source of truth. dev-frame-opencode MUST validate its output against these schemas. Any automation that reads flow state MUST use these schemas, not Markdown reports.

## Precedence

Contracts > Policies > Conventions. If a policy contradicts a contract, the contract wins.

---

## Runner Schemas (AA-2)

Added by AA-2: Flow Runner / TaskSpec Runner contracts. These extend AA-1 schemas with runner-level execution rules.

| Schema | Purpose | Key Rules |
|--------|---------|-----------|
| `RUNNER_CONTRACT.schema.json` | Top-level runner invocation | `terminal=false` requires `input_taskspec_path` or `next_action`; `high_risk_triggers_human_required` always true; `fail_closed` always true |
| `RUNNER_STATE.schema.json` | Runner state machine (persisted for recovery) | `terminal=false` requires `next_action`; `human_required`+`terminal=true` requires `resume_command`; heartbeat for liveness |
| `RUNNER_STEP_RESULT.schema.json` | Per-step execution result | 6 step statuses; `step_success_continue` requires `next_action`; `step_partial` is non-terminal; high-risk → `step_human_required` |

### Relationship to AA-1 Schemas

- `RUNNER_CONTRACT` references `FLOW_OUTCOME` (via `input_outcome_path`) and `TASKSPEC` (via `input_taskspec_path`)
- `RUNNER_STATE` inherits terminal semantics from `FLOW_OUTCOME` and `DISPATCH_RESULT`
- Terminal semantics are local to the explicit bounded chain. A coordinator
  may close a milestone with `accepted_done` and retain a resumable backlog
  pointer without creating a new `next_task_spec_path`.
- `RUNNER_STEP_RESULT` reuses the three-layer model (transport/business/dispatch) from `FLOW_OUTCOME`

Runner schemas are the execution layer on top of AA-1's normative layer. AA-1 defines WHAT state looks like; AA-2 defines HOW a runner must behave against that state.
