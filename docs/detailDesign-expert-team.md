---
description: Proposed expert-team plugin and data packs: expert catalog, human-gated pipeline orchestration, and the paper team's phased research workflow.
---

# Detailed Design: Expert Team

English | [中文](detailDesign-expert-team.zh.md)

## Summary

This reference specifies the expert-team feature: a mechanism layer that runs multi-expert workflows as persona-scoped sessions derived on the host's agent registry, plus team data packs that describe experts and their phase graph. The core plugin owns catalog loading, orchestration with human gates, and a read-only Host status Remote; each team (paper, software development) is a pack of expert Markdown files, skill directories, a `team.yml`, and result-object JSON Schemas, so a new team needs zero code. Expert output is observed context and the recorded human gate decision is the trust anchor, the same notary model the [memory design](detailDesign-part3.md) applies to confirmed facts. The current checkout contains the paper pack's ten phases, the software-development pack's six hierarchical phases, and the Web status entry.

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
| `UC3` | The user asks one expert a question outside any pipeline. | `expert_team_run` accepts `expert` plus `question`, derives a single-turn session with that expert's persona and tool allowlist, and returns a bounded answer; no run or artifact is created. |
| `UC4` | A deployment mounts an additional team pack. | The catalog picks it up from configuration alone; no core change, and an invalid pack fails loud at load. |

### Functional requirements

| ID | Required behavior |
| --- | --- |
| `FR1` | Load every `<pack>/experts/<expert-id>.md` from the mounted packs; validate the frontmatter contract; fail loud on malformed experts and duplicated pack directories or team ids. |
| `FR2` | Load and validate `team.yml`: unique phase ids, existing expert references, `depends_on` backward-only (acyclic by construction), `entry` consistent, referenced schema files present inside the pack. |
| `FR3` | Execute a run's phases in declaration order; each phase derives one persona-scoped session briefed with the run request, upstream artifact paths, the handoff checklist, and the output contract. |
| `FR4` | Persist an artifact under `<artifactsDir>/<runId>/` only after the phase reply passes its result contract — the fenced JSON result object, and the declared JSON Schema when the phase has one; a contract failure re-drives the same session at most twice, then the phase fails. |
| `FR5` | Park a gated phase after its artifact lands and wait for a human decision; approve resumes the pipeline, reject re-drives the phase with the comment, and every decision is recorded with decision, comment, and time. |
| `FR6` | Expose four model tools: `expert_team_list`, `expert_team_run`, `expert_team_status`, and `expert_team_approve`; consultation is an input form of `expert_team_run`. |
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

