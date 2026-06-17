# TaskSpec Runner Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (oracle_taskspec_runner.py)
> Version: 1.0.0
> Depends on: TASKSPEC.schema.json, RUNNER_STEP_RESULT.schema.json

---

## Core Rule

A TaskSpec must be **machine-readable JSON** validated against `contracts/TASKSPEC.schema.json`. Markdown-only TaskSpecs are **rejected** — they may exist as human-readable companions but are not valid execution input.

---

## TaskSpec Validation (Pre-Execution)

Before executing any TaskSpec, the runner MUST:

1. **Parse as JSON**: The TaskSpec file must be valid JSON.
2. **Validate against schema**: Must pass `TASKSPEC.schema.json` validation.
3. **Check required fields**: `task_id`, `stage`, `goal`, `allowed_actions`, `forbidden_actions`, `required_outputs`, `terminal_conditions` must all be present.
4. **Check high_risk flag**: If `high_risk: true`, the runner MUST stop with `step_human_required` before executing.
5. **Check forbidden_actions**: Any action listed in `forbidden_actions` must be blocked at the schema level.

If any validation fails: `step_failed` with `reason: "TaskSpec validation failed"`.

---

## TaskSpec Execution

1. **Read allowed_actions**: Only execute actions in the `allowed_actions` list.
2. **Enforce forbidden_actions**: If a task attempts a forbidden action, the runner must block it with `step_blocked`.
3. **Generate evidence**: After execution, generate evidence pack per `EVIDENCE_PACK_CONTRACT.md`.
4. **Review gate**: If `review_required: true`, submit evidence to GPT via Oracle flow.
5. **Terminal check**: Read `terminal_conditions.terminal`:
   - `false`: produce `step_success_continue` with `next_action` set to `next_on_accepted`
   - `true`: produce `step_success_terminal` with reason from `terminal_conditions.reason`

---

## High-Risk TaskSpec Path

```
TaskSpec parsed → high_risk=true detected
  → runner stops BEFORE execution
  → status: step_human_required
  → terminal: true
  → reason: "High-risk task requires human confirmation"
  → required_next_action: "Human must review and confirm execution of [task_id]"
  → resume_command: "python tools/oracle_flow_runner.py --resume --task-id [task_id]"
```

---

## Markdown-Only Rejection

If a TaskSpec exists only as Markdown (no JSON schema-validatable file):

```
→ runner cannot parse structured fields
→ status: step_failed
→ reason: "TaskSpec is Markdown-only; machine-readable JSON required per TASKSPEC.schema.json"
→ terminal: true
```

---

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| Runner executes Markdown TaskSpec | Not machine-readable | Reject; require JSON |
| Runner skips schema validation | Invalid inputs silently executed | Validate first |
| Runner ignores high_risk flag | Dangerous actions auto-executed | Stop with human_required |
| Runner ignores forbidden_actions | Scope violation | Block at schema level |
| Runner treats partial output as complete | Missing required_outputs | Check all outputs exist |
