---
description: "Paper-research data pack for the expert-team plugin: ten Chinese-primary expert personas, a ten-phase human-gated pipeline with parallel review and revision, acceptance handoff checks, review skills, and phase-result JSON Schemas mounted through the core's Config.packs."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-pack-paper

English | [中文](README.zh.md)

## Summary

`dsh-experimental-expert-pack-paper` is a pure data pack for the `dsh-experimental-expert-team` core — expert personas, a pipeline definition, review skills, and JSON Schemas, with no code. Mounting this directory through the core's `packs` config gives a deployment the paper-research team: `topic-scout` expands one research topic into distinct research perspectives; `literature-reviewer` produces a citation-disciplined survey with a gaps analysis; `idea-selector` distills candidate research questions; `method-designer` turns the human-selected question into an executable experimental design; `experimenter` records reproducible experiment results; `writer` drafts the paper; three reviewers independently check methodology, statistics, and writing; and `writer` prepares a revision plan from their reports. Human gates sit after the survey, after question selection, and after the revision plan: expert output is observed data and human approval is the trust anchor. Artifacts land under a run directory of the core's `artifactsDir`.

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
| `experiments` | `experimenter` | `method-design` | `experiments.md` | — |
| `writing` | `writer` | `experiments` | `draft.md` | — |
| `review-methodology` | `reviewer-1` | `writing` | `review-methodology.md` | — |
| `review-statistics` | `reviewer-2` | `writing` | `review-statistics.md` | — |
| `review-writing` | `reviewer-3` | `writing` | `review-writing.md` | — |
| `revision` | `writer` | all three reviews | `revision-plan.md` | `human-review` |

A rejected gate returns the artifact to the owning expert with the reviewer's comments for revision; the phase personas verify their handoff checks before accepting upstream artifacts. Eight phases return structured result objects validated by their corresponding schemas under [`schemas/`](schemas/); `perspective-discovery` and `method-design` are the two schema-less phases. The three review phases depend independently on `draft.md`, and `revision` consumes all three reports before the final human gate.

### Skills and memory

The [review-checklist skill](skills/review-checklist/SKILL.md) and the reviewer-specific skills are the structured disciplines the personas load when checking upstream artifacts or self-checking a delivery. Memory anchoring rides the project-memory entity design: `literature-reviewer` records one bounded note after the accepted survey, and `experimenter` records one bounded reproducibility note after experiments, both tagged with the research topic as the entity tag. This remains best-effort: not mounting the memory plugin fails this pack's mount loud with `EXPERT_TEAM_TOOL_MISSING`, while a mounted-but-unconfigured vault makes the memory tools report `MEMORY_UNAVAILABLE` and the phase continues without a memory note.

-----

<a id="understand-the-pack"></a>
## Understand the pack

<details>
<summary>Pack internals — click to expand</summary>

A pack is a directory contract, not a library: the core's catalog loader reads these files at load time, and every phase composes its subagent request from them at run time.

| Path | Role |
|---|---|
| [`team.yml`](team.yml) | The pipeline: team id and title, mode, entry phase, and the ten phases with dependencies, inputs, artifacts, schema references, supersedes links, and gates |
| [`experts/topic-scout.md`](experts/topic-scout.md) | Perspective discovery persona (STORM borrowing) |
| [`experts/literature-reviewer.md`](experts/literature-reviewer.md) | Citation-disciplined survey persona (PaperQA2 borrowing); carries `memory_append` |
| [`experts/idea-selector.md`](experts/idea-selector.md) | Research-question selection persona (AI-Researcher borrowing) |
| [`experts/method-designer.md`](experts/method-designer.md) | Experimental design persona |
| [`experts/experimenter.md`](experts/experimenter.md) | Reproducible experiment persona; carries `memory_append` |
| [`experts/writer.md`](experts/writer.md) | Evidence-bounded paper drafting and revision persona |
| [`experts/reviewer-1.md`](experts/reviewer-1.md) | Methodology review persona |
| [`experts/reviewer-2.md`](experts/reviewer-2.md) | Statistical review persona |
| [`experts/reviewer-3.md`](experts/reviewer-3.md) | Writing and claim review persona |
| [`schemas/survey-summary.schema.json`](schemas/survey-summary.schema.json) | Draft-07 validation of the literature-review result object |
| [`schemas/research-questions-summary.schema.json`](schemas/research-questions-summary.schema.json) | Draft-07 validation of the idea-selection result object |
| [`schemas/experiments-summary.schema.json`](schemas/experiments-summary.schema.json) | Draft-07 validation of the experiments result object |
| [`schemas/draft-summary.schema.json`](schemas/draft-summary.schema.json) | Draft-07 validation of the writing result object |
| [`schemas/review-summary.schema.json`](schemas/review-summary.schema.json) | Draft-07 validation of each review result object |
| [`schemas/revision-plan-summary.schema.json`](schemas/revision-plan-summary.schema.json) | Draft-07 validation of the revision result object |
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

The pack registers no tools, prompt sections, or session events of its own; the core's four tools — `expert_team_list`, `expert_team_run`, `expert_team_status`, and `expert_team_approve` — are the only model-visible additions and are owned by the core package. `expert_team_run` also accepts `expert` plus `question` for a bounded consultation outside a run. During a run, each phase's subagent request carries the persona body of the phase expert verbatim (Chinese-primary), references to the upstream artifacts, and its phase result schema; the `tools` frontmatter allowlist bounds the subagent's callable tools.

#### Token effect

Zero while no run is active. During a run, each phase request adds its persona (a few KiB), the upstream artifact references, and its result schema where declared; each phase result and each accepted memory note appends a bounded JSON after the reusable prefix.

#### KV Cache effect

Pack files are static, so within a phase the persona and schema sit in the stable request prefix and artifact content appends behind them. Editing any pack file changes what later runs compose and starts a new prefix for the affected requests; across runs in different sessions there is nothing to reuse.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits are current pack constraints, not a task backlog.

- **The pack is data only.** Orchestration, gate approval, schema validation, and memory recording are owned by the expert-team core; the pack cannot run alone, and its execution evidence lives in the core's catalog tests against this pack.
- **Serial execution of the declared DAG.** The three review phases are independent in the data contract, but the core currently executes all phases in declaration order rather than concurrently; parallel review is a future performance optimization.
- **Citation discipline is prompt-enforced.** The survey schema requires citation entries but cannot verify that the sources exist or that claims match them; a literature index behind the reviewer is deferred.
- **Memory recording is best-effort.** `literature-reviewer` and `experimenter` carry the memory tools: not mounting the memory plugin fails the pack's mount with `EXPERT_TEAM_TOOL_MISSING`, while a mounted-but-unconfigured vault degrades to `MEMORY_UNAVAILABLE` and no note, reported honestly; guaranteed per-artifact memory writes belong to the core.
- **Chinese-primary personas.** Persona bodies pin model behavior in Chinese while schema descriptions are English; a deployment wanting English-first personas must fork the pack.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
