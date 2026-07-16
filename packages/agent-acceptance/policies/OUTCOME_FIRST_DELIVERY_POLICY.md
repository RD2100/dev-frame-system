# Outcome-First Delivery Policy

> Authority: agent-acceptance
> Consumers: project coordinators, watchdogs, dispatchers, and runners
> Version: 1.0.0
> Priority: P0 for authority and safety boundaries; P1 for delivery efficiency

---

## Purpose

Governance exists to make useful outcomes trustworthy. It must not become a
substitute for those outcomes.

This policy keeps the existing no-fake-green, scope, secret, destructive-action,
and evidence hard stops. It changes how coordinators select work, size batches,
choose verification, and continue a finite Delivery Goal across milestones.

## Scope Boundary

The delivery hierarchy is:

1. project objective;
2. finite Delivery Goal;
3. bounded milestone;
4. batch or TaskSpec;
5. execution step.

`terminal=false` and mandatory TaskSpec consumption apply to an already active,
explicit runner chain. They do not mean that a project must invent another
batch after a milestone is accepted. A completed milestone may use
`accepted_done`, but that closes only the inner milestone chain. While its
parent Delivery Goal is active and the frozen candidate set has eligible safe
local work, the project root coordinator intentionally selects and activates
the next natural milestone without waiting for the global controller.

The coordinator MUST NOT create a TaskSpec, RED case, worker run, or review
request solely to avoid an idle status or to expand the finite Delivery Goal.

## Ownership Boundary

The global controller owns the Delivery Goal boundary, cross-project priority,
safety envelope, exception decisions, idle recovery, and final acceptance. It
MUST NOT prescribe ordinary milestone order, file sets, commands, tests, pull
requests, or batch boundaries to a healthy project root coordinator.

The project root coordinator owns the finite candidate set, milestone
selection and ordering, batching, implementation, verification, and
project-local status. At goal start it freezes candidates from committed
`HEAD`, the authoritative HANDOFF, and real failure evidence. Newly discovered
P0/P1 delivery blockers may enter the set; unrelated or lower-priority findings
go to the backlog unless the goal boundary is explicitly revised.

Workers execute bounded TaskSpecs. They do not own the parent Delivery Goal or
decide project closure.

## Outcome Evidence

The following count as delivery progress when they advance the milestone:

- a user-visible or research artifact;
- an actual product or test diff;
- a real-path test, build, or focused verification result;
- a review verdict with actionable findings;
- an accepted commit, pull request, or release candidate;
- a new bounded milestone contract tied to authoritative backlog evidence.

The following are control events, not delivery progress by themselves:

- creating or refreshing a Goal;
- reading a TaskSpec or source hash;
- probing an already attested provider;
- starting a worker, reviewer, test, hook, push, or CI run;
- polling a PID or reporting unchanged external state;
- creating a report that only restates existing evidence.

Control events may be recorded quietly. They MUST NOT be used to claim outcome
progress or justify another governance-only batch.

## Work Selection Gate

Before creating remediation work, the coordinator MUST:

1. inspect the capability in committed `HEAD` and its existing tests;
2. compare the authoritative backlog with the actual diff and current failure;
3. distinguish missing behavior from an uncommitted candidate, stale Goal, or
   external gate;
4. select the smallest milestone-relevant gap from the finite candidate set.

A dirty or untracked candidate is not proof that `HEAD` lacks the capability.
Repeated negative probes for behavior already present in `HEAD` are a task
selection failure.

## Risk Profiles

Verification and review intensity MUST follow blast radius, reversibility, and
evidence criticality.

| Profile | Typical work | Per-batch verification | Milestone verification | Review |
|---------|--------------|------------------------|------------------------|--------|
| `critical` | Production data, credentials, deployment, formal experiment entry, destructive or irreversible work | Focused checks plus a safe real-path probe when possible | Relevant full suite and explicit human gate | Independent review required; no self-review fallback |
| `high` | P0/P1 security, auth, concurrency, shared contracts, release blockers | Focused and affected integration checks, including a real-path regression | Relevant full suite before acceptance or PR | Independent review required |
| `medium` | Multi-file product P2, shared UI/business flow, non-destructive config | Focused tests and affected build/integration checks | Broad regression once per grouped milestone or PR | One batch-level review; independent review when repository policy requires it |
| `low` | Local P2/P3, docs, selectors, pure reducers, narrow diagnostics | Static or focused checks | Broader checks only at the containing milestone boundary | Root review is sufficient unless a stricter repository rule applies |
| `read_only` | Inventory, audit, evidence reconciliation | Source/evidence citations | None unless the audit changes a gate decision | No independent code review |

