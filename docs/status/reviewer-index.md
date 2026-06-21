# Reviewer Index

This index summarizes the current rdgoal/control-plane release slice for human
review. It is intentionally concise and points reviewers to the files and
commands that matter most.

## Changed File Groups

- Public overview and quickstart docs:
  `README.md`, `README.zh-CN.md`, `packages/control-plane/README.md`,
  `packages/control-plane/QUICKSTART.md`.
- Release and readiness docs:
  `docs/agent-runtime/rdgoal-total-control.md`,
  `docs/status/release-readiness.md`, `docs/status/reviewer-index.md`.
- Verification scripts:
  `scripts/verify-public-snapshot.ps1`,
  `scripts/verify-control-plane-wheel.ps1`,
  `scripts/verify-release.ps1`.
- CI entrypoint:
  `.github/workflows/release-verify.yml`.
- Control-plane rdgoal implementation:
  `packages/control-plane/control_plane/agent_adapter.py`,
  `packages/control-plane/control_plane/backup_guard.py`,
  `packages/control-plane/control_plane/decision_engine.py`,
  `packages/control-plane/control_plane/dispatch_packet.py`,
  `packages/control-plane/control_plane/orchestrator.py`,
  `packages/control-plane/control_plane/project_contract.py`,
  `packages/control-plane/control_plane/rdgoal.py`,
  `packages/control-plane/control_plane/rdgoal_cli.py`,
  `packages/control-plane/control_plane/runtime_digest.py`,
  `packages/control-plane/control_plane/runtime_store.py`,
  `packages/control-plane/control_plane/worker.py`.
- Existing control-plane integration points:
  `packages/control-plane/control_plane/cli.py`,
  `packages/control-plane/control_plane/pipeline_runner.py`.
- Starter project templates:
  `packages/control-plane/templates/code_project/*`,
  `packages/control-plane/templates/runtime-bootstrap/*`,
  `templates/runtime-bootstrap/bootstrap.ps1`.
- Public rules and schemas:
  `rules/orchestration.md`, `rules/project-contracts/_template.md`,
  `schemas/project_contract.schema.json`,
  `schemas/rdgoal_dispatch_packet.schema.json`.
- Tests:
  `packages/control-plane/tests/test_rdgoal.py`,
  `packages/control-plane/tests/test_cli.py`,
  `packages/control-plane/tests/test_public_snapshot.py`, `pytest.ini`.

## Critical Code Paths

- `devframe rdgoal` routing:
  `control_plane/cli.py` delegates to `control_plane/rdgoal_cli.py`.
- Project contract creation:
  `control_plane/rdgoal.py` writes project-local contracts by default under
  `<project>/rules/project-contracts/`.
- Bootstrap behavior:
  source checkout can run root bootstrap assets; wheel installs safely return
  `bootstrap_unavailable` while still producing a dispatch packet.
- Dispatch packet handoff:
  `control_plane/dispatch_packet.py` writes `packet.json`, `TASKSPEC.json`,
  and `TASKSPEC.md` into the runtime outbox.
- Snapshot guard:
  `control_plane/backup_guard.py` validates targets are inside the project
  before creating snapshot directories.
- Worker result semantics:
  `control_plane/worker.py` and `rdgoal_cli.py` keep `blocked`, `failed`, and
  unknown report states non-zero.
- Cross-process digest:
  `control_plane/runtime_store.py` and `runtime_digest.py` rebuild status from
  runtime files rather than process memory.

## Verification Evidence

Primary release gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The gate must pass all of the following:

- `python -m pytest -q`
- `powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\verify-control-plane-wheel.ps1`
- `git diff --check`

Additional targeted probes covered by tests:

- Generated `build` directories are rejected by the public snapshot checker.
- Public Markdown docs are UTF-8 readable and do not contain private path or
  mojibake markers.
- Blocked/failed rdgoal workers return non-zero.
- Command workers do not run held packets.
- Snapshot-backed actions reject targets outside the project root before
  creating snapshot directories.
- Dispatch packets and project contracts validate against public schemas.

## Generated Artifacts

The release gate may temporarily create:

- `packages/control-plane/build`
- `packages/control-plane/devframe_control_plane.egg-info`
- temporary wheel smoke directories under the OS temp directory

The wheel smoke script removes these artifacts in `finally`. A clean final
state has no `build`, `dist`, `*.egg-info`, or `public-snapshot-probe*`
directories in the repository.

## Known Gaps

- The wheel distribution intentionally does not include the full repository
  root bootstrap assets. This is documented as `bootstrap_unavailable` behavior.
- Real external AI/browser dispatch is outside this release slice; the current
  worker path proves packet handoff, local dry-run, command worker, and aihub
  adapter invocation semantics.
- GitHub CI/PR state is not represented by local verification alone. Reviewers
  should run or add CI before merging if this becomes a remote release.

## Suggested Review Focus

- Confirm no private runtime state, evidence packs, generated archives, or
  local browser/agent state were added.
- Confirm release verification runs from a fresh checkout on Windows PowerShell.
- Confirm `.github/workflows/release-verify.yml` invokes the same release gate.
- Confirm worker failure semantics cannot produce fake green results.
- Confirm source checkout and wheel install paths both match the documented
  rdgoal behavior.
- Confirm docs are understandable for a new open-source reader without internal
  project history.
