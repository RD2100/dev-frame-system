# Outcome-First Delivery

Lifecycle state: active operating guidance

Authority: the normative rules are in
[`OUTCOME_FIRST_DELIVERY_POLICY.md`](../../packages/agent-acceptance/policies/OUTCOME_FIRST_DELIVERY_POLICY.md).
This document explains the operating model and the evidence behind it.

Related docs: [Agent Coding Discipline](agent-coding-discipline.md),
[Verification Gates](verification-gates.md),
[Runtime Invariants](runtime-invariants.md), and
[Sub-Agent Dispatch Protocol](sub-agent-dispatch-protocol.md).

## Why This Exists

A cross-project retrospective of seven concurrent deliveries found a stable
pattern:

- fake-green prevention, real-path testing, dirty-tree protection, precise Git
  handling, and high-risk fail-closed gates improved trust;
- end-to-end throughput fell when those same controls were applied to every
  small change, every turn, and every idle state;
- control-plane activity was often counted as progress even when it produced no
  product, research, test, review, or delivery evidence.

The lesson is not to remove governance. It is to place governance at the
boundaries where it changes the probability or cost of failure.

## Root-Cause Model

The observed slowdown came from eight interacting causes:

1. **Hierarchy collapse**: project objective, finite Delivery Goal, milestone,
   batch, and step were treated as one endless `terminal=false` loop.
2. **Risk flattening**: a small selector or reducer inherited the same full
   suite and review path as auth, concurrency, release, or formal experiments.
3. **Micro-batching**: coherent changes were split by function or turn, then
   each fragment paid the full setup, review, Git, and CI cost.
4. **Control-event inflation**: Goal updates, hashes, worker starts, PID polls,
   and repeated gate reports were presented as delivery progress.
5. **Task-selection drift**: dirty candidates were treated as missing features
   before committed `HEAD` and existing tests were checked.
6. **Executor persistence past value**: empty workers and reviewers were retried
   after the dispatch pattern had already proved ineffective.
7. **State plurality**: Goal metadata, local contracts, dashboards, PR state,
   and working-tree state competed as business truth.
8. **Polling orchestration**: long tests, hooks, pushes, and CI were started in
   one turn and repeatedly polled in later turns instead of being awaited or
   moved into an explicit external wait state.
9. **Master micro-management**: the global controller prescribed the next
   ordinary files, tests, pull requests, and merges, so project roots learned to
   complete one batch and wait instead of owning the Delivery Goal.

## The Five-Level Model

| Level | Question | Valid completion |
|-------|----------|------------------|
| Project objective | What durable user or research value is sought? | Product/research closure or a user-approved external gate |
| Finite Delivery Goal | Which evidence-backed candidate set is being closed now? | All in-scope candidates close or reach a valid terminal gate |
| Milestone | What bounded outcome will be produced next? | Outcome evidence and required risk gates pass |
| Batch or TaskSpec | What coherent rollback unit advances the milestone? | Actual diff/artifact plus profile-appropriate verification |
| Step | What command or edit is executing now? | Exit, timeout, failure, or explicit next step |

Run-until-terminal applies inside the explicit batch chain. At a natural
milestone boundary, `accepted_done` is honest for that inner chain. If the
parent Delivery Goal remains active and has an eligible candidate, the project
root coordinator activates the next milestone without waiting for the global
controller. It does not manufacture work outside the frozen candidate set.

## Milestone Contract

Keep one small project-local milestone record with:

```yaml
milestone_id: M-017
delivery_goal_id: DG-004
outcome: "One user-observable or research result"
authoritative_backlog_refs: []
candidate_set_ref: "HANDOFF#delivery-goal-candidates"
head_capability_checked: true
risk_profile: low | medium | high | critical | read_only
batch_scope: []
outcome_evidence: []
focused_verification: []
milestone_verification: []
review_profile: root | batch_independent | mandatory_independent | human
external_gates: []
stop_condition: "Evidence and required gates pass"
resume_pointer: "Backlog item or next milestone candidate"
parent_goal_terminal: false
```

