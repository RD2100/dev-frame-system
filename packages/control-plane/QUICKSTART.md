# Control Plane Quickstart

This quickstart starts from a clone of `RD2100/dev-frame-system`.

## 1. Install the CLI

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
cd .\packages\control-plane
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 2. Check the package

```powershell
devframe doctor
```

From the repository root, run the public checks:

```powershell
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

## 3. Initialize a local workflow project

```powershell
cd .\packages\control-plane
devframe init code_project D:\tmp\demo-project
```

This writes the starter workflow files into the target project.

## 4. Run a dry pipeline

```powershell
cd D:\tmp\demo-project
devframe run --pipeline PIPELINE.yaml
```

The default runner validates and prints the pipeline stages without performing
live external effects.

## 5. Route work through rdgoal

In external-brain chat, use `/rdgoal <project> <goal>`. In a shell, use the
installed `rdgoal` command:

```powershell
rdgoal "D:\tmp\demo-project" "Build the MVP" --digest
```

`rdgoal` writes controller runtime state outside the public repository. Use
`--runtime-dir` for an explicit local runtime location and `--contracts-dir` for
an explicit project-contract directory. Without `--contracts-dir`, the contract
is created under `D:\tmp\demo-project\rules\project-contracts`.

`--apply-rdinit` requires a source checkout with the full root bootstrap assets.
Wheel installs can still create dispatch packets, but will report
`bootstrap_unavailable` if those assets are not present.

## 6. Consume a dispatch packet

Use the local dry-run worker first:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\demo-project\<packet-id>"
```

When a real runner is ready, use the command worker:

```powershell
rdgoal worker "C:\Users\you\.devframe-runtime\rdgoal-outbox\demo-project\<packet-id>" `
  --command python -m your_worker_module
```

The worker receives `RDGOAL_TASKSPEC_JSON`, `RDGOAL_PACKET_JSON`, and
`RDGOAL_REPORT_PATH` environment variables and must produce an ExecutionReport.
Worker exit code is non-zero for `blocked`, `failed`, or unknown report states.

## 7. Prepare parallel coding-agent work with /go

Use `devframe code` when you want a Codex/Claude Code/OpenCode-style coding
entrypoint in the current repository:

```powershell
cd D:\tmp\demo-project
devframe code "Build the MVP" `
  --target src `
  --runtime-dir C:\Users\you\.devframe-runtime `
  --dashboard
```

By default this prepares one coding-agent session and prints the worker command
without spending agent tokens. Add `--execute` only when you want the worker to
run. Add `--agents 3` when you want concurrent coding shards. `--dashboard`
serves the same runtime in the read-only visual interface; append `?lang=zh-CN`
to the printed URL for Chinese. `--changed` targets only modified, staged, or
untracked git files; use repeated `--target <path>` when you want to name a
specific slice manually.

Use `devframe go` when you want to name the project path explicitly or prepare
several shards directly:

```powershell
devframe go "D:\tmp\demo-project" "Build the MVP" `
  --agents 3 `
  --target src `
  --runtime-dir C:\Users\you\.devframe-runtime
```

By default this is a token-safe dispatch step: it writes a `go-run.json` record,
creates one rdgoal packet per coding-agent shard, and prints the exact worker
commands. Add `--execute` to run the shards concurrently. Without `--command`,
the default worker command is `opencode run -m stepfun/step-3.7-flash --agent build`;
pass `--command <your-worker>` to use another executor that reads
`RDGOAL_TASKSPEC_JSON` and writes `RDGOAL_REPORT_PATH`.
The dashboard reads the same runtime and shows the go-run plus each shard's
target, packet path, status, and worker command in a dedicated `/go Coding
Agents` section.

## 8. Review the runtime digest

```powershell
rdgoal digest
```

The digest is rebuilt from runtime files, so it can show decisions and worker
ExecutionReports across separate CLI invocations.

## 9. Export visual state

```powershell
devframe visual-state --runtime-dir C:\Users\you\.devframe-runtime
devframe visual-state --runtime-dir C:\Users\you\.devframe-runtime --format html --output visual-state.html
devframe actions --runtime-dir C:\Users\you\.devframe-runtime
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --status open --source-type gate
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo --source-id demo-paper-paper-review
devframe actions --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo --status ready --source-type run --format markdown --output ACTION_QUEUE.md
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo
```

The dashboard binds to loopback only by default; pass `--allow-remote` to expose it on non-loopback hosts.

This produces the read-only Visual Control Plane state snapshot for a future GUI
or CLI inspector. The HTML output is a local, static dashboard snapshot that can
be opened directly in a browser; the dashboard server exposes the same model at
`/state.json`, the filtered queue at `/actions.json`, the Markdown handoff view
at `/actions.md`, and a refreshable read-only page at `/`. `--paper-project`
adds a paper iteration workspace as an `rdpaper` run with its privacy gate, next
local command, `WEB_AI_ADAPTER.yaml` provider binding, manual fallback
instructions, and provider safety gate next action. Active gates appear in a
front-page Gate Focus section with their action id, resume filter, and served
Markdown handoff link. The served dashboard homepage links to the JSON and Markdown
endpoints so they are discoverable from the browser. Current gate, run, and
decision guidance is grouped into an Action Queue for quick triage; `devframe
actions` prints that queue with action ids without opening the full JSON or
dashboard, and the dashboard table shows the same ids plus resume filters beside
each action. The Agent Registry shows each agent's provider and binding health,
while Run Details cards show the current controller decision and its next action
beside the TaskSpec/evidence paths. Use
`--format markdown --output ACTION_QUEUE.md` when the queue
needs to become a manual resume or Web AI handoff packet; the packet includes
action ids so a single-action export remains traceable, plus a copyable
`--action-id` resume filter for the same item. Use `--source-id` or
`--action-id` when only one gate/run/decision should be handed off. Use
`--status`, `--priority`, `--source-type`, and `--fail-on-match` when a script
needs to probe for unresolved actions. The dashboard endpoints return `400` for
invalid filter values so typos do not look like an empty queue.
