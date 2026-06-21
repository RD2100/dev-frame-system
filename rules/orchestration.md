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

## Runtime State

Snapshots, rollback logs, and rdgoal event journals are runtime state. They
must stay outside this public repository. The default runtime location is
`DEVFRAME_RUNTIME_DIR` when set, otherwise the user's `.devframe-runtime`
directory.