The Delivery Goal record and authoritative HANDOFF are business truth. A Goal
API can schedule them, but cannot redefine their candidate set or closure
state.

## Work Selection

Before opening a remediation batch:

1. inspect committed `HEAD` and relevant tests;
2. build the smallest capability matrix needed for the decision;
3. compare backlog claims with the actual failure and actual diff;
4. classify the risk and choose a coherent outcome unit;
5. decline work already covered by `HEAD` or blocked only by unchanged external
   state.

This preflight is deliberately small. It prevents repeated negative probes
without creating a new inventory bureaucracy.

## Verification and Review

Use the matrix in the normative policy. In practice:

- local low-risk changes receive static or focused checks while a coherent
  batch forms;
- medium-risk work adds affected integration or build checks;
- high and critical work keeps real-path regression, broad verification, and
  independent review;
- broad or full suites run once at the milestone, PR, or release boundary when
  several related low-risk changes can share the cost.

Formal `@go` acceptance remains intentionally strict. Lower-risk work avoids
that cost by using the ordinary development path until a formal acceptance
boundary is actually needed. This preserves independent-review integrity
instead of weakening the reviewer identity rules.

## Delegation

Workers are an execution option, not a proof of process maturity.

- Dispatch when isolation, specialization, or parallelism is likely to repay
  the setup cost.
- Treat a run with no requested artifact, relevant test result, or file change
  as empty.
- Narrow once after an empty delivery. After a second empty delivery, stop that
  dispatch pattern.
- Root takeover is appropriate only when the scope, risk profile, and project
  policy permit it.
- A reviewer that reads inputs but returns no verdict has not reviewed the
  change.

## Watchdog Behavior

A watchdog observes milestones; it does not issue line-by-line work.

It should notify only when there is:

- a state transition;
- a new outcome artifact or accepted delivery;
- a real failure or no-progress timeout;
- an exception that needs a decision;
- a change in an external or human gate.

An active milestone with business progress receives no follow-up. When a
project becomes idle while its finite Delivery Goal still has safe local work,
the watchdog sends one generic resume directive: continue from authoritative
project state, choose and execute the next natural milestone. It does not name
that milestone or prescribe files, commands, tests, pull requests, or batches.

A closed or valid human-gated project remains quiet until the gate changes.
Periodic polling may update internal observations, but unchanged observations
are not user notifications. One observation read failure receives one retry;
repeated failures move to fallback evidence and backoff rather than repeated
project wakeups.

The existing `rdgoal` entry point exposes the same boundary decision as
machine-readable JSON without performing the external wakeup itself:

```powershell
rdgoal supervise <project-path> `
  --lifecycle idle `
  --delivery-state ready_to_continue `
  --safe-local-work-remaining
```

The caller owns thread observation and message delivery. It should send the
returned `prompt` only when `action` is `resume_goal`; the prompt deliberately
returns ordinary milestone selection to the project root.

## Governance Budget

Use a coarse milestone estimate:

```text
governance ratio = governance effort / total milestone effort
```

The default target is at most about 20 percent for ordinary delivery. Do not
create detailed time sheets to measure it. When the ratio is clearly exceeded,
remove duplicate reporting, retries, full-suite runs, and micro-batches before
touching safety gates.

Track four outcome-oriented measures instead:

- time to a trusted milestone;
- outcome artifacts delivered;
- escaped or prevented high-severity defects;
- false task rate: proposed remediation already covered by `HEAD`.

## What Remains Non-Negotiable

- no fake green;
- no secret exposure;
- no destructive or irreversible action without authority;
- no broad staging or dirty-tree ownership guessing;
- no P0/P1 acceptance without relevant real-path evidence;
- no high or critical acceptance without the required independent or human
  review.

Outcome-first delivery removes redundant ceremony. It does not trade away the
controls that make the outcome trustworthy.
