# Context Management Architecture Plan

Lifecycle state: Historical plan; scheduling superseded by `HANDOFF.md`

## Purpose

This document records the plan for a DevFrame-owned context management workflow.

Reader: a future maintainer deciding how DevFrame should prepare, budget, retrieve, compress, and verify context before sending work to Codex, OpenCode, Claude, a web AI session, or another agent runtime.

Post-read action: use this plan to design the next implementation slice without relying on model-specific automatic context compression.

Related docs: [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Model Knowledge Gap Governance Plan](model-knowledge-gap-governance-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Context-Led Model Performance Control Plan](context-led-model-performance-control-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md)

## Problem Statement

DevFrame should not depend on whatever a model or client does after the context window is full.

Automatic chat compression is not enough because:

- it is usually not auditable;
- it may drop the exact file, command, or decision that later explains a bug;
- it differs across Codex, Claude, OpenCode, browser-hosted AI, and future providers;
- it makes public-test and multi-model comparisons unfair because each model may receive a different hidden context;
- it can keep stale decisions alive after the project has changed;
- it encourages users to treat a bigger context window as a substitute for context discipline.

The project needs an explicit context workflow that runs before dispatch and produces reviewable context artifacts.

## Research-Informed Direction

External context and memory systems suggest five useful patterns:

1. **Memory hierarchy**
   MemGPT and Letta treat the active prompt as a small working memory backed by larger archival memory. DevFrame should use the same idea: current task context is small, persistent project memory is larger, and evidence remains outside the prompt until retrieved.

2. **Temporal memory**
   Zep and Graphiti emphasize time-aware context graphs. DevFrame needs this because project facts age. A blocker, branch state, provider health result, or reviewer verdict must carry freshness and scope.

3. **Retrieval before stuffing**
   RAG systems such as LlamaIndex show that context should be selected, not dumped. DevFrame should retrieve relevant paths, symbols, evidence, and memories through structured indexes before assembling a packet.

4. **Hierarchical summaries**
   RAPTOR-style recursive summaries are useful for long corpora because they preserve both local detail and higher-level structure. DevFrame should keep task-level, module-level, and project-level summaries separately instead of one giant compressed summary.

5. **Compression with verification**
   Prompt-compression work such as LLMLingua/LongLLMLingua is useful, but compressed text cannot become the source of truth. Compressed context must cite original files, evidence, commands, or memory records.

The most important negative lesson is from long-context evaluation work: a large context window does not mean the model reliably uses the middle of that context. DevFrame should optimize signal placement, not just token volume.

## Target Principle

Every serious workflow should start with a context plan.

The model should receive a bounded `CONTEXT_PACKET`, not an accidental accumulation of chat history, terminal noise, copied files, and prior summaries.

The context plan must also name knowledge gaps. If a task depends on current
ecosystem reality, project-local facts, library behavior, provider capability,
or competitor state, the packet must say what was checked and what remains an
assumption.

The context plan must also control noise. The goal is not to retrieve the most
material. The goal is to give the model a small, current, authority-labeled, and
task-relevant working set while recording what was deliberately excluded.

## Context Layers

DevFrame should manage context in five layers:

| Layer | Purpose | Source of Truth |
|---|---|---|
| Current Task Context | Goal, constraints, targets, acceptance criteria, selected profile | Current user request and router decision |
| Working Set | Relevant code, tests, logs, ZIPs, screenshots, generated reports | Repository, runtime directory, uploaded artifacts |
| Project Memory | Stable conventions, decisions, user preferences, architecture boundaries | Project memory records and status docs |
| Evidence Store | Commands, test output, manifests, reviewer indexes, failure matrices, audits | Append-only or versioned evidence files |
| Retrieval Index | Fast selection over code, docs, memory, and evidence | CodeGraph, text index, vector index, temporal graph |

The active prompt should be treated as a cache assembled from these layers.

## Context Lifecycle

Each `/rd...` command should follow this lifecycle:

1. **Intake**
   Parse the user goal, identify domain intent, profile, risk, and output expectation.

2. **Context Plan**
   Write a small plan that states what context is required, optional, missing, and forbidden.

3. **Budget**
   Assign token budgets by context category before retrieval.

