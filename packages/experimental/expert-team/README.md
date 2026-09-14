---
description: "Expert-team core plugin: fail-loud pack mounting with strict expert-md and team.yml validation, pipeline orchestration with human-review gates, persona-derived phase subagents over the agent registry's scoped-create seam, and the five model tools (list, run, status, approve, consult)."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-team

English | [中文](README.zh.md)

## Summary

`dsh-experimental-expert-team` mounts expert teams from data packs: expert personas (`experts/<id>.md`), a pipeline definition (`team.yml`), pack skills, and phase-result JSON Schemas, validated fail-loud at load and orchestrated phase by phase at run time. One Cordis row provides `ctx.expertTeam` and registers the five model tools (`expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`, `consult_expert`); each phase derives a persona-scoped subagent through the agent registry's scoped-create seam, delivers its artifact as a file under `<artifactsDir>/<runId>/`, and parks the run at any declared human-review gate — the human approval is the trust anchor, and expert output is observed data. The shipped [paper-research data pack](../expert-pack-paper/README.md) is the reference consumer of the pack format.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

### Mount the plugin

The plugin mounts as a plain `cordis.yml` row. Both config fields are required with no defaults: `packs` is at least one team-pack directory, and `artifactsDir` is the runtime artifacts root a run writes under (`<artifactsDir>/<runId>/`; a repo-relative path resolves against the process working directory). A pack that fails validation — missing `team.yml`, a malformed expert file, a forward or unknown `depends_on`, a missing schema or skill file, a duplicated team id — fails the load instead of half-mounting.

```yaml
- name: '@deepseek-ai/dsh-experimental-expert-team'
  config:
    packs:
      - ./packages/experimental/expert-pack-paper
    artifactsDir: ./research-artifacts
```

### What you get

The row provides `ctx.expertTeam` (a `TeamOrchestrator`) and five model tools on `ctx.tools`.

- `expert_team_list` — every mounted team with its phases, dependencies, artifacts, gates, and experts; read this before running a team.
- `expert_team_run` — starts one pipeline run over the free-form input (for example the research topic) and returns when the run parks: at a human gate (`waiting-approval`), on completion, or on a failure.
- `expert_team_status` — one run snapshot: per-phase states with artifacts, attempts, and recorded reviews.
- `expert_team_approve` — records the human decision on a parked gate; an approval resumes the pipeline to the next park point and delivers a best-effort acceptance follow-up to the phase session, a rejection returns the artifact to the same phase session with the comment as revision guidance.
- `consult_expert` — one bounded expert answer outside any run: no artifacts, no run state, no phase side effects.

An expert's `tools` front matter is an allowlist enforced twice: the derivation restricts the subagent's visible tools to it, and an executor guard denies anything else by name. A pack naming a tool the deployment does not mount fails the run start (or the consult) with `EXPERT_TEAM_TOOL_MISSING` instead of composing a phase that cannot keep its own promise.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the plugin and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Pack contract and fail-loud mounting

The catalog (`src/catalog.ts`) mounts every configured pack once per process: strict key-set parsing of the expert md front matter and `team.yml` (`src/expert-md.ts`, `src/team-yml.ts`), cross-checks that each phase's expert exists, its `depends_on` references only earlier phases (acyclic by construction), its schema file exists inside the pack, and each declared skill carries a `SKILL.md`. Every violation throws `ExpertTeamError` with a stable `EXPERT_TEAM_*` code at load.

### The phase result protocol

A phase expert has no write tool. It answers with the artifact as the reply body plus a fenced-JSON result object (`artifactPath`, `summary`, optional `openQuestions`) as the last block (`src/result-protocol.ts`); the runtime splits the reply, validates the result against the declared artifact name and the pack's JSON Schema when present, writes the body atomically only after the contract passes, and re-drives the same session at most two times on a contract failure so revisions stay in context (`src/runtime.ts`). The briefings that carry the run facts, upstream artifact paths, handoff checks, and the output contract are composed in `src/briefing.ts`.

### Gate semantics

Run state is authoritative in memory and mirrored to `<artifactsDir>/<runId>/run-state.json` at every commit point (`src/orchestrate.ts`). A gated phase parks as `gate-pending` / `waiting-approval`; concurrent approvals serialize through a per-run gate. A phase that exhausted its contract retries parks the run at its gate with the failure reported — the human cannot approve a failed phase (nothing accepted exists to pass downstream), but a rejection with a comment re-opens it as a guided revision in the same session. An approval also delivers a best-effort follow-up to the gated phase session — the artifact was accepted, with the reviewer's comment when present — so the persona's post-acceptance steps (for example a memory note) can fire in a real turn; the pipeline never waits on that delivery, and a failed follow-up is logged without failing the run.

### The derivation seam

Phases derive through `ctx.agents.create({ sessionId, meta, agentOptions, setup })` — the agent registry's scoped-create face — followed by `followup()` plus `await agent.whenIdle()` to drive one turn. It is deliberately not the agent-hierarchy dispatch engine: a pipeline phase needs a persona-scoped session with a bounded tool face, no worktree, and no role binding; hierarchical mode is the seam that would map gates onto dispatch instead. Deriving through the registry keeps this package a plain plugin over existing loop behavior — no new execution loop.

