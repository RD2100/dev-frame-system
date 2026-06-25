# DevFrame Code Quickstart

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

Use `devframe code` when you want an OpenCode-first coding-agent entrypoint in
the current repository:

```powershell
cd D:\tmp\demo-project
devframe code
devframe code workers
devframe code "Build the MVP" `
  --target src `
  --runtime-dir C:\Users\you\.devframe-runtime `
  --preview
devframe code "Fix the branch" --changed --agents auto --worker opencode --preview
```

Run `devframe code` with no goal to start from a `Goal:` prompt in the current
repository. By default this prepares one coding-agent session and prints the
worker command without spending agent tokens. Add `--preview` when you only
want to inspect the shard plan plus worker command template and avoid creating
runtime packets. Run `devframe code workers` first when you want to check
whether `opencode` or a custom executor command is present
locally; it is status-only and does not create packets or run workers.
Use `--worker opencode` to pick the built-in coding CLI that should consume
each packet, or pass `--command <your-worker>`
for another executor command (for example, `python -m your_worker_module`).
Add `--execute` only when you want the worker to run. In a real
git worktree, use `--changed --agents auto` to target modified, staged, or
untracked files and choose a bounded shard count automatically; use
`--max-agents` to cap the fan-out. Preview and dispatch balance targets by
estimated bytes to avoid overloading one worker with most of the context.
`--dashboard` serves the same runtime in the read-only visual interface; use
the English/中文 switch in the page, or open `?lang=zh-CN` directly for Chinese.
Each go-run card shows copyable `devframe code status` and
`devframe code execute` commands for the prepared run.
The terminal output also prints those exact commands, so the first usable loop
can stay entirely in the CLI: prepare, inspect with `status`, then execute when
you are ready.
Use repeated `--target <path>` when you want to name a specific slice manually.
Use `--since <git-ref>` when the task should cover the branch delta against a
base ref, for example `--since origin/main`.

For longer prompts, keep the task in a file or pipe it from another tool:

```powershell
devframe code --prompt-file .\TASK.md --changed --agents auto
Get-Content .\TASK.md | devframe code --changed --agents auto --preview
devframe code --prompt-file .\TASK.md --since origin/main --agents auto --preview
devframe code status --runtime-dir C:\Users\you\.devframe-runtime
devframe code execute --runtime-dir C:\Users\you\.devframe-runtime
```

`devframe code status` is read-only: it loads the latest `go-run.json` by
default, or a named go-run id when provided, and does not create packets or run
workers. `devframe code execute` runs the latest or named prepared go-run later
from the same metadata, reusing existing packet directories instead of creating
new prompts. Agents that already passed are skipped unless `--rerun-passed` is
provided.

If the project was initialized with `templates/runtime-bootstrap/bootstrap.ps1`,
you can use its project-local `/go` bridge instead:

```powershell
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed -Prepare -Dashboard
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed -Execute
```

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
commands. Add `--execute` to run the shards concurrently. Use
`--worker opencode` to choose the built-in worker profile; the default is
`opencode run -m stepfun/step-3.7-flash --agent build`.
Pass `--command <your-worker>` to use another executor that reads
`RDGOAL_TASKSPEC_JSON` and writes `RDGOAL_REPORT_PATH`.
Use `--since <git-ref>` or `--changed` to keep `/go` shards focused on the files
that actually changed instead of giving every worker project-wide context.
The dashboard reads the same runtime and shows the go-run plus each shard's
target, estimated bytes, changed files, packet path, status, and worker command
in a dedicated `/go Coding Agents` section. It also shows copyable status and
execute commands for the go-run. When workers finish, `devframe code` and
`devframe go` also print each shard's ExecutionReport path, changed files, and
first evidence line in the terminal.

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
devframe client --dry-run --runtime-dir C:\Users\you\.devframe-runtime
devframe client smoke --runtime-dir C:\Users\you\.devframe-runtime
devframe client smoke --runtime-dir C:\Users\you\.devframe-runtime --format json
devframe client bridge --runtime-dir C:\Users\you\.devframe-runtime --output .\devframe-t3-bridge
devframe client bridge --runtime-dir C:\Users\you\.devframe-runtime --t3-root D:\t3code --force
cd D:\t3code
node devframe.t3web.mjs
devframe client serve --runtime-dir C:\Users\you\.devframe-runtime --open
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime
devframe dashboard serve --runtime-dir C:\Users\you\.devframe-runtime --paper-project D:\papers\demo
```

