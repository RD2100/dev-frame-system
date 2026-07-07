# Runtime Governance And Evidence Closure Transformation Plan

Lifecycle state: Draft active plan

Reader: DevFrame maintainers implementing the next control-plane architecture slices

Post-read action: Execute the phased migration from fragmented run records to one fail-closed runtime and evidence lifecycle, starting with the contract-only slice

Related docs: [Workflow Consolidation and Command Plan](workflow-consolidation-and-command-plan.md), [Context Management Architecture Plan](context-management-architecture-plan.md), [Context-Led Model Performance Control Plan](context-led-model-performance-control-plan.md), [Documentation Management Detailed Rollout Plan](documentation-management-detailed-rollout-plan.md)

Promotion target: `docs/agent-runtime/runtime-governance.md` after the first complete vertical workflow proves the contracts

## Purpose

This plan defines the next architecture step after skill management, workflow
consolidation, context management, and documentation governance.

It is deliberately grounded in the current repository. DevFrame already has
useful dispatch, runtime, evidence, review, schema, test, and read-model
components. The problem is not a lack of components. The problem is that the
components do not yet form one authoritative lifecycle from user intent to a
governance-owned final verdict.

This document is an implementation plan, not a claim that the target runtime
already exists.

## Current Execution Status

Update date: 2026-07-08.

The initial Batch A "Immediate Next Slice" in this plan has been superseded by
later local implementation audits. Batches A through D now have public contract,
RunIndex, prepare-only review, and independent evidence-gate records. Batch E
has also advanced through workflow review-pending behavior, explicit team
evidence and context references, review/final-verdict reference projection,
manual @go finalizer guidance, chain-evidence schema compatibility, FinalVerdict
lifecycle metadata, and fail-closed ai-workflow-hub chain evidence
classification.

Recent completed public-snapshot slices have kept the Batch E evidence visible,
kept preserved stop lines explicit, and prevented future agents from treating
stale Batch A planning language as the next implementation target. That
reconciliation has now been followed by read-only FinalVerdict supersession
projection, bounded supersession-chain projection, and chain resolution
diagnostics. The next implementation slice must choose one of the remaining gaps
explicitly; it is still not automatic runtime finalization by default.

Still out of scope without a separate bounded implementation slice:

- generic `go` dispatch automatic finalization;
- sealed ContextPacket or ContextLedger production beyond current provenance
  references;
- paper or ai-workflow-hub domain adapters and canonical normalization;
- automatic superseding FinalVerdict generation for divergent reruns;
- runtime storage migration or dashboard authority changes.

The preserved stop line remains: terminal status, file shape,
`next_commands.finalize`, worker success, and projection status must not create
acceptance authority.

## Executive Recommendation

Do not build another workflow engine, another evidence format, or another
dashboard state model.

Build a thin canonical runtime-governance layer around the primitives that are
already present:

```text
Intent/Profile
  -> Context Packet
  -> TaskSpec
  -> Run Record
  -> Append-Only Events
  -> Artifact and Evidence References
  -> Independent Review
  -> Governance Final Verdict
  -> Read Models
```

The first real vertical slice should be a prepare-only `/rdreview` flow. It is
read-only, directly exercises the evidence-driven acceptance skill, and can
prove the context, evidence, review, and verdict boundaries before coding or
paper execution is migrated.

## Audit Snapshot

Audit date: 2026-07-03.

The assessment used:

- CodeGraph structural inspection of 307 indexed files, 5,454 symbols, and
  11,116 edges;
- direct inspection of the control-plane CLI, rdgoal dispatch, team runtime,
  workflow engine, evidence finalizer, runtime schemas, paper workflow state,
  test-frame surfaces, and visual read model;
- comparison of the root runtime schemas with the copies under test-frame;
- focused verification of the current runtime primitives.

Focused verification command:

```powershell
python -m pytest `
  packages/control-plane/tests/test_rdgoal.py `
  packages/control-plane/tests/test_team_runtime.py `
  packages/control-plane/tests/test_workflow_engine.py `
  tests/test_go_evidence.py -q
```

