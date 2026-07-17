# Model Knowledge Gap Governance Plan

Lifecycle state: Historical planning record; scheduling superseded by `HANDOFF.md`

Plan status: Accepted as the model-assumption and knowledge-gap layer for the
document-driven transformation plan. Not yet an implementation claim.

Reader: DevFrame and RDCode maintainers designing workflows where model
judgment may be wrong because the model lacks current ecosystem, project,
library, competitor, or evidence context.

Post-read action: treat route, product, architecture, dependency, and acceptance
judgments as knowledge-dependent claims. Require a knowledge-gap check before
those claims can guide implementation or become planning authority.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Context Management Architecture Plan](context-management-architecture-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Competitive Moat And User Demand Critical Review](competitive-moat-and-user-demand-critical-review.md), [Governance Rules Spec](governance-rules-spec.md)

## Purpose

Models often fail not because they cannot reason, but because they reason from
missing, stale, or unverified premises.

The skill-import discussion exposed the pattern. Before checking the current
ecosystem, "import skills" looked like a possible differentiator. After checking
AGENTS.md, Agent Skills, OpenHands Skills, Cline Memory Bank, Continue rules,
Context7, and Hermes-style learning loops, that same capability became table
stakes.

The lesson is broader than skills:

```text
If a judgment depends on current ecosystem reality, project-specific facts, or
recent tool behavior, model common sense is not enough.
```

This plan defines how DevFrame should make that uncertainty explicit.

## External Lessons

| Source | Lesson for DevFrame |
|---|---|
| [AGENTS.md](https://agents.md/) | Agent instructions and project rules are becoming a common standard, not a differentiator by themselves. |
| [Agent Skills](https://agentskills.io/home) and [OpenHands Skills](https://docs.openhands.dev/overview/skills) | Reusable skills and domain prompts are already a known agent pattern. DevFrame should govern when they are enough, stale, missing, or unsafe. |
| [Cline Memory Bank](https://docs.cline.bot/best-practices/memory-bank) | Project memory can reduce repeated context loss, but memory needs freshness and source boundaries. |
| [Continue Rules](https://docs.continue.dev/customize/deep-dives/rules) | Rules and contextual instructions are expected coding-agent capabilities. They must not be mistaken for a moat without evidence-backed governance. |
| [Context7](https://github.com/upstash/context7) | Version-specific documentation retrieval addresses stale model training knowledge. DevFrame should trigger retrieval when library or API freshness matters. |
| RAG and Self-RAG research | Retrieval is needed when parametric knowledge is insufficient, but retrieval should be deliberate and evaluated rather than dumped blindly. |
| Lost-in-the-Middle research | Larger context does not guarantee reliable use. DevFrame must track what was selected and why, not only how many tokens were supplied. |
| Reflexion-style learning | Failure lessons can improve later behavior, but they must remain proposals or evidence-linked constraints until adopted. |

## Core Decision

Model knowledge gaps are a governance concern.

Do not treat a model's confident product, architecture, ecosystem, or acceptance
judgment as ready unless the workflow can answer:

1. What knowledge did this judgment depend on?
2. Which of that knowledge is project-local, external, current, or volatile?
3. Which sources were checked?
4. Which gaps remain unresolved?
5. Is the claim allowed to guide implementation, or must it stay an assumption?

This is not a new top-level object. In phase one, represent the result inside
`Artifact(kind=context_snapshot)` and related evidence or decision rationale.

## Trigger Conditions

A knowledge-gap check is required when a work item involves:

- product positioning or moat claims;
- competitor, open-source, ecosystem, or paper comparisons;
- dependency, framework, library, or API behavior;
- provider/model capability claims;
- project rules, user preferences, or historical decisions;
- security, release, licensing, legal, privacy, or financial risk;
- any claim that would change phase order, object model, stop lines, or
  implementation scope.

It is also required whenever the model says or implies:

```text
This should be a differentiator.
This is standard.
This is safe to defer.
This library/API works this way.
Users probably want this.
The current design is enough.
```

Those statements may be correct. They are not governance facts until checked.

## Phase-One Representation

Do not add `KnowledgeGap`, `Assumption`, or `ResearchTask` as top-level objects
in phase one.

Represent knowledge-gap state through:

- `Artifact(kind=context_snapshot)` payload fields;
- `Evidence` records for checked sources;
- `Decision` rationale when a claim is accepted, blocked, or marked
  insufficient;
- projection warnings for unresolved gaps.

Minimum context snapshot payload fields:

```text
knowledge_gap_assessment
required_knowledge
assumption_claims
checked_sources
resolved_sources
unresolved_gaps
freshness
source_refs
selection_rationale
content_hash
```

The field values can be small in the first fixture. The important property is
that the packet distinguishes verified context from model assumption.

## Acceptance Rules

### KG-001: Knowledge-dependent claims need source refs

If a claim depends on current external reality or project-specific facts, it
must cite source refs before it can support a gate decision.

### KG-002: Table stakes cannot be called moat without competitor evidence

Any product differentiator claim must name what comparable tools already do and
what remains underserved.

### KG-003: Stale or unknown knowledge blocks final claims

If a required source is stale, missing, or unknown, the work item may continue
as exploration, but the final gate must not claim implementation-ready certainty.

### KG-004: Retrieval must be scoped

Knowledge refresh should retrieve what the task needs. Do not dump docs, skills,
memory, or web results into context without selection rationale.

### KG-005: Memory is not authority

Project memory, skills, and prior chat summaries can guide retrieval. They do
not become evidence unless they cite source, freshness, and scope.

### KG-006: External research must be distilled

Web, paper, or competitor findings must be distilled into evidence or a planning
record before they influence the master plan.

## Impact On `/rdreview`

The review-first kernel should not become a research platform.

It should add one small requirement:

```text
The context snapshot must say whether the reviewed claim depends on
project-local knowledge, external-current knowledge, or model assumption.
```

For phase one, that is enough to catch the dangerous case:

```text
The model made a route or acceptance judgment from unverified common sense.
```

Optional later fixtures can show:

- competitor claim blocked until sources are cited;
- dependency/API claim blocked until version-specific docs are checked;
- project-rule claim blocked until current status docs are cited.

## Relationship To User Assets

User workflow assets can reduce repeated knowledge gaps, but they do not remove
the need for knowledge-gap checks.

A skill, prompt, memory bank, MCP config, or evidence recipe may be:

- useful context;
- a retrieval hint;
- a candidate governed asset.

It is not automatically:

- current;
- complete;
- authoritative;
- sufficient evidence.

This is why "import skills" is not a product moat by itself. The moat is knowing
when imported knowledge is enough, when it is stale, and when it cannot support
completion.

## Stop Lines

Stop and revise if:

- a product or architecture claim enters the master plan without source refs;
- a competitor-common feature is described as a differentiator;
- a model capability claim is accepted without current evidence;
- a context snapshot does not distinguish verified sources from assumptions;
- memory, skill, or prompt content is treated as proof without source and
  freshness;
- knowledge-gap handling becomes a new top-level object system before the
  review-first kernel is proven.

## Product Framing

Avoid:

```text
RDCode supports skill import.
```

Prefer:

```text
RDCode helps prevent agents from working from stale or missing knowledge.
```

The user-facing value is:

```text
Do not let AI act from outdated common sense.
Refresh the right context, record what was checked, and block final claims when
knowledge is missing.
```

## Summary

Model information gaps are not a side issue. They are a root cause of poor
product judgment, wrong architecture advice, stale API usage, and false
completion.

DevFrame should not assume the model knows the current world. It should force
important judgments to carry source refs, freshness, unresolved gaps, and
decision consequences.
