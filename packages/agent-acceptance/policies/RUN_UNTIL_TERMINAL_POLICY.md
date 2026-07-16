# Run-Until-Terminal Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (oracle_flow_runner.py)
> Version: 1.1.0
> Depends on: TERMINAL_STATE_POLICY.md, RUNNER_STATE.schema.json

---

## Core Rule

The runner's default mode is **run-until-terminal** for the explicit bounded
chain it was given: it continues executing steps as long as `terminal=false`.
It only stops when `terminal=true` for a valid terminal reason.

**terminal=false NEVER means "stop."** It ALWAYS means "continue."

This rule does not make the entire project one endless runner chain. The runner
must not synthesize a new TaskSpec or RED case outside the finite Delivery Goal
after a milestone completes. Project-level continuation and project-root-owned
milestone activation are governed by `OUTCOME_FIRST_DELIVERY_POLICY.md`.

---

## Valid Stop Conditions (terminal=true)

The runner may only set `terminal=true` for these reasons (inherited from TERMINAL_STATE_POLICY.md):

| # | Reason | Trigger |
|---|--------|---------|
| 1 | **accepted_done** | Task accepted and no further stages exist |
| 2 | **human_required** | Human attestation/intervention needed before continuing |
| 3 | **blocked_unresolvable** | Entity is blocked with no reconciliation path |
| 4 | **technical_failure** | Technical error prevents progress (CDP down, schema missing, etc.) |
| 5 | **max_rounds_reached** | Review round limit exceeded |
| 6 | **high_risk_required** | High-risk action detected, human confirmation needed |

---

## Continue Conditions (terminal=false)

The runner MUST continue when:

| Condition | Action |
|-----------|--------|
| `terminal=false` in RUNNER_STATE | Read `next_action` and execute it |
| `next_task_spec_path` exists | Consume and execute the TaskSpec |
| `last_decision=accepted` and `allow_next_stage=true` | Generate/consume next stage TaskSpec |
| `status=step_success_continue` | Execute `next_action` |
| `status=step_partial` | Continue with remaining partial actions |
| `dispatch_status=ready_to_dispatch` | Execute dispatch to transition to `dispatched` |
| `dispatch_status=taskspec_generated` | Dispatch the generated TaskSpec for execution |

The table applies only when the referenced next action or TaskSpec already
belongs to the active bounded chain.

---

## Step Loop

```
while terminal == false:
    1. Read next_action from RUNNER_STATE
    2. Validate next action against allowed_actions / forbidden_actions
    3. Execute step
    4. Produce RUNNER_STEP_RESULT
    5. Update RUNNER_STATE (increment step, set terminal, set next_action)
    6. Write RUNNER_STATE.json
    7. If terminal == true: break and produce final report
    8. If step >= max_steps: terminal = true (max_rounds_reached)
```

---

## Terminal=false + No Next Action = Invalid

If `terminal=false` and RUNNER_STATE has no `next_action` and no `next_task_spec_path`:

```
→ RUNNER_STATE is INVALID
→ runner must fail-closed with reason: "terminal=false but no next_action or next_task_spec_path"
→ status: step_failed
```

This is a schema-level constraint enforced by RUNNER_STATE.schema.json.

---

## Generating TaskSpec != Terminal

Generating a next-stage TaskSpec is a `step_success_continue`, not `step_success_terminal`. The runner must proceed to dispatch and execute the generated TaskSpec.

---

## Long-Running Step Closure

When a step starts a test, build, hook, push, or other long-running command, the
runner should wait in the same execution session until the command exits,
times out, or enters a recorded external wait state. Routine PID or case
progress may be logged without ending the run.

Starting a command, returning a final answer, and relying on later watchdog
turns for ordinary polling is not run-until-terminal behavior.

---

## Natural Milestone Completion

When the bounded milestone has no explicit stage left and its required evidence
passes, use `terminal=true` with `reason=accepted_done`. Preserve a resumable
pointer as metadata if useful. If the parent finite Delivery Goal remains
active and an eligible candidate remains, the project root coordinator
deliberately starts the next milestone; the global controller does not choose
or prescribe that ordinary TaskSpec.

---

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| Runner stops at terminal=false | Loses continuation | Continue to next_action |
| Runner produces final report at terminal=false | Masks incomplete flow | Only report at terminal=true |
| Runner treats TaskSpec generation as done | Leaves generated TaskSpec unconsumed | Continue to dispatch |
| Runner continues when terminal=true | Ignores stop signal | Stop and produce final report |
| Runner invents terminal reasons | Not in the 6 allowed reasons | Only use defined terminal reasons |
| Runner creates an out-of-scope batch only to remain active | Expands the finite Delivery Goal | Close with `accepted_done` and leave the discovery in backlog |
| Global controller prescribes the next ordinary runner batch | Converts project root into a one-shot executor | Let the project root activate the next eligible milestone |
| Runner ends a turn while its ordinary command is still running | Converts execution into repeated polling | Await exit, timeout, failure, or a recorded external wait state |
