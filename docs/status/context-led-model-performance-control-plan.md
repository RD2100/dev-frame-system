# Context-Led Model Performance Control Plan

## Purpose

This document turns the context-management discussion into a document-driven development plan for improving model performance inside DevFrame.

Reader: a future maintainer who needs to decide what to build after the context-management plan, without treating "better prompt" or "larger context window" as the whole solution.

Post-read action: classify each model-performance improvement as one of the layers below, then implement the smallest slice that makes model work more bounded, auditable, and comparable.

Related docs: [Context Management Architecture Plan](context-management-architecture-plan.md), [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md)

## Starting Point

DevFrame already has several useful foundations:

- a runtime event journal for recording work;
- a team runtime for multi-agent activity;
- a workflow engine for plan -> execute -> review runs;
- project memory and user preference storage;
- methodology skills;
- evidence manifests, gate results, execution reports, and final verdict schemas;
- a dashboard and visual-state read model;
- a paper-oriented context layer with privacy filtering, metadata filtering, keyword scoring, top-k retrieval, and retrieval traces;
- planning documents for workflow consolidation and context management.

These foundations are real. The problem is that they are not yet governed by one model-performance control loop.

## Critical Assessment

### What Is Strong

DevFrame is strongest where it forces proof:

- evidence-first acceptance;
- runtime records instead of chat-only claims;
- schemas for reports and gates;
- read-only dashboard projections;
- fail-closed privacy behavior in the paper context layer;
- project-local skills that can package repeatable methodology.

This gives the project a good base for model performance because performance here means more than output quality. It means the model can be checked.

### What Is Weak

The current system still leaves too much to the model runtime:

- context is not always planned before work starts;
- memory entries are too thin to express freshness, source references, or verification status;
- retrieval exists, but mainly as a paper/RAG implementation rather than a general control-plane service;
- workflows can run without a standard context packet;
- acceptance gates can judge evidence, but do not yet verify whether the model received the right context;
- dashboard views show state, but not enough about context quality, token budget, missing context, or stale references;
- model comparisons can be unfair if each model receives a different hidden or compressed context.

The main architectural risk is duplication: adding a new context manager in control-plane without reusing the existing context-layer lessons would create another parallel subsystem.

## Target Model

Model performance should be controlled through eight layers.

| Layer | Question | Desired Control |
|---|---|---|
| Context Selection | Did the model receive the right material? | Context packet, required/omitted/missing context |
| Context Noise Control | Was stale, misleading, duplicated, disposable, or low-authority material filtered before dispatch? | Noise gate, excluded-context summary, authority and freshness ranking |
| Freshness | Is the material still trustworthy? | Freshness labels and verification status |
| Task Shape | Is the work sized correctly? | Intent profile, shard boundary, acceptance criteria |
| Tool Feedback | Can the model check reality? | CodeGraph, tests, probes, evidence readers, package audits |
| Memory Governance | What becomes durable memory, and which memory may influence the current task? | Source-backed, dated, scoped, conflict-checked entries with retrieval evaluation |
| Output Contract | Does the model know what done means? | Structured report, reviewer index, gate result, final verdict |
| Model Routing | Is the right model doing the right job? | Profile-driven model/provider selection and fair comparison |

Context management is the first layer, not the only layer.

Noise control is part of that layer. A larger context window can make a model
slower, more expensive, and less reliable when low-authority or distracting
material crowds out governing facts.

## Design Principle

DevFrame should make model work externally controllable.

That means every serious run should answer:

1. What was the goal?
2. What context was selected?
3. What context was missing or intentionally omitted?
4. What tools were available?
5. What evidence was produced?
6. What memory was updated, if any?
7. What gate accepted or blocked the result?
8. Did every compared model receive equivalent context?

If the system cannot answer these questions, the run may still be useful, but it should not be treated as a strong acceptance result.

## Relationship To Existing Plans

The workflow consolidation plan defines the public command shape:

- `/rdcode`
- `/rdtest`
- `/rdpaper`
- `/rdreview` or `/rdaccept`
- `/rdrelease`
- `/rdview`

The context-management plan defines the pre-dispatch context packet and context ledger.

This plan defines the wider performance-control loop around those pieces.

In short:

- workflow consolidation decides how the user enters the system;
- context management decides what the model sees;
- model performance control decides how DevFrame keeps the whole run bounded, testable, and comparable.

## Proposed Control Loop

Every serious workflow should follow this loop:

1. **Intent**
   Classify user intent and risk. Select a command profile.

2. **Context**
   Build a context plan and context packet. Mark required, retrieved, omitted, and missing context.

3. **Budget**
   Allocate token budget by purpose: goal, source, evidence, memory, risks, output contract.

