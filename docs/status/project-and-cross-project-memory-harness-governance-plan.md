# Project And Cross-Project Memory Harness Governance Plan

Lifecycle state: Draft active planning record

Plan status: Accepted as the memory-governance design direction for project
memory, cross-project memory candidates, and harness-based evaluation. Not yet
an implementation claim.

Reader: DevFrame and RDCode maintainers designing memory features that should
help agents reuse lessons without letting stale, private, or cross-project
assumptions pollute the current project.

Post-read action: design memory as a governed input and output of the harness:
project memory can become authoritative only through source-backed evidence and
decisions; cross-project memory enters as a low-authority candidate until
tested, scoped, and promoted.

Related docs: [Context Management Architecture Plan](context-management-architecture-plan.md), [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Model Knowledge Gap Governance Plan](model-knowledge-gap-governance-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md), [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md)

## Purpose

Memory should reduce repeated work. It should not become an invisible authority
layer.

The project needs two related but separate capabilities:

1. **Project memory**
   Durable knowledge rooted in one project: conventions, decisions, failures,
   evidence recipes, reviewer preferences, and current constraints.

2. **Cross-project memory**
   Reusable lessons learned elsewhere: user preferences, workflow patterns,
   recurring failures, tool behavior, and candidate practices.

These capabilities must be governed by a harness. The harness decides when
memory can be read, written, retrieved, injected into context, evaluated,
promoted, expired, or blocked.

## External Lessons