The dashboard binds to loopback only by default; pass `--allow-remote` to expose it on non-loopback hosts.

This produces the default-read-only Visual Control Plane state snapshot for a future GUI
or CLI inspector. `devframe client --dry-run` prints the zero-config local Agent
client launch plan with the browser URL, `/client-plan.json`,
`/client-manifest.json`, `/t3-bridge.json`, `/t3-shell.json`, and OpenCode
readiness. `devframe client bridge --output <dir>` writes the installable T3
Code bridge bundle for a local T3 checkout. `devframe client bridge --t3-root
<t3code-checkout>` installs generated bridge files and refuses to overwrite
existing T3 files unless `--force` is explicit; the forced install wires T3
Web's shell state, thread detail state, and connection catalog to DevFrame's
default-read-only `/t3-shell.json` projection and writes `devframe.t3web.mjs`. Run
`node devframe.t3web.mjs` from the T3 checkout root to start T3 Web with
DevFrame environment variables injected without overwriting T3's `.env.local`.
`devframe client serve --open` starts the
browser-facing client entrypoint on loopback:
T3 Code is the visual-client bridge target, OpenCode is the local executor, and
DevFrame keeps the governed read model, gates, actions, and evidence. The HTML
output is a local, static dashboard snapshot that can be opened directly in a
browser; the dashboard server exposes the same model at `/state.json`, the
filtered queue at `/actions.json`, the Markdown handoff view at `/actions.md`,
the controlled action page at `/actions/open`, and a refreshable page at `/`.
`/actions/execute` is reserved for same-origin confirmed go-run execution.
`/go/dispatch` is the browser entry for creating a new `/go` run from a
registered local project root; it can prepare packets only or start shards
immediately, depending on whether the user checks `Execute immediately`.
`--paper-project`
adds a paper iteration workspace as an `rdpaper` run with its privacy gate, next
local command, `WEB_AI_ADAPTER.yaml` provider binding, manual fallback
instructions, and provider safety gate next action. Active gates appear in a
front-page Gate Focus section with their action id, resume filter, and served
Markdown handoff link; queued go-runs also expose a local controlled-action
page. The served dashboard homepage links to the JSON, Markdown, controlled
action, and `/go` dispatch endpoints so they are discoverable from the browser.
Current gate, run, and
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

## 10. Import a summary-only Web AI session

```powershell
devframe web-ai import .\chatgpt-summary.json --runtime-dir C:\Users\you\.devframe-runtime
```

If Chrome is already open with local CDP enabled and ChatGPT is loaded, bind it
without copying any raw conversation content:

```powershell
devframe web-ai bind-chrome --runtime-dir C:\Users\you\.devframe-runtime --project demo-project --cdp-endpoint http://127.0.0.1:9222
```

The command records only a summary session and keeps cookies, browser profile
data, local storage, raw transcripts, and message text out of the runtime file.

The import command recursively rejects raw transcript fields
(`raw_transcript`, `transcript`, `conversation`, `raw_messages`) and rejects
`messages[].content` / `messages[].text`; use `content_summary` only. Valid
summaries are normalized and written into `<runtime-dir>\web-ai-sessions\`. After import, the session appears
in `devframe sessions` and the read-only dashboard. Raw transcripts, cookies,
browser profile exports, and secret material must not appear in these files.

## 11. Inspect sessions (including imported web AI sessions)