Observed result: `97 passed in 6.16s`.

This result proves the inspected primitives behave as their tests specify. It
does not prove that they are already connected into the target end-to-end
acceptance lifecycle.

## Current Real Architecture

### Control-Plane Command Surface

The installed package exposes `devframe` and `rdgoal`. The `devframe` router
already supports coding dispatch, recorded workflows, rdgoal, visual state,
sessions, dashboard, Web AI operations, MCP operations, writeback, handoff,
pipeline execution, and evidence-pack validation.

The proposed `/rdcode`, `/rdtest`, `/rdpaper`, `/rdreview`, `/rdrelease`, and
`/rdview` product commands are still planning concepts. They are not yet a
single implemented command family.

### rdgoal Path

The rdgoal path is the strongest existing governance substrate:

```text
CLI
  -> ensure project contract
  -> register project
  -> decision engine
  -> backup/risk guard
  -> dispatch packet and TaskSpec
  -> worker
  -> execution report ingestion
  -> runtime digest
```

Useful existing properties:

- runtime data is kept outside the public repository by default;
- risky target changes can require snapshots;
- dispatch packets have stable packet and project identifiers;
- TaskSpec artifacts are emitted in JSON and Markdown;
- execution reports are ingested and summarized;
- project registration and dispatch decisions are journaled.

Current boundary:

- the packet has no canonical context packet reference;
- report ingestion records worker status but does not complete independent
  review or governance finalization;
- the rdgoal journal and the go/team journal are separate state histories;
- the digest shows decisions and reports, not one canonical run lifecycle.

### go And Recorded Workflow Path

`devframe go` creates resumable multi-agent run metadata and uses TeamRuntime to
record task creation, claim, and result events. `devframe workflow` adds a
recorded `plan -> execute -> review` phase loop.

Useful existing properties:

- target sharding and optional worktree isolation already exist;
- worker execution can be resumed from run metadata;
- events are append-only and stored outside the repository;
- team events are projected into task, agent, conflict, evidence, message, and
  gate read models;
- the workflow path has focused tests for phase and event behavior.

Current boundary:

- the workflow `reviewer` verdict is calculated from worker result statuses;
- the review gate projected by TeamRuntime is also derived from task results;
- therefore a worker success can appear as a review success without a separate
  reviewer artifact;
- workflow verdict terms (`continue`, `revise`, `stop`), worker statuses, task
  statuses, gate statuses, and final-verdict states are not one vocabulary;
- the small standalone state machine is not the authoritative state machine for
  rdgoal, go, workflow, paper, and test runs.

### @go Evidence Path

`devframe atgo` creates an evidence directory and a chain-evidence skeleton.
`tools/go_evidence.py` can validate the required files, reject executor-authored
review roles, block open P0/P1 findings, and write a deterministic final report.

Useful existing properties:

- executor and reviewer roles are separated;
- missing evidence fails closed;
- TDD can require red and green test evidence;
- the finalizer does not make a fresh code-quality judgment;
- tests cover pass, blocked, invalid role, invalid verdict, and missing evidence
  behavior.

Current boundary:

- evidence initialization and go execution are adjacent CLI paths rather than
  one canonical run;
- finalization is a manual follow-up command;
- the final report is Markdown and is not the same artifact as the existing
  machine-readable FinalVerdict schema;
- the richer EvidenceManifest schema is not the artifact emitted by this path;
- the context used by the worker and reviewer is not recorded as a first-class
  run input.

### Paper Workflow Path

The paper workflow has its own Pydantic state, run directory, evidence fields,
human-gate fields, acceptance fields, finalizer, and governance summary.

Useful existing properties:

- domain-specific state is explicit;
- human review and privacy fields already exist;
- run files and final reports are durable;
- the paper path demonstrates why domain extensions are necessary.

Current boundary:

- it is a parallel run model rather than a domain adapter over a shared run
  envelope;
