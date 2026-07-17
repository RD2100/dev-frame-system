# Review-First Governance Kernel Contraction Plan

Lifecycle state: Historical contraction plan; scheduling superseded by `HANDOFF.md`

Plan status: Accepted as the near-term narrowing plan under the document-driven
transformation master plan.

Reader: DevFrame maintainers who need to decide what to build next without
reopening broad coordinator, RDCode, model-routing, or memory work.

Post-read action: constrain the next implementation discussion to the
review-first governance kernel, and reject work that does not directly prove
context, run, artifact, evidence, decision, and projection boundaries.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Rules Spec](governance-rules-spec.md), [Governance Contradiction Matrix](governance-contradiction-matrix.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md)

## Purpose

The master plan is intentionally broad. This contraction plan narrows the next
step.

The next slice is not:

- a complete Global Coordinator;
- full RDCode writeback;
- long-term memory;
- model auto-routing;
- platform-wide event sourcing;
- a new dashboard system;
- a large status-folder reorganization.

The next slice is a review-first governance kernel that proves whether DevFrame
can turn a review request into a context-backed run, evidence-backed decision,
and projection-safe status.

## Contraction Decision

Build only the minimum slice that proves this chain:

```text
Project
  -> WorkItem(kind=review)
  -> Artifact(kind=context_snapshot)
  -> Run
  -> Artifact(output)
  -> Evidence
  -> Decision(kind=review)
  -> Decision(kind=gate)
  -> Projection(read-only status)
```

Everything outside that chain is deferred unless it is required to make the
chain truthful, testable, or reviewable.

## Why This Is The Right Narrowing

This slice attacks the highest-risk contradictions first:

| Risk | How the slice addresses it |
|---|---|
| Run success being mistaken for completion | Completion requires a gate decision |
| Report claims replacing proof | Gate decision must cite evidence |
| Context living only in chat | Run must reference a context snapshot artifact |
| RDCode or dashboard owning truth | Projection only displays backend-derived status |
| Coordinator authority being overestimated | No autonomous promotion or high-power mutation is included |
| Evaluation being treated as acceptance | Evaluation is out of scope until the review gate works |

The slice is small, but it touches the platform's core truth boundary.

## In Scope

### Object Fixtures

Create small fixtures or examples for:

- one project;
- one review work item;
- one context snapshot artifact;
- one run;
- one output artifact;
- one evidence record;
- one review decision;
- one gate decision;
- one projection summary.

### Contract Shape

Define enough contract shape to validate:

- required object identities;
- object links;
- allowed decision kinds;
- allowed work item status values;
- context snapshot immutability;
- evidence-to-claim linkage.

### Gate Behavior

Prove these behaviors:

- missing context blocks readiness;
- report-only output produces insufficient evidence;
- run success alone does not complete the work item;
- blocked review remains blocked in projection;
- completed status appears only after a gate decision.

### Projection Behavior

Projection may show:

- work item status;
- run summary;
- artifact summary;
- evidence summary;
- decision summary;
- human-required or blocked reason.

Projection may not:

- mark a work item complete directly;
- invent status independently;
- bypass evidence;
- grant authority to a coordinator, agent, model, or client.

## Out Of Scope

These items are deliberately frozen for this slice:

- broad `/rdcode` workflow redesign;
- full `/rdgoal` replacement;
- persistent Global Coordinator runtime;
- shared blackboard or long-term memory;
- model-provider ranking or auto-routing;
- autonomous learning promotion;
- RDCode full writeback;
- new authorization graph;
- full event-sourcing ledger;
- LangGraph migration;
- large historical document archive.

If one of these appears necessary, the implementer must write a short exception
note explaining why the review-first chain cannot be proven without it.

## Minimum Deliverables

The first implementation package should contain only:

1. kernel fixture definitions;
2. validation or contract checks for the fixtures;
3. a prepare-only review work item flow or equivalent local driver;
4. evidence and decision examples for success, blocked, and insufficient
   evidence;
5. read-only projection output;
6. tests or probes that demonstrate the gate behaviors.

No UI polish, autonomous execution, model comparison, or memory promotion is
required.

## Acceptance Tests To Demand

At minimum, the slice must be able to prove:

| Test | Required result |
|---|---|
| Work item without context snapshot | Not ready or blocked |
| Successful run without review decision | Not completed |
| Review report without evidence references | Insufficient evidence |
| Evidence-backed review failure | Blocked or failed gate |
| Evidence-backed review pass plus gate decision | Completed |
| Projection attempts to mark complete directly | Rejected or impossible by design |

These tests can start as fixture-level tests before becoming full runtime tests.

## Suggested Work Packages

### Package 1: Kernel Fixtures

Define example objects and relationships. This package should not build a new
runtime. It only proves the vocabulary can represent the slice.

Done when: fixtures validate and a reader can trace each object link.

### Package 2: Contract Checks

Add validation rules for required links and forbidden shortcuts.

Done when: invalid fixtures fail for missing context, missing evidence, and
completion without decision.

### Package 3: Review Flow Skeleton

Create the smallest prepare-only flow that emits the objects or records needed
for review.

Done when: one sample review work item can move from draft to reviewing without
claiming completion.

### Package 4: Gate Decisions

Attach review and gate decisions to fixture or skeleton outputs.

Done when: success, blocked, and insufficient-evidence examples produce
different final states.

### Package 5: Projection Summary

Expose or generate read-only projection data from the governance objects.

Done when: projection status is derived from backend facts and decisions.

## Stop Lines

Stop and revise the plan if implementation starts to:

- add new top-level objects;
- make run success complete a work item;
- treat report text as evidence;
- give RDCode or dashboard direct authority;
- implement coordinator autonomy before the review gate;
- add memory, routing, or learning promotion to make the slice look richer;
- rewrite large historical docs as a substitute for proving runtime behavior.

## Handoff Prompt For The Next Implementation Agent

Use this prompt when turning the contraction plan into code work:

```text
Implement only the review-first governance kernel slice for DevFrame.

Read these docs first:
- docs/status/review-first-governance-kernel-contraction-plan.md
- docs/status/review-first-governance-kernel-implementation-spec.md
- docs/status/unified-object-model-decision-record.md
- docs/status/governance-rules-spec.md
- docs/status/document-driven-transformation-master-plan.md

Do not implement broad coordinator autonomy, full RDCode writeback, model
routing, long-term memory, LangGraph migration, or platform-wide event sourcing.

Goal:
Prove this chain with fixtures/contracts/tests:
Project -> WorkItem(kind=review) -> Artifact(kind=context_snapshot) -> Run
-> Artifact(output) -> Evidence -> Decision(kind=review)
-> Decision(kind=gate) -> read-only Projection.

Required negative cases:
- no context snapshot means not ready or blocked;
- run success without review/gate decision is not completed;
- report-only output is insufficient evidence;
- projection cannot directly mark work complete.

Keep changes minimal and public-repo safe. Report exact files changed, tests
run, generated artifacts, known gaps, and review focus.
```

## Completion Criteria

This contraction plan has served its purpose when:

- it is linked from the documentation map, status inventory, master plan, and
  reviewer index;
- implementation work can be split into the five packages above;
- the first package has no reason to touch coordinator autonomy or RDCode
  writeback;
- the review-first chain has passing positive and negative evidence.
