# Recon Receipt: M9 agent recovery summary

## Target

- user_goal: identify paused, blocked, or failed coding agents in text status
  without showing internal report or runtime data.
- out_of_scope: execution, approvals, writes, provider/network/browser work,
  report contents, JSON changes, and unknown-run behavior.

## Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Real status route | `cmd_code_status()` | Reuse directly. |
| Agent fields | existing `agent_id`, `status`, `worker_status` | Reuse allowlisted values only. |
| Status normalization | `_ui_status()` | Reuse directly. |
| CLI regression | `test_cli.py` | Use real `devframe_cli_main()` path. |

## Frozen TaskSpec

- write_set: `cli/_coding.py`, `tests/test_cli.py`, `packages/control-plane/README.md`, this receipt, status inventory.
- RED: a failed agent is listed but no summary says which agent needs attention.
- GREEN: text status names only affected agent IDs and normalized statuses; no report/runtime path, execute command, or JSON change.
