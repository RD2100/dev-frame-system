# Workflow Consolidation and Command Plan

Lifecycle state: Draft active plan

## Purpose

This document records the current architectural direction for consolidating DevFrame workflows.

Reader: a future maintainer or reviewer who needs to decide whether a workflow should remain user-facing, become an internal module, merge into another flow, or be exposed as a slash command.

Post-read action: use the framework below to review any DevFrame feature surface and classify it as **Code**, **Gate**, **View**, **Adapter**, or **Template**.

## Current Problem

The project has grown several useful workflow surfaces, but too many of them are presented as peers:

- `devframe code`
- `devframe go` / `/go`
- `devframe workflow`
- `rdgoal`
- `go_evidence`
- dashboard / actions / sessions / visual-state
- Web AI intake and review commands
- client / T3 bridge commands
- paper workflow
- test and model-evaluation workflow ideas

Most of these capabilities are valid. The problem is not that they exist. The problem is that they currently compete at the same conceptual level.

The product should not make users choose between internal mechanisms. Users should express goals; DevFrame should choose the safest visible route.

## Existing Workflow Surfaces

### Main Coding Loop

`devframe code` is the daily product entrypoint. It prepares a governed coding run, shows the worker command, can execute later, and records status for review.

Architectural status: keep as the primary user-facing path.

### Go Dispatch

`devframe go` and `/go` prepare or execute parallel coding-agent shards. They create packets, split targets, select workers, and collect execution reports.

Architectural status: keep the capability, but demote it from product workflow to dispatch protocol.

`@go read`, `@go edit`, and `@go risky` should become internal dispatch profiles. Advanced users may still call them explicitly, but ordinary use should not require the user to know them.

### Recorded Workflow Engine

`devframe workflow` records a plan -> execute -> review sequence into the team runtime.

Architectural status: keep as a mode of the main coding loop, not a separate story. It is the recorded form of a governed coding run.

### RDGoal

`rdgoal` owns contracts, controller decisions, backup guard checks, dispatch packets, worker reports, and runtime digest.

Architectural status: keep as the governance substrate. Do not market it as a competing end-user workflow.

### Evidence Finalization

`go_evidence.py` validates evidence files and final reports. The new `evidence-driven-acceptance` skill adds the stronger human-review discipline: do not trust large packages, pretty reports, or final PASS claims unless evidence lines up.

Architectural status: merge these ideas into a single Acceptance Gate layer.

### Control-Plane View

dashboard, actions, sessions, and visual-state all expose the same read model in different forms.

Architectural status: group them as View. They inspect state and present safe next actions; they do not decide whether work is complete.

### Web AI Surface

Web AI commands import sessions, record task intake, submit review packages, record MCP results, and live-check provider behavior.

Architectural status: Adapter. It connects external AI sessions to DevFrame, but should not define the core workflow.

### Client / T3 Bridge

The client and T3 bridge expose DevFrame state through a secondary UI shell.

Architectural status: Adapter plus View. It should remain projection-based: DevFrame is the governance source of truth.

### Paper Flow

Paper work combines privacy gates, citation checks, redaction, Web AI review, and evidence packs.

Architectural status: Domain Template. It should reuse the same dispatch, evidence, and gate layers rather than become a separate architecture.

### Test / Evaluation Flow

Testing, regression, failure matrices, model public-test evaluation, and ZIP evidence review belong together.

Architectural status: Domain Template. It should become a first-class `/rdtest` style workflow, backed by the same Acceptance Gate.

## Target Model

The architecture should be explained with four core nouns and one extension noun:

| Layer | Meaning | Examples |
|---|---|---|
| Code | Do the work | coding, bug fixes, refactors, implementation |
| Gate | Decide whether the work can be trusted | evidence finalization, reviewer verdict, package audit |
| View | Inspect state and next actions | dashboard, actions, sessions, visual-state |
| Adapter | Connect outside systems | Web AI, MCP, T3/RD-Code, provider bindings |
| Template | Domain-specific workflow shape | test, paper, release, evidence review |

This gives a simple rule:

User-facing commands should describe what the user wants to accomplish. Internal modules should describe how DevFrame accomplishes it.

Context management sits before this whole model. Before any Code, Gate, View, Adapter, or Template layer runs, DevFrame should create a bounded context plan and context packet that states what the agent is allowed to rely on. This is captured in `docs/status/context-management-architecture-plan.md` and should become the shared pre-dispatch layer for all serious `/rd...` workflows.

## Slash Command Direction

Slash commands should package user tasks, not internal modules.

Recommended public command family:

