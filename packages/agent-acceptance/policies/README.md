# Policies

Normative policy documents. These define behavioral rules that complement the JSON schemas.

## Policy Index

| Policy | Purpose | Priority |
|--------|---------|----------|
| `TERMINAL_STATE_POLICY.md` | Defines when terminal=true is valid; when false, agent MUST continue | P0 |
| `DISPATCHER_POLICY.md` | Dispatcher must produce actionable DISPATCH_RESULT; not just suggestions | P0 |
| `AUTONOMOUS_PROGRESS_POLICY.md` | What can auto-advance vs what requires human | P0 |
| `HUMAN_REQUIRED_TAXONOMY.md` | 8-category taxonomy for human_required reasons | P1 |
| `STAGE_GATE_POLICY.md` | Gate definitions and stage advancement conditions | P0 |
| `EVIDENCE_PACK_CONTRACT.md` | Minimum evidence pack requirements, manifest format | P1 |

## Relationship to Contracts

- **Contracts** (schemas/) define WHAT the data must look like
- **Policies** (policies/) define HOW automation must behave
- If a policy contradicts a contract, the contract wins (contracts are machine-enforceable)
- Policies provide the rationales and decision matrices that contracts reference

## Precedence

Within policies: P0 policies override P1 policies.

---

## Runner Policies (AA-2)

Added by AA-2: Flow Runner / TaskSpec Runner behavioral rules.

| Policy | Purpose | Priority |
|--------|---------|----------|
| `FLOW_RUNNER_POLICY.md` | Runner is dev-frame execution layer; reads agent-acceptance rules; validates schemas before execution; only terminal=true produces final report | P0 |
| `TASKSPEC_RUNNER_POLICY.md` | TaskSpec must be machine-readable JSON; Markdown-only rejected; high_risk → human_required; forbidden_actions blocked at schema level | P0 |
| `RUN_UNTIL_TERMINAL_POLICY.md` | Default: run-until-terminal; terminal=false NEVER stops; only 6 valid terminal reasons; TaskSpec generation ≠ terminal | P0 |
| `NEXT_TASKSPEC_CONSUMPTION_POLICY.md` | next_task_spec_path is mandatory consumption; ready_to_dispatch ≠ dispatched; unconsumed TaskSpec = P0 violation | P0 |
| `RUNNER_FAILURE_POLICY.md` | Fail-closed on schema missing/invalid, outcome missing, GPT unknown, CDP failure; high-risk → human_required; repeated failure escalation | P0 |

### Runner Policy Precedence

Runner policies (AA-2) build on AA-1 policies. When a runner policy references the same concept as an AA-1 policy (e.g., terminal state), the AA-2 policy provides **runner-level enforcement** — the AA-1 policy remains the normative definition.

AA-1 policies define WHAT the rules are. AA-2 runner policies define HOW the runner mechanically enforces them.
