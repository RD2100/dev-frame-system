# Recon Receipt: M5 session-detail CLI usage

> Governs the M5 public documentation slice under `rules/recon.md` recon-001/003.

## Target

- user_goal: make the existing public session-detail CLI route discoverable.
- target: CLI usage strings and `packages/control-plane/README.md`.
- out of scope: session projection, runtime data, execution, approvals, network,
  browser, provider, and any write behavior.

## Reuse Decision

Reuse the existing `devframe sessions` command and M4 public detail contract;
only describe its existing `--session-id`, JSON, and fail-closed behavior.

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/cli/_usage.py`
  - `packages/control-plane/README.md`
  - `packages/control-plane/tests/test_cli.py`
  - `docs/status/recon-receipt-session-detail-cli-usage.md`
- RED: help omitted `--session-id`; public usage docs omitted the command.
- GREEN: `devframe sessions --help` exposes the option and docs state the
  read-only public-boundary behavior.