4. **Retrieve**
   Pull only relevant source files, symbols, docs, memories, evidence, and recent runtime state.

5. **Filter Noise**
   Classify candidate context as included, background, negative example,
   duplicate, stale, disposable, sensitive, unrelated, or low-authority.

6. **Assemble**
   Produce a `CONTEXT_PACKET` with stable sections and citations.

7. **Execute**
   Send the packet to the chosen agent or tool. The agent should not freely rediscover the whole project unless the packet says discovery is required.

8. **Record**
   Save a `context-ledger` recording what was included, what was omitted, and why.

9. **Distill**
   After execution, extract only durable lessons into project memory. Do not persist transient logs as memory.

10. **Verify**
   The Acceptance Gate checks whether the context was sufficient, current, and honestly represented.

## Context Packet Shape

The initial artifact can be both JSON and Markdown. The JSON is for machines; the Markdown is for humans and agents.

Minimum fields:

```text
context_packet_id
created_at
project_id
workflow_command
selected_profile
goal
targets
allowed_actions
forbidden_actions
acceptance_criteria
required_context
retrieved_context
omitted_context
missing_context
freshness_notes
context_profile
candidate_source_summary
noise_filter_policy
background_context
negative_examples
forbidden_context
excluded_context_summary
high_impact_exclusions
authority_ranking
freshness_ranking
distractor_risk
knowledge_gap_assessment
required_knowledge
assumption_claims
checked_sources
unresolved_gaps
risk_notes
evidence_refs
memory_refs
memory_scope
memory_authority_level
memory_freshness
memory_limitations
source_refs
token_budget
compression_trace
selection_rationale
ledger_ref
handoff_instructions
```

Every entry that affects a decision should carry a reference. A summary without references is guidance, not evidence.

Knowledge-dependent claims without source refs should be marked as assumptions,
not context facts.

## Budget Policy

Default budget split for non-trivial tasks:

| Category | Suggested Share |
|---|---|
| Goal, constraints, profile, and acceptance | 10% |
| Relevant source/docs | 30% |
| Tests, evidence, and recent runtime state | 20% |
| Project memory and prior decisions | 15% |
| Risk, failure cases, and negative examples | 15% |
| Output contract and handoff instructions | 10% |

This is not a hard formula. It is a forcing function: the assembler must choose, not dump.

## Compression Policy

Use four levels of compression:

| Level | Description | Can Replace Original? |
|---|---|---|
| Inventory | File paths, hashes, timestamps, commands, artifact lists | No |
| Structured Summary | Fixed fields such as what changed, risk reduced, known gaps | No |
| Retrieval Summary | Search-oriented summaries for future recall | No |
| Human Summary | User-facing explanation | No |

No compressed artifact should be treated as proof unless it points back to the original source.

## Freshness Policy

Each memory or evidence reference should be classified:

- `current`: verified in this run or cheap to verify and checked;
- `recent`: likely relevant, but not re-verified in this run;
- `historical`: useful background only;
- `stale_or_unknown`: cannot support acceptance without re-checking.

Acceptance should fail closed when a final verdict depends on stale or unknown context.

## Integration With Slash Commands

The context manager should sit before dispatch:

| Command | Context Packet Focus |
|---|---|
| `/rdcode` | goal, target files, relevant symbols, tests, project rules, acceptance criteria |
| `/rdtest` | test scope, packages under review, failure matrix, scoring rubric, evidence history |
| `/rdpaper` | paper artifacts, privacy boundaries, citation sources, redaction rules, allowed excerpts |
| `/rdreview` or `/rdaccept` | reviewer index, manifests, final reports, command output, known gaps, package audit |
| `/rdrelease` | release scope, changed files, risk register, rollback plan, deployment gates |
| `/rdview` | current state, open gates, next actions, evidence references |

The selected command should not decide by itself what context to include. It should ask the context manager for the correct packet type.

## Integration With Workflow Layers

### Intent Router

The router chooses a profile and asks for a context plan. It should not execute work before the plan exists.

### Dispatch Engine

Go dispatch should receive the context packet path in each TaskSpec. Shards should get shard-specific context plus shared project constraints.

### Team Runtime

