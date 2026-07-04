# Context Noise Governance And Automation Plan

Lifecycle state: Draft active planning record

Plan status: Accepted as the noise-control layer for automated context
management. Not yet an implementation claim.

Reader: DevFrame and RDCode maintainers designing high-frequency workflows
where agents need useful context by default without being distracted by stale,
irrelevant, over-broad, or misleading material.

Post-read action: design context automation so every serious run can explain
what context was selected, what was excluded as noise, why the selection was
safe enough, and how a later gate can verify that claim.

Related docs: [Context Management Architecture Plan](context-management-architecture-plan.md), [Model Knowledge Gap Governance Plan](model-knowledge-gap-governance-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md)

## Purpose

High-frequency agent use fails when the user must manually curate context for
every run.

It also fails when the system blindly retrieves everything that looks related.
Long chat history, old plans, stale evidence, irrelevant logs, and semantically
similar but answer-irrelevant search results can all distract a model.

The target is an automated context management flow that performs reduction
before generation:

```text
select less, select better, label authority, record omissions, verify later
```

This plan defines the noise-control layer inside that flow.

## External Lessons

Current agent tools and research point in the same direction:

| Source | Lesson for DevFrame |
|---|---|
| OpenHands context condenser | Older conversation history should be summarized while preserving goals, progress, critical files, and recent exchanges. Condensation must be visible, not hidden magic. |
| aider repo map | Large repositories need structural maps and relevance ranking, not whole-repo stuffing. |
| Continue context providers | Context should come from explicit providers such as files, code, diffs, issues, docs, or custom sources. |
| Cline Memory Bank | Persistent memory works better when split into active context, progress, decisions, and project facts instead of one expanding transcript. |
| Letta archival memory | Long-term memory should usually be queried on demand; it should not be pinned into every prompt. |
| LlamaIndex postprocessors and rerankers | Retrieval should include filtering and reranking after initial recall. |
| Lost in the Middle and context-rot research | Bigger context windows do not guarantee better use of information. Signal position and density matter. |
| RECOMP, LLMLingua, and RAPTOR | Compression and hierarchical summaries can reduce burden on the model, but they need source references and cannot replace original evidence. |
| Self-RAG and distracting-passage research | Retrieval itself can introduce harmful distractors. The system must decide when to retrieve, what to retrieve, and when retrieved material should be rejected. |

The product lesson is simple: DevFrame should not only find context. It should
protect the model from bad context.

## Noise Taxonomy

Use four first-class noise categories.

| Noise type | Examples | Risk |
|---|---|---|
| Project noise | obsolete plans, temporary exports, old review packs, generated archives, unrelated status docs | model treats historical or disposable material as current authority |
| Conversation noise | failed approaches, early brainstorming, outdated user assumptions, model summaries from before a decision changed | model follows stale discussion instead of current contract |
| Retrieval noise | semantically similar but answer-irrelevant docs, duplicated chunks, stale API docs, old competitor pages | model anchors on misleading external or local material |
| Execution noise | long logs, stack traces, repeated test output, noisy diffs, unrelated terminal state | model optimizes for the loudest text instead of the governing fact |

Noise is not the same as irrelevance. Some noisy material is useful as evidence
of a failure or historical trace. The point is to label its role before the
model uses it.

## Core Decision

Automated context management must include a noise gate before dispatch.

The flow should be:

```text
Intent
  -> Context Need Profile
  -> Candidate Source Pool
  -> Noise Filter
  -> Authority And Freshness Ranking
  -> Budgeted Context Packet
  -> Context Ledger
  -> Agent Execution
  -> Acceptance Gate
  -> Evaluation And Learning Feedback
```

This is not a new phase-one top-level object. In phase one, noise decisions are
represented inside `Artifact(kind=context_snapshot)`, `Evidence`, and
`Decision` rationale.

## Automated Context Flow

### 1. Intent And Profile

The router identifies the task type and selects a context profile.

Examples:

| Profile | Default sources |
|---|---|
| `review` | reviewer index, changed artifacts, evidence manifest, final report, relevant status docs |
| `code` | target files, symbol map, tests, project rules, recent failures |
| `research` | current web or paper sources, local planning docs, knowledge-gap checklist |
| `release` | release boundary, diff, gates, deployment notes, rollback plan |
| `planning` | master plan, relevant active plans, contradiction matrix, open decisions |

The profile decides what is normally required, optional, forbidden, and
expensive.

### 2. Candidate Source Pool

The system gathers candidates from structured providers:

- task request and acceptance criteria;
- active planning docs;
- stable runtime docs;
- selected source files and symbols;
- tests and recent failures;
- evidence manifests and reviewer indexes;
- project memory records;
- web or paper sources when a knowledge-gap trigger fires.

Candidate collection is broad enough to avoid missing obvious context. It is
not the prompt.

### 3. Noise Filter

The filter classifies each candidate:

```text
include
include_as_background
include_as_negative_example
exclude_as_stale
exclude_as_duplicate
exclude_as_disposable_export
exclude_as_unrelated
exclude_as_sensitive
exclude_as_low_authority
```

Every exclusion that could affect the result should be recorded in the ledger.
Routine duplicate removal can be aggregated.

### 4. Authority And Freshness Ranking

Included material is ranked by:

- source authority: stable doc, active plan, evidence record, memory, chat,
  external source;
- freshness: current, recent, historical, stale or unknown;
- task relevance;
- decision impact;
- evidence strength;
- recency only after authority is known.

Recent chat should not outrank a current governing document merely because it is
recent.

### 5. Budgeted Assembly

The context packet is assembled under a budget:

- top: goal, constraints, current authority, acceptance criteria;
- middle: selected source and evidence with compact excerpts;
- bottom: risks, omissions, assumptions, handoff instructions.

Critical instructions should not be buried in the middle of a long prompt.

### 6. Ledger And Replay

The context ledger records:

- selected profile;
- candidate source counts;
- included items;
- excluded item classes;
- high-impact exclusions;
- freshness warnings;
- compression trace;
- source hashes or stable references;
- unresolved gaps.

The ledger lets a reviewer ask: "Did the model fail because the context was
wrong, noisy, stale, or missing?"

### 7. Gate And Learning

The acceptance gate checks whether the run used a valid context packet and
whether final claims rely on excluded, stale, missing, or uncited context.

Evaluation then records context-related failure patterns such as:

- relevant source omitted;
- stale plan treated as current;
- disposable export treated as source of truth;
- long log distracted the model from a failing gate;
- retrieval introduced a semantically related distractor;
- model cited memory as authority without source references.

Repeated patterns may create improvement proposals for context profiles,
filters, summaries, or regression fixtures. They do not automatically rewrite
default policy.

## Context Packet Additions

The context packet should add these fields when the noise gate exists:

```text
context_profile
candidate_source_summary
noise_filter_policy
included_context
background_context
negative_examples
forbidden_context
excluded_context_summary
high_impact_exclusions
authority_ranking
freshness_ranking
distractor_risk
compression_trace
selection_rationale
ledger_ref
```

The first implementation can keep values small. The important behavior is that
the model receives selected context, while reviewers receive the selection
record.

## High-Frequency Defaults

For real daily use, the system needs defaults that do not require constant
human approval.

Default automatic actions:

- ignore known disposable exports;
- prefer active planning docs over historical handoffs;
- prefer stable runtime docs over chat summaries for runtime claims;
- include current task goal and acceptance criteria;
- include governing project rules;
- include relevant changed files or symbol maps for code tasks;
- include evidence manifests for review tasks;
- classify old memory as background unless refreshed;
- deduplicate repeated logs and summaries;
- warn, rather than ask, when low-risk optional context is omitted.

Human attention is required only when:

- required context is missing;
- two current authority sources conflict;
- sensitive or private material would enter the packet;
- a high-impact source is excluded and the task cannot safely continue;
- the workflow wants to promote a new default filter or context profile.

## Phase-One Boundary

Phase one should not build a full memory platform, vector database, or
self-improving context engine.

The review-first kernel only needs to prove:

1. a context snapshot can include noise-filter fields;
2. a fixture with stale or irrelevant context can be blocked or warned;
3. a fixture with a disposable export treated as authority fails;
4. a final claim cannot cite excluded context as proof;
5. context-related failures can become evaluation observations or improvement
   proposals without changing defaults.

## Stop Lines

Stop and revise if:

- the system optimizes for maximum retrieved context instead of useful context;
- summaries replace source references;
- conversation history becomes authority without adoption;
- old handoff files override current planning records;
- memory entries are treated as proof without freshness and source scope;
- context filters silently hide high-impact omissions;
- automatic learning changes context defaults without evidence and decision.

## Working Thesis

The high-frequency value of RDCode and DevFrame is not that the model sees more.

It is that the model works inside a cleaner, sharper, auditable context lane:

```text
less accidental context, more governed signal
```
