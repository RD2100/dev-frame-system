---
description: Proposed expert-team plugin and data packs: expert catalog, human-gated pipeline orchestration, and the paper team's phased research workflow.
---

# Detailed Design: Expert Team

English | [中文](detailDesign-expert-team.zh.md)

## Summary

This reference specifies the expert-team feature: a mechanism layer that runs multi-expert workflows as persona-scoped sessions derived on the host's agent registry, plus team data packs that describe experts and their phase graph. The core plugin owns exactly two abstractions — the expert catalog and pipeline orchestration with human gates — while each team (paper, software development) is a pack of expert Markdown files, skill directories, a `team.yml`, and result-object JSON Schemas, so a new team needs zero code. Expert output is observed context and the recorded human gate decision is the trust anchor, the same notary model the [memory design](detailDesign-part3.md) applies to confirmed facts. The first milestone ships the core package plus the paper team's first four phases.

## Table of Contents

- [Background and borrowed mechanisms](#background)
- [Requirements analysis](#requirements)
- [Outline design](#outline)
- [Expert format](#expert)
- [Team definition and validation](#team)
- [Orchestration and gates](#orchestration)
- [Model tools and configuration](#tools)
- [Team packs](#packs)
- [Testing strategy](#testing)
- [Milestones](#milestones)

<a id="background"></a>

## Background and borrowed mechanisms

Six open-source projects inform the design. Each contributes a specific mechanism, listed beside what this design deliberately does not take; the pack format additionally bets on the industry de-facto standard of a Markdown persona plus a skills directory, isomorphic to Claude Code subagents and skills.

| Project | Taken into this design | Deliberately not taken |
| --- | --- | --- |
| [ChatDev](https://github.com/OpenBMB/ChatDev) | The phase chain as the unit of composition, and a human entering the loop by occupying a review position at chosen phases. | The fixed virtual software-company analogy and chat-message passing between roles. |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | "Code = SOP(Team)": the standard operating procedure lives in data, and roles exchange structured artifacts, not conversation transcripts. | Its built-in role set and internal communication substrate. |
| [CrewAI](https://github.com/crewAIInc/crewAI) | The persona triple (role, goal, backstory), tasks with expected outputs and a dependency DAG, and pipeline/hierarchical as the two orchestration modes. | Its runtime: DSH session derivation, skills, and human decisions replace it. |
| [AI-Researcher](https://github.com/HKUDS/AI-Researcher) | The staged decomposition of an automated research workflow (literature review, topic selection, method, experiment, writing review) and a run entry that starts from different input levels. | Its five-stage order as law: the paper pack adapts the stages, and experiment/writing stages are deferred. |
| [PaperQA2](https://github.com/Future-House/paper-qa) | Citation discipline (every survey claim carries a verifiable citation) and a retraction/reliability check as survey requirements. | Its storage engine and background indexer; experts use the session's ordinary file and search tools. |
| [STORM](https://github.com/stanford-oval/storm) | Perspectives first: discover research perspectives before literature work, then use them to control question depth and breadth. | Its outline-generation and writing pipeline specifics. |

The governing architecture principle is mechanism/data separation. The core plugin provides only the expert catalog and pipeline orchestration with human gates; the paper team and the software-development team are pure data packs. Everything else rides existing DSH capabilities instead of introducing new ones: the [agent registry](../packages/core/agent/README.md)'s scoped-create face, system-prompt sections, tool restriction and execution guards, the deployment's [default model selection](../packages/core/agent-default-model/README.md), [project-memory](../packages/experimental/project-memory/README.md) entity anchoring, and the session event log. The agent loop is untouched.

<a id="requirements"></a>

## Requirements analysis

### Use cases

| ID | Use case | Outcome |
| --- | --- | --- |
| `UC1` | The user starts a paper-team run with a research topic. | The run executes phases in declaration order and parks at the first human gate with the artifact on disk. |
| `UC2` | The user decides a gate: approve, or reject with comments. | Approve resumes the run; reject returns the artifact to the gated phase's expert with the reviewer's comment as revision guidance, and the revised artifact re-enters the gate. |
| `UC3` | The user asks one expert a question outside any pipeline. | `consult_expert` derives a single-turn session with that expert's persona and tool allowlist and returns a bounded answer; no run or artifact is created. |
| `UC4` | A deployment mounts an additional team pack. | The catalog picks it up from configuration alone; no core change, and an invalid pack fails loud at load. |

### Functional requirements

| ID | Required behavior |
| --- | --- |
| `FR1` | Load every `<pack>/experts/<expert-id>.md` from the mounted packs; validate the frontmatter contract; fail loud on malformed experts and duplicated pack directories or team ids. |
| `FR2` | Load and validate `team.yml`: unique phase ids, existing expert references, `depends_on` backward-only (acyclic by construction), `entry` consistent, referenced schema files present inside the pack. |
| `FR3` | Execute a run's phases in declaration order; each phase derives one persona-scoped session briefed with the run request, upstream artifact paths, the handoff checklist, and the output contract. |
| `FR4` | Persist an artifact under `<artifactsDir>/<runId>/` only after the phase reply passes its result contract — the fenced JSON result object, and the declared JSON Schema when the phase has one; a contract failure re-drives the same session at most twice, then the phase fails. |
| `FR5` | Park a gated phase after its artifact lands and wait for a human decision; approve resumes the pipeline, reject re-drives the phase with the comment, and every decision is recorded with decision, comment, and time. |
| `FR6` | Expose five model tools: `expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`, and `consult_expert`. |
| `FR7` | Mirror run state to `<artifactsDir>/<runId>/run-state.json` at every commit point, so the files on disk tell the whole run story; everything model-visible — briefings, tool results, decisions — is reconstructable from the session log. |

### Non-functional requirements

| ID | Required property |
| --- | --- |
| `NFR1` | Mechanism/data separation: adding a team is pack files only; the core package does not change. |
| `NFR2` | Misconfiguration fails loud: pack defects reject the mount with stable `EXPERT_TEAM_*` error codes; a half-mounted expert team is worse than an absent one. |
| `NFR3` | No hardcoded tunables: `packs` and `artifactsDir` are validated Config fields; the result-contract retry bound of 2 and the run-id mint format are fixed invariants of this design, not tunables. |
| `NFR4` | Trust model: expert artifacts are `observed`, and the recorded human gate decision is the trust anchor; pack content is quoted data that never grants tools, permissions, or authority. |
| `NFR5` | Model-visible ⟺ logged: anything a briefing, tool result, or recorded decision shows the model reconstructs from session events. |
| `NFR6` | Capability reuse over loop changes: all behavior rides the agent registry, prompt sections, tool restriction, default model selection, and project-memory; no new execution loop. |
| `NFR7` | Bounded exposure: briefings carry upstream artifact paths and short descriptors, not artifact contents; personas, artifact bodies, result summaries, and consult answers carry explicit byte bounds. |

### Scope boundaries

- In scope for the first milestone: the core package (catalog, pipeline orchestration, gates, five tools) and the paper team's first four phases, including the reviewer's best-effort project-memory note.
- Deferred to later milestones: the paper team's experiment, writing, review, and revision phases; guaranteed core-level per-artifact memory recording; the software-development team, which this document covers as design only; resuming a parked run in a new process.
- Out of scope: agent-loop changes; a literature index or vector store (revisit only on a measured retrieval problem); cross-team orchestration inside one run; hierarchical execution, which the runtime rejects fail-loud until M3; any path where the model makes the gate decision instead of relaying the reviewer's.

<a id="outline"></a>

## Outline design

### Concept model

| Concept | Definition |
| --- | --- |
| Pack | A read-only team directory: `team.yml`, `experts/*.md`, optional `skills/<name>/` directories with a `SKILL.md` each, optional `schemas/*.json` JSON Schema files. |
| Expert | One expert Markdown file: a persona body plus frontmatter (identity, role, goal, tool allowlist, optional skills and handoff checks). |
| Team | A named orchestration declared by `team.yml`: mode, entry phase, and the phase list. |
| Phase | One expert, its `depends_on` set, its output artifact, optional result schema, and an optional gate. |
| Run | One execution of one team under a host-minted branded `runId`; artifacts and `run-state.json` live under `<artifactsDir>/<runId>/`. |
| Artifact | One file a phase produces; the host — never the expert — writes it, after the reply passed its result contract. |
| Gate | A human checkpoint on a phase (`human-review`); the run parks until the decision is recorded — approve resumes, reject re-drives with the comment. |

### Architecture and module layout

```text
pack (data, read-only)                core plugin (mechanism)
+--------------------------+  load   +-------------------------------+
| team.yml                 |-------->| catalog loader + validators   |
| experts/<expert-id>.md   |         | pipeline orchestrator (DAG)   |
| skills/<name>/SKILL.md   |         | expert runtime (sessions)     |
| schemas/<result>.json    |         | five model tools on ctx.tools |
+--------------------------+         +-------------------------------+
```

The orchestrator and gates sit on the orchestrator module; the runtime derives sessions and enforces the result contract; the catalog is the only pack reader. Two new packages under `packages/experimental/`:

| Package | Owns |
| --- | --- |
| `@deepseek-ai/dsh-experimental-expert-team` (`packages/experimental/expert-team/`) | The catalog loader and validators, the pipeline orchestrator, the expert runtime, and registration of the five tools; Config `{ packs, artifactsDir }`; provides `ctx.expertTeam`. |
| `@deepseek-ai/dsh-experimental-expert-pack-paper` (`packages/experimental/expert-pack-paper/`) | The paper team pack: expert files, skill directories, `team.yml`, and result-object JSON Schemas; a pure data package with no runtime code. |

### DSH seam mapping

| Concern | Existing capability | Use |
| --- | --- | --- |
| Phase session | [Agent registry](../packages/core/agent/README.md) scoped-create (`ctx.agents.create`) | One persona-scoped session per phase, named `expert-team-<runId>-<phaseId>`, driven one turn with `followup` plus `whenIdle`; the run directory is the session's durable cwd. Deliberately not the subagent delegation tool and not the dispatch engine — hierarchical mode (M3) is the seam that maps gates onto dispatch. |
| Persona and tool allowlist | Prompt sections + tool restriction | The persona body rides a system-prompt section verbatim; the expert's `tools` list is both a visibility restriction and an execution guard on the derived session. |
| Skills | Pack skill text as prompt sections | A declared pack skill's `SKILL.md` is injected as its own prompt section — pack data resolved at load, not a registry skill entry. |
| Model selection | [agent-default-model](../packages/core/agent-default-model/README.md) | Phase and consult sessions derive with the deployment's default model; a missing selection fails loud before any session derives. |
| Gate decisions | Recorded reviews | `expert_team_approve` records the reviewer's decision — decision, comment, timestamp — as run state; the pinned usage section obliges the model to relay the human's own decision and words. |
| Memory | [dsh-experimental-project-memory](../packages/experimental/project-memory/README.md) | The pack's reviewer carries `memory_search`/`memory_append` and records a best-effort note per accepted survey, anchored by entity tag; core-level guaranteed recording is deferred (M2). |
| Durability | `run-state.json` + session log | Every commit point mirrors run state atomically ([dsh-atomic-write](../packages/util/atomic-write/README.md)); model-visible content is session events. |

<a id="expert"></a>

## Expert format

An expert is one file, `<pack>/experts/<expert-id>.md`: a fixed-key YAML frontmatter block plus the persona body. The frontmatter key set is exact — unknown keys reject:

| Key | Contract |
| --- | --- |
| `id` | Kebab-case (`[a-z0-9]` segments joined by dashes, max 64 bytes) and equal to the file name without the extension. |
| `team` | Kebab-case; must equal the pack's `team.yml` `team` id. |
| `name` | Display name shown in listings and briefings; one line, max 128 bytes. |
| `role` | One line naming the expert's function; max 256 bytes. |
| `goal` | One line naming the artifact-level objective; max 512 bytes. |
| `tools` | Non-empty array allowlist of tool names the phase session may call (max 32 entries); proven at mount — an unmounted name fails with `EXPERT_TEAM_TOOL_MISSING`, and a name of this plugin's own tools (`expert_team_*`, `consult_expert`) with `EXPERT_TEAM_TOOL_FORBIDDEN` — and enforced at execution. |
| `skills` | Optional array; each entry names a directory under the pack's `skills/` that must provide a `SKILL.md` (max 16 entries). |
| `handoff-checks` | Optional array of one-line acceptance strings (max 16, 256 bytes each); the briefing hands them to the expert as the checklist to verify before producing, and an unmet check stops the phase with an explanation. |

The body is the persona text, Chinese-primary, non-blank, max 16 KiB; CRLF normalizes to LF before parsing. The persona is quoted task context for the phase session, never host instruction. An example from the paper pack:

```text
---
id: literature-reviewer
team: paper
name: 文献综述专家
role: 带引用纪律与撤稿检查意识的文献综述专家。
goal: 围绕确认的研究视角产出可溯源、含 gaps 分析的综述 survey.md。
tools:
  - read
  - grep
  - glob
  - memory_search
  - memory_append
skills:
  - review-checklist
handoff-checks:
  - perspectives.md 存在且非空，每个视角都有核心问题、研究理由与视角边界。
  - …
---

（中文为主的人设正文：工作方式、综述纪律、引用规则、放弃条件……）
```

<a id="team"></a>

## Team definition and validation

`<pack>/team.yml` (the paper team's first four phases):

```yaml
team: paper
title: 论文研究专家团
mode: pipeline
entry: perspective-discovery
phases:
  - id: perspective-discovery
    expert: topic-scout
    input: 运行请求给出的研究主题，以及可选的范围约束与既有项目记忆笔记的检索结果
    output:
      artifact: perspectives.md
  - id: literature-review
    expert: literature-reviewer
    depends_on:
      - perspective-discovery
    input: perspectives.md 中列出的研究视角与研究主题
    output:
      artifact: survey.md
      schema: schemas/survey-summary.schema.json
    gate: human-review
  - id: idea-selection
    expert: idea-selector
    depends_on:
      - literature-review
    input: survey.md 及其研究缺口（gaps）分析与开放问题清单
    output:
      artifact: research-questions.md
      schema: schemas/research-questions-summary.schema.json
    gate: human-review
  - id: method-design
    expert: method-designer
    depends_on:
      - idea-selection
    input: 经人类关口选定的研究问题（research-questions.md 中被批准的候选）
    output:
      artifact: method.md
```

The top-level key set is exact (`team`, `title`, `mode`, `entry`, `phases`); per phase the required keys are `id`, `expert`, `output`, the optional ones `depends_on`, `input`, `gate`.

| Key | Contract |
| --- | --- |
| `team` | Kebab-case pack-unique team id; every expert's `team` field must match it, and two packs may not mount the same team id. |
| `title` | Human-readable title shown by `expert_team_list`; max 256 bytes. |
| `mode` | `pipeline` or `hierarchical`. |
| `entry` | A phase id whose phase declares no `depends_on`; the first phase a run executes. |
| `phases[].id` | Unique kebab-case phase id (max 64 bytes); at most 64 phases per team. |
| `phases[].expert` | An expert id present in the same pack. |
| `phases[].depends_on` | Optional array (max 16) of earlier phase ids — list order defines "earlier", which makes the graph acyclic by construction; a forward, self, or unknown reference fails with `EXPERT_TEAM_PHASE_CYCLE`. |
| `phases[].input` | Optional free-form descriptor of what the phase consumes (max 512 bytes); the entry phase's descriptor is the run input. |
| `phases[].output.artifact` | Artifact file name written under the run directory; a single path segment, max 128 bytes. |
| `phases[].output.schema` | Optional pack-relative path to a JSON Schema file; must stay inside the pack and point at an existing file. |
| `phases[].gate` | Optional; the only allowed value is `human-review`. |

Validation fails loud at mount with stable error codes. Self-contained checks — every tool allowlist included — reject the load; the session-dependent model check rejects at the earliest resolvable point, before any session derives:

| Error code | Condition |
| --- | --- |
| `EXPERT_TEAM_CONFIG_INVALID` | Plugin config failed validation: `packs` missing or empty, a blank, padded, or control-character path, or an empty run input. |
| `EXPERT_TEAM_CATALOG_INVALID` | A pack or its `team.yml` is missing, malformed, duplicated, or self-inconsistent: unknown or missing keys, a bad `mode` or `gate`, duplicate phase ids, oversized fields, an `entry` that is not a no-`depends_on` phase, an expert whose `team` mismatches, a team id mounted twice. |
| `EXPERT_TEAM_EXPERT_INVALID` | An expert file failed its structural or bound validation: frontmatter shape, key set, id/file-stem mismatch, field shapes or bounds, blank or oversized persona. |
| `EXPERT_TEAM_EXPERT_MISSING` | A phase references an expert id the pack does not define; also a consult lookup miss. |
| `EXPERT_TEAM_TEAM_MISSING` | The requested team id is not mounted. |
| `EXPERT_TEAM_PHASE_CYCLE` | A `depends_on` references a non-earlier phase id (forward, self, or unknown). |
| `EXPERT_TEAM_SCHEMA_MISSING` | A referenced schema path escapes the pack, does not exist, or is not a file. |
| `EXPERT_TEAM_SKILL_MISSING` | A declared skill has no `SKILL.md` in the pack, or the file vanished by delegation time. |
| `EXPERT_TEAM_TOOL_MISSING` | An expert allowlist names a tool this deployment does not mount. |
| `EXPERT_TEAM_TOOL_FORBIDDEN` | An expert allowlist names one of this plugin's own tools (`expert_team_*` or `consult_expert`). |
| `EXPERT_TEAM_MODEL_MISSING` | The deployment provides no default model selection to derive expert sessions with. |
| `EXPERT_TEAM_RUN_UNKNOWN` | The requested run id is malformed or not a live run of this process. |
| `EXPERT_TEAM_GATE_PENDING` | No gate awaits a decision, or an approval targets a failed phase. |
| `EXPERT_TEAM_RESULT_INVALID` | A phase reply violated the result contract: fence, JSON, artifact name, summary bound, or declared schema. |
| `EXPERT_TEAM_MODE_UNSUPPORTED` | The team's mode is not orchestrated by this runtime (hierarchical until M3). |

<a id="orchestration"></a>

## Orchestration and gates

### Pipeline mode

The orchestrator executes phases serially in declaration order — the backward-only `depends_on` rule makes declaration order a topological order — even where the DAG would allow parallelism. Starting a run requires non-empty input, mints the branded `runId` (`run-<compact UTC instant>-<8 hex>`, a single path segment), creates `<artifactsDir>/<runId>/`, and mirrors the run state to `run-state.json` at every commit point.

Per phase, the runtime derives or reuses the session `expert-team-<runId>-<phaseId>` with the run directory as its durable cwd. The system prompt composes the persona section (frontmatter facts plus the body verbatim) and one section per declared pack skill; the first user message is the phase briefing: the run request, the phase's `input` descriptor, the upstream artifact paths to read, the handoff checklist, and the output contract. The expert has no write tool by design: it writes the artifact as its reply body and closes the reply with one fenced `json` result block.

The result contract pins the result object `{ artifactPath, summary, openQuestions? }`: `artifactPath` must equal the declared artifact name, `summary` is a non-empty Chinese summary of at most 8 KiB, and the artifact body is at most 256 KiB. When the phase declares a schema, the result object must satisfy it (JSON Schema draft-07; every violation is reported at once so one revision can fix them all). A violation re-drives the same session with a revision message; after at most 2 retries the phase fails with the last detail recorded. Only a passing reply is persisted — the host writes the artifact atomically with exactly one trailing newline — so a parked failure never leaves a half-accepted artifact.

Gate flow:

1. A gate-declaring phase parks `gate-pending` after a valid artifact write; the run status becomes `waiting-approval`.
2. `expert_team_approve` records `{ decision, comment?, at }` on the phase. `approved` marks the phase done and drives the pipeline to the next park point; it additionally delivers a best-effort post-approval followup to the gated phase's session, so the persona's post-acceptance memory note can fire in a real turn — the followup is fire-and-forget, failures are logged by name, and advancing does not block on it. `rejected` re-drives the same session with the comment as revision guidance — a pinned fallback message applies when no comment is given — and re-arms the gate.
3. A failed gate-declaring phase also parks the run at `waiting-approval`: the human cannot approve a failed phase, because nothing accepted exists to pass downstream; a rejection with a comment re-opens it as a guided revision.
4. A failed phase without a gate fails the run (`failed`).
5. Completion marks the run `completed` and disposes its phase sessions; a parked run keeps its sessions so a rejection revises in context.

Every mutating span on a run is serialized through a per-run chain, so concurrent `expert_team_approve` calls cannot interleave transitions or drive the same session twice. A run does not resume in a new process (an M1 scope limit); `run-state.json` keeps the parked story readable. Each rejection is itself an explicit human decision, so reject/revise loops need no numeric bound; the result-contract retry bound of 2 is a fixed invariant of this design, matching the approved blueprint, not a Config field.

### Hierarchical mode

Hierarchical mode is reserved for teams whose phases decompose into dispatched sub-work; the software-development team is the planned consumer (M3). The M1 runtime rejects a hierarchical team fail-loud at run start with `EXPERT_TEAM_MODE_UNSUPPORTED` instead of half-implementing it. The M3 mapping: a phase's owner dispatches lead/worker children under the host's role policy on [dsh-experimental-agent-dispatch](../packages/experimental/agent-dispatch/README.md) and [agent-hierarchy](../packages/experimental/agent-hierarchy/README.md), phase ordering rides task dependencies, and a phase completes when its dispatched child settles, inheriting the existing dispatch completion-gate semantics. No pack uses this mode before M3.

### Trust model

Expert artifacts are `observed`: useful context, never authority. The recorded human decision is the trust anchor, isomorphic to the memory design's rule that confirmed status requires a direct human source. The executor enforces gate blocking and approval recording — a gated phase parks until a decision is recorded, and approval is refused where nothing accepted exists — while decision provenance, that a human actually spoke, is prompt-pinned: the pinned global usage section teaches the model its place: when a run parks, the decision is the reviewer's, not the model's — ask the human, then `expert_team_approve` with their decision and their own words as the comment, and never paraphrase a gate as finished. Every decision is recorded with decision, comment, and timestamp in run state, and the session log carries everything model-visible, so the recorded story is reconstructable; binding a decision to a human-verified channel is the documented M2 hardening path (a capability-level approval seam). Pack content (personas, `team.yml`, schemas, skill text) is quoted data; it never registers tools, permissions, or checks by itself.

<a id="tools"></a>

## Model tools and configuration

| Tool | Input | Behavior and output |
| --- | --- | --- |
| `expert_team_list` | None. | Lists mounted packs: team id, title, mode, entry, each expert's `name`/`role`/tools, and each phase with dependencies, artifact, and gate. |
| `expert_team_run` | `team`, `input` — the free-form run request the entry phase consumes, for example the research topic. | Starts a run and returns its snapshot at the first park point (`waiting-approval`, `completed`, or `failed`). |
| `expert_team_status` | `run_id`. | The run snapshot: status, per-phase status with attempts, artifact references, failure detail, and recorded reviews. |
| `expert_team_approve` | `run_id`, `decision` (`approved`/`rejected`), optional `comment` carrying the reviewer's own words. | Records the decision on the parked gate and applies the transition; on rejection the comment becomes the revision guidance. |
| `consult_expert` | `team`, `expert`, `question`. | One bounded answer (`{ answer, truncated }`) outside any run: a fresh single-turn session with the same persona and allowlist composition, disposed after; no artifacts, no run state. |

`expert_team_run`, `expert_team_status`, and `expert_team_approve` return the same frozen run snapshot, rendered as canonical JSON — the same shape the orchestrator mirrors into `run-state.json`. Run statuses are `running`, `waiting-approval`, `completed`, `failed`; phase statuses are `pending`, `running`, `gate-pending`, `done`, `failed`.

Configuration is a validated Cordis plugin Config that fails loud at activation:

```yaml
packs:
  - ./packages/experimental/expert-pack-paper
artifactsDir: ./research-artifacts
```

| Field | Contract |
| --- | --- |
| `packs` | `string[]`, required, at least one entry; each a clean path to an existing pack directory, validated at load. |
| `artifactsDir` | `string`, required; the artifacts root, resolved against the process working directory when relative. A run writes under `<artifactsDir>/<runId>/` and never outside it. |

The plugin is a function plugin (`name`/`inject`/`Config`/`apply`) named `expert-team`: it validates config, loads the catalog (every pack problem fails the load), provides `ctx.expertTeam`, registers the five tools and the static usage section, and its disposal removes the tools, the section, the service, and every derived session. The `runId` is a branded opaque id whose mint format is an invariant; parsing a model-supplied id is a shape check — an unknown but well-formed id fails the lookup with `EXPERT_TEAM_RUN_UNKNOWN`.

<a id="packs"></a>

## Team packs

### Paper team

The paper team implements the staged research workflow. Phases 1-4 ship in the first milestone; phases 5-8 are declared here and marked deferred.

| # | Phase id | Expert | depends_on | Artifact | Result schema | Gate | Milestone |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `perspective-discovery` | `topic-scout` | — (entry) | `perspectives.md` | — | — | M1 |
| 2 | `literature-review` | `literature-reviewer` | `perspective-discovery` | `survey.md` | `survey-summary.schema.json` | `human-review` | M1 |
| 3 | `idea-selection` | `idea-selector` | `literature-review` | `research-questions.md` | `research-questions-summary.schema.json` | `human-review` | M1 |
| 4 | `method-design` | `method-designer` | `idea-selection` | `method.md` | — | — | M1 |
| 5 | Experiment execution | deferred | `method-design` | deferred | deferred | deferred | M2 |
| 6 | Paper writing | deferred | experiment execution | deferred | — | — | M2 |
| 7 | Three-pass review | deferred | paper writing | deferred | deferred | deferred | M2 |
| 8 | Revision | deferred | three-pass review | deferred | — | — | M2 |

Phase jobs: `topic-scout` surveys several research perspectives from the topic, and `perspectives.md` controls the depth and breadth of later questioning (STORM). `literature-reviewer` retrieves and reads literature; every claim carries a citation, and `survey.md` includes a gaps analysis (PaperQA2) — the survey result schema requires per-claim citations, making the citation discipline machine-checkable; its gate confirms the survey direction with a human. `idea-selector` distills 2-3 candidate research questions from the gaps, each with a novelty argument and risks (AI-Researcher); its result schema requires the open questions the gate must weigh, and its gate has the human select the topic. `method-designer` produces the experiment design, datasets, baselines, and metrics in `method.md`.

The reviewer also carries the project-memory tools and records a best-effort note per accepted survey, tagged with the research topic as the entity anchor; an unconfigured memory reports `MEMORY_UNAVAILABLE` and the phase continues without a note. Guaranteed per-artifact recording belongs to the core and lands in M2.

### Software-development team (M3 outline)

The software-development team is design-only in this document; its pack and the hierarchical runtime land in M3. The outline: a PM drafts a PRD (gate: human confirmation); an architect turns it into a design document; a tech lead decomposes the work into a task DAG; engineers implement in hierarchical mode, reusing the agent-dispatch completion gate and hierarchy roles; QA tests; a final review is gated on human acceptance. Its artifacts are DSH-native rather than run-directory files: the PRD and the design document write into the project's `docs/`, and decomposed tasks bind to the project goal. That integration is the M3 design work; this outline fixes the direction, not the contract.

<a id="testing"></a>

## Testing strategy

Evidence follows the [testing policy](testing.md): prefer the real implementation, prove behavior at the shipping entry path, and keep opt-ins out of shipped defaults.

| Tier | Covers |
| --- | --- |
| REAL-composition | Boot a test-only composition (a fixture pack in a temporary directory) through the Loader: the five tools appear, a run executes phases through real derived sessions, artifacts land under the configured `artifactsDir` with `run-state.json` mirroring, and approve/reject flows run end to end. Mock only the model backend. |
| Unit | Every `EXPERT_TEAM_*` validation case (one invalid pack per code), the backward-only `depends_on` rule, result-contract splitting and bounds, gate transitions including the failed-phase approval rejection, the retry bound (re-driving stops at 2 retries), and config validation. |
| Snapshot | Explicitly deferred: recording a scenario requires a provider key, and none is recorded for M1. Interim model-visible coverage is carried by the REAL-composition spec, which drives the same five tools — a run with a gate pause, approve and reject flows, and a consult — through a mock model adapter. |

Gate semantics take a real path: the approve/reject flow is exercised end to end in the REAL-composition tier, not against a stubbed orchestrator. Expert persona quality is not machine-tested; the snapshot tier, once recorded, pins stable model-visible text only.

<a id="milestones"></a>

## Milestones

| Milestone | Scope | Primary evidence |
| --- | --- | --- |
| M1 | Core package (catalog, pipeline orchestration, gates, five tools) and the paper pack's phases 1-4, with run-state mirroring. Memory recording is best-effort through the reviewer's own tools; guaranteed per-artifact recording is deferred by design — the session log and `run-state.json` keep runs reconstructable in the meantime. | REAL-composition, unit; the snapshot tier is deferred (recording needs a provider key). |
| M2 | Paper pack phases 5-8; core-level project-memory recording of phase artifacts with the entity tag naming the run's subject (the project name; for a paper run, the research topic), alongside the automatic workspace anchor. | Same tiers, plus recording the deferred snapshot tier with the memory-recording scenario. |
| M3 | Software-development team pack on hierarchical mode over agent-dispatch and agent-hierarchy, with DSH-native artifacts (PRD and design document into project `docs/`, tasks into goal binding). | Same tiers plus dispatch-composition evidence. |
| M4 | Hardening and release readiness: multi-pack composition evidence, measured token/KV effects, the cross-process resume decision, run-history observability, and projection of the user-facing guide. | Budget and observability evidence per the testing policy. |

## Dev Note

This document formalizes the approved expert-team blueprint; the implementation packages mirror the structure and conventions of [dsh-experimental-project-memory](../packages/experimental/project-memory/README.md). The documented choices are deliberate: phase sessions derive through the agent registry's scoped-create face with pack skills as prompt sections, because a pipeline phase needs a persona-scoped session, not a delegation or dispatch binding; M1 memory is the reviewer's best-effort note while guaranteed recording lands in M2; the result-contract retry bound is a fixed invariant; and a parked run does not resume in a new process. The cited external projects are mechanism sources, not code to vendor.