A low-risk hunk MUST NOT inherit a full release verification cycle merely
because it follows a high-risk batch. Critical and high-risk work MUST NOT be
downgraded to meet a governance budget.

## Batch and Pull Request Shape

- Group related low- and medium-risk changes into one coherent batch, commonly
  three to five small changes when the scope remains reviewable.
- Run focused checks while the batch is forming. Run broad or full checks once
  at the risk or milestone boundary.
- Use one pull request for one product or risk theme. A new theme receives a
  new branch or a later milestone instead of expanding an existing review.
- A batch boundary is defined by a coherent outcome and rollback unit, not by
  one function, one selector, or one turn.

## Executor and Reviewer Failure

Delegation is optional when direct root execution is safer and cheaper.

- An executor attempt with no file change, test result, or requested artifact
  is an empty delivery.
- After one empty delivery, the coordinator may narrow the same task once.
- After a second empty delivery, stop re-dispatching the same executor pattern.
  The root may take over if scope and project policy authorize it; otherwise
  record one precise blocker.
- A review artifact is invalid without an explicit verdict and findings list.
- Replace an empty reviewer once. For `critical` or `high` work, missing
  independent review remains blocking. For lower-risk work, a clearly labeled
  root-equivalent review is allowed only when project policy preauthorizes it.

Provider identity, transport, or CLI probes are collected once and reused until
the relevant external state changes. They are not a standing delivery lane.

## Long-Running Operations

Tests, builds, hooks, pushes, and CI checks SHOULD be awaited to exit, timeout,
or a recorded external wait state within the execution session that started
them. Routine progress is logged quietly. Notify the coordinator only on:

- completion;
- a new failure;
- a real no-progress timeout;
- a required scope or authority decision.

Starting a long command and ending the turn merely to poll it later is not a
completed batch.

## State Authority

The project-local Delivery Goal record and authoritative HANDOFF are the
authority for goal scope, finite candidates, outcomes, backlog, and closure
evidence. The active milestone record is authoritative inside that goal. Goal
APIs, dashboards, and watchdog records are scheduling projections.

When they disagree, reconcile the projection from the milestone record. Do not
create work merely to make a stale scheduling object look active.

## Goal Continuation and Quiet Gates

A bounded milestone may set `accepted_done` when its outcome evidence and
required risk gates pass. If its parent Delivery Goal remains active and an
eligible candidate remains, the project root coordinator SHOULD intentionally
activate and execute the next milestone in the same turn when feasible. A turn
boundary may use `ready_to_continue`, but it is not a request for the global
controller to design the next ordinary batch.

The project becomes quiescent only when the finite Delivery Goal is `closed`,
all remaining in-scope work is a valid `human_required` gate, or an
evidence-backed `exception_blocked` decision proves that no non-degrading local
path remains. Backlog outside the frozen candidate set does not keep the goal
open.

If a closure audit proves that remaining work is entirely an external or human
gate, record `human_required` once and stay quiescent until the external state
or authorization changes. Repeated unchanged wakeups are policy violations.

## Governance Budget

For ordinary delivery, governance effort SHOULD remain near or below 20 percent
of milestone effort. This is a coarse diagnostic, not a new per-step reporting
system and not a reason to skip a hard safety gate.

When the budget is exceeded, first reduce:

1. repeated status messages and polling;
2. duplicate full-suite runs;
3. micro-batches and duplicate reports;
4. executor or reviewer retries without new evidence;
5. redundant Goal and provider reconciliation.

Measure outcome throughput, escaped defects, invalid task selection, and time
to milestone. Do not optimize message count, batch count, or perpetual agent
activity as success metrics.

## Anti-Patterns

| Anti-pattern | Correct behavior |
|--------------|------------------|
| Stop after every milestone and wait for a master-designed batch | Project root activates the next eligible candidate while the Delivery Goal remains active |
| Start another RED outside the frozen candidate set solely to stay active | Close the Delivery Goal or leave the discovery in backlog |
| Global controller specifies the next ordinary file, test, PR, or batch | State the outcome and safety boundary; let the project root choose the milestone |
| Run the full suite after every low-risk hunk | Run focused checks, then one milestone-level broad check |
| Treat worker start or PID polling as progress | Wait for a deliverable, exit, failure, or timeout |
| Infer missing behavior from dirty files | Inspect `HEAD` and existing tests first |
| Retry empty workers or reviewers indefinitely | Narrow once, then take over or block according to risk |
| Keep a human-gated project awake without state change | Record the gate once and stay quiescent |
| Let Goal metadata override the milestone contract | Reconcile Goal metadata from project-local truth |