TeamRuntime should record context packet IDs and context-ledger paths as real events, so the dashboard can explain what every agent saw.

### Acceptance Gate

The gate should check:

- whether a context packet exists;
- whether required context was included or explicitly missing;
- whether references are current enough;
- whether the agent claims to have used context not in the packet;
- whether final reports cite evidence that was never retrieved.

### View Layer

Dashboard/actions/sessions should show:

- selected profile;
- context packet path;
- context budget summary;
- freshness warnings;
- missing context;
- next safe action.

## Storage Plan

Recommended runtime layout:

```text
<runtime>/
  context/
    packets/
      <context_packet_id>.json
      <context_packet_id>.md
    ledgers/
      context-ledger.jsonl
    indexes/
      text-index/
      vector-index/
      graph-index/
    summaries/
      project/
      module/
      task/
```

Recommended repository assets:

```text
schemas/context_packet.schema.json
schemas/context_ledger.schema.json
docs/agent-runtime/context-management.md
packages/control-plane/control_plane/context_manager.py
packages/control-plane/tests/test_context_manager.py
```

These are planned paths, not current implementation requirements.

## Evaluation Metrics

Context management should be tested with more than token counts.

Useful metrics:

- percentage of cited claims backed by source references;
- stale reference rate;
- missing required-context rate;
- duplicate context ratio;
- prompt token budget used by useful context versus noise;
- high-impact exclusion review rate;
- stale or disposable source leakage rate;
- retrieval distractor rate;
- agent re-discovery rate after packet assembly;
- acceptance failures caused by context loss;
- multi-model fairness: whether different models received equivalent context packets.

## Rollout Plan

### Phase 1: Planning Artifacts

Add this architecture plan and align workflow docs around context as a pre-dispatch layer.

Exit criteria: maintainers can explain where context management sits in the `/rd...` command system.

### Phase 2: Minimal Context Packet Schema

Define `context_packet.schema.json` and `context_ledger.schema.json`.

Exit criteria: a non-executing command can generate a valid packet for a small task.

### Phase 3: Manual Packet Generator

Add a CLI or internal helper that creates packets from explicit targets and evidence paths.

Exit criteria: `/rdreview` and `/rdtest` can use a packet without automatic retrieval.

### Phase 4: Retrieval Connectors

Connect source/docs retrieval through existing project tools such as CodeGraph and text search. Keep vector or graph memory optional.

Exit criteria: packet assembly can cite source files, status docs, evidence files, and memory records.

### Phase 5: Dispatch Integration

Pass context packet paths into go dispatch and TaskSpec. Record packet usage in TeamRuntime.

Exit criteria: every agent run can answer "what context did this agent receive?"

### Phase 6: Acceptance Gate Integration

Require context packet and context ledger checks for serious workflows.

Exit criteria: final PASS cannot be produced when required context is missing, stale, or uncited.

### Phase 7: Domain Templates

Create packet templates for `/rdcode`, `/rdtest`, `/rdpaper`, `/rdreview`, and `/rdrelease`.

Exit criteria: each domain gets context suitable for its risks without inventing a separate context system.

## Non-Goals

- Do not build a universal vector memory platform first.
- Do not store private secrets, browser profiles, raw cookies, or sensitive transcripts as memory.
- Do not treat summaries as proof.
- Do not let each agent runtime invent its own context lifecycle.
- Do not optimize only for maximum context size.
- Do not treat automated retrieval as automatic authority.
- Do not silently hide high-impact omissions from the context ledger.

## Open Questions

1. Should project memory remain file-based first, or should a graph store be introduced early?
2. What freshness threshold should block acceptance for code, tests, paper, and release workflows?
3. Should context packets be immutable after dispatch?
4. How much context should be shared across shards versus customized per shard?
5. Should context compression be deterministic, model-assisted, or hybrid?
6. How should human edits to context packets be represented in the ledger?

## Working Thesis

DevFrame should treat context as a governed resource:

> Plan it before work, budget it before retrieval, filter noise before
> assembly, cite it before execution, record it during dispatch, and verify it
> before acceptance.

The goal is not to make the prompt bigger. The goal is to make the model's working context smaller, sharper, fresher, and auditable.
