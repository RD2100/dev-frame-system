# Flow Runner Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (oracle_flow_runner.py)
> Version: 1.0.0
> Depends on: FLOW_OUTCOME.schema.json, TASKSPEC.schema.json, DISPATCH_RESULT.schema.json, RUNNER_CONTRACT.schema.json, RUNNER_STATE.schema.json

---

## Core Rule

The Flow Runner is a dev-frame-opencode execution component whose **sole normative authority** is agent-acceptance. The runner must not invent its own rules — it reads contracts, policies, and schemas from agent-acceptance.

---

## Runner Responsibilities

1. **Validate inputs before execution**: Every runner invocation must validate FLOW_OUTCOME, TASKSPEC, DISPATCH_RESULT against their respective schemas before executing any action.

2. **Run-until-terminal by default**: Unless mode is `single_step` or `dry_run`, the runner continues executing steps until `terminal=true`.

3. **Output final report ONLY when terminal=true**: The runner must not produce a terminal summary while `terminal=false`. A "final report" at `terminal=false` is a policy violation (P0).

4. **Consume next_action when terminal=false**: If `terminal=false`, the runner must read `next_action` or `next_task_spec_path` from RUNNER_STATE and execute it.

5. **Persist RUNNER_STATE after every step**: The runner must write RUNNER_STATE.json after each step, enabling crash recovery.

6. **Write FLOW_OUTCOME after each GPT round**: After each GPT review cycle, the runner must write FLOW_OUTCOME.json.

7. **Machine-readable only**: The runner must not use Markdown reports as automation decision input. Only JSON schemas and machine-readable state files.

---

## Runner Lifecycle

```
1. Dispatcher invokes runner with RUNNER_CONTRACT
2. Runner validates all input schemas
3. Runner executes Step 1
4. Runner writes RUNNER_STATE (terminal=false, next_action set)
5. If step status is step_success_continue: execute next_action
6. Repeat until terminal=true or max_steps/max_rounds reached
7. On terminal=true: write final FLOW_OUTCOME, produce final report
```

---

## Crash Recovery

1. On startup, runner checks for existing RUNNER_STATE.json
2. If RUNNER_STATE exists with terminal=false: resume from `current_step` using `resume_command`
3. If RUNNER_STATE exists with terminal=true: report terminal without re-execution
4. If no RUNNER_STATE: start fresh from RUNNER_CONTRACT

---

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| Runner invents stop/continue logic | Normative authority is agent-acceptance | Read terminal from RUNNER_STATE |
| Runner writes final report at terminal=false | Loses continuation signal | Only report at terminal=true |
| Runner reads Markdown for decisions | Not machine-readable | Read JSON schemas only |
| Runner skips schema validation | Invalid inputs → wrong behavior | Validate all inputs first |
| Runner doesn't persist state | Cannot resume after crash | Write RUNNER_STATE after every step |

---

## Integration with AA-1

The Flow Runner extends AA-1's contracts:
- Reads FLOW_OUTCOME (AA-1) to know business_decision and terminal
- Reads TASKSPEC (AA-1) to know what to execute
- Reads DISPATCH_RESULT (AA-1) to know dispatch state
- Uses RUNNER_CONTRACT (AA-2) for invocation parameters
- Writes RUNNER_STATE (AA-2) for recovery
