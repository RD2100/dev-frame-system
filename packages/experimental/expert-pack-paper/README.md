---
description: "Paper-research data pack for the expert-team plugin: four Chinese-primary expert personas, a four-phase human-gated pipeline (perspective discovery, literature review, research-question selection, method design), acceptance handoff checks, a review-checklist skill, and phase-result JSON Schemas mounted through the core's Config.packs."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-pack-paper

English | [中文](README.zh.md)

## Summary

`dsh-experimental-expert-pack-paper` is a pure data pack for the `dsh-experimental-expert-team` core — expert personas, a pipeline definition, a skill, and JSON Schemas, with no code. Mounting this directory through the core's `packs` config gives a deployment the paper-research team: `topic-scout` expands one research topic into distinct research perspectives (the STORM discipline of discovering perspectives before controlling question depth and breadth), `literature-reviewer` produces a citation-disciplined survey with a gaps analysis, `idea-selector` distills two or three candidate research questions with novelty arguments and risks, and `method-designer` turns the human-selected question into an executable experimental design. Human gates sit after the survey and after the question selection: expert output is observed data and the human approval is the trust anchor. Artifacts land under a run directory of the core's `artifactsDir`.

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
  - ./packages/experimental/expert-pack-paper
artifactsDir: ./research-artifacts
```

The core validates `team.yml` and the expert files fail-loud at load: unique phase ids, existing expert references, acyclic backward-only `depends_on` lists, entry consistency, existing schema files, and expert tool allowlists that name only mounted tools. A pack that fails validation never half-mounts.

### The pipeline

| Phase | Expert | Depends on | Artifact | Gate |
|---|---|---|---|---|
| `perspective-discovery` | `topic-scout` | — (entry) | `perspectives.md` | — |
| `literature-review` | `literature-reviewer` | `perspective-discovery` | `survey.md` | `human-review` |
| `idea-selection` | `idea-selector` | `literature-review` | `research-questions.md` | `human-review` |
| `method-design` | `method-designer` | `idea-selection` | `method.md` | — |

A rejected gate returns the artifact to the owning expert with the reviewer's comments for revision; `literature-reviewer` and `idea-selector` verify the handoff checks in their frontmatter before accepting an upstream artifact. The `literature-review` and `idea-selection` phases return a structured result object validated by [schemas/survey-summary.schema.json](schemas/survey-summary.schema.json) and [schemas/research-questions-summary.schema.json](schemas/research-questions-summary.schema.json); the two schema-less phases return a free summary beside `perspectives.md` and `method.md`.

### Skills and memory

The [review-checklist skill](skills/review-checklist/SKILL.md) is the structured review discipline the personas load when checking upstream artifacts or self-checking a delivery; `literature-reviewer` and `idea-selector` reference it. Memory anchoring rides the project-memory entity design: the reviewer carries `memory_append` and records one bounded note per accepted survey tagged with the research topic as the entity tag. M1 keeps this best-effort, and the two degradation cases differ: not mounting the memory plugin fails this pack's mount loud with `EXPERT_TEAM_TOOL_MISSING` (the reviewer's allowlist names tools the deployment does not mount), while a mounted-but-unconfigured vault makes the memory tools report `MEMORY_UNAVAILABLE` and the phase continues without a memory note. The remaining phases defer their memory writes to the core.

-----

<a id="understand-the-pack"></a>
## Understand the pack

<details>
<summary>Pack internals — click to expand</summary>

A pack is a directory contract, not a library: the core's catalog loader reads these files at load time, and every phase composes its subagent request from them at run time.

| Path | Role |
|---|---|
| [`team.yml`](team.yml) | The pipeline: team id and title, mode, entry phase, and the four phases with dependencies, inputs, artifacts, schema references, and gates |
| [`experts/topic-scout.md`](experts/topic-scout.md) | Perspective discovery persona (STORM borrowing) |
| [`experts/literature-reviewer.md`](experts/literature-reviewer.md) | Citation-disciplined survey persona (PaperQA2 borrowing); carries `memory_append` |
| [`experts/idea-selector.md`](experts/idea-selector.md) | Research-question selection persona (AI-Researcher borrowing) |
| [`experts/method-designer.md`](experts/method-designer.md) | Experimental design persona |
| [`schemas/survey-summary.schema.json`](schemas/survey-summary.schema.json) | Draft-07 validation of the literature-review result object |
| [`schemas/research-questions-summary.schema.json`](schemas/research-questions-summary.schema.json) | Draft-07 validation of the idea-selection result object |
| [`skills/review-checklist/SKILL.md`](skills/review-checklist/SKILL.md) | The review-checklist skill, shaped like a Claude Code skill |
| [`skills/review-checklist/references/checklist.md`](skills/review-checklist/references/checklist.md) | The checklist items the skill applies |

Expert files are YAML frontmatter plus a Chinese-primary persona body. The frontmatter keys (`id`, `team`, `name`, `role`, `goal`, `tools`, optional `skills` and `handoff-checks`) are the load-time contract, and the `tools` allowlist bounds what the phase subagent may call. The result-object schemas validate `{ artifactPath, summary, citations?, openQuestions? }`: the survey schema requires citations (the citation discipline made machine-checkable) and the research-questions schema requires open questions (what the human gate must weigh); both draft the shared citation shape inline so each schema stays standalone.

### Invariant

No runtime invariant companion is published: the pack is data consumed through the core's catalog loader — the fail-loud guarantees live in the loader's mount-time validation and the run-time result checks, not in a package-local observable relationship.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Expert personas on subagent requests

#### What the model sees

The pack registers no tools, prompt sections, or session events of its own; the core's five tools — `expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`, and `consult_expert` — are the only model-visible additions and are owned by the core package. During a run, each phase's subagent request carries the persona body of the phase expert verbatim (Chinese-primary), references to the upstream artifacts, and the phase result schema for the two schema-gated phases; the `tools` frontmatter allowlist bounds the subagent's callable tools, and `consult_expert` rides the same personas outside any pipeline.

#### Token effect

Zero while no run is active. During a run, each phase request adds its persona (a few KiB), the upstream artifact references, and — for the two gated phases — the result schema; each phase result and each accepted-survey memory note appends a bounded JSON after the reusable prefix.

#### KV Cache effect

Pack files are static, so within a phase the persona and schema sit in the stable request prefix and artifact content appends behind them. Editing any pack file changes what later runs compose and starts a new prefix for the affected requests; across runs in different sessions there is nothing to reuse.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits are current pack constraints, not a task backlog.

- **The pack is data only.** Orchestration, gate approval, schema validation, and memory recording are owned by the expert-team core; the pack cannot run alone, and its execution evidence lives in the core's catalog tests against this pack.
- **M1 pipeline scope.** `team.yml` carries the first four phases; experiments, writing, multi-pass review, and revision are deferred, and no other team pack (software development, M3) exists here.
- **Citation discipline is prompt-enforced.** The survey schema requires citation entries but cannot verify that the sources exist or that claims match them; a literature index behind the reviewer is deferred.
- **Memory recording is best-effort.** Only `literature-reviewer` carries the memory tools: not mounting the memory plugin fails the pack's mount with `EXPERT_TEAM_TOOL_MISSING`, while a mounted-but-unconfigured vault degrades to `MEMORY_UNAVAILABLE` and no note, reported honestly; guaranteed per-artifact memory writes belong to the core.
- **Chinese-primary personas.** Persona bodies pin model behavior in Chinese while schema descriptions are English; a deployment wanting English-first personas must fork the pack.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