### Source map

| File | Role |
|---|---|
| [`src/types.ts`](src/types.ts) | Expert, phase, and team definitions; run and phase state; the stable `EXPERT_TEAM_*` error-code union |
| [`src/validate.ts`](src/validate.ts) | Shared strict-value validators for the pack file parsers |
| [`src/expert-md.ts`](src/expert-md.ts) | Strict parsing of one expert definition file |
| [`src/team-yml.ts`](src/team-yml.ts) | `team.yml` parsing and pack-level cross validation |
| [`src/catalog.ts`](src/catalog.ts) | Pack mounting and immutable team/expert lookups |
| [`src/config.ts`](src/config.ts) | Explicit config validation (packs, artifactsDir) |
| [`src/ids.ts`](src/ids.ts) | The opaque `RunId` brand and its mint/parse |
| [`src/result-protocol.ts`](src/result-protocol.ts) | Reply splitting, result-contract checks, schema validation, consult bound |
| [`src/briefing.ts`](src/briefing.ts) | Phase briefings, revision follow-ups, and consult messages |
| [`src/runtime.ts`](src/runtime.ts) | Persona-derived subagents, the bounded retry loop, consults |
| [`src/orchestrate.ts`](src/orchestrate.ts) | Runs, topological phase execution, gates, run-state mirroring |
| [`src/tools.ts`](src/tools.ts) | The five model tool definitions |
| [`src/plugin.ts`](src/plugin.ts) | Loader wiring: config, catalog, service, tools, usage section, disposal |

### Invariant

No runtime invariant companion is published: the orchestrator holds no cross-process observable relationship to assert — its guarantees (artifact written only after the contract passes, state mirrored at commit points, serialized approvals) are enforced inside one process and validated by the orchestration behavior tests.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Expert-team tools and guidance

#### What the model sees

The five tools join the scopes that see them: `expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`, and `consult_expert`. One static usage section (`expert-team:usage`) joins the global prompt layer, teaching when to list, run, approve with the reviewer's own words, and prefer a consult over a full run, and that artifacts are files to reference by path. During a run, each phase subagent's request carries the expert persona verbatim, one section per declared pack skill, the upstream artifact paths, the handoff checks, and the phase output contract including the schema text — artifact content itself never re-enters the prompt, only its path does.

#### Token effect

The five tool schemas cost tokens on every request in the scopes that see them, and the usage section's fixed text joins every request's prompt once. A run's cost arrives per phase: each phase request adds its persona (a few KiB) plus skill sections, upstream references, and the declared schema text; each phase result and each gate decision appends a bounded JSON after the reusable prefix.

#### KV Cache effect

Prefix-stable while the mounted packs and tool schemas stay unchanged: the schemas and the static usage section are declared once, and per-phase content appends behind the reusable request prefix. Editing any pack file changes what later runs compose and starts a new prefix for the affected requests; mount or unmount changes the tool list and breaks the affected agents' provider cache reuse for the next request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits are current plugin constraints, not a task backlog.

- **Hierarchical mode is not orchestrated.** A team declaring `mode: hierarchical` mounts and lists, but `expert_team_run` refuses it with `EXPERT_TEAM_MODE_UNSUPPORTED`; mapping gates onto the agent-hierarchy dispatch engine is deferred until a real hierarchical pack needs it.
- **A run does not resume in a new process.** `run-state.json` mirrors state for inspection, but a parked or in-flight run is lost on restart; resuming from the mirrored state is deferred until a deployment runs teams across restarts.
- **Memory recording is delegated, not owned.** Entity anchoring into project-memory rides the pack's tool allowlists: an expert that declares `memory_append` may record its artifact with the research topic as the entity tag, and an unconfigured memory degrades to `MEMORY_UNAVAILABLE` reported by the tool. The orchestrator itself never calls memory; a core-owned per-artifact memory write is deferred until a measured need, and no alias registry exists for entity tags, so cross-run recall depends on the writing model reusing tags.
- **Phases execute serially.** Declaration order is a topological order, but the executor never parallelizes independent phases; a measured latency need justifies the change.
- **The gate records a decision, not a verified human.** The orchestrator parks the run and records what `expert_team_approve` was told, but it cannot verify that a human spoke: that the approver is the human reviewer is prompt-pinned in the usage section, not capability-enforced.
- **No per-team concurrency cap in M1.** The trusted driver session may issue concurrent `expert_team_run` calls for the same team. Packs cannot recurse — a pack naming one of the plugin's own tools fails the mount (`EXPERT_TEAM_TOOL_FORBIDDEN`), so phase experts cannot approve gates or start runs — but the driver session is trusted and uncapped.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The decision record for the M1 scope lives in [the expert-team Agent Note](../../../.agents/notes/implemented/feature/2026-09-14-expert-team-m1.md).

</details>