- In scope in the current implementation: the core package (catalog, pipeline and hierarchical orchestration, gates, four tools, and the read-only Host status Remote), the paper team's ten phases, the software-development team's six hierarchical phases, and the resident Web status card.
- Deferred: guaranteed core-level per-artifact memory recording, parallel execution of independent DAG phases, the website guide projection, and resuming a parked run in a new process.
- Out of scope: agent-loop changes; a literature index or vector store (revisit only on a measured retrieval problem); cross-team orchestration inside one run; worktree-backed `agent_dispatch` execution for expert phases; any path where the model makes the gate decision instead of relaying the reviewer's.

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
| schemas/<result>.json    |         | four model tools on ctx.tools; read-only status Remote |
+--------------------------+         +-------------------------------+
```

The orchestrator and gates sit on the orchestrator module; the runtime derives sessions and enforces the result contract; the catalog is the only pack reader. Two new packages under `packages/experimental/`:

| Package | Owns |
| --- | --- |
| `@deepseek-ai/dsh-experimental-expert-team` (`packages/experimental/expert-team/`) | The catalog loader and validators, pipeline/hierarchical orchestrator, expert runtime, four model tools, and read-only status gateway; Config `{ packs, artifactsDir }`; provides `ctx.expertTeam` and `ctx.expertTeamGateway`. |
| `@deepseek-ai/dsh-experimental-client-ui-expert-team` (`packages/experimental/client-ui-expert-team/`) | The Web Remote binding and resident read-only sidebar status card; browser-only, no model-visible contribution. |
| `@deepseek-ai/dsh-experimental-expert-pack-paper` (`packages/experimental/expert-pack-paper/`) | The paper team pack: expert files, skill directories, `team.yml`, and result-object JSON Schemas; a pure data package with no runtime code. |

### DSH seam mapping

| Concern | Existing capability | Use |
| --- | --- | --- |
| Phase session | [Agent registry](../packages/core/agent/README.md) scoped-create (`ctx.agents.create`) | One persona-scoped session per phase, named `expert-team-<runId>-<phaseId>`, driven one turn with `followup` plus `whenIdle`; the run directory is the session's durable cwd. Hierarchical phases reuse this seam and then record role/parent bindings through `agentBindings`; they do not allocate worktrees or call `agent_dispatch`. |
| Persona and tool allowlist | Prompt sections + tool restriction | The persona body rides a system-prompt section verbatim; the expert's `tools` list is both a visibility restriction and an execution guard on the derived session. |
| Skills | Pack skill text as prompt sections | A declared pack skill's `SKILL.md` is injected as its own prompt section — pack data resolved at load, not a registry skill entry. |
| Model selection | [agent-default-model](../packages/core/agent-default-model/README.md) | Phase and consultation sessions derive with the deployment's default model; a missing selection fails loud before any session derives. |
| Gate decisions | Recorded reviews | `expert_team_approve` records the reviewer's decision — decision, comment, timestamp — as run state; the pinned usage section obliges the model to relay the human's own decision and words. |
| Memory | [dsh-experimental-project-memory](../packages/experimental/project-memory/README.md) | Pack-owned allowlists decide which experts may search or append. The shipped paper pack gives those tools to `literature-reviewer` and `experimenter`; the development pack gives them to `engineer`. Recording remains best-effort and is skipped honestly when the Vault is unavailable. |
| Run observability | `run-index.json` + Host Remote | The orchestrator mirrors lightweight run metadata to `<artifactsDir>/run-index.json`; the gateway exposes the live process view to Web consumers. The file is an audit mirror, not a recovery source. |
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
| `tools` | Non-empty array allowlist of tool names the phase session may call (max 32 entries); proven at mount — an unmounted name fails with `EXPERT_TEAM_TOOL_MISSING`, and a name of this plugin's own tools (`expert_team_*`) with `EXPERT_TEAM_TOOL_FORBIDDEN` — and enforced at execution. |
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
| `EXPERT_TEAM_EXPERT_MISSING` | A phase or consultation request references an expert id the pack does not define. |
| `EXPERT_TEAM_TEAM_MISSING` | The requested team id is not mounted. |
| `EXPERT_TEAM_PHASE_CYCLE` | A `depends_on` references a non-earlier phase id (forward, self, or unknown). |
| `EXPERT_TEAM_SCHEMA_MISSING` | A referenced schema path escapes the pack, does not exist, or is not a file. |
| `EXPERT_TEAM_SKILL_MISSING` | A declared skill has no `SKILL.md` in the pack, or the file vanished by delegation time. |
| `EXPERT_TEAM_TOOL_MISSING` | An expert allowlist names a tool this deployment does not mount. |
| `EXPERT_TEAM_TOOL_FORBIDDEN` | An expert allowlist names one of this plugin's own tools (`expert_team_*`). |
| `EXPERT_TEAM_MODEL_MISSING` | The deployment provides no default model selection to derive expert sessions with. |
| `EXPERT_TEAM_RUN_UNKNOWN` | The requested run id is malformed or not a live run of this process. |
| `EXPERT_TEAM_GATE_PENDING` | No gate awaits a decision, or an approval targets a failed phase. |
| `EXPERT_TEAM_RESULT_INVALID` | A phase reply violated the result contract: fence, JSON, artifact name, summary bound, or declared schema. |
| `EXPERT_TEAM_MODE_UNSUPPORTED` | A future or otherwise unsupported team mode reaches the runtime. The shipped `pipeline` and `hierarchical` modes are both orchestrated. |

<a id="orchestration"></a>

## Orchestration and gates

### Pipeline mode

The orchestrator executes phases serially in declaration order — the backward-only `depends_on` rule makes declaration order a topological order — even where the DAG would allow parallelism. Starting a run requires non-empty input, mints the branded `runId` (`run-<compact UTC instant>-<8 hex>`, a single path segment), creates `<artifactsDir>/<runId>/`, and mirrors the run state to `run-state.json` at every commit point.

Per phase, the runtime derives or reuses the session `expert-team-<runId>-<phaseId>` with the run directory as its durable cwd. The system prompt composes the persona section (frontmatter facts plus the body verbatim) and one section per declared pack skill; the first user message is the phase briefing: the run request, the phase's `input` descriptor, the upstream artifact paths to read, the handoff checklist, and the output contract. A pack may grant file tools to a phase; the phase writes the declared artifact as its reply body and closes the reply with one fenced `json` result block, while any code edits stay within the run directory and do not replace the result contract.

The result contract pins the result object `{ artifactPath, summary, openQuestions? }`: `artifactPath` must equal the declared artifact name, `summary` is a non-empty Chinese summary of at most 8 KiB, and the artifact body is at most 256 KiB. When the phase declares a schema, the result object must satisfy it (JSON Schema draft-07; every violation is reported at once so one revision can fix them all). A violation re-drives the same session with a revision message; after at most 2 retries the phase fails with the last detail recorded. Only a passing reply is persisted — the host writes the artifact atomically with exactly one trailing newline — so a parked failure never leaves a half-accepted artifact.

Gate flow:

1. A gate-declaring phase parks `gate-pending` after a valid artifact write; the run status becomes `waiting-approval`.
2. `expert_team_approve` records `{ decision, comment?, at }` on the phase. `approved` marks the phase done and drives the pipeline to the next park point; it additionally delivers a best-effort post-approval followup to the gated phase's session, so the persona's post-acceptance memory note can fire in a real turn — the followup is fire-and-forget, failures are logged by name, and advancing does not block on it. `rejected` re-drives the same session with the comment as revision guidance — a pinned fallback message applies when no comment is given — and re-arms the gate.
3. A failed gate-declaring phase also parks the run at `waiting-approval`: the human cannot approve a failed phase, because nothing accepted exists to pass downstream; a rejection with a comment re-opens it as a guided revision.
4. A failed phase without a gate fails the run (`failed`).
5. Completion marks the run `completed` and disposes its phase sessions; a parked run keeps its sessions so a rejection revises in context.

Every mutating span on a run is serialized through a per-run chain, so concurrent `expert_team_approve` calls cannot interleave transitions or drive the same session twice. A run does not resume in a new process (an M1 scope limit); `run-state.json` keeps the parked story readable. Each rejection is itself an explicit human decision, so reject/revise loops need no numeric bound; the result-contract retry bound of 2 is a fixed invariant of this design, matching the approved blueprint, not a Config field.

### Hierarchical mode

The software-development pack uses hierarchical mode. The runtime executes its phases through the same scoped-create seam in declaration/topological order, seeds `parentSession` and `delegationDepth`, and records each controller, lead, or worker in `agentBindings`; a worker resolves the nearest completed lead or controller along the dependency graph as its parent. This establishes a durable role relationship without allocating a worktree or reusing the `agent_dispatch` completion gate. Independent phases remain serial, and the role allowlist remains the primary tool restriction.

### Trust model

Expert artifacts are `observed`: useful context, never authority. The recorded human decision is the trust anchor, isomorphic to the memory design's rule that confirmed status requires a direct human source. The executor enforces gate blocking and approval recording — a gated phase parks until a decision is recorded, and approval is refused where nothing accepted exists — while decision provenance, that a human actually spoke, is prompt-pinned: the pinned global usage section teaches the model its place: when a run parks, the decision is the reviewer's, not the model's — ask the human, then `expert_team_approve` with their decision and their own words as the comment, and never paraphrase a gate as finished. Every decision is recorded with decision, comment, and timestamp in run state, and the session log carries everything model-visible, so the recorded story is reconstructable; binding a decision to a human-verified channel is the documented M2 hardening path (a capability-level approval seam). Pack content (personas, `team.yml`, schemas, skill text) is quoted data; it never registers tools, permissions, or checks by itself.

<a id="tools"></a>

## Model tools and configuration

| Tool | Input | Behavior and output |
| --- | --- | --- |
| `expert_team_list` | None. | Lists mounted packs: team id, title, mode, entry, each expert's `name`/`role`/tools, and each phase with dependencies, artifact, and gate. |
| `expert_team_run` | Either `team`, `input` for a run, or `expert`, `question` with optional `team` for a consultation. | Starts a run and returns its snapshot at the first park point (`waiting-approval`, `completed`, or `failed`), or returns one bounded consultation answer (`{ answer, truncated }`) without creating a run. |
| `expert_team_status` | `run_id`. | The run snapshot: status, per-phase status with attempts, artifact references, failure detail, and recorded reviews. |
| `expert_team_approve` | `run_id`, `decision` (`approved`/`rejected`), optional `comment` carrying the reviewer's own words. | Records the decision on the parked gate and applies the transition; on rejection the comment becomes the revision guidance. |

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

The plugin is a function plugin (`name`/`inject`/`Config`/`apply`) named `expert-team`: it validates config, loads the catalog (every pack problem fails the load), provides `ctx.expertTeam`, registers the four tools and the static usage section, and owns a read-only `ctx.expertTeamGateway` for the Web Remote. Its disposal removes the tools, the section, the services, and every derived session. The `runId` is a branded opaque id whose mint format is an invariant; parsing a model-supplied id is a shape check — an unknown but well-formed id fails the lookup with `EXPERT_TEAM_RUN_UNKNOWN`.

<a id="packs"></a>

## Team packs

### Paper team

The paper team implements the staged research workflow. All ten phases are declared and mounted: perspective discovery, literature review, question selection, method design, experiment execution, writing, three independent reviews, and revision.

| # | Phase id | Expert | depends_on | Artifact | Result schema | Gate | Milestone |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `perspective-discovery` | `topic-scout` | — (entry) | `perspectives.md` | — | — | M1 |
| 2 | `literature-review` | `literature-reviewer` | `perspective-discovery` | `survey.md` | `survey-summary.schema.json` | `human-review` | M1 |
| 3 | `idea-selection` | `idea-selector` | `literature-review` | `research-questions.md` | `research-questions-summary.schema.json` | `human-review` | M1 |
| 4 | `method-design` | `method-designer` | `idea-selection` | `method.md` | — | — | M1 |
| 5 | `experiments` | `experimenter` | `method-design` | `experiments.md` | `experiments-summary.schema.json` | — | M2 |
| 6 | `writing` | `writer` | `experiments` | `draft.md` | `draft-summary.schema.json` | — | M2 |
| 7 | `review-methodology` | `reviewer-1` | `writing` | `review-methodology.md` | `review-summary.schema.json` | — | M2 |
| 8 | `review-statistics` | `reviewer-2` | `writing` | `review-statistics.md` | `review-summary.schema.json` | — | M2 |
| 9 | `review-writing` | `reviewer-3` | `writing` | `review-writing.md` | `review-summary.schema.json` | — | M2 |
| 10 | `revision` | `writer` | all three reviews; supersedes `writing` | `revision-plan.md` | `revision-plan-summary.schema.json` | `human-review` | M2 |

Phase jobs: `topic-scout` surveys several research perspectives from the topic, and `perspectives.md` controls the depth and breadth of later questioning (STORM). `literature-reviewer` retrieves and reads literature; every claim carries a citation, and `survey.md` includes a gaps analysis (PaperQA2); its gate confirms the survey direction with a human. `idea-selector` distills candidate research questions from the gaps, with novelty arguments and risks (AI-Researcher); its gate has the human select the topic. `method-designer` produces the experiment design, datasets, baselines, and metrics in `method.md`. `experimenter` records results, `writer` drafts, three reviewers assess the draft independently, and `revision` prepares the final revision plan from all reports.

`literature-reviewer` and `experimenter` carry the project-memory tools and record best-effort notes after their accepted work, tagged with the research topic as the entity anchor; an unconfigured memory reports `MEMORY_UNAVAILABLE` and the phase continues without a note. Guaranteed per-artifact recording remains outside the core.

### Software-development team (M3 outline)

The software-development team is implemented as a six-phase hierarchical pack: a PM drafts a PRD (gate: human review); an architect turns it into a design document; a tech lead decomposes the work into a task DAG; an engineer implements inside the run directory; QA tests; and a final review is gated on human acceptance. Controller, lead, and worker sessions are recorded through `agentBindings`; the pack does not use worktree-backed `agent_dispatch`, and its declared artifacts remain in the run directory.

<a id="testing"></a>

## Testing strategy

Evidence follows the [testing policy](testing.md): prefer the real implementation, prove behavior at the shipping entry path, and keep opt-ins out of shipped defaults.

| Tier | Covers |
| --- | --- |
| REAL-composition | Boot a test-only composition (a fixture pack in a temporary directory) through the Loader: the four tools appear, a run executes phases through real derived sessions, artifacts land under the configured `artifactsDir` with `run-state.json` mirroring, and approve/reject flows run end to end. Mock only the model backend. |
| Unit | Every `EXPERT_TEAM_*` validation case (one invalid pack per code), the backward-only `depends_on` rule, result-contract splitting and bounds, gate transitions including the failed-phase approval rejection, the retry bound (re-driving stops at 2 retries), and config validation. |
| Snapshot | Explicitly deferred: recording a scenario requires a provider key, and none is recorded yet. Interim model-visible coverage is carried by the REAL-composition spec, which drives the same four tools — a run with a gate pause, approve and reject flows, and the consultation form — through a mock model adapter. |

Gate semantics take a real path: the approve/reject flow is exercised end to end in the REAL-composition tier, not against a stubbed orchestrator. Expert persona quality is not machine-tested; the snapshot tier, once recorded, pins stable model-visible text only.

<a id="milestones"></a>

## Milestones

| Milestone | Scope | Primary evidence |
| --- | --- | --- |
| M1 | Core package (catalog, pipeline orchestration, gates, four tools) and the paper pack's first four phases, with run-state mirroring. Memory recording is best-effort through pack-owned tools. | REAL-composition, unit; the snapshot tier is deferred (recording needs a provider key). |
| M2 | The paper pack's remaining phases: experiments, writing, three reviews, and revision; best-effort memory notes from the literature and experiment phases. | Same tiers; parallel review and guaranteed core-owned recording remain deferred. |
| M3 | Software-development team pack on hierarchical mode with controller/lead/worker bindings through `agentBindings`; phase artifacts remain in the run directory rather than worktree-backed dispatch outputs. | Same tiers plus hierarchy-composition evidence. |
| M4 | Hardening and release readiness: multi-pack composition evidence, the cross-process resume decision, run-history observability, and the read-only Web status entry. Token/KV measurement and website guide projection remain deferred. | Focused composition, observability, and client type evidence; snapshot recording still needs a provider key. |

## Dev Note

This document formalizes the expert-team blueprint and its current implementation status; the implementation packages mirror the structure and conventions of [dsh-experimental-project-memory](../packages/experimental/project-memory/README.md). The documented choices are deliberate: phase sessions derive through the agent registry's scoped-create face with pack skills as prompt sections, hierarchical bindings are recorded without worktree dispatch, memory remains pack-owned and best-effort, the result-contract retry bound is a fixed invariant, run history is an audit mirror, and a parked run does not resume in a new process. The cited external projects are mechanism sources, not code to vendor.
