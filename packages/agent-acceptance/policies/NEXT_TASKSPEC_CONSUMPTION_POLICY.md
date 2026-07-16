# Next TaskSpec Consumption Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (oracle_flow_runner.py, oracle_taskspec_runner.py)
> Version: 1.1.0
> Depends on: TASKSPEC.schema.json, DISPATCH_RESULT.schema.json, RUN_UNTIL_TERMINAL_POLICY.md

---

## Core Rule

**If `next_task_spec_path` exists, it MUST be consumed.** A generated TaskSpec is a mandatory next step, not an optional suggestion.

Failing to consume `next_task_spec_path` when `terminal=false` is a P0 policy violation.

This is a consumption rule, not a TaskSpec creation mandate. A coordinator
MUST NOT create `next_task_spec_path` solely to avoid an idle project or to
prove continued activity after a milestone reaches `accepted_done`. See
`OUTCOME_FIRST_DELIVERY_POLICY.md`.

---

## Consumption Chain

```
next_task_spec_path set
  → runner reads TaskSpec from path
  → runner validates TaskSpec against TASKSPEC.schema.json
  → runner checks high_risk flag
  → runner executes TaskSpec (or human_required if high_risk)
  → runner produces RUNNER_STEP_RESULT
  → runner updates RUNNER_STATE (clear next_task_spec_path, set new next_action)
```

---

## Key Distinctions

### resumable pointer != next_task_spec_path

A closed milestone may name the next eligible candidate or a backlog item for
recovery. That pointer is scheduling metadata. While the parent finite Delivery
Goal remains active, the project root coordinator decides whether to activate
the candidate as `next_task_spec_path`; the global controller does not design
the ordinary batch. Once activated in a non-terminal chain, consumption is
mandatory.

### ready_to_dispatch != dispatched

`dispatch_status: ready_to_dispatch` means a TaskSpec is ready. It does NOT mean it has been dispatched. The runner must:
1. Read the TaskSpec
2. Validate it
3. Execute it (or dispatch it)
4. Transition to `dispatch_status: dispatched`

Merely setting `ready_to_dispatch` without executing the TaskSpec is incomplete.

### taskspec_generated != terminal

`dispatch_status: taskspec_generated` means the TaskSpec was created. It is not a terminal state. The runner must continue to dispatch and execute.

### TaskSpec exists but not consumed

If a TaskSpec file exists at `next_task_spec_path` and the runner stops without consuming it:

```
→ FAIL: POLICY VIOLATION
→ reason: "next_task_spec_path exists but was not consumed"
→ required action: "Resume runner to consume [path]"
```

---

## Consumption Failure Modes

| Failure | Runner Action |
|---------|-------------|
| TaskSpec path broken/missing | step_failed: "TaskSpec not found at [path]" |
| TaskSpec invalid JSON | step_failed: "TaskSpec is not valid JSON" |
| TaskSpec fails schema validation | step_failed: "TaskSpec fails TASKSPEC.schema.json" |
| TaskSpec is Markdown-only | step_failed: "TaskSpec is Markdown-only, JSON required" |
| TaskSpec high_risk=true | step_human_required: "High-risk TaskSpec requires human confirmation" |
| TaskSpec contains forbidden action | step_blocked: "TaskSpec contains forbidden action [action]" |
| Runner cannot execute (mode=single_step) | step_success_continue: "TaskSpec validated, ready for execution" with resume_command |

---

## Runner Cannot Execute

If the runner is in a mode where it can only prepare but not execute (e.g., `single_step` or `dry_run`):

1. Set `status: step_success_continue` (not terminal)
2. Write `resume_command` in RUNNER_STATE
3. Set `reason: "TaskSpec validated and ready; use resume_command to execute"`
4. Do NOT set `terminal=true`

---

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| next_task_spec_path set but ignored | Unconsumed TaskSpec = broken chain | Consume immediately |
| ready_to_dispatch treated as dispatched | State misrepresented | Execute, then set dispatched |
| TaskSpec generated treated as terminal | Stops before execution | Continue to dispatch |
| Runner defers consumption without resume_command | Cannot resume later | Always provide resume_command |
| Coordinator creates an out-of-scope TaskSpec only to avoid idle | Expands the finite Delivery Goal | Close the goal or retain the discovery in backlog |
| Global controller chooses the next ordinary TaskSpec | Removes project-root ownership | Send a generic resume directive and let the project root select it |
