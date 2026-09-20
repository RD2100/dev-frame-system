---
description: "Software-development data pack for the expert-team plugin: six Chinese-primary expert personas, a six-phase human-gated hierarchical team (PRD, architecture, task breakdown, implementation, testing, review), acceptance handoff checks, an acceptance-checklist skill, and phase-result JSON Schemas mounted through the core's Config.packs"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-pack-dev

English | [中文](README.zh.md)

## Summary

`dsh-experimental-expert-pack-dev` is a pure data pack for the `dsh-experimental-expert-team` core — expert personas, a team definition, a skill, and JSON Schemas, with no code. Mounting this directory through the core's `packs` config gives a deployment the software-development team: `product-manager` turns a raw request into a PRD with user stories, scope, testable acceptance criteria, and non-goals; `architect` turns the approved PRD into module boundaries, interface contracts, data structures, technology choices with reasons, and a risk list; `tech-lead` decomposes the design into a task DAG where every task carries an acceptance criterion and dependencies; `engineer` implements inside the run directory with the pack's widest tool face (shell, file writes, todos) and logs the work; `qa` derives a test plan from the acceptance criteria and reports defects with reproduction steps; `code-reviewer` reviews correctness, maintainability, test coverage, and security for the human's final decision. Human gates sit after the PRD and after the review: expert output is observed data and the human approval is the trust anchor. Artifacts land under a run directory of the core's `artifactsDir`.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the pack](#understand-the-pack)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

### Mount the pack

The core package `@deepseek-ai/dsh-experimental-expert-team` owns the model tools, orchestration, gates, and validation; this pack contributes only data. Point one `packs` entry at this directory — a repo-relative or absolute path, or the installed package directory:

```yaml
# the expert-team core row in cordis.yml; the field contract is owned by the core package
packs:
  - ./packages/experimental/expert-pack-dev
artifactsDir: ./dev-artifacts
```

The core validates `team.yml` and the expert files fail-loud at load: unique phase ids, existing expert references, acyclic backward-only `depends_on` lists, entry consistency, existing schema files, and expert tool allowlists that are non-empty, name only mounted tools, and never name the plugin's own tools. A pack that fails validation never half-mounts.

### The pipeline

| Phase | Expert | Depends on | Artifact | Gate |
|---|---|---|---|---|
| `prd` | `product-manager` | — (entry) | `prd.md` | `human-review` |
| `architecture` | `architect` | `prd` | `design.md` | — |
| `task-breakdown` | `tech-lead` | `architecture` | `tasks.md` | — |
| `implementation` | `engineer` | `task-breakdown` | `implementation.md` | — |
| `testing` | `qa` | `implementation` | `test-results.md` | — |
| `review` | `code-reviewer` | `testing` | `review.md` | `human-review` |

A rejected gate returns the artifact to the owning expert with the reviewer's comments for revision. Each downstream expert verifies the handoff checks in its frontmatter before accepting upstream material: `architect` verifies the PRD's acceptance criteria are independently decidable, `tech-lead` verifies the design contracts are complete enough to decompose, `engineer` verifies the task boundaries and finished dependencies, `qa` verifies every task has an acceptance criterion, and `code-reviewer` verifies the test report is evidence-backed. All six phases return a structured result object validated by their corresponding schemas under [`schemas/`](schemas/); the implementation phase's declared artifact is `implementation.md`, while code the engineer writes with its file tools lands beside that artifact in the run directory.

### Skills, tools, and memory

The [acceptance-checklist skill](skills/acceptance-checklist/SKILL.md) is the discipline for writing and verifying acceptance criteria: `product-manager` self-checks with it before the gate, `architect` applies it at the PRD handoff, and `tech-lead` applies it to every task's acceptance criterion. Tool faces differ by role: all six personas share `read`, `grep`, `glob`, and `memory_search`; `engineer` additionally carries `pwsh`, `write`, `edit`, `read_image`, `todo_write`, and `memory_append`, and `qa` additionally carries `pwsh`. A deployment missing any of those tools fails the run loud with `EXPERT_TEAM_TOOL_MISSING` at the earliest resolvable point (the allowlists are proven mounted before anything is created), while a mounted-but-unconfigured vault makes the memory tools report `MEMORY_UNAVAILABLE` and the phase continues without a memory note, reported honestly. Memory anchoring rides the project-memory entity design: the engineer records one bounded note per implementation log tagged with the project or module name as the entity tag.

-----

<a id="understand-the-pack"></a>
## Understand the pack

<details>
<summary>Pack internals — click to expand</summary>

A pack is a directory contract, not a library: the core's catalog loader reads these files at load time, and every phase composes its subagent request from them at run time.

| Path | Role |
|---|---|
| [`team.yml`](team.yml) | The team: team id and title, `hierarchical` mode, entry phase, and the six phases with dependencies, inputs, artifacts, schema references, and gates |
| [`experts/product-manager.md`](experts/product-manager.md) | PRD persona: user stories, scope, testable acceptance criteria, non-goals |
| [`experts/architect.md`](experts/architect.md) | Design persona: module boundaries, interface contracts, data structures, technology choices, risks |
| [`experts/tech-lead.md`](experts/tech-lead.md) | Task-breakdown persona: the task DAG with acceptance criteria and dependencies |
| [`experts/engineer.md`](experts/engineer.md) | Implementation persona: the pack's widest tool face (`pwsh`, `write`, `edit`, `todo_write`); writes code into the run directory |
| [`experts/qa.md`](experts/qa.md) | Testing persona: test plans from acceptance criteria, defect reports with reproduction steps |
| [`experts/code-reviewer.md`](experts/code-reviewer.md) | Review persona: correctness, maintainability, test coverage, security |
| [`schemas/prd-summary.schema.json`](schemas/prd-summary.schema.json) | Draft-07 validation of the prd result object |
| [`schemas/design-summary.schema.json`](schemas/design-summary.schema.json) | Draft-07 validation of the architecture result object |
| [`schemas/tasks-summary.schema.json`](schemas/tasks-summary.schema.json) | Draft-07 validation of the task-breakdown result object |
| [`schemas/implementation-summary.schema.json`](schemas/implementation-summary.schema.json) | Draft-07 validation of the implementation result object |
| [`schemas/test-results-summary.schema.json`](schemas/test-results-summary.schema.json) | Draft-07 validation of the testing result object |
| [`schemas/review-summary.schema.json`](schemas/review-summary.schema.json) | Draft-07 validation of the code-review result object |
| [`skills/acceptance-checklist/SKILL.md`](skills/acceptance-checklist/SKILL.md) | The acceptance-checklist skill, shaped like a Claude Code skill |
| [`skills/acceptance-checklist/references/checklist.md`](skills/acceptance-checklist/references/checklist.md) | The checklist items the skill applies |

Expert files are YAML frontmatter plus a Chinese-primary persona body. The frontmatter keys (`id`, `team`, `name`, `role`, `goal`, `tools`, optional `skills` and `handoff-checks`) are the load-time contract, and the `tools` allowlist bounds what the phase subagent may call. Each phase-result schema validates the shared `{ artifactPath, summary, openQuestions? }` result shape together with its phase-specific constraints; the schemas remain standalone so the catalog can validate every referenced file inside the pack.

### Invariant

No runtime invariant companion is published: the pack is data consumed through the core's catalog loader — the fail-loud guarantees live in the loader's mount-time validation and the run-time result checks, not in a package-local observable relationship.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Expert personas on subagent requests

#### What the model sees

The pack registers no tools, prompt sections, or session events of its own; the core's four tools — `expert_team_list`, `expert_team_run`, `expert_team_status`, and `expert_team_approve` — are the only model-visible additions and are owned by the core package. `expert_team_run` also accepts `expert` plus `question` for a bounded consultation outside a run. During a run, each phase's subagent request carries the persona body of the phase expert verbatim (Chinese-primary), references to the upstream artifacts, and its phase result schema; the `tools` frontmatter allowlist bounds the subagent's callable tools. The engineer's and qa's allowlists include `pwsh`, so those phase sessions run shell commands with the run directory as their working directory.

#### Token effect

Zero while no run is active. During a run, each phase request adds its persona (a few KiB), the upstream artifact references, and its result schema; each phase result and the engineer's accepted memory note appends a bounded JSON after the reusable prefix.

#### KV Cache effect

Pack files are static, so within a phase the persona and schema sit in the stable request prefix and artifact content appends behind them. Editing any pack file changes what later runs compose and starts a new prefix for the affected requests; across runs in different sessions there is nothing to reuse.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits are current pack constraints, not a task backlog.

- **Hierarchical execution uses scoped-create, not agent-dispatch.** The six phases execute in declaration/topological order through the core's scoped-create seam. When `session-identity` is mounted, controller, lead, and worker sessions are recorded with their parent bindings and delegation depth; the expert-team runtime does not allocate worktrees or call the `agent_dispatch` tool. Independent phases remain serial.
- **The pack is data only.** Orchestration, gate approval, schema validation, and memory recording are owned by the expert-team core; the pack cannot run alone, and its execution evidence lives in the core's catalog tests against this pack.
- **Tool faces require mounted tools.** `engineer` and `qa` name `pwsh`, and the engineer additionally names `read_image`, `todo_write`, and `memory_append`: a deployment without those tools fails the run loud with `EXPERT_TEAM_TOOL_MISSING`, while a mounted-but-unconfigured vault degrades to `MEMORY_UNAVAILABLE` and no note, reported honestly; guaranteed per-artifact memory writes belong to the core.
- **Chinese-primary personas.** Persona bodies pin model behavior in Chinese while schema descriptions are English; a deployment wanting English-first personas must fork the pack.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The core's phase briefing describes the actual output contract and tells a phase not to use tools outside its allowlist. The engineer's allowlist includes `write`/`edit`, so implementation code may be changed inside the run directory; the runtime still validates and persists `implementation.md` from the reply contract before the phase is accepted.

</details>
