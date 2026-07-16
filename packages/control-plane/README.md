# DevFrame Code

DevFrame Code should be understood first as a **governed coding CLI**.

If you only remember one command, remember:

```powershell
devframe code
```

That is the product-shaped daily loop. Everything else in this package exists to
support, inspect, or extend that loop.

The current role split is:

- **Primary**: `devframe code`
- **Secondary**: `devframe dashboard`, `devframe actions`, `devframe sessions`
- **Advanced**: `devframe go`, `rdgoal`, `devframe client`, `devframe web-ai`

This package lives inside the public `RD2100/dev-frame-system` repository. It
must stay independent of private handoff logs, browser profiles, and local
runtime state checked into source control.

## Install

From the repository root:

```powershell
cd .\packages\control-plane
python -m pip install -e .
```

After installation, the `devframe` command is available:

```powershell
devframe code
devframe code workers
devframe code status --runtime-dir C:\Users\you\.devframe-runtime
devframe code execute --runtime-dir C:\Users\you\.devframe-runtime
devframe code "Fix the branch" --changed --agents auto --worker opencode --preview
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime
```

## Daily Loop

The mainline workflow is:

1. `devframe code`
2. `devframe code status`
3. `devframe code execute`

`devframe code workers` and `devframe code providers` are optional setup
commands when you need to inspect local capability or choose a provider.

`devframe code` is the OpenCode-backed entrypoint. Run it with no positional
goal to get a `Goal:` prompt in the current repository, or pass the goal on the
command line. It prepares a bounded run, prints the exact worker command, and
records state for later inspection.

Use:

- `--preview` to inspect the plan without creating packets
- `--execute` to spend worker tokens immediately
- `--worker opencode` for the built-in profile
- `--command <your-worker>` for a custom executor
- `--changed --agents auto` to keep scope tight in a real git worktree
- `--since <git-ref>` to scope the task to a branch delta
- `--dashboard` when you want the control-plane view immediately

`devframe code status` and `devframe code execute` are there so a run becomes a
recoverable session rather than a one-shot command. The text status view gives
a path-free, read-only next-step summary: prepared work is ready to run;
paused, blocked, and failed work needs attention; completed work is ready for
result review.

## Secondary Surfaces

These support the main coding loop but are not the first thing a new user
should learn:

- `devframe dashboard serve`
- `devframe actions`
- `devframe sessions`
- `devframe client --dry-run`

The dashboard is the control-plane view. It is useful, but it is not the
primary product surface.

## Advanced Surfaces

These are important, but they are not the default path:

- `devframe go`
- `rdgoal`
- `devframe client bridge|serve|t3desktop|smoke`
- `devframe web-ai ...`
- `devframe run --pipeline ...`

Treat them as advanced or specialist surfaces layered on top of the main coding
loop.

## Advanced Notes

Use `devframe client --dry-run` to print the zero-config local Agent client
launch plan, including the browser URL, `/client-manifest.json`,
`/client-plan.json`, `/t3-bridge.json`, `/t3-shell.json`, and the OpenCode
readiness state.
Use `devframe client smoke` to run a zero-config preflight that starts an
in-process dashboard on a loopback port (auto-selected by default), fetches
the required JSON endpoints, validates the T3 shell team projection and launch
surfaces, and optionally verifies the T3 bridge bundle install without
launching Electron.
Use `devframe client bridge --output <dir>` to materialize the T3 Code bridge
bundle: Vite env values, a machine-readable `devframe.local.json`, a
`devframe.t3web.mjs` launcher, and small T3-side shell/thread sources that
fetch DevFrame's `OrchestrationShellSnapshot` and default-read-only
`OrchestrationThread` details. The bundle also patches T3's connection catalog
so the DevFrame local environment appears in T3 project and thread views.
Use `devframe client bridge --t3-root <t3code-checkout>` to install those
generated bridge files into a local T3 Code checkout without copying T3 source
into this repository. Existing T3 files are never overwritten unless `--force`
is explicit; with `--force`, the generated `apps/web/src/state/shell.ts` and
`apps/web/src/state/threads.ts` point T3 Web at DevFrame's default-read-only
`/t3-shell.json`, and T3's native `/.well-known/t3/environment` bootstrap reads
the DevFrame descriptor. Run `node devframe.t3web.mjs` from the T3 checkout root
to start T3 Web with the DevFrame environment variables injected without
overwriting T3's `.env.local`.
Use `devframe client serve --open` when you want the local visual client entry
to open directly in the browser. This is the T3 Code bridge path: T3 owns the
future visual shell, OpenCode owns local execution, and DevFrame owns the read
model, gates, evidence, and write policy. The thread detail overlay stays
inspection-first, but queued go-run actions now include local `Open action`
links that land on `/actions/open?action_id=...` and require an explicit
same-origin confirmation before `/actions/execute` starts local execution.
Project-level `/go` dispatch stays on the dashboard side instead of being
forced into a T3 thread surface: `/go/dispatch` lets the browser prepare or
execute coding-agent shards through the same governed runtime, using the
registered project roots already present in the Visual Control Plane.
Use `devframe code session` to inspect the latest or a named `go-run`'s agent
sessions from local runtime metadata without creating new packets or spending
worker tokens. The read-only Local Agent Control Plane surfaces session status,
provider, targets, changed files, and commands without exposing private local
paths. The dashboard also exposes `/sessions.json` for direct read-only
inspection from the runtime.

