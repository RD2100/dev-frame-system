# rdgoal Total-Control Orchestration

`rdgoal` is the controller layer above project-local `rdinit` workflows. It is
for running many projects at once while replacing routine human approval loops
with recorded decisions, rollback snapshots, and final review.

## Reader Outcome

After reading this document, an operator should be able to register a project,
route a requirement through the controller, and understand why a decision was
executed, snapshotted, drafted, or stopped.

## Operating Principle

The controller is not an approval queue. It acts as the temporary project lead:

- routine reversible work is dispatched;
- direction choices use the recommended MVP path;
- local destructive work is snapshotted before dispatch;
- external irreversible work is prepared as a draft;
- secret exposure is stopped.

The human reviews the resulting prototype and digest instead of approving every
intermediate choice.

## Project Contracts

Each project has a contract under its own `rules/project-contracts/` directory
unless `--contracts-dir` points to a controller-owned contract directory. The
contract defines the goal, non-goals, autonomy level, decision policy,
prototype bias, and stop lines.

The default autonomy level is `total_control`. In that mode, the controller is
expected to choose and continue inside the project goal. Use `supervised` or
`green_only` only when a project needs a narrower operating envelope.

## Decision Modes

`auto_execute` dispatches routine reversible work.

`snapshot_execute` creates a local rollback snapshot before dispatching a local
delete, overwrite, config edit, migration, dependency upgrade, or destructive
refactor.

`recommend_execute` is used for direction choices. The controller chooses the
path closest to the existing project style and working prototype goal, then
records the recommendation.

`draft_only` prepares scripts, checklists, or patch drafts for external
real-world effects. It does not publish, spend money, delete remote production
data, or perform live deployment.

`hard_stop` is reserved for secret or credential boundaries.

## CLI Shape

The human-facing entrypoint is:

```text
/rdgoal <project> <goal>
```

In a shell, use the installed console script:

```powershell
rdgoal "D:\projects\app-a" "Build the MVP" --digest
```

The same entry point remains available through the umbrella control-plane CLI
and the Python module path for compatibility:

```powershell
devframe rdgoal "D:\projects\app-a" "Build the MVP" --digest
python -m control_plane.rdgoal_cli "D:\projects\app-a" "Build the MVP" --digest
```

Use `--operation` and repeated `--target` values to route a specific next
operation:

```powershell
rdgoal "D:\projects\app-a" "Build the MVP" `
  --operation "delete obsolete local module" `
  --target "src/old_module.py" `
  --digest
```

If the operation needs a snapshot, rollback state is written to the local
runtime directory. Set `DEVFRAME_RUNTIME_DIR` to control that location.

Use `--contracts-dir` only when a controller repository should own contracts
for several projects. Without it, rdgoal writes the contract into the target
project's `rules/project-contracts/` directory.

`--apply-rdinit` runs the full bootstrap only when rdgoal is executed from a
source checkout that has the root `rules/`, `schemas/`, and
`docs/agent-runtime/` assets. Wheel installs can still create contracts and
dispatch packets, but report `bootstrap_unavailable` instead of failing when
those bootstrap assets are absent.

## Relationship to rdinit and SADP

`rdgoal` does not replace the project-local workflow. It creates a
self-contained SADP objective for the sub-agent and expects the project-local
agent to produce the usual ExecutionReport, evidence, reviewer focus, and known
gaps.

The controller owns cross-project scheduling and decision policy. The
project-local workflow owns implementation, test evidence, and reviewer
separation.

## First MVP Boundary

The first implementation proves the controller path: contract loading, decision
classification, snapshot logging, objective generation, and digest rendering.
Live worker dispatch can be attached after this path is stable.

## Dispatch Packets

Each controller decision writes a dispatch packet to the local runtime outbox.
The packet directory contains:

- `packet.json`: machine-readable project id, operation, decision mode,
  TaskSpec subset, targets, and objective text.
- `TASKSPEC.json`: canonical machine-readable TaskSpec for runners that consume
  the agent-runtime TaskSpec schema.
- `TASKSPEC.md`: human-readable worker handoff for a project-local agent.

The packet is the handoff boundary between the total-control controller and any
worker implementation. A future worker may be an opencode runner, CDP-dispatched
ChatGPT tab, WorkQueue consumer, or direct Codex session. The packet format keeps
that choice outside the controller.

## Report Ingest

After a worker completes, ingest its ExecutionReport:

```powershell
rdgoal ingest "C:\Users\you\.devframe-runtime\rdgoal-outbox\app\packet-id" `
  "D:\projects\app\reports\ExecutionReport.md"
```

Ingest creates an execution summary in the runtime report store and adds a
controller journal event. The digest can then show both decisions and returned
worker status.

To inspect persisted runtime state across CLI invocations:

```powershell
rdgoal digest
```

## Local Dry-Run Worker

The first worker implementation is intentionally conservative. It consumes a
packet, writes an `ExecutionReport.md`, and ingests that report without changing
project files:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\app\packet-id"
```

Use it to prove the controller loop before attaching a live runner. A
dispatch-ready packet reports `pass`; a draft-only or held packet reports
`blocked` with no project changes.

## Command Worker Adapter

When a live runner is ready, use the command worker adapter:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\app\packet-id" `
  --command python -m your_worker_module
```

The command runs from the packet's `project_root`. It receives these environment
variables:

- `RDGOAL_PACKET_DIR`: packet directory.
- `RDGOAL_PACKET_JSON`: machine-readable packet path.
- `RDGOAL_TASKSPEC_JSON`: canonical TaskSpec JSON path.
- `RDGOAL_TASKSPEC_MD`: human-readable TaskSpec path.
- `RDGOAL_REPORT_PATH`: where the worker must write `ExecutionReport.md`.

If the command exits non-zero, times out, or does not write the report, rdgoal
creates a failed ExecutionReport. Runner failure must not become a fake pass.
The worker CLI exits non-zero when the generated summary is `blocked`,
`failed`, or unknown.

## AI Workflow Hub Worker

When `ai_workflow_hub` is available, rdgoal can call its existing `go` entry
point directly:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\app\packet-id" `
  --aihub-go
```

This runs:

```text
python -m ai_workflow_hub.cli go TASKSPEC.json --project <project_id> --dry-run
```

Use `--apply` only when the project is ready for the existing AI Workflow Hub
runner to make changes. The default path is dry-run so the controller can prove
the handoff before live execution. Use `--python` or `--aihub-module` when the
runner lives in a non-default Python environment.