| Command | User Meaning | Internal Route |
|---|---|---|
| `/rdcode` | Do coding work: implement, fix, refactor, analyze code | Code loop, go dispatch profiles, optional recorded workflow |
| `/rdtest` | Test, evaluate, compare models, review public-test outputs | Test template plus Acceptance Gate |
| `/rdpaper` | Review papers, citations, redaction, privacy-safe evidence | Paper template plus Web AI adapter and Gate |
| `/rdreview` or `/rdaccept` | Judge whether a delivery is real and acceptable | Evidence-driven Acceptance Gate |
| `/rdrelease` | Package, release, deploy, or prepare handoff | Release template, human confirmation, rollback evidence |
| `/rdview` | Inspect state without executing | Control-plane View |

Commands that should remain advanced/internal:

| Surface | New Role |
|---|---|
| `/go` | Compatibility and expert dispatch entrypoint |
| `rdgoal` | Governance substrate |
| `devframe workflow` | Recorded mode of a code run |
| Web AI commands | Adapter operations |
| dashboard/actions/sessions | View operations |

## Automatic Dispatch Policy

The user should not need to write `@go` in normal use. DevFrame should infer the route and show the decision.

Default routing:

| User Intent | Auto Profile |
|---|---|
| Ask about code or project structure | read-only |
| Modify code or docs | code-edit |
| Run tests or evaluate outputs | test-eval |
| Judge a ZIP, screenshot, or model delivery | evidence-review |
| Paper, citation, redaction, or privacy review | paper-review |
| Deploy, publish, external network, or destructive action | risky-release |

Rules:

1. Automatic dispatch may prepare work.
2. Token-spending execution must be visible.
3. Risky execution must require human confirmation.
4. Network access, deployment, deletion, credential use, and external submission must never be silent.
5. Acceptance review should be on by default after execution.
6. The selected profile should be shown in status, dashboard, and reports.

## Acceptance Gate Direction

The Acceptance Gate should be the common end of all workflows.

Minimum gate questions:

1. Did the agent read the right context?
2. Did it produce real artifacts?
3. Did it run tests, probes, or validation?
4. Did it test bad cases?
5. Do reports, manifests, matrices, and paths agree?
6. Is it connected to the real path, or only to a synthetic lab?

For batch public-test output, the gate must also:

- group by task, model, and latest comparable round;
- avoid scoring by ZIP size or file count;
- check reviewer-index, final report, manifest, verification commands, failure matrix, and zip contents audit first;
- treat final `PASS` as a claim, not proof;
- downgrade packages with invented schema fields, duplicated evidence, hidden manual-only steps, or lab-only coverage presented as production.

## Consolidation Plan

### Phase 1: Naming and Documentation

Use the Code / Gate / View / Adapter / Template vocabulary consistently.

Expected result: new readers no longer see every module as a separate workflow.

### Phase 2: Slash Command Product Layer

Define `/rdcode`, `/rdtest`, `/rdpaper`, `/rdreview`, and `/rdrelease` as user-task commands.

Expected result: users choose domain intent, not internal mechanisms.

### Phase 3: Intent Router

Add a lightweight router that maps natural requests to profiles. Keep explicit slash commands as overrides.

Expected result: `@go` becomes automatic dispatch metadata in normal use.

### Phase 4: Context Packet Layer

Create a shared context manager that prepares, budgets, retrieves, cites, and records context before dispatch.

Expected result: every serious run can answer "what context did this agent receive, what was omitted, and which references were current enough to trust?"

### Phase 5: Unified Acceptance Gate

Connect evidence-driven acceptance into evidence finalization and workflow review.

Expected result: all workflows end with the same pass / blocked / fail discipline.

### Phase 6: Domain Templates

Turn test, paper, release, and evidence-review flows into templates over the same lifecycle:

intake -> plan -> execute -> evidence -> review -> gate -> view

Expected result: new domains can be added without creating another parallel workflow architecture.

### Phase 7: View Alignment

Make dashboard, actions, sessions, and client/T3 projections show:

- selected profile;
- context packet path and freshness warnings;
- current gate;
- evidence paths;
- next safe action;
- manual confirmation points;
- known blockers.

Expected result: the user sees one control plane, not many disconnected views.

## Review Questions For Future Work

When reviewing a new feature or workflow, ask:

1. Is this a user goal, or an internal mechanism?
2. Should it be a slash command, a profile, a gate, a view, an adapter, or a template?
3. Does it duplicate `devframe code`, go dispatch, rdgoal, or the Acceptance Gate?
4. Does it make execution safer, or only add another name?
5. Can it end in the unified gate?
6. Can dashboard/actions show its state without special casing?
7. Is the user's next action obvious?

If a feature cannot answer these questions clearly, it should not become a new top-level workflow.

## Working Thesis

The project should converge on this shape:

> one main way to do work, one common way to verify work, one read model to inspect work, and domain commands that package the common system for specific jobs.

In short:

> `/rdcode` does code, `/rdtest` tests and evaluates, `/rdpaper` handles paper work, `/rdreview` verifies trust, `/rdrelease` handles risky release work. Everything else is a module behind those commands.
