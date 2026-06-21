# DevFrame Control Plane

The control plane is the local CLI and Python package for dev-frame-system. It
keeps workflow execution, handoff generation, runtime probes, and rdgoal
orchestration in a small installable package.

This package is distributed inside the public `RD2100/dev-frame-system`
repository. It should not depend on private handoff logs, browser profiles,
local runtime state, or old `devframe-control-plane` checkout paths.

## Install

From the repository root:

```powershell
cd .\packages\control-plane
python -m pip install -e .
```

After installation, the `devframe` command is available:

```powershell
devframe doctor
devframe init code_project D:\tmp\demo-project
devframe run --pipeline pipelines\example_pipeline.yaml
```

## rdgoal

`rdgoal` is the total-control orchestration entry point. It registers a project,
creates or loads a project contract, classifies the next operation, writes a
dispatch packet, and records controller state in the local runtime directory.

```powershell
devframe rdgoal "D:\my-project" "Build the MVP" --digest
```

For local destructive operations, pass explicit targets so rdgoal can snapshot
them before dispatch:

```powershell
devframe rdgoal "D:\my-project" "Remove the obsolete module" `
  --operation "delete obsolete local module" `
  --target "src\old_module.py" `
  --digest
```

Runtime state is written outside the repository by default under
`%USERPROFILE%\.devframe-runtime`. Set `DEVFRAME_RUNTIME_DIR` when you need a
different local runtime location. Project contracts are written to
`<project>\rules\project-contracts` unless `--contracts-dir` is provided.

After a worker runs, inspect persisted decisions and ExecutionReports with:

```powershell
devframe rdgoal digest
```

Worker commands return exit code `0` only for `passed` or `completed` reports.
`blocked`, `failed`, and unknown report states return non-zero so automation
cannot accidentally treat a held packet as success.

`--apply-rdinit` can run the full bootstrap only from a source checkout that
contains the root `rules/`, `schemas/`, and `docs/agent-runtime/` assets. Wheel
installs still create contracts and dispatch packets, but report
`bootstrap_unavailable` instead of failing when those full bootstrap assets are
not packaged.

## Verification

From the repository root:

```powershell
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

The root `pytest.ini` points pytest at this package's tests and ensures the
in-repo `control_plane` package is imported even if another editable checkout is
installed on the machine.

## Safety Boundaries

- Live browser/CDP submission remains opt-in.
- Runtime state, rollback snapshots, and report summaries must stay outside the
  public repository.
- Secret exposure is a hard stop.
- External irreversible effects are prepared as drafts, not executed live.

## License

Apache License 2.0, inherited from the repository root.