```powershell
devframe code session --runtime-dir C:\Users\you\.devframe-runtime
devframe code session --runtime-dir C:\Users\you\.devframe-runtime --format json
```

Use `devframe sessions --session-id <id> --format json` to inspect one public
DevFrameSession detail. The command reads local visual state only, omits native
runtime references and local paths, and exits nonzero when the id is missing.

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
matching action id, copyable resume filter, served Markdown handoff link, and a
controlled action page for queued go-runs. A default-read-only Action Queue
derived from gates, runs, and decisions lets
`devframe actions` print that queue directly as text, JSON, YAML, or a Markdown
handoff packet.
Run Details cards include TaskSpec/evidence paths, the current controller
decision, its next action, and the next safe local command.
Text, Markdown, and dashboard queue views include action ids and copyable
`--action-id` resume filters for precise follow-up. It can filter by status,
priority, source type, source id, or action id, and `--fail-on-match` turns a
filtered queue into a read-only gate for scripts. The dashboard server exposes
the same queue at `/actions.json`, with `status`, `priority`, `source_type`,
`source_id`, and `action_id` query filters, at `/actions.md` as a Markdown
handoff view for manual resume, and at `/actions/open` as a local controlled
action page. Markdown handoff packets include each `action_id` so filtered
single-action exports stay self-identifying. `/actions/execute` is the only
mutating endpoint in the dashboard surface: it is loopback-only, rejects
cross-origin POSTs, and requires `confirm=execute` before it starts a queued
DevFrame Code go-run. The served dashboard homepage links to the read endpoints
and to per-action handoff or controlled-action views. Invalid filter values
return `400` instead of a misleading empty queue.
The same homepage now also links to `/go/dispatch`, which is the project-level
browser entry for preparing `/go` packets or starting local OpenCode-backed
shards. That POST path is also loopback-only and same-origin, and it only
accepts project roots already registered in the current control-plane state.

Worker commands return exit code `0` only for `passed` or `completed` reports.
`blocked`, `failed`, and unknown report states return non-zero so automation
cannot accidentally treat a held packet as success.

`--apply-rdinit` can run the full bootstrap only from a source checkout that
contains the root `rules/`, `schemas/`, and `docs/agent-runtime/` assets. Wheel
installs still create contracts and dispatch packets, but report
`bootstrap_unavailable` instead of failing when those full bootstrap assets are
not packaged.

## Web AI Session Import

DevFrame can import summary-only web AI sessions from the runtime directory.
Drop JSON session summaries into `<runtime-dir>/web-ai-sessions/` to project
them into the Visual Control Plane without persisting raw transcripts, or use
the built-in import command:

```powershell
devframe web-ai import .\chatgpt-summary.json --runtime-dir C:\Users\you\.devframe-runtime
```

When Chrome is already running with a local CDP endpoint and ChatGPT is open,
DevFrame can create the same summary-only runtime session directly:

```powershell
devframe web-ai bind-chrome --runtime-dir C:\Users\you\.devframe-runtime --project demo-project --cdp-endpoint http://127.0.0.1:9222
```

This command reads Chrome debugger metadata and the ChatGPT tab URL only. It
does not read cookies, browser profiles, local storage, raw transcripts, or
message text. The imported `chatgpt` session makes the default `chatgpt-web`
provider binding appear as `ready` in the Visual Control Plane.

The import command recursively rejects raw transcript fields
(`raw_transcript`, `transcript`, `conversation`, `raw_messages`) and rejects
`messages[].content` / `messages[].text`; use `content_summary` only. Valid
summaries are normalized and written into `<runtime-dir>/web-ai-sessions/`.

Each JSON file should contain enough summary fields to identify and display the
session:

- `session_id`
- `provider`
- `agent_role`
- `project_id`
- `status`
- `messages` (summary-only)
- `tool_calls`
- `changed_files`
- `diff_summary`
- `evidence_refs`
- `cost`
- `tokens`
- `gates`
- `actions`

`native_refs` is optional; DevFrame adds `native_refs.runtime = "web-ai-import"`
and `native_refs.source_file` during import.

Smoke test:

```powershell
$runtime = "$env:USERPROFILE\.devframe-runtime"
$summary = ".\demo-web-ai-summary.json"
@'
{
  "session_id": "demo-session",
  "provider": "chatgpt",
  "agent_role": "coordinator",
  "project_id": "demo-project",
  "run_id": "demo-run",
  "task_spec_id": "TASKSPEC.json",
  "status": "completed",
  "messages": [
    {
      "message_id": "1",
      "role": "user",
      "content_summary": "Build the MVP"
    }
  ],
  "tool_calls": [],
  "changed_files": [],
  "diff_summary": "",
  "evidence_refs": [],
  "cost": {"amount": 0, "currency": "USD"},
  "tokens": {"input": 0, "output": 0, "total": 0},
  "gates": [],
  "actions": [],
  "native_refs": {"runtime": "web-ai-import"}
}
'@ | Set-Content -Path $summary -Encoding UTF8

devframe web-ai import $summary --runtime-dir $runtime
devframe visual-state --runtime-dir $runtime
devframe dashboard serve --runtime-dir $runtime
```

The dashboard and `devframe visual-state` surface imported sessions,
provider bindings, and agents in the read-only Visual Control Plane.

## Verification

From the repository root, run the full release gate before sharing or packaging
this control-plane package:

```powershell
python -m pip install -e ".\packages\control-plane[dev]" -e ".\packages\ai-workflow-hub[dev]"
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
