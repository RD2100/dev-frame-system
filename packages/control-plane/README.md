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
devframe code "Build the MVP" --project D:\tmp\demo-project --target src --dashboard
devframe code "Build the MVP" --project D:\tmp\demo-project --target src --preview
devframe run --pipeline pipelines\example_pipeline.yaml
```

`devframe code` is the Codex-like coding entrypoint. It defaults to preparing a
bounded coding-agent session, prints the worker command, and records runtime
state for `devframe dashboard serve`. Use `--dashboard` to serve that visual UI
immediately, `--preview` to inspect the shard plan and worker command template
without creating packets, `--execute` to run the worker, and `--agents <n>` to
split the goal into concurrent coding shards. Use `--changed --agents auto` to
keep worker prompts focused on modified, staged, or untracked git files and
automatically choose a bounded shard count; use `--max-agents` to cap that
fan-out or `--target <path>` for manual scoping. Dispatch and preview balance
targets by estimated bytes so large files are spread across workers more evenly.

The focused total-control entrypoint is also installed:

```powershell
rdgoal "D:\tmp\demo-project" "Build the MVP" --digest
```

## rdgoal

`rdgoal` is the total-control orchestration entry point. It registers a project,
creates or loads a project contract, classifies the next operation, writes a
dispatch packet, and records controller state in the local runtime directory.
In external-brain conversations this is the `/rdgoal <project> <goal>` slash
entrypoint; in a shell it is the installed `rdgoal` console script.

```powershell
rdgoal "D:\my-project" "Build the MVP" --digest
```

For local destructive operations, pass explicit targets so rdgoal can snapshot
them before dispatch:

```powershell
rdgoal "D:\my-project" "Remove the obsolete module" `
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
rdgoal digest
```

To export the same runtime as the first Visual Control Plane read model:

```powershell
devframe visual-state --runtime-dir C:\Users\you\.devframe-runtime
devframe visual-state --runtime-dir C:\Users\you\.devframe-runtime --format html --output visual-state.html
devframe actions --runtime-dir C:\Users\you\.devframe-runtime
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo --status open --source-type gate
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo --source-id demo-paper-paper-review
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo --status ready --source-type run --format markdown --output ACTION_QUEUE.md
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo
```

The dashboard binds to loopback only by default; pass `--allow-remote` to expose it on non-loopback hosts.

When `--paper-project` is supplied, the read model also surfaces that workspace's
`WEB_AI_ADAPTER.yaml` as a provider binding with local health, fallback notes,
manual fallback instructions, and a provider safety gate with a next action. The
dashboard Agent Registry joins each agent to its provider and binding health so
role, scope, provider, and status can be reviewed in one table. The
same state includes a dashboard Gate Focus section for active gates with the
matching action id, copyable resume filter, and served Markdown handoff link. A
read-only Action Queue derived from gates, runs, and decisions lets
`devframe actions` print that queue directly as text, JSON, YAML, or a Markdown
handoff packet.
Run Details cards include TaskSpec/evidence paths, the current controller
decision, its next action, and the next safe local command.
Text, Markdown, and dashboard queue views include action ids and copyable
`--action-id` resume filters for precise follow-up. It can filter by status,
priority, source type, source id, or action id, and `--fail-on-match` turns a
filtered queue into a read-only gate for scripts. The dashboard server exposes
the same queue at `/actions.json`, with `status`, `priority`, `source_type`,
`source_id`, and `action_id` query filters, and at
`/actions.md` as a Markdown handoff view for manual resume. Markdown handoff
packets include each `action_id` so filtered single-action exports stay
self-identifying. The served dashboard homepage links to these read-only
endpoints and to per-action Markdown handoff views. Invalid filter values return
`400` instead of a misleading empty queue.

Worker commands return exit code `0` only for `passed` or `completed` reports.
`blocked`, `failed`, and unknown report states return non-zero so automation
cannot accidentally treat a held packet as success.

`--apply-rdinit` can run the full bootstrap only from a source checkout that
contains the root `rules/`, `schemas/`, and `docs/agent-runtime/` assets. Wheel
installs still create contracts and dispatch packets, but report
`bootstrap_unavailable` instead of failing when those full bootstrap assets are
not packaged.

## Verification

From the repository root, run the full release gate before sharing or packaging
this control-plane package:

```powershell
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The root `pytest.ini` points pytest at this package's tests and ensures the
in-repo `control_plane` package is imported even if another editable checkout is
installed on the machine. The full release gate is required for package sharing
because `verify-public-snapshot.ps1` alone does not cover release-readiness
checks.

## Safety Boundaries

- Live browser/CDP submission remains opt-in.
- Runtime state, rollback snapshots, and report summaries must stay outside the
  public repository.
- Secret exposure is a hard stop.
- External irreversible effects are prepared as drafts, not executed live.

## License

Apache License 2.0, inherited from the repository root.
