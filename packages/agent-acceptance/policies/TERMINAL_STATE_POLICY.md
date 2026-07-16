# Terminal State Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (must read), any automation agent
> Version: 1.1.0

---

## Core Rule

**Within an explicit bounded runner chain, terminal=false means the automation
MUST continue.** It is a hard signal, not a suggestion.

This signal is local to the active milestone, batch, or TaskSpec chain. It does
not keep the whole project in one runner chain after the current milestone
reaches `accepted_done`, and it does not authorize inventing work outside the
finite Delivery Goal merely to avoid idleness. While that parent goal remains
active, the project root may deliberately activate its next eligible milestone.
See `OUTCOME_FIRST_DELIVERY_POLICY.md`.

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
| 1 | **accepted_done** | Current bounded milestone accepted and no explicit stage remains active; later project backlog may still exist | `reason: "accepted_done"` |
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

### Resumable Backlog != Active TaskSpec

A milestone may record a resumable pointer while using `terminal=true` and
`reason=accepted_done`. A pointer is not a `next_task_spec_path`. When the
parent finite Delivery Goal remains active, the project root coordinator may
activate the next eligible milestone explicitly; it does not keep the previous
runner chain open or wait for the global controller to design that milestone.

---

## Enforcement

1. Any automation that outputs a final report when `terminal=false` is a policy violation (P0).
2. Any automation that treats `dispatch_status: ready_to_dispatch` as equivalent to `stopped` is a policy violation (P0).
3. The contract schemas (`FLOW_OUTCOME.schema.json`, `DISPATCH_RESULT.schema.json`) enforce these rules at the schema level.
4. Tests in `packages/control-plane/tests/test_outcome_first_delivery_policy.py`
   validate the bounded-chain interpretation and policy links.
5. Creating an out-of-scope TaskSpec solely to avoid `accepted_done` or an idle
   project state is a P0 authority-boundary violation.
6. A global controller prescribing the next ordinary project TaskSpec is an
   ownership-boundary violation; recovery must return milestone choice to the
   project root coordinator.
