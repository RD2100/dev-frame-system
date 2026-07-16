# Recon Receipt: M1 `/go` explicit team-message route

> Governs a bounded M1 collaboration-runtime slice under `rules/recon.md`
> recon-001/003/008/009 and `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: Let an executing `/go` agent record an explicit, auditable message
  to another agent in the same run without turning worker text into an execution
  channel.
- target: `go_dispatch.py`, `team_runtime.py`, and their direct runtime tests.
- current_slice_goal: ingest a packet-local structured message sidecar after a
  worker completes, then record a durable `agent_message` event.
- out of scope: A2A/network transport, HTTP/MCP writes, shared memory,
  blackboards, UI, command dispatch, cross-runtime queues, and worker
  authority changes.

## Resource Map

- execution entrypoint: `execute_go_run()` -> `_execute_parallel()` ->
  `_run_group()` -> `_run_agent_in_place()` in
  `packages/control-plane/control_plane/go_dispatch.py`.
- worker boundary: each agent receives its packet directory plus
  `RDGOAL_REPORT_PATH`; the current `ExecutionReport.md` parser accepts
  free-form Markdown status, changed-file, and verification text.
- durable state: `TeamRuntime.record_agent_message()` appends an
  `agent_message` event to outside-repository `team-events.jsonl`.
- read model: `build_team_runtime_view()` projects an `agent_message` event to
  the Message Bus and Event Log.
- direct real-path test: `packages/control-plane/tests/test_go_team_runtime.py`.

## Capability Matrix And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Durable append and outside-repository protection | `TeamRuntime` | Reuse directly |
| Message projection | `build_team_runtime_view()` | Reuse directly |
| Worker result protocol | `ExecutionReport.md` | Do not extend for messages: it is free-form text |
| External multi-agent transport | A2A | Do not import: one local trusted controller has no remote trust boundary |

The custom code, if the RED probe confirms the gap, is a minimal sidecar parser
at the existing controller-to-worker packet boundary. It is data-only; it never
causes commands, dispatch, files, or network calls.

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Markdown text is mistaken for a real agent message | P0 | Never parse messages from `ExecutionReport.md`. |
| An agent impersonates another sender or addresses another run | P0 | Bind sender to the executing agent and validate recipient against the current run. |
| A message becomes an execution instruction | P0 | Allowlisted message kinds, bounded text, durable projection only; no consumer executes it. |
| Missing/malformed sidecar hides a worker result | P1 | Treat it as no explicit message; retain normal report/result flow. |
| Journal/runtime state enters the public repository | P1 | Reuse `TeamRuntime` outside-repository guard and test via `/go`. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/go_dispatch.py`
  - `packages/control-plane/tests/test_go_team_runtime.py`
  - `scripts/verify-public-snapshot.ps1`
  - `packages/control-plane/tests/test_public_snapshot.py`
  - `docs/status/recon-receipt-go-explicit-team-messages.md`
  - `docs/status/status-document-inventory.md`
- production contract:
  - a worker may write one packet-local JSON sidecar containing only an
    allowlisted `kind`, a bounded `summary`, and an intended recipient;
  - the controller binds the sender to the executing agent and accepts only a
    distinct participant in the same `go-run`;
  - accepted data calls `TeamRuntime.record_agent_message()` after the worker
    result; malformed, self-addressed, cross-run, or unknown-recipient data is
    rejected without becoming a message or invoking any action.
- real RED probe: a two-agent prepared run writes a valid sidecar for agent 1;
  current `execute_go_run()` completes but no `agent_message` reaches the
  runtime view.
- GREEN evidence: the same public execution path records exactly one durable
  explicit message with its real sender/recipient; negative sidecar cases prove
  no message/action is produced; direct runtime and `/go` regressions pass.
- release-gate extension: only locally ignored build outputs under
  `products/tutti/` are skipped by the public snapshot scan; tracked paths and
  every non-Tutti generated directory remain subject to the existing gate.

## Team Objects

In scope: Message Bus and Event Log. Reused unchanged: Agent Registry, Task
Board, Evidence Store, Review Gate, and Conflict Control. Deferred: shared
memory/blackboard, remote A2A transport, and any write-capable UI.
