# Recon Receipt: M7 recoverable code-status guidance

> Governs M7 under `rules/recon.md` recon-001/003/009 and
> `docs/agent-runtime/agent-coding-discipline.md` agent-discipline-001/004/005/006.

## Target

- user_goal: let a daily CLI user understand the state of an existing coding
  run and the safe next step without reading internal runtime terminology.
- current_slice_goal: improve text output of `devframe code status`; preserve
  the raw JSON contract for machine clients.
- out_of_scope: execution, approvals, writes, network/provider/browser work,
  new commands, session storage, raw messages/tool inputs, credentials, and
  native or runtime paths.

## Resource Map And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Real CLI entrypoint | `cmd_code_status()` in `cli/_coding.py` | Reuse directly. |
| Run lookup / fail-closed behavior | `_load_go_run_status()` | Reuse directly; retain nonzero missing-run errors. |
| Status vocabulary | `_ui_status()` | Extend only the text renderer's recovery mapping. |
| Text status renderer | `_render_go_run_status()` | Adapt in place; no new transport or data model. |
| Direct CLI regression harness | `tests/test_cli.py` | Reuse the real `devframe_cli_main()` path. |

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Runtime/report path leaks | P0 | Text renderer must not emit `runtime_dir` or `report_path`. |
| Status suggests unsafe execution | P0 | Guidance stays descriptive/read-only; no execute command or mutation URL. |
| Missing run falls back to another run | P0 | Keep exact `_load_go_run_status()` error path unchanged. |
| JSON automation breaks | P1 | Do not change `--format json`. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/cli/_coding.py`
  - `packages/control-plane/tests/test_cli.py`
  - `packages/control-plane/README.md`
  - `docs/status/recon-receipt-code-status-recovery.md`
  - `docs/status/status-document-inventory.md`
- real RED: invoke `devframe_cli_main()` through `devframe code status` for
  prepared and failed records; existing output leaks its runtime path and lacks
  plain-language, status-specific recovery guidance.
- GREEN: text output is path-free, has status-appropriate read-only guidance,
  and exact missing-run/JSON behavior remains covered by direct CLI tests.
