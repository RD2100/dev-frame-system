# Recon Receipt: M1 explicit team messages

> Governs the next write-capable M1 slice under `rules/recon.md`
> recon-001/003/008/009 and `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: make agent-to-agent communication a recorded runtime fact, rather
  than a message synthesized from task lifecycle events.
- target: `packages/control-plane/control_plane/team_runtime.py` and its direct
  tests.
- current_slice_goal: append and read one explicit, text-only `agent_message`
  event in the existing outside-repository team journal.
- out of scope: HTTP/MCP write endpoints, external A2A transport, task-claim
  contention, shared memory, execution commands, and UI changes.

## Resource Map

- runtime entrypoint: `go_dispatch.py` owns the existing execution-time
  `TeamRuntime` instance; `workflow_engine.py` records workflow facts through
  the same class.
- durable state: `team-events.jsonl`, held under the configured runtime
  directory and rejected when that directory is inside the public repository.
- read model: `build_team_runtime_view()` folds journal records into the
  existing `message_bus` and `event_log` schema shapes.
- schema consumer: `visual_state.py` and `t3_adapter.py` merge real facts into
  their existing team projections.
- direct tests: `packages/control-plane/tests/test_team_runtime.py`.

## Current Gap

`task_created`, `task_claimed`, `task_result`, review, verdict, and workflow
records currently create message-shaped read entries. They are useful lifecycle
notifications, but there is no durable event for an agent-originated message to
a named recipient. Treating those projections as agent-to-agent messaging would
violate recon-008's first-class-object requirement.

## Capability Matrix And Reuse Decision

| Capability | Candidate | Decision |
| --- | --- | --- |
| Durable, concurrent append-only facts | Existing `TeamRuntime` JSONL writer and outside-repo guard | Reuse directly |
| Team message/read-model shape | Existing `message_bus` entries and visual-state schema | Reuse directly |
| Cross-system agent protocol | [A2A specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md), verified 2026-07-16 | Do not import yet |

A2A 1.0 defines interoperable message and task operations for independent
agent systems. This slice has one trusted local runtime, no network transport,
and no discovery or authentication boundary to integrate. Adding an A2A SDK or
HTTP binding would enlarge both the public and security surface without helping
the required local fact model. DevFrame retains ownership of the journal,
contracts, evidence, and review gates.

## Integration Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| A projected lifecycle message is mistaken for a real message | P0 | Require a distinct `agent_message` journal event before projection. |
| Message text becomes an execution channel | P0 | Store and project text only; no dispatcher, command parser, or HTTP/MCP write route. |
| Journal leaks into public distribution | P1 | Preserve `TeamRuntime._append()` outside-repository guard and test it through the new method. |
| Adjacent team objects drift | P1 | Change only direct runtime/test paths; leave task claims, blackboard, UI, and schema untouched. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/team_runtime.py`
  - `packages/control-plane/tests/test_team_runtime.py`
  - this receipt
- production contract: `record_agent_message(run_id, from_agent_id,
  to_agent_id, kind, summary)` records one append-only `agent_message` fact.
  `build_team_runtime_view()` exposes that fact as one `agent-message` event and
  one exact `message_bus` entry.
- fail-closed contract: missing sender, recipient, kind, or summary is rejected;
  an in-repository runtime directory remains rejected; no new network or command
  path is introduced.
- real RED probe: create a `TeamRuntime`, append a direct message request, and
  assert the durable read model has no corresponding exact sender/recipient/kind
  entry before implementation.
- GREEN evidence: direct durable journal and read-model test, targeted team
  runtime regression, relevant control-plane regression, actual-diff review,
  and independent Reviewer Index.

## Team Objects

In scope: Message Bus and Event Log. Reused but unchanged: Agent Registry, Task
Board, Evidence Store, Review Gate, Conflict Control. Deferred: claim
contention and shared memory.
