<p align="center">
  <img src="docs/assets/devframe-system-banner.svg" alt="devframe-system: web AI as an external brain" width="100%" />
</p>

<h3 align="center">An OpenCode-first governed coding CLI for serious software work. `devframe code` is the product; the control plane sits behind it.</h3>

<p align="center">
  English | <a href="README.zh-CN.md">Simplified Chinese</a>
</p>

<p align="center">
  <a href="#why-this-exists">Why this exists</a> |
  <a href="#what-it-does">What it does</a> |
  <a href="#quick-start">Quick start</a> |
  <a href="#repository-layout">Repository layout</a>
</p>

<p align="center">
  <img alt="Web AI External Brain" src="https://img.shields.io/badge/Web%20AI-External%20Brain-1f6feb" />
  <img alt="No Submodules" src="https://img.shields.io/badge/submodules-none-20c997" />
  <img alt="Focus" src="https://img.shields.io/badge/focus-code%20quality%20%2B%20direction-00a884" />
  <img alt="Agents" src="https://img.shields.io/badge/agents-OpenCode%20%7C%20custom%20CLI-6f42c1" />
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20PowerShell-24506b" />
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-green" />
</p>

```text
devframe code "<goal>"   # 1. prepare a governed coding run
devframe code status     # 2. inspect its status
devframe code execute    # 3. execute when you choose
devframe code workers    # optional: check local worker availability
devframe dashboard serve # optional control-plane view

# advanced / secondary surfaces
devframe client
devframe go <project> <goal>
rdgoal <project> <goal>
```

**DevFrame should be read first as a governed coding product. `devframe code` is the mainline daily loop. The dashboard, rdgoal, RD-Code client, MCP/ACP surfaces, and paper workflow are supporting or advanced layers around that loop.**

> **Project status:** This repository is local-gate-green and chain-verified in
> a development context, not a published, externally reviewed release. See
> [Release readiness](docs/status/release-readiness.md) for the exact scope of
> what has and has not been validated.

The core bet is simple:

> make one coding entrypoint feel disciplined, resumable, and reviewable
> without forcing users to adopt a heavyweight platform first

DevFrame uses a web AI as an external brain when that helps with direction and
review, but the product you use every day is still a local coding tool. The
mainline path is `devframe code`: enter a goal, prepare bounded work, inspect
the exact worker command, execute when you choose, and continue from the same
run later.

Everything else exists to support that loop:

- the dashboard is an optional read-only diagnostic view
- `rdgoal` is the deeper orchestration layer
- the T3/RD-Code bridge is a secondary client track
- MCP/ACP, provider selection, and paper flows are advanced capability surfaces

## Start Here

If you only want the product-shaped path, do this:

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
python -m pip install -e ".\packages\control-plane[dev]" -e ".\packages\ai-workflow-hub[dev]"
.\scripts\verify-release.ps1

devframe code
devframe code workers
devframe code status
```

That is the mainline. Learn the rest only when the default loop is working for
you.

## Why This Exists

AI coding tools are good at producing code. They are weaker at remembering the product direction, proving that the code got better, and stopping the work before it drifts.

dev-frame-system puts a thinking layer above the tools:

| Common workflow | dev-frame-system workflow |
|---|---|
| Ask one agent to fix something | Use the bound web AI to define scope, risk, and acceptance first |
| Trust the final answer | Require evidence, verification output, and reviewer-readable reports |
| Let each tool keep separate context | Keep direction and decisions in one external brain |
| Add another paid platform | Reuse the web AI and tools you already have |
| Review after the mess grows | Gate every task through rules, schemas, and evidence |

The short version:

> The web AI thinks and coordinates. Tools execute. Evidence decides whether the work is accepted.

## What It Does

DevFrame's main product behavior is:

- **Governed coding loop**: prepare a bounded coding run, inspect it, execute it, and resume it later through `devframe code`.
- **Execution boundary**: make token-spending or worker-spending actions explicit instead of implicit.
- **Evidence-first review**: keep ExecutionReport, status, changed files, and review surfaces visible enough that "done" is not just a claim.

Supporting behaviors:

- **Optional diagnostics**: inspect runs, actions, sessions, and gates in the read-only dashboard when a visual view is useful.
- **Advanced orchestration**: use `rdgoal`, `go`, or Web AI bindings when the default coding loop is not enough.
- **Bootstrap and reuse**: install the same operating layer into another repo.

## Quick Start

Clone the repository:

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
```

Inspect the public snapshot:

