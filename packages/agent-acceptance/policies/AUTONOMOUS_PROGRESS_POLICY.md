# Autonomous Progress Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode, any automation agent
> Version: 1.0.0

---

## Core Rule

Automation may autonomously advance through non-destructive stages without per-step human confirmation. Certain actions always require human confirmation regardless of stage.

---

## Allowed Autonomous Actions

The following may proceed without human confirmation at each step:

| Category | Specific Actions |
|----------|-----------------|
| **Stage advancement** | Moving to next stage when gate is `accepted` and `allow_next_stage=true` |
| **TaskSpec generation** | Creating next-stage TaskSpec from GPT decision |
| **Non-destructive execution** | Running tests, generating reports, executing code in allowed scope |
| **Test execution** | Running automated test suites |
| **Evidence pack generation** | Creating evidence packs for GPT review |
| **GPT review submission** | Uploading evidence and prompt to GPT via Chrome CDP |
| **Status file writing** | Writing FLOW_OUTCOME.json, DISPATCH_RESULT.json, ACTION_LOG.md |
| **Gate evaluation** | Evaluating agent-acceptance gates against evidence |

---

## Human-Required Actions (Always)

These actions SHALL NOT proceed without human attestation:

| Category | Subtype | HUMAN_REQUIRED_TAXONOMY Code |
|----------|---------|------------------------------|
| **File deletion** | Any `rm`, `del`, `git clean` | `destructive_action` |
| **File movement** | `mv`, git mv | `destructive_action` |
| **File renaming** | Renaming any file outside task scope | `destructive_action` |
| **Worktree cleanup** | `git clean -f`, removing worktrees | `destructive_action` |
| **Evidence overwrite** | Overwriting historical GPT review results | `evidence_overwrite` |
| **Sensitive config modification** | Editing .env, secrets, credentials | `sensitive_config` |
| **Baseline fabrication** | Creating fake baseline or attestation | `manual_attestation_required` |
| **Human attestation fabrication** | Forging human approval records | `manual_attestation_required` |
| **Sensitive information upload** | Uploading secrets to external services | `external_secret` |
| **Scope expansion** | Adding files outside approved AA-1 scope | `scope_expansion` |
| **Ambiguous authority** | Actions where ownership is unclear | `ambiguous_authority` |

---

## Stage Advancement Rules

### Auto-Advance Conditions (ALL must be true)

1. Previous stage gate result is `accepted`
2. `allow_next_stage` is `true`
3. Next stage TaskSpec exists and is valid
4. Next stage actions are all in the "Allowed Autonomous" list
5. No `human_required` taxonomy code applies to any next-stage action

### Human-Confirmation Conditions (Any one triggers stop)

1. Previous stage gate result is `partial` without explicit next-stage allowance
2. Next stage contains any "Human-Required" action
3. `high_risk` flag is true in TaskSpec
4. GPT decision is `human_required`
5. `terminal` is true in current FLOW_OUTCOME

---

## Enforcement

1. Before any autonomous advance, the agent MUST check this policy.
2. If any forbidden action is detected in the next stage, the agent MUST stop and generate `HUMAN_REQUIRED_TASKSPEC.md`.
3. The agent SHALL NOT use "I assumed it was OK" as justification for bypassing human-required actions.
