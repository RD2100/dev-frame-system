# Runner Failure Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode (oracle_flow_runner.py, oracle_taskspec_runner.py)
> Version: 1.0.0
> Depends on: HUMAN_REQUIRED_TAXONOMY.md, AUTONOMOUS_PROGRESS_POLICY.md

---

## Core Rule

The runner MUST **fail-closed**: when uncertain, stop and require human intervention. The runner must never guess, assume, or silently skip.

---

## Failure Mode Matrix

| Failure Condition | Runner Status | terminal | Next Action |
|-------------------|---------------|----------|-------------|
| **Schema missing** (FLOW_OUTCOME, TASKSPEC, DISPATCH_RESULT, RUNNER_CONTRACT not found) | step_failed | true | "Schema file [name] not found. Create the schema before running." |
| **Schema invalid** (JSON parse error or validation failure) | step_failed | true | "Schema [name] is invalid: [error]. Fix the schema file." |
| **Outcome missing** (FLOW_OUTCOME.json not found when required) | step_failed | true | "FLOW_OUTCOME.json not found at [path]." |
| **TaskSpec invalid** (fails TASKSPEC.schema.json validation) | step_failed | true | "TaskSpec at [path] fails validation: [errors]." |
| **GPT review unknown** (GPT reply unparseable) | step_failed | true | "GPT decision unparseable. Re-run review or request human interpretation." |
| **CDP failure** (Chrome DevTools Protocol unavailable) | step_failed | true | "CDP not available on ports 9222-9225. Start Chrome with --remote-debugging-port=9222." |
| **High-risk action detected** (delete, move, rename, clean, overwrite) | step_human_required | true | "High-risk action [action] requires human confirmation." |
| **Repeated same failure** (same error N times consecutively) | step_blocked | true | "Same failure repeated [N] times. Human diagnosis required." |
| **Max retries exceeded** | step_blocked | true | "Max retries ([N]) exceeded for step [step_id]." |
| **Max steps exceeded** | step_blocked | true | "Max steps ([N]) reached. Human review required." |
| **Max rounds exceeded** | step_blocked | true | "Max rounds ([N]) reached. Human review required." |
| **Forbidden action attempted** | step_blocked | true | "Action [action] is forbidden per RUNNER_CONTRACT." |

---

## Fail-Closed Principle

When the runner encounters an unknown or ambiguous condition:

1. **STOP immediately** — do not attempt to continue
2. **Set terminal=true** — prevent further automatic execution
3. **Write clear reason** — explain what failed and why
4. **Provide resume_command** — tell the human how to resume after fixing

The runner must not:
- Skip the failure and continue ("best effort")
- Guess at the correct behavior
- Assume success when evidence is missing
- Silently ignore schema validation errors

---

## High-Risk Action Detection

The runner must check every action against the HUMAN_REQUIRED_TAXONOMY:

| Action Category | Taxonomy Code | Runner Behavior |
|----------------|---------------|----------------|
| File deletion | destructive_action | step_human_required |
| File movement | destructive_action | step_human_required |
| File renaming | destructive_action | step_human_required |
| Worktree cleanup | destructive_action | step_human_required |
| Evidence overwrite | evidence_overwrite | step_human_required |
| Sensitive config | sensitive_config | step_human_required |
| Scope expansion | scope_expansion | step_human_required |
| Secret exposure | external_secret | step_human_required |
| Baseline fabrication | manual_attestation_required | step_human_required |

---

## Repeated Failure Escalation

1. **1st failure**: retry with same parameters (step_retries incremented)
2. **2nd failure**: retry with different parameters if possible
3. **3rd consecutive same failure**: step_blocked, terminal=true, "Repeated failure requires human diagnosis"
4. **N failures across steps**: check `max_consecutive_failures` in safety_policy

---

## Recovery After Failure

For `step_failed` and `step_blocked`:
- RUNNER_STATE is saved with `terminal=true`
- `resume_command` is provided
- Human fixes the issue
- Human runs `resume_command`
- Runner resumes from `current_step` with fresh `terminal=false`