| Source | Lesson for DevFrame |
|---|---|
| [ChatGPT Projects](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) and [Memory FAQ](https://help.openai.com/articles/8590148-memory-faq) | Project memory and cross-chat memory are product-level concerns. Project-only memory shows that cross-project recall and project isolation must both exist. |
| [Mem0](https://github.com/mem0ai/mem0) and OpenMemory MCP | A shared memory layer can work across tools and clients. DevFrame should learn the portability pattern, but not inherit memories as authority. |
| [Graphiti](https://github.com/getzep/graphiti) and Zep | Temporal knowledge graphs are useful because facts change. Cross-project memory needs provenance, time scope, invalidation, and conflict handling. |
| [Cognee](https://github.com/topoteretes/cognee) | Self-hosted graph memory is useful for persistent recall across sessions, but graph storage does not by itself solve authority, privacy, or promotion. |
| [LangGraph memory](https://docs.langchain.com/oss/python/concepts/memory) and LangMem | Memory should be split by scope and type. Hot-path writing, background consolidation, semantic memory, episodic memory, and procedural memory have different risks. |
| [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/) | Repository knowledge should live in structured docs as the system of record. Agent instruction files are maps, not encyclopedias. |
| [Your harness, your memory](https://www.langchain.com/blog/your-harness-your-memory) | Memory belongs to the harness because the harness owns context, tools, state, and execution traces. Closed or hidden memory creates lock-in and audit risk. |
| [Promptfoo RAG evaluation](https://www.promptfoo.dev/docs/guides/evaluate-rag/) and [harness-evals](https://github.com/harness/harness-evals) | Memory retrieval and memory-influenced outputs must be evaluated separately. A memory system needs explicit metrics and pass/fail thresholds. |

The shared lesson is:

```text
memory is useful only when its scope, source, freshness, and authority are visible
```

## Core Decision

DevFrame memory should be project-owned first and cross-project second.

Default rule:

```text
Project memory may support a project claim when source-backed.
Cross-project memory may suggest context, never finalize authority by itself.
```

Cross-project memory is a candidate signal. It can say:

```text
This looks similar to a prior project.
This failure pattern may apply.
This user usually prefers this workflow.
This tool has failed this way before.
```

It must not say:

```text
This project is complete.
This rule is authoritative here.
This dependency behaves this way now.
This evidence is sufficient.
```

Those claims require current project evidence, context, and decisions.

## Memory Classes

Use these memory classes before choosing storage or retrieval technology.

| Class | Example | Default authority |
|---|---|---|
| Project fact | Current test command, release rule, active architecture boundary | May become authoritative through source and decision |
| User preference | Preferred language, report style, review depth | Personal hint unless scoped and current |
| Failure lesson | "Skill import looked like a moat before ecosystem check" | Candidate constraint or regression case |
| Workflow pattern | Reusable review checklist, evidence recipe, screenshot guide | Candidate user asset until validated |
| Tool knowledge | A CLI flag, provider quirk, Windows encoding issue | Requires freshness and project applicability |
| Policy hint | Prior human decisions about approvals or escalation | Candidate policy input, not policy itself |
| External ecosystem fact | Competitor feature, library behavior, model capability | Must be refreshed before final claims |

## Scope And Authority Matrix

| Scope | Meaning | Default use |
|---|---|---|
| `run` | One execution attempt | Evidence or trace only |
| `work_item` | One task, review, or goal | Context for that work item |
| `project` | One repository or product | Project memory candidate or adopted project fact |
| `user` | User-wide preference or recurring pattern | Low-authority personal hint |
| `org` | Shared organizational convention | Requires stronger adoption and owner |
| `global` | Cross-project default pattern | Deferred until memory harness evaluation exists |

Authority levels:

```text
hint
candidate
validated
adopted
deprecated
blocked
```

Phase one should not create a top-level `Memory` object. Represent memory state
through context snapshot fields, evidence, decisions, and projection warnings
until an independent lifecycle is proven.

## Memory Harness Responsibilities

The memory harness owns six jobs.

### 1. Ingest

Collect possible memory inputs from:

- accepted and blocked runs;
- review reports;
- context ledgers;
- failure records;
- human decisions;
- project documents;
- user-provided assets;
- external research distilled into planning records.

### 2. Propose

Convert raw observations into proposed memory records. Agent-created records
must remain proposed or candidate until reviewed or policy-handled.

### 3. Scope

Classify each memory by project, user, organization, or global scope. If the
scope is uncertain, keep it project-local or candidate-only.

### 4. Retrieve

Retrieve memory only through the context manager. Memory should enter a
`CONTEXT_PACKET` with source references, freshness, scope, and authority level.

### 5. Evaluate

Measure whether memory retrieval helped or harmed. A memory item that is often
retrieved but rarely useful should decay or be deprecated.

### 6. Promote Or Retire

Promote memory only through evidence, review, and policy or adoption decisions.
Retire memory when it is stale, contradicted, private, too broad, or harmful.

## Memory Record Shape

The first schema can be small, but it should preserve these fields:

```text
memory_id
memory_type
scope
authority_level
source_project
source_work_item
source_run
source_refs
source_evidence_refs
created_at
observed_at
freshness
valid_from
valid_until
confidence
allowed_target_projects
blocked_target_projects
redaction_level
privacy_notes
conflict_refs
evaluation_refs
promotion_decision_ref
supersedes
superseded_by
status
```

Do not store secrets, raw private transcripts, browser profiles, cookies, or
sensitive user data as memory records.

## Cross-Project Retrieval Policy

Cross-project memory retrieval must be opt-in by profile, policy, or task risk.

Default behavior:

- project memory may be retrieved for project tasks;
- user preference memory may be retrieved as a personal hint;
- cross-project failure lessons may be retrieved as background;
- cross-project facts must be refreshed before they support final claims;
- project-only or sensitive memories must never cross scope;
- cross-project memories must be labeled as external to the current project.

If a cross-project memory influences a plan, review, or implementation, the
context packet must show:

```text
source_project
why_it_was_retrieved
authority_level
freshness
applicability_notes
unresolved_risks
```

## Memory Evaluation Harness

Memory quality must be tested separately from model output quality.

Minimum evaluation dimensions:

| Dimension | Question |
|---|---|
| Retrieval precision | Were retrieved memories actually useful for the task? |
| Retrieval recall | Did the harness retrieve known required memories? |
| Abstention | Did the harness avoid retrieving memory when none should apply? |
| Isolation | Did project-only or sensitive memory stay inside its scope? |
| Freshness | Were stale or superseded memories downgraded or blocked? |
| Conflict handling | Did conflicting memories surface as conflict instead of one silent answer? |
| Contamination | Did memory from another project distort the current task? |
| Evidence linkage | Could each memory claim be traced to source refs or evidence? |
| Promotion safety | Could agent-created memory become authoritative without review? |

Required negative fixtures:

- cross-project memory presented as project authority;
- stale memory used to pass a gate;
- user preference overriding project rule;
- sensitive project memory retrieved in another project;
- memory without source refs treated as evidence;
- contradictory memories merged without warning;
- agent self-approves a memory promotion.

## Relationship To Existing Governance

### Context Management

Memory is one context source, not the context owner. The context manager decides
whether memory belongs in the packet.

### Context Noise Governance

Old memory is a common noise source. The noise gate should classify memory as
included, background, stale, low-authority, sensitive, or blocked.

### Knowledge-Gap Governance

Memory can suggest that a knowledge gap exists. It cannot close a knowledge gap
unless it cites current enough sources.

### Evaluation And Learning

Memory write proposals should come from observations and failure patterns. They
should not be direct side effects of a successful run.

### Total-Control Policy

The Global Coordinator may use memory to route routine work. It must not use
memory to expand its own authority.

### User Assets

Some memories are reusable workflow assets in disguise: evidence recipes,
review checklists, prompt patterns, and tool notes. They should follow the user
asset governance path before becoming defaults.

## Phase Plan

### Phase 1: Project-Memory Metadata In Context Snapshots

Add small memory metadata fields to context snapshots:

```text
memory_refs
memory_scope
memory_authority_level
memory_freshness
memory_limitations
```

No cross-project memory store is required.

### Phase 2: Project-Local Memory Proposal

Allow accepted, blocked, and failed runs to produce proposed project-memory
records. They remain candidates and do not modify stable project rules.

### Phase 3: Read-Only Cross-Project Hints

Allow cross-project memory retrieval as background hints. Context packets must
label source project, freshness, authority level, and applicability notes.

### Phase 4: Memory Evaluation Harness

Add retrieval, isolation, freshness, conflict, and contamination fixtures.
Measure memory quality before memory can influence defaults.

### Phase 5: Governed Promotion

Permit selected memories to become project, user, or organization defaults only
through evidence, review, and policy or adoption decisions.

### Phase 6: Optional Memory Infrastructure Reuse

Only after the harness exposes a real gap, evaluate Mem0/OpenMemory, Graphiti,
Cognee, LangGraph/LangMem, or another memory backend behind a DevFrame adapter.

## Phase-One Boundary

Phase one must not build:

- a global memory database;
- automatic cross-project writeback;
- hidden personalization;
- a vector memory platform;
- memory-based model routing;
- self-promoting policy memory;
- broad memory UI;
- memory marketplace or sharing system.

The phase-one review kernel may only carry memory references and limitations
inside context snapshots.

## Stop Lines

Stop and revise if:

- cross-project memory supports a final gate without current project evidence;
- memory writes happen as a side effect of agent success;
- user preference weakens project or global rules;
- stale memories are silently treated as current;
- sensitive project memory crosses project boundaries;
- memory backend choice drives the governance model;
- the system hides which memory affected a result;
- memory promotion bypasses evidence, review, or policy.

## Product Framing

Avoid:

```text
RDCode remembers everything across projects.
```

Prefer:

```text
RDCode reuses lessons across projects without letting them silently become
authority.
```

The moat is not bigger memory. The moat is governed transfer:

```text
reuse what helps, isolate what should not cross, test what memory changes
```
