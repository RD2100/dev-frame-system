# Recon Receipt: go-dispatch claim-propagation real-path regression

> Governs the bounded M1 `/go` claim-propagation regression test under
> `rules/recon.md` recon-001/003/008/009. Closes the gap between the proven
> unit-level claim rejection (`test_team_runtime.py`) and the real production
> execution path (`execute_go_run -> _execute_parallel -> _run_agent_in_place`).

## Target

- user_goal: prove that when two agents in a real `/go` run target the same
  file, the second agent is failed cleanly without journal mutation, without
  invoking the worker, and with a human-readable error artifact.
- current_slice_goal: add one hermetic real-path regression test that exercises
  the full production chain and asserts every downstream observable.
- out of scope: A2A/network transport, distributed leases, worktree isolation,
  ACP driver, UI, and changes to production code.

## Resource Map

- write boundary: `packages/control-plane/tests/test_go_team_runtime.py`.
- production path under test:
  `execute_go_run` -> `load_go_run_result` (reads `go-run.json`) ->
  `_execute_parallel` -> `plan_write_set_groups` (overlapping targets are
  grouped and run serially) -> `_run_group` -> `_run_agent_in_place` ->
  `TeamRuntime.record_task_created` / `record_task_claimed` (raises
  `ValueError` on overlap before append) -> except block marks agent failed,
  writes `go-agent-error.txt`, and records a failed `task_result` without
  running the worker.
- reuse: existing `_noop_report_command`, `run_go_dispatch(execute=False)`,
  public `execute_go_run`, and `TEAM_EVENTS_FILE` / journal JSONL parsing.
- durable state: outside-repository `team-events.jsonl` and per-agent
  `go-agent-error.txt` under the runtime packet dir.

## Production Path Trace

1. `run_go_dispatch(execute=False)` creates two non-overlapping agent packets
   (`a.py`, `b.py`) and writes `go-run.json` metadata; no execution occurs.
2. The test mutates only the temporary `go-run.json` so agent 2's `targets`
   become agent 1's targets (`a.py`), simulating metadata drift.
3. `execute_go_run(runtime, go_run_id)` loads the mutated metadata and calls
   `_execute_parallel`.
4. `plan_write_set_groups([["a.py"], ["a.py"]])` puts both agents in one serial
   group because their target sets intersect.
5. `_run_agent_in_place` for agent 1: records `task_created` + `task_claimed`
   (succeeds), runs the noop worker (pass), records `task_result` (pass).
6. `_run_agent_in_place` for agent 2: records `task_created`, then
   `record_task_claimed` raises `ValueError` before append.
7. The `except Exception` guard sets `agent.status = "failed"`,
   `agent.worker_status = "failed"`, writes `go-agent-error.txt` naming the
   conflict, and records `task_result` (failed) without invoking the worker.

## Capability Matrix And Reuse Decision

| Capability | Candidate | Decision |
| --- | --- | --- |
| Claim conflict detection | Existing `TeamRuntime.record_task_claimed` | Reuse directly (no change) |
| Serial grouping of overlapping agents | Existing `plan_write_set_groups` | Reuse directly (no change) |
| Failure recording | Existing `_write_agent_failure` + `record_result(failed)` | Reuse directly (no change) |
| Metadata load/execute cycle | Existing `execute_go_run` + `load_go_run_result` | Reuse directly (no change) |
| Hermetic worker | Existing `_noop_report_command` | Reuse directly (no change) |

No production code was changed. The test reuses the existing noop worker,
metadata round-trip, and TeamRuntime failure recording path without new
abstractions.

## Scope And Exclusions

- In scope: one regression test proving the real-path claim-propagation
  behavior, plus this receipt and the inventory entry.
- Excluded: production code changes, new packages, distributed coordination,
  ACP driver, worktree isolation, UI, and any change to the existing
  non-overlap test.
- The existing `test_execution_records_team_events_and_surfaces_in_state`
  (normal non-overlap path) is preserved unchanged.

## Actual Probe

The test exercises the real `execute_go_run` public entry point with a mutated
two-agent run and asserts:

1. Agent 1 succeeds (`worker_status` in success statuses, `status == completed`).
2. Agent 2 is failed (`worker_status == failed`, `status == failed`).
3. Only agent 1 has a `task_claimed` journal event; agent 2's claim was rejected
   before append (no journal mutation for the failed claim).
4. Both `task_result` journal events reflect the real passed/failed outcome.
5. Agent 2's `go-agent-error.txt` contains `"already claimed"` and the
   conflicting target file name.

This is a real-path probe: it would fail if `_run_agent_in_place` stopped
catching `ValueError`, if `record_task_claimed` stopped raising on overlap, or
if the failure path stopped writing the error artifact or recording the result.

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/tests/test_go_team_runtime.py`
  - `docs/status/recon-receipt-go-dispatch-claim-propagation.md`
  - `docs/status/status-document-inventory.md`
- production contract (unchanged): `execute_go_run` ->
  `_execute_parallel` -> `plan_write_set_groups` -> `_run_group` ->
  `_run_agent_in_place` records `task_created` + `task_claimed`; when the claim
  raises `ValueError`, the except guard marks the agent failed, writes
  `go-agent-error.txt`, records a failed `task_result`, and never invokes the
  worker.
- real probe: the test above (24th test in `test_go_team_runtime.py`).
- evidence: `python -m pytest -q packages/control-plane/tests/test_go_team_runtime.py packages/control-plane/tests/test_team_runtime.py` -> 24 passed.

## Exclusions

No staging, commit, push, Git configuration changes, or edits outside the
declared write set. No production code was modified.