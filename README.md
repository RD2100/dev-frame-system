<p align="center">
  <img src="docs/assets/devframe-system-banner.svg" alt="devframe-system: web AI as an external brain" width="100%" />
</p>

<h3 align="center">Use GPT Web, or any capable web AI, as an external brain for every software tool and coding agent you already use.</h3>

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
  <img alt="Agents" src="https://img.shields.io/badge/agents-Codex%20%7C%20Claude%20Code%20%7C%20CLI-6f42c1" />
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20PowerShell-24506b" />
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-green" />
</p>

```text
/rdinit                 # initialize the external-brain operating layer
/bindChrome <url>       # bind GPT Web, DeepSeek, Doubao, or another web AI URL
/rdgoal <project> <goal> # route a goal through the total-control loop
/rdpaper <project> <goal> # route a paper task through the paper review loop
```

**The core question is not "how do we build another governance framework?" Many people are already doing that. The real question is: how can we improve code quality and direction control for free, or as close to free as possible, with the simplest workflow?**

dev-frame-system answers by turning a web AI session into an **external brain** for software development. GPT Web is the default example, but DeepSeek, Doubao, or another capable browser-accessible AI can play the same role. The external brain keeps product direction, engineering tradeoffs, task boundaries, evidence, and review memory in one place. Your IDE, CLI, browser, scripts, tests, and coding agents become replaceable executors.

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

dev-frame-system gives you a portable operating layer for agent-assisted development:

- **Direction control**: keep the real goal, tradeoffs, and constraints visible before code changes start.
- **Task dispatch**: turn vague requests into bounded TaskSpecs for Codex, Claude Code, CLI tools, browser automation, or other agents.
- **Evidence-based review**: use ExecutionReport, evidence indexes, review gates, and negative fixtures to prevent fake success.
- **Reusable bootstrap**: install the same operating layer into another project with a PowerShell bootstrap.
- **External-brain binding**: use `/bindChrome` to tie a stable browser AI session to the current project.
- **Total-control orchestration**: use `rdgoal` to coordinate several project-local workflows while logging controller decisions, snapshots, and final review points.
- **Paper review loop**: use `/rdpaper` to combine a web AI reviewer with a local agent that prepares privacy-safe paper packets and records evidence.

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

After bootstrap, bind your browser AI session from your agent environment:

```text
/bindChrome https://chatgpt.com/...
```

Optionally install the control-plane CLI and route a project through `rdgoal`:

```powershell
cd .\packages\control-plane
pip install -e .
rdgoal "D:\my-project" "Build the MVP" --digest
```

`/rdgoal` is the human-facing slash entrypoint. In a shell, use the installed
`rdgoal` command. `devframe rdgoal` remains available as the compatibility
form for scripts that already use the umbrella CLI.

Then run work through the external-brain loop:

1. Define the goal, risk, scope, and acceptance criteria in the web AI.
2. Convert the work into a bounded TaskSpec.
3. Dispatch to an executor such as Codex, Claude Code, a CLI script, or browser automation.
4. Collect ExecutionReport and verification output.
5. Accept only when evidence passes the review gates.
6. Feed reusable lessons back into the project memory.

## Four Skill Entrypoints

| Skill | Purpose | Result |
|---|---|---|
| `/rdinit` | Initialize a repository with dev-frame-system assets | `AGENTS.md`, rules, schemas, tool policy, capability inventory, and runtime docs |
| `/bindChrome <url>` | Bind a browser AI session to the current project | A stable external-brain session tied to local project context |
| `/rdgoal <project> <goal>` | Route a project goal through the total-control controller | Project contract, controller decision, dispatch packet, worker report, and runtime digest |
| `/rdpaper <project> <goal>` | Route a paper task through the paper review controller | Paper workspace, Web AI Adapter config, privacy gate, review report, and evidence summary |

Provider note: GPT Web is the default reference path because it is widely available and good at long-form coordination. The provider is replaceable; the contract is not. Browser-hosted providers use `docs/agent-runtime/web-ai-adapter-contract.md` and `schemas/web_ai_adapter.schema.json`; Chrome plus ChatGPT is a reference adapter, not a hard-coded boundary. If another web AI cannot preserve project context, coordinate tasks, and review evidence, use it as a secondary reviewer rather than the primary external brain.

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