- status and acceptance terms differ from the control-plane terms;
- `summarize_run_governance` previously treated a `passed` or `blocked`
  workflow status as sufficient to set `chain_trusted` when it was not already
  trusted; Batch E removed that fail-open inference and now requires explicit
  boolean chain trust;
- the paper finalizer and the generic evidence finalizer do not share one final
  verdict contract.

### Test-Frame Path

Test-frame has real orchestration, normalizers, aggregation, quality gates,
failure records, and machine-readable verdicts. It also contains copies of
agent-runtime schemas.

Useful existing properties:

- it distinguishes implementation, runtime explorer, full runtime, and code
  review verdicts;
- it is the best candidate for a later `/rdtest` domain adapter;
- it already models blocked results instead of forcing binary pass/fail.

Current boundary:

- its result and verdict model is separate from rdgoal/go/paper run identity;
- copied schemas create an authority and synchronization risk;
- of the root agent-runtime files inspected, 17 copies were byte-identical,
  three differed by encoding or line-ending details, and eight had no peer;
- test results are not automatically linked to a canonical context packet,
  evidence manifest, review record, and governance final verdict.

### Visual And Read-Model Path

The visual state already combines project, session, task, evidence, gate,
message, event, and action projections. It also discovers @go evidence
artifacts.

Useful existing properties:

- the UI/read model can display most target concepts;
- mutation is kept separate from read projections;
- runtime facts can be inspected without putting private runtime data in the
  public repository.

Current boundary:

- the read model folds several storage conventions and sometimes infers facts;
- inferred review gates can look stronger than their source evidence;
- adding more inference to the large visual-state module would deepen the
  problem;
- the view should consume canonical run projections, not become the runtime
  authority.

## Findings And Priority

### P0: Acceptance Authority Is Not Yet Enforced End To End

The repository has schemas and rules that prevent executors from issuing final
verdicts. The recorded workflow path does not yet enforce the same boundary:
its reviewer verdict is derived from worker status.

Required correction:

- worker completion may open a review gate;
- worker completion must never pass the review gate;
- only a validated independent ReviewRecord can pass review;
- only the governance finalizer can create a FinalVerdict.

### P0: Evidence Trust Must Never Be Inferred From Run Status

The paper governance fallback that promotes `chain_trusted` from a terminal run
status must be removed in the first implementation batch touching that module.

Required correction:

- evidence trust comes from explicit chain/evidence validation;
- `passed`, `completed`, or `blocked` are outcomes, not proof of provenance;
- unknown trust stays unknown and blocks final readiness.

### P1: There Is No Canonical Run Identity Across Domains

Current identifiers include packet IDs, go run IDs, paper run IDs, test runs,
review run IDs, sessions, and workflow events. They can be related by paths or
convention, but there is no required parent run envelope.

Required correction:

- define one provider-neutral `run_id` and `project_id` linkage contract;
- retain domain-native IDs as `external_refs` or `domain_refs`;
- do not rename every existing identifier in one migration.

### P1: Status, Phase, Outcome, And Acceptance Are Conflated

The current code uses overlapping terms such as queued, ready, deferred,
planned, running, completed, passed, blocked, failed, continue, revise, stop,
accepted, and final_ready.

Required correction:

- phase answers where execution is;
- outcome answers how execution ended;
- gate result answers whether a check passed;
- acceptance state answers what governance permits the system to claim.

These must be separate fields, not one expanding status enum.

### P1: Context Management Is Planned But Not Implemented

There is currently no canonical context-packet or context-ledger schema and no
runtime builder connected to dispatch. The architecture plans describe the
target correctly, but no serious run can yet prove exactly what context the
worker received.

Required correction:

- implement explicit-input packets before automatic retrieval;
- record packet IDs on TaskSpec and run events;
- block strong acceptance when required context is missing or stale.

### P1: Evidence Components Are Strong But Fragmented

