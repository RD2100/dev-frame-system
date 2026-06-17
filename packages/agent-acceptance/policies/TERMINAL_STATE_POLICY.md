# Terminal State Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (must read), any automation agent
> Version: 1.0.0

---

## Core Rule

**terminal=false means the automation MUST continue.** It is a hard signal, not a suggestion.

When `terminal=false`, the agent SHALL NOT:
- Output a final summary report
- Stop execution
- Treat the current task as complete
- Treat `ready_to_dispatch` as `dispatched`

When `terminal=false`, the agent SHALL:
- Read `next_task_spec_path` from FLOW_OUTCOME or DISPATCH_RESULT
- Execute the next TaskSpec
- If no `next_task_spec_path` but `required_next_action` exists, follow that action

---

## Valid Terminal States (terminal=true Allowed)

Only these 6 states permit `terminal=true`:

| # | Terminal State | Meaning | Required Fields |
|---|---------------|---------|----------------|
| 1 | **accepted_done** | Task accepted and no further stages | `reason: "accepted_done"` |
| 2 | **human_required** | Human attestation/intervention needed | `required_next_action`, `resume_command` |
| 3 | **blocked_unresolvable** | Entity blocked and no reconciliation possible | `required_next_action` |
| 4 | **technical_failure** | Technical error preventing progress | `errors[]`, `required_next_action` |
| 5 | **max_rounds_reached** | Review round limit exhausted | `reason`, `required_next_action` |
| 6 | **high_risk_required** | High-risk action needs human confirmation | `required_next_action` |

---

## Non-Terminal States (terminal=false Required)

These states MUST have `terminal=false`:

| State | Meaning | Next Action |
|-------|---------|------------|
| **TaskSpec generated** | TaskSpec ready, not yet dispatched | Dispatch the TaskSpec |
| **ready_to_dispatch** | Decision made, TaskSpec waiting | Execute dispatch |
| **dispatched** | Runner invoked, awaiting result | Monitor execution |
| **accepted + allow_next_stage=true** | GPT accepted, next stage allowed | Advance to next stage |
| **partial** | Partial acceptance with allowed subset | Execute allowed subset |

---

## Key Distinctions

### TaskSpec Generated != Terminal
Generating a TaskSpec is an intermediate step. The flow is not complete until the TaskSpec is executed or the flow reaches a terminal state.

### ready_to_dispatch != dispatched
`ready_to_dispatch` means: "a decision has been made, a TaskSpec exists, and it is ready to be dispatched."
`dispatched` means: "the runner has been invoked with the TaskSpec."

The presence of `ready_to_dispatch` does NOT mean the task is done. It means the next step (dispatch) must happen.

### ready_to_dispatch != terminal
A flow in `ready_to_dispatch` state is, by definition, NOT terminal. There is still work to do.

---

## Enforcement

1. Any automation that outputs a final report when `terminal=false` is a policy violation (P0).
2. Any automation that treats `dispatch_status: ready_to_dispatch` as equivalent to `stopped` is a policy violation (P0).
3. The contract schemas (`FLOW_OUTCOME.schema.json`, `DISPATCH_RESULT.schema.json`) enforce these rules at the schema level.
4. Tests in `tests/test_terminal_state_policy.py` validate enforcement.