4. **Dispatch**
   Send the packet path and profile to the worker, not only free-form prompt text.

5. **Execution**
   Let the worker use tools, but require real-path evidence for claims.

6. **Recording**
   Record context packet ID, worker profile, tools used, evidence paths, and generated reports.

7. **Gate**
   Check artifact reality, test evidence, context sufficiency, stale references, and report consistency.

8. **Distillation**
   Save only durable lessons into project memory. Do not store transient logs as long-term memory.

9. **View**
   Show current status, context warnings, missing evidence, next action, and final verdict in dashboard/read-model surfaces.

## Development Roadmap

### Phase 1: Planning Alignment

Keep the current work as documentation-only. Align the workflow, context, and performance-control plans.

Exit criteria:

- the three documents can be read together without contradictory architecture;
- reviewer index points to all three planning documents;
- the next coding slice is obvious and small.

### Phase 2: Context Packet Schema

Create schemas for context packets and context ledgers.

Exit criteria:

- a context packet can represent goal, selected profile, required context, retrieved context, omitted context, missing context, freshness, source references, evidence references, and token budget;
- a ledger can record context assembly events without depending on a specific model provider.

### Phase 3: Minimal Context Packet Generator

Add a non-executing generator that builds packets from explicit inputs.

Exit criteria:

- `/rdreview` or an equivalent internal command can generate a packet for a package review;
- the generated packet is human-readable and schema-valid;
- malformed or missing context produces warnings instead of silent success.

### Phase 4: Runtime Integration

Connect packet IDs to workflow and team-runtime events.

Exit criteria:

- every recorded worker run can show the context packet it received;
- dashboard/read-model output can expose context packet path, freshness warnings, and missing-context warnings;
- dispatch can pass context packet paths to workers.

### Phase 5: General Retrieval Interface

Extract the paper context-layer lessons into a general retrieval interface.

Exit criteria:

- privacy filtering, metadata filtering, keyword scoring, top-k selection, and retrieval trace are available as reusable concepts;
- paper remains a domain template, not the owner of the global context system;
- code/test/review workflows can retrieve source docs, evidence, and memory through the same pattern.

### Phase 6: Acceptance Gate Expansion

Teach the gate to judge context quality as part of acceptance.

Exit criteria:

- final PASS is blocked when required context is missing without explanation;
- stale or unverified memory cannot support a final acceptance claim;
- reports that cite evidence not present in the context/evidence ledger are downgraded.

### Phase 7: Model Comparison Fairness

Make context packets first-class in test/evaluation workflows.

Exit criteria:

- public-test model comparisons can prove that competing models received equivalent context packets;
- scoring reports include context quality and evidence quality, not only final output quality;
- hidden provider-side compression is treated as a risk, not as a trusted evaluation condition.

## Immediate Next Slice

The next implementation slice should be deliberately small:

1. define `context_packet` and `context_ledger` schemas;
2. add a minimal context packet builder with no automatic retrieval;
3. write tests that prove missing required context is represented explicitly;
4. expose the generated packet path in one prepare-only workflow;
5. document that automatic retrieval is a later phase.

This slice avoids the trap of building a large RAG platform before DevFrame has a stable contract for context.

## Design Constraints

- Do not store secrets, cookies, raw browser profiles, or sensitive transcripts in context packets.
- Do not treat compressed summaries as proof.
- Do not silently ignore malformed context inputs in serious workflows.
- Do not make paper/RAG code the global context architecture by accident.
- Do not require a vector database for the first version.
- Do not let each model provider decide context lifecycle independently.
- Do not use context size as the main quality metric.

## Evaluation Metrics

Useful metrics for later development:

- required-context coverage;
- stale-reference rate;
- missing-context warning rate;
- citation-backed claim rate;
- duplicate-context ratio;
- token budget spent on useful context versus noise;
- worker rediscovery rate after packet assembly;
- acceptance failures caused by context loss;
- model-comparison fairness across equivalent packets;
- memory entries written with source and freshness metadata.

## Review Checklist

Before implementing a model-performance feature, ask:

1. Does it improve context selection, freshness, task shape, tool feedback, memory governance, output contract, or model routing?
2. Does it reuse existing runtime, evidence, memory, or context-layer assets?
3. Does it make the run more auditable?
4. Does it reduce hidden model/provider behavior?
5. Does it help dashboard or reviewer surfaces explain what happened?
6. Does it avoid creating another top-level workflow?
7. Can it fail closed when context or evidence is missing?

If the answer is mostly no, the feature is probably complexity rather than performance control.

## Working Thesis

Model performance in DevFrame should be improved by controlling the conditions of model work.

The goal is not to make every prompt longer. The goal is to make every serious run smaller, sharper, fresher, better tooled, better recorded, and harder to overclaim.