The project has review, safety, chain, gate, execution-report,
evidence-manifest, failure-record, audit-event, and final-verdict contracts.
Different runtime paths consume only subsets of them.

Required correction:

- define one evidence service interface over the existing schemas;
- keep domain evidence files, but index them through one manifest;
- make finalization deterministic and automatic after a valid review arrives.

### P2: Runtime Stores Need A Shared Read Contract, Not Immediate Physical Merger

rdgoal events, team events, go metadata, @go evidence, paper runs, and test
outputs use different directories. Moving everything at once would create high
risk and little immediate value.

Required correction:

- add a canonical run index and adapters first;
- preserve old paths through compatibility readers;
- migrate physical storage only after two domain workflows are proven.

### P2: Schema Copies Need One Authority

Root agent-runtime schemas should be canonical. Package copies should be
generated or verified mirrors, not independently edited sources.

Required correction:

- declare root schema ownership;
- add a semantic synchronization check that normalizes BOM and line endings;
- package canonical schemas during build instead of maintaining hand-edited
  copies where feasible.

### P2: The View Layer Is Carrying Too Much Interpretation

The visual layer is feature-rich but should not infer acceptance authority.

Required correction:

- expose provenance for every projected gate and verdict;
- label inferred/legacy projections;
- move canonical folding into a small runtime read-model service;
- let visual state render that service's output.

## Target Runtime Model

### Core Records

The target should reuse current schemas where possible and add only the missing
contracts.

| Record | Role | Direction |
|---|---|---|
| GoalRecord | User outcome and command profile | Small new contract or extension of project contract/task proposal |
| ContextPacket | Bounded context sent to execution or review | New schema already planned |
| ContextLedger | Append-only context assembly and use events | New schema already planned |
| TaskSpec | Unit of work and execution boundary | Reuse canonical root schema; extend by version |
| RunRecord | Canonical run envelope and links | New small schema |
| AuditEvent | Durable runtime fact | Reuse existing schema and align TeamEvent/JournalEvent envelopes |
| ArtifactRef | Pointer, hash, producer, media type, freshness | Add as a shared definition, not a new artifact store |
| EvidenceManifest | Index and completeness assessment | Reuse existing schema with profiles |
| ReviewRecord | Independent reviewer verdict and findings | Reuse existing review schema |
| FinalVerdict | Governance-owned final claim | Reuse existing final-verdict schema |
| FailureRecord | Classified failure or blocker | Reuse existing schema |

### Separate Lifecycle Axes

The canonical RunRecord should not use one overloaded status field.

```text
phase:
  created | prepared | authorized | dispatched | running |
  verifying | awaiting_review | finalizing | closed

outcome:
  unknown | passed | blocked | failed | cancelled | human_required

acceptance_state:
  not_evaluated | review_pending | final_ready |
  accepted_with_limitation | blocked | failed | deferred
```

Rules:

- phases may skip `authorized` when the selected profile does not require
  explicit runtime authorization;
- `phase=closed` does not imply success;
- `outcome=passed` does not imply acceptance;
- `acceptance_state=final_ready` requires a valid FinalVerdict;
- a blocked run may still have useful artifacts and evidence;
- reopening creates a new attempt or explicit resume event, not silent mutation
  of historical facts.

### Canonical Links

Every serious record should carry the identifiers relevant to its role:

```text
project_id
goal_id
task_id
run_id
attempt_id
context_packet_id
parent_run_id (optional)
domain
profile
producer_role
created_at
```

Existing packet, go-run, paper-run, test-run, session, and provider identifiers
should be retained under structured `domain_refs` during migration.

### Runtime Invariants

1. Runtime authorization is not a quality verdict.
2. Executor completion is not independent review.
3. A read model cannot create new acceptance facts.
4. Missing or corrupt required evidence blocks final readiness.
5. Unknown evidence provenance remains unknown.
6. Every final verdict identifies the reviewed evidence and reviewer record.
7. Every serious run identifies the context packet used by each worker.
8. Append-only events are the audit trail; mutable summaries are rebuildable
   views.
