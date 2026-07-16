# Orchestration Rules -- rdgoal Total Control

> Domain: multi-project orchestration
> Purpose: let a controller advance many project-local rdinit workflows while
> replacing routine human approvals with reversible execution and decision logs.

This rule set complements `core.md`, `git.md`, and the Sub-Agent Dispatch
Protocol. It does not weaken secret protection, evidence requirements, reviewer
separation, or no-fake-green behavior.

## Core Model

The controller classifies every operation into an execution mode:

| Mode | Meaning | Controller behavior |
|------|---------|---------------------|
| `auto_execute` | Routine reversible work | Dispatch to the project workflow |
| `snapshot_execute` | Local destructive or costly work | Snapshot targets, log rollback reference, then dispatch |
| `recommend_execute` | Directional or architecture choice | Choose the recommended path, record the reason, then dispatch |
| `draft_only` | External real-world effect | Prepare scripts, checklist, and rollback notes, but do not perform the live action |
| `hard_stop` | Secret or system boundary | Stop and report the blocked reason |

## RULE orch-001: Decide Before Dispatch

- **Priority**: P0
- **Trigger**: Any operation routed through rdgoal
- **Rule**: The controller must produce an execution mode before dispatching
  work to a project-local agent.
- **Verification**: The runtime journal contains a `decision_made` event with
  `decision_mode`.

## RULE orch-002: Direction Choices Are Delegated

- **Priority**: P1
- **Trigger**: Architecture, design, product-shape, or ambiguous requirement
  decisions inside the project contract
- **Rule**: Direction choices use `recommend_execute`. The controller chooses
  the path closest to the existing project style and working MVP goal.
- **Verification**: The digest records the decision mode and recommended path.

## RULE orch-003: Snapshot Before Local Destruction

- **Priority**: P0
- **Trigger**: Local delete, overwrite, replacement, destructive refactor,
  config edit, migration, or dependency upgrade
- **Rule**: The controller must create a rollback snapshot outside the repo
  before dispatching.
- **Verification**: The rollback log contains a snapshot reference for the
  operation.

## RULE orch-004: External Effects Become Drafts

- **Priority**: P0
- **Trigger**: Production release, publishing, spending money, deleting remote
  production data, force push, or similar live external effect
- **Rule**: The controller prepares an execution draft and does not perform the
  live action.
- **Verification**: The decision mode is `draft_only` and `dispatch_ready` is
  false.

## RULE orch-005: Secrets Are Hard Stops

- **Priority**: P0
- **Trigger**: Reading, exposing, or copying secrets, tokens, credentials,
  `.env`, `.pem`, or equivalent material
- **Rule**: The controller must not draft or dispatch the action.
- **Verification**: The decision mode is `hard_stop`.

## RULE orch-006: Bound Work to an Outcome Milestone

- **Priority**: P1
- **Trigger**: Creating a project Goal, batch, TaskSpec, or watchdog recovery
- **Rule**: The controller must name a finite Delivery Goal before dispatch.
  Project objective, Delivery Goal, milestone, batch, and step are separate
  levels. At goal start the project root freezes an evidence-backed candidate
  set; new P0/P1 blockers may enter, while unrelated or lower-priority findings
  go to backlog. `terminal=false` applies only to the explicit active chain and
  must not be used to expand the goal.
- **Verification**: The project-local Delivery Goal and milestone records name
  the outcome, candidate-set authority, risk profile, evidence, stop condition,
  and resume pointer.

## RULE orch-007: Match Governance to Risk

- **Priority**: P1
- **Trigger**: Sizing a batch or selecting tests and review
- **Rule**: Use the risk profiles in
  `packages/agent-acceptance/policies/OUTCOME_FIRST_DELIVERY_POLICY.md`. Group
  related low- and medium-risk changes into one reviewable batch. Focused checks
  run while the batch forms; broad or full checks run at the relevant
  milestone, PR, or high-risk boundary. Critical and high-risk work keeps its
  real-path and independent-review gates.
- **Verification**: The milestone record ties verification and review commands
  to one declared risk profile. One PR contains one coherent product or risk
  theme.

## RULE orch-008: Natural Stops and Quiet Gates Are Valid

- **Priority**: P1
- **Trigger**: A bounded milestone completes or reaches an external gate
- **Rule**: When outcome evidence and required gates pass, close the milestone
  as `accepted_done`. If the parent Delivery Goal remains active and an eligible
  candidate remains, the project root selects and executes the next natural
  milestone without waiting for a master-designed batch. Do not create work
  outside the finite candidate set solely to avoid idle. When all remaining
  in-scope work is an unchanged human or external gate, record
  `human_required` once and remain quiescent until state or authority changes.
- **Verification**: Milestone closure has evidence and either the next
  project-selected milestone, a turn-boundary `ready_to_continue` pointer, or a
  valid Delivery Goal terminal state. Repeated watchdog notifications require a
  state transition, new failure, new outcome, or decision request.

## RULE orch-009: Stop Empty Executor and Reviewer Loops

- **Priority**: P1
- **Trigger**: A worker produces no requested artifact, or a reviewer produces
  no explicit verdict
- **Rule**: Narrow an empty executor once; after a second empty delivery, stop
  that dispatch pattern and take over only when scope and policy permit.
  Replace an empty reviewer once. Missing independent review remains blocking
  for critical and high-risk work; lower-risk fallback must be explicitly
  preauthorized and labeled non-independent.
- **Verification**: ExecutionReport records attempts, deliverables, explicit
  verdict, fallback authority, and the final routing decision.

## RULE orch-010: Close Long Operations in Their Execution Session

- **Priority**: P1
- **Trigger**: Tests, builds, hooks, pushes, CI, or other long-running commands
- **Rule**: The session that starts the operation waits until exit, timeout, or
  a recorded external wait state. Routine PID and case progress stay quiet.
  Notify only on completion, new failure, real no-progress timeout, or a needed
  scope or authority decision.
- **Verification**: The operation record contains start, terminal event or
  external wait state, exit status when available, and no duplicate restart.

## RULE orch-011: Business Truth Is Project-Local

- **Priority**: P1
- **Trigger**: Goal, dashboard, watchdog, milestone, and working-tree state
  disagree
- **Rule**: The project-local Delivery Goal record and authoritative HANDOFF are
  authoritative for business scope, finite candidates, backlog, and closure;
  the active milestone record is authoritative within that goal. Goal APIs and
  dashboards are scheduling projections. Reconcile projections from
  project-local truth; do not create work to make stale metadata appear active.
- **Verification**: A reconciliation names the authoritative record and updates
  or retires the stale projection without changing business scope.

## RULE orch-012: Global Controller Supervises, Project Root Executes

- **Priority**: P1
- **Trigger**: Initial Delivery Goal dispatch, watchdog recovery, or project
  coordinator continuation
- **Rule**: The global controller owns goal boundaries, cross-project priority,
  risk exceptions, idle recovery, and final acceptance. It must not design an
  ordinary next milestone by prescribing files, commands, tests, pull requests,
  or batch boundaries. The project root coordinator owns milestone selection,
  ordering, batching, implementation, verification, and status until the finite
  Delivery Goal reaches a valid terminal state.
- **Verification**: A recovery directive references the authoritative project
  state and tells the project root to choose and execute its next natural
  milestone. It contains no controller-selected ordinary batch plan.

## Runtime State

Snapshots, rollback logs, and rdgoal event journals are runtime state. They
must stay outside this public repository. The default runtime location is
`DEVFRAME_RUNTIME_DIR` when set, otherwise the user's `.devframe-runtime`
directory.