```powershell
.\scripts\verify-public-snapshot.ps1
```

Before cutting a local release or sharing the control-plane package, run the
release verification entrypoint:

```powershell
python -m pip install -e ".\packages\control-plane[dev]" -e ".\packages\ai-workflow-hub[dev]"
.\scripts\verify-release.ps1
```

Bootstrap the operating layer into another project:

```powershell
.\templates\runtime-bootstrap\bootstrap.ps1 `
  -ProjectName "my-project" `
  -ProjectRoot "D:\my-project" `
  -DryRun

.\templates\runtime-bootstrap\bootstrap.ps1 `
  -ProjectName "my-project" `
  -ProjectRoot "D:\my-project"
```

After bootstrap, bind your browser AI session only if you need the external
brain loop:

```text
/bindChrome https://chatgpt.com/...
```

Bootstrap also generates a project-local `/go` bridge for advanced use:

```powershell
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed -Prepare -Dashboard
.\tools\devframe-go.ps1 -Goal "Build the MVP" -Changed -Execute
```

The wrapper defaults to preview mode, so it shows changed-file shards and worker
command templates before any rdgoal packets or worker runs are created. Use
`-Prepare -Dashboard` to create queued packets and view them without running
workers.

Install the CLI and use the mainline coding loop first:

```powershell
cd .\packages\control-plane
pip install -e .
cd D:\my-project
devframe code "Build the MVP" --target src --runtime-dir "$env:TEMP\devframe-code" --dashboard
devframe code workers
devframe code "Fix the branch" --changed --agents auto --worker opencode --preview
devframe code status --runtime-dir "$env:TEMP\devframe-code"
devframe code execute --runtime-dir "$env:TEMP\devframe-code"
```

Advanced orchestration stays available when you need it:

```powershell
rdgoal "D:\my-project" "Build the MVP" --digest
devframe go "D:\my-project" "Build the MVP" --agents 3 --target src --runtime-dir "$env:TEMP\devframe-go"
```

`devframe code` is the product-shaped coding entrypoint. It defaults to the
current repository and prompts for a goal when one is not supplied, prepares one
bounded coding-agent session, prints the exact worker command, and records state
for the dashboard. Use `--worker opencode` to choose the built-in OpenCode worker profile, the default local coding-agent runtime. Use `--command <your-worker>` only for explicit custom executor commands (for example, `python -m your_worker_module`). Run `devframe code workers`
first to see which local worker CLIs are
available; it is status-only and does not create packets or spend worker
tokens. Use `--changed --agents auto` to target modified, staged, or
untracked git files and fan them out across bounded shards; `--max-agents` caps
the automatic fan-out. Use `--preview` to print the shard plan and worker
command template without creating packets or spending worker tokens. Shards are
balanced by estimated target bytes so one agent does not accidentally receive
most of the file context. Add `--execute` only when you are ready to spend
worker tokens. Add `--dashboard` to open the read-only local visual interface
for the same runtime; the dashboard has an English/中文 language switch, and
`?lang=zh-CN` still opens the Chinese view directly. Each go-run card also
shows the exact `devframe code status` and `devframe code execute` commands for
that prepared run.
After preparing a run, use `devframe code execute [latest|<go-run-id>]` to
spend worker tokens later without creating another set of packets; passed
agents are skipped unless `--rerun-passed` is provided.

`rdgoal`, `/go`, `devframe client`, and the broader Web AI surfaces are not the
first thing a new daily user should learn. They are second-line tools for when
the main `devframe code` loop is already working and you need more orchestration.

`/go` is the coding-tool entrypoint. In a shell, `devframe go` prepares parallel
coding-agent dispatch packets and shows the exact worker commands without
spending agent tokens by default. Add `--execute` to run the shards concurrently;
use `--worker opencode` to pick the built-in worker profile, or pass
`--command <your-worker>` to route the same TaskSpec packets through another
executor command (for example, `python -m your_worker_module`). The Visual
Control Plane reads the same runtime and
shows the go-run plus each coding-agent shard, target, packet, status, and
worker command, plus copyable status and execute commands for the go-run.
Pass `--changed --agents auto` to derive shard targets from git changes instead
of sending a project-wide task or guessing the shard count manually.

Then run work through the external-brain loop:

1. Define the goal, risk, scope, and acceptance criteria in the web AI.
2. Convert the work into a bounded TaskSpec.
3. Dispatch to an executor such as OpenCode, a custom CLI script, or browser automation.
4. Collect ExecutionReport and verification output.
5. Accept only when evidence passes the review gates.
6. Feed reusable lessons back into the project memory.

## Advanced Entrypoints

| Skill | Purpose | Result |
|---|---|---|
| `/rdinit` | Initialize a repository with dev-frame-system assets | `AGENTS.md`, rules, schemas, tool policy, capability inventory, and runtime docs |
| `/bindChrome <url>` | Bind a browser AI session to the current project | A stable external-brain session tied to local project context |
| `/go <project> <goal>` | Prepare or run parallel coding-agent shards when `devframe code` is not enough | A go-run record, per-agent rdgoal packets, worker commands, and dashboard-visible runs |
| `/rdgoal <project> <goal>` | Route a project goal through the deeper control loop | Project contract, controller decision, dispatch packet, worker report, and runtime digest |
| `/rdpaper <project> <goal>` | Route a paper task through the paper review controller | Paper workspace, Web AI Adapter config, privacy gate, review report, and evidence summary |

Provider note: GPT Web is the default reference path because it is widely available and good at long-form coordination. The provider is replaceable; the contract is not. Browser-hosted providers use `docs/agent-runtime/web-ai-adapter-contract.md` and `schemas/web_ai_adapter.schema.json`; Chrome plus ChatGPT is a reference adapter, not a hard-coded boundary. If another web AI cannot preserve project context, coordinate tasks, and review evidence, use it as a secondary reviewer rather than the primary external brain.

Future product shape: see [Visual Control Plane](docs/agent-runtime/visual-control-plane.md) for the governance-first client model that connects projects, provider bindings, agents, runs, evidence, review, and gates.
The first read-only state export is available with `devframe visual-state --runtime-dir <dir>`, as a local HTML snapshot with `devframe visual-state --runtime-dir <dir> --format html --output visual-state.html`, as a local dashboard with `devframe dashboard serve --runtime-dir <dir>`, or as a focused queue with `devframe actions --runtime-dir <dir>`. The dashboard binds to loopback only by default; pass `--allow-remote` to expose it on non-loopback hosts. Add `--paper-project <dir>` to include a paper iteration workspace, its `WEB_AI_ADAPTER.yaml` provider binding, manual fallback instructions, and the matching provider safety gate with a next action in the same control-plane view. The dashboard Agent Registry shows each agent's role, scope, provider, binding health, and status in one table, while Run Details cards show TaskSpec/evidence paths, the current controller decision, and the next safe local command. The dashboard and actions CLI both group current gate/run/decision guidance into a read-only Action Queue with visible action ids and copyable `--action-id` resume filters; the actions CLI and `/actions.json` dashboard endpoint can also filter by status, priority, source type, source id, or action id for scriptable triage. Use `devframe actions --format markdown --output ACTION_QUEUE.md` or the dashboard `/actions.md` endpoint to turn a filtered queue into a manual resume or Web AI handoff packet.

## Integrated Modules

| Path | Integrated from | Purpose |
|---|---|---|
| `packages/agent-acceptance/` | `agent-acceptance` | acceptance contracts, policies, and CI preflight templates |
| `packages/ai-workflow-hub/` | `dev-frame-opencode/ai-workflow-hub` | workflow orchestration, task queues, evidence adapters, and context layer |
| `packages/control-plane/` | `devframe-control-plane` | runtime coordination, pipeline specs, handoff helpers, and state-machine pieces |
| `packages/test-frame/` | `test-frame` | verification adapters, normalizers, test orchestration, and mini-program E2E package |

These modules were integrated as a curated snapshot. Their old Git histories and internal process artifacts were intentionally not imported.

## Repository Layout

```text
dev-frame-system/
|-- README.md
|-- README.zh-CN.md
|-- AGENTS.md
|-- docs/
|   |-- agent-runtime/
|   |-- assets/
|   `-- module-sources.md
|-- packages/
|   |-- agent-acceptance/
|   |-- ai-workflow-hub/
|   |-- control-plane/
|   `-- test-frame/
|-- rules/
|-- schemas/
|-- scripts/
`-- templates/
    `-- runtime-bootstrap/
```

## Who Should Use This

Use dev-frame-system if you already use AI coding tools but keep running into the same problems:

- the agent writes code before the direction is clear;
- every tool has its own context and forgets the bigger picture;
- "done" means "the agent said done" rather than "the evidence proves it";
- repeated mistakes disappear into chat history;
- you want better code review pressure without adding another heavy platform.

## License

Licensed under the [Apache License 2.0](LICENSE).