9. Domain workflows may extend state but may not redefine core acceptance
   semantics.
10. Private runtime data remains outside the public repository.

## Proposed Runtime Layout

The long-term layout can be:

```text
<runtime>/
  projects/<project_id>/
    goals/<goal_id>.json
    runs/<run_id>/
      run.json
      task-spec.json
      context/
        packet.json
        packet.md
        ledger.jsonl
      artifacts/
        artifact-index.json
      evidence/
        evidence-manifest.json
        gate-results/
        failure-records/
      review/
        review.json
        review.md
      final/
        final-verdict.json
        final-report.md
      events.jsonl
  indexes/
    runs.jsonl
```

This is a target, not the first migration action. Initial adapters should read
the current `rdgoal-outbox`, `rdgoal-reports`, `go-runs`, `atgo-runs`, team
journal, paper run, and test output locations without moving them.

## Open-Source Reuse Position

The architecture should reuse standards selectively:

- Borrow the common event-envelope idea from the CNCF
  [CloudEvents specification](https://github.com/cloudevents/spec). Do not add a
  broker or CloudEvents SDK merely to write local JSONL.
- Treat [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/)
  as optional observability exports. Traces and logs may explain runtime
  behavior, but they are not governance evidence or acceptance authority.
- Borrow the separation between thread-scoped checkpoints and cross-thread
  durable stores from
  [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
  Do not make LangGraph a prerequisite for the provider-neutral run contract.
- Continue using JSON Schema as the public contract mechanism because the
  repository already has a substantial Draft 2020-12 schema set and tests.

The decision is therefore `reuse concepts and formats now; add dependencies
only when a measured implementation need appears`.

## Phased Transformation

### Phase 0: Authority And Recon Baseline

Goal: make implementation authority explicit before touching runtime behavior.

Actions:

1. complete the documentation-governance Phase 1 header work for active plans;
2. create a new Recon Receipt for runtime-governance unification;
3. inventory every status and verdict token used by rdgoal, go, workflow,
   paper, test-frame, evidence tools, and visual projections;
4. mark root agent-runtime schemas as canonical;
5. record current runtime paths and compatibility requirements.

Expected changes:

- documentation and recon records only;
- no runtime behavior change.

Exit criteria:

- one reviewer can identify the canonical contract owner;
- every existing runtime path has a migration disposition;
- no proposed schema silently invalidates current artifacts.

Hard stop:

- stop if a current public integration depends on an undocumented status or
  path that cannot be represented without data loss.

### Phase 1: Contract-Only Runtime Envelope

Goal: define the missing shared contracts without wiring execution.

Actions:

1. add ContextPacket and ContextLedger schemas;
2. add a minimal RunRecord schema with separate phase, outcome, and acceptance
   axes;
3. define shared identifier and ArtifactRef definitions;
4. add a status-vocabulary mapping document for legacy adapters;
5. add schema fixtures for positive, blocked, stale-context, missing-review,
   and executor-self-review cases;
6. add semantic schema-mirror verification for test-frame packaging.

Expected implementation surface:

- root agent-runtime schemas;
- schema fixtures and schema-validation tests;
- package build or verification helper for mirrored schemas.

Exit criteria:

- all new schemas validate positive and negative fixtures;
- current TaskSpec, EvidenceManifest, ReviewRecord, FailureRecord, and
  FinalVerdict remain valid;
- mirror verification ignores encoding/line-ending noise but detects semantic
  drift;
- no executor role can satisfy a final-verdict fixture.

Hard stop:

- do not start runtime integration while phase/outcome/acceptance mappings are
  ambiguous.

### Phase 2: Canonical Run Index With Legacy Adapters

Goal: create one read-side identity without moving existing runtime files.

Actions:

1. implement a small RunRegistry or RunIndex service;
2. adapt rdgoal packets/reports, go-run metadata, team events, @go evidence,
   paper runs, and test runs into canonical RunRecord projections;
3. record domain-native IDs under `domain_refs`;
4. expose provenance and adapter version on every projected field;
5. make corrupt or incomplete legacy records visible as blocked/unknown, not
   silently skipped.

Expected implementation surface:

- one new focused control-plane module and tests;
- small adapters beside existing domain modules;
- no rewrite of visual state yet.

Exit criteria:

- one query lists runs from at least rdgoal, go, and @go evidence paths;
- every projected value can be traced to a source file or event;
- unreadable records produce FailureRecord-compatible diagnostics;
- old CLI behavior remains unchanged.

Hard stop:

- do not make the registry writable authority until replay and compatibility
  tests prove deterministic projections.

### Phase 3: Prepare-Only `/rdreview` Vertical Slice

Goal: prove the full contract chain without executing code.

Lifecycle:

```text
review intent
  -> explicit-input ContextPacket
  -> TaskSpec
  -> RunRecord
  -> evidence inventory
  -> review request
  -> no final verdict until an independent review exists
```

Actions:

1. add a minimal context builder using explicit files, ZIPs, screenshots,
   rubric, and project rules;
2. route the evidence-driven acceptance skill as methodology metadata;
3. emit context packet JSON and Markdown plus a context ledger;
4. create a prepare-only review run through the canonical registry;
5. expose missing, stale, omitted, and forbidden context explicitly;
6. provide inspect and resume commands without performing external submission.

Exit criteria:

- a real public-test package can be prepared reproducibly;
- two model packages can be shown to have equivalent or intentionally
  different context;
- a missing required screenshot, ZIP, rubric, or source reference is visible;
- prepare-only never produces `final_ready`.

Hard stop:

- no automatic retrieval, browser submission, or live external reviewer in
  this phase.

### Phase 4: Unified Evidence And Review Gate

Goal: connect existing evidence schemas and the deterministic finalizer.

Actions:

1. extract the reusable validation logic from `go_evidence.py` behind a library
   interface while keeping the CLI compatible;
2. generate or validate EvidenceManifest by profile;
3. validate ReviewRecord through the canonical review schema;
4. require reviewer identity and reviewed input references;
5. generate FinalVerdict JSON and a human-readable final report together;
6. record gate and verdict events in the canonical run journal;
7. classify failures as code, model, environment, timeout, human-required, or
   governance failure.

Exit criteria:

- missing reviewer evidence results in blocked acceptance;
- executor-authored review is rejected on the real finalize path;
- open P0/P1 findings block final readiness;
- final JSON and Markdown agree;
- rerunning finalization is idempotent or creates an explicit superseding
  verdict.

Hard stop:

- a finalizer may summarize validated inputs but must not invent a review
  judgment.

### Phase 5: Correct Workflow And Team Runtime Semantics

Goal: make recorded coding workflows use the independent gate.

Actions:

1. change workflow review from worker-status derivation to `awaiting_review`;
2. treat worker results as execution outcomes only;
3. record context packet references on task creation/claim events;
4. record evidence references as explicit events rather than only report-path
   projections;
5. make TeamRuntime project real gate state from review/final-verdict events;
6. retain `continue/revise/stop` only as controller next-action advice, not
   acceptance state;
7. remove the paper run-governance fail-open trust inference.

Exit criteria:

- a passed worker with no review remains review-pending or blocked;
- a failed worker cannot produce a passing gate;
- independent review and final verdict appear as distinct events;
- existing go resume and worktree-isolation tests remain green;
- a real-path regression test demonstrates the former self-approval path is
  now blocked.

Hard stop:

- do not rename or remove legacy CLI commands in this phase.

### Phase 6: Domain Adapters

Goal: move domains onto the shared lifecycle without flattening their useful
state.

Order:

1. `/rdtest` adapter over test-frame;
2. `/rdcode` adapter over go/workflow/rdgoal;
3. `/rdpaper` adapter over PaperWorkflowState and paper run storage;
4. `/rdrelease` only after human authorization and rollback contracts are
   proven;
5. `/rdview` as a read-only command over the canonical registry.

Rules:

- domain state remains in domain extensions;
- core phase/outcome/acceptance meanings remain unchanged;
- domain adapters emit the same core records and evidence links;
- slash commands package user intent; existing internal commands remain
  compatibility and expert surfaces.

Exit criteria:

- at least two domains produce comparable core run records;
- domain-specific fields survive round-trip projection;
- no domain can bypass context, evidence, review, or finalization requirements;
- explicit slash commands and automatic routing select the same profiles for
  equivalent requests.

### Phase 7: Read Model And Observability Alignment

Goal: simplify visual projections after canonical facts exist.

Actions:

1. add a small canonical runtime read-model builder;
2. make visual state consume canonical runs, gates, evidence, reviews, and
   verdicts;
3. label legacy or inferred projections until migration is complete;
4. show selected profile, context freshness, missing evidence, current phase,
   outcome, acceptance, and next safe action;
5. add optional OpenTelemetry export for latency, failures, and phase timing;
6. never use telemetry as evidence of acceptance.

Exit criteria:

- dashboard values can be traced to canonical records;
- the UI cannot turn an unknown or pending gate into pass;
- legacy adapters can be disabled in tests without changing canonical runs;
- observability export can be absent without changing governance behavior.

### Phase 8: Storage Migration And Deprecation

Goal: remove redundant paths only after compatibility is proven.

Actions:

1. measure which legacy stores are still written and read;
2. migrate one path at a time with replay tests;
3. generate package schema copies from the canonical source;
4. deprecate, then remove, duplicate status and finalizer code;
5. promote stable runtime governance documentation out of `docs/status/`.

Exit criteria:

- two releases or equivalent internal milestones have read compatibility;
- no public command depends on removed paths;
- migrated runs retain hashes, timestamps, provenance, and verdict boundaries;
- stable docs describe only the surviving architecture.

Hard stop:

- do not bulk-move runtime directories or rewrite historical evidence.

## Recommended Implementation Batches

### Batch A: Contract Safety

Scope:

- Recon Receipt;
- status vocabulary inventory;
- ContextPacket, ContextLedger, and RunRecord schemas;
- negative fixtures;
- schema mirror check.

Verdict target: `passed` only if no runtime behavior changes and all schema
negative cases fail as designed.

### Batch B: Read-Only Run Registry

Scope:

- canonical run projection;
- rdgoal/go/@go adapters;
- provenance and corrupt-record handling.

Verdict target: `accepted_with_limitation`; write authority remains legacy.

### Batch C: `/rdreview` Prepare Path

Scope:

- explicit context builder;
- review TaskSpec;
- run preparation;
- inspect/resume output.

Verdict target: `accepted_with_limitation`; no external reviewer or final pass.

### Batch D: Independent Gate

Scope:

- EvidenceManifest profile;
- ReviewRecord validation;
- FinalVerdict generation;
- self-approval and missing-evidence real-path tests.

Verdict target: `passed` only with an actual independent reviewer fixture and
deterministic gate evidence.

### Batch E: Workflow Integration

Scope:

- go/workflow/team runtime linkage;
- paper fail-open correction;
- canonical events;
- visual read-model compatibility.

Verdict target: `passed` only when worker success without review remains
non-final.

## Verification Strategy

Each implementation batch must include:

1. schema positive and negative fixtures;
2. unit tests for mappings and state invariants;
3. replay tests for append-only events;
4. compatibility tests for existing CLI outputs and runtime paths;
5. at least one real-path test for every P0/P1 correction;
6. public-snapshot verification;
7. a Reviewer Index with exact changed files, commands, artifacts, gaps, and
   suggested review focus.

Required high-risk scenarios:

| Scenario | Required Result |
|---|---|
| Worker passes, reviewer absent | review pending or blocked |
| Executor authors review | blocked |
| Evidence manifest missing | blocked |
| Context packet missing required source | blocked for strong acceptance |
| Context reference stale or unknown | blocked or accepted with explicit limitation |
| Runtime authorization present, tests absent | not accepted |
| Final report disagrees with FinalVerdict JSON | failed consistency gate |
| Corrupt legacy run | visible failure record, no silent skip |
| Domain adapter reports unknown status | explicit unknown mapping, no pass |
| Replayed events | deterministic read model |

## Success Metrics

Architecture metrics:

- percentage of serious runs with a ContextPacket;
- percentage of runs with one canonical RunRecord;
- percentage of final verdicts backed by an independent ReviewRecord;
- percentage of evidence references with hashes and producer identity;
- number of status vocabularies still interpreted without an explicit mapping;
- number of hand-maintained schema copies;
- number of read-model fields without provenance.

Quality metrics:

- self-approval escape rate: target zero;
- missing-evidence false-pass rate: target zero;
- stale-context false-pass rate: target zero;
- deterministic replay agreement: target 100 percent;
- legacy CLI compatibility during migration: target 100 percent for declared
  supported commands;
- context-equivalence coverage for model comparisons: target 100 percent for
  `/rdtest` comparison runs.

Efficiency metrics:

- manual commands required between execution, evidence, review, and finalization;
- repeated repository discovery after context packet preparation;
- duplicate evidence generation across domain workflows;
- time for a reviewer to locate TaskSpec, context, tests, review, and final
  verdict from a run ID.

## Explicit Non-Goals

This plan does not authorize:

- replacing all runtime stores in one rewrite;
- making LangGraph, Temporal, OpenTelemetry, or an event broker mandatory;
- treating a dashboard as the source of truth;
- automatically accepting worker output;
- silently submitting work to external reviewers;
- storing secrets, cookies, raw browser profiles, or private transcripts in
  context packets;
- moving historical evidence into the public repository;
- implementing every slash command before one vertical slice is proven.

## Open Decisions

These decisions should be resolved in Phase 0 or Phase 1:

1. Should RunRecord use UUIDs exclusively or preserve readable prefixes?
2. Is `attempt_id` required for every resume, or only after terminal outcomes?
3. Should context packets be immutable after dispatch, with amendments recorded
   only in the ledger?
4. Which EvidenceManifest profiles are required for code, test, paper, review,
   and release?
5. Who or what may hold the `governance` producer role in unattended local runs?
6. How long should local event and context records be retained?
7. Which legacy commands are public compatibility commitments versus internal
   development surfaces?

## Current Next Slice

The post-Batch-E status reconciliation and the read-only FinalVerdict
supersession read-model slices are complete at the public snapshot level:

1. this plan no longer treats the original Batch A immediate-next guidance as
   current execution state;
2. the Reviewer Index records the post-Batch-E gaps and review focus;
3. RunIndex projects optional `final_verdict_ref.supersedes` metadata from a
   validated FinalVerdict artifact;
4. RunIndex projects a bounded `final_verdict_ref.supersession_chain` with
   diagnostic `resolution_state` values for resolved, missing, invalid,
   id-mismatch, cycle, and depth-limited historical links;
5. the public snapshot and markdown-safe diff must remain the verification gate
   for follow-up public-surface changes.

The next implementation slice must choose one of the remaining gaps explicitly,
cite the relevant Batch E audit record, and include a real-path regression test
before changing runtime behavior.

Still do not:

- add runtime automation for generic `go` finalization;
- change `chain_trusted` semantics for missing ai-workflow-hub
  `chain-evidence.json` with legacy trusted state;
- create sealed ContextPacket or ContextLedger production;
- normalize ai-workflow-hub `nodes` evidence into the canonical @go schema;
- add paper or ai-workflow-hub domain adapters;
- generate superseding FinalVerdict records automatically;
- treat bounded FinalVerdict supersession chains or their diagnostics as
  acceptance authority;
- expand bounded supersession-chain projection into a complete graph,
  migration surface, or dashboard authority source;
- move runtime files, alter dashboard authority, or issue a new final
  acceptance claim.
