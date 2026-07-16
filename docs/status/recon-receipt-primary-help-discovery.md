# Recon Receipt: M8 primary CLI help discovery

> Governs M8 under `rules/recon.md` recon-001/003/009 and
> `docs/agent-runtime/agent-coding-discipline.md` agent-discipline-001/004/005/006.

## Target

- user_goal: make the top-level `devframe --help` output explain the daily
  `code -> status -> execute` path before optional configuration and advanced
  capability families.
- out_of_scope: command semantics, dispatch/execution, approval, storage,
  providers, network/browser behavior, and removal of existing commands.

## Resource Map And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Top-level help | `HELP_TEXT` in `cli/_usage.py` | Adapt directly. |
| CLI production path | `devframe_cli_main()` | Reuse for direct help regression. |
| Product entry documentation | root `README.md`, `packages/control-plane/README.md` | Align existing mainline wording; no new docs surface. |
| Advanced command access | Existing help sections | Preserve verbatim command availability under secondary headings. |

No new command, transport, client, or runtime is needed.

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Existing command becomes undiscoverable | P0 | Direct help test asserts representative control-plane and advanced commands remain. |
| Help implies behavior not implemented | P1 | Describe existing prepare/status/execute commands only. |
| Private runtime data enters public docs | P0 | Use generic command forms only; no local paths or tokens. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/cli/_usage.py`
  - `packages/control-plane/tests/test_cli.py`
  - `README.md`
  - `packages/control-plane/README.md`
  - `docs/status/recon-receipt-primary-help-discovery.md`
  - `docs/status/status-document-inventory.md`
- real RED: `devframe --help` lacks a clear ordered prepare/status/execute
  workflow and presents workers/providers as peers of the main loop.
- GREEN: real help renders the three ordered steps first, configuration is
  explicitly optional, representative secondary/advanced commands remain, and
  public docs use the same primary-product framing.
