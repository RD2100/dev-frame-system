# Autonomous Progress Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode, any automation agent
> Version: 1.1.0

---

## Core Rule

Automation may autonomously advance through non-destructive stages of an
explicit bounded milestone without per-step human confirmation. Certain
actions always require human confirmation regardless of stage. Automation must
not invent a new milestone or TaskSpec merely to remain active.

See `OUTCOME_FIRST_DELIVERY_POLICY.md` for outcome evidence, risk profiles,
batch sizing, quiet gates, and natural milestone completion.

---

## Outcome-First Preconditions

Before auto-advancing, the coordinator must know:

1. which bounded milestone is active;
2. which user, product, research, or risk outcome the next stage advances;
3. which risk profile controls verification and review;
4. that committed `HEAD` does not already provide the claimed missing
   capability;
5. that the next stage is explicit in the milestone rather than created only
   to avoid an idle state.

Goal refreshes, provider probes, worker starts, and unchanged status polling do
not satisfy these preconditions by themselves.

---

## Allowed Autonomous Actions

The following may proceed without human confirmation at each step:

| Category | Specific Actions |
|----------|-----------------|
| **Stage advancement** | Moving to next stage when gate is `accepted` and `allow_next_stage=true` |
| **TaskSpec generation** | Creating next-stage TaskSpec from GPT decision |
| **Non-destructive execution** | Running tests, generating reports, executing code in allowed scope |
| **Test execution** | Running the focused, affected, or milestone-level checks required by the selected risk profile |
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

1. A bounded milestone is active and names the outcome advanced by the next stage
2. Previous stage gate result is `accepted`
3. `allow_next_stage` is `true`
4. Next stage TaskSpec exists and is valid
5. Next stage actions are all in the "Allowed Autonomous" list
6. No `human_required` taxonomy code applies to any next-stage action
7. A remediation TaskSpec is supported by committed `HEAD`, actual diff, or current failure evidence

### Human-Confirmation Conditions (Any one triggers stop)

1. Previous stage gate result is `partial` without explicit next-stage allowance
2. Next stage contains any "Human-Required" action
3. `high_risk` flag is true in TaskSpec
4. GPT decision is `human_required`
5. `terminal` is true in current FLOW_OUTCOME

---

## Natural Milestone Completion

When the active milestone's outcome evidence and required gates pass, the
coordinator may set `terminal=true` with `reason=accepted_done`. Later project
backlog does not invalidate that bounded terminal state.

If the parent finite Delivery Goal remains active and its frozen candidate set
has eligible safe local work, the project root coordinator intentionally
activates and executes the next natural milestone without waiting for the
global controller to design it. It must not create or dispatch work outside the
candidate set merely to remain active.

The completion record should contain a resumable pointer when execution reaches
a turn boundary. That pointer is owned by the project root, not a request for a
master-selected batch.

If all remaining work is an unchanged external or human gate, record
`human_required` once and remain quiescent until the gate changes.

---

## Enforcement

1. Before any autonomous advance, the agent MUST check this policy.
2. If any forbidden action is detected in the next stage, the agent MUST stop and generate `HUMAN_REQUIRED_TASKSPEC.md`.
3. The agent SHALL NOT use "I assumed it was OK" as justification for bypassing human-required actions.
4. The agent SHALL NOT use "the project would otherwise be idle" as
   justification for generating or dispatching a new TaskSpec.
