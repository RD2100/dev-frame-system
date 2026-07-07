# Recon Receipt: Runtime Governance Unification

Lifecycle state: Recon receipt for Batch A runtime-governance contracts

This receipt governs the contract-only runtime governance and evidence
unification slice described in
`runtime-governance-and-evidence-closure-transformation-plan.md`.

It does not authorize runtime execution changes, schema adoption, dashboard
authority changes, slash-command routing, automatic retrieval, or final
acceptance claims.

## Target

- user_goal: Continue document-driven DevFrame implementation while preserving
  review, evidence, and public-surface governance.
- target_repo_or_kb: `<repo-root>` public `dev-frame-system` snapshot.
- current_slice_goal: Record the Recon Receipt required before write-capable
  work on runtime, evidence, review gate, and final-verdict unification.
- requested_outcome: A durable receipt that maps existing runtime and evidence
  primitives, records reuse decisions, and unlocks only the next contract-first
  Batch A slice.
- date: 2026-07-07
- planner_agent_id: codex-main

## Resource Map

- repository_roots: `<repo-root>`
- top_level_tree: `.github/`, `docs/`, `packages/`, `rules/`, `schemas/`,
  `scripts/`, `templates/`, `tests/`, `tools/`, root `README.md`,
  `README.zh-CN.md`, `AGENTS.md`, `LICENSE`, `pytest.ini`.
- important_dirs:
  - `packages/control-plane/control_plane/` - current control-plane runtime,
    CLI, governance validators, projection surfaces, and read models.
  - `packages/control-plane/tests/` - public control-plane regression tests.
  - `packages/test-frame/` - test orchestration, aggregation, verdict, and
    evidence utilities that remain a separate domain path today.
  - `schemas/agent-runtime/` - existing root agent-runtime contract schemas.
  - `schemas/examples/review-governance/` - review-governance kernel fixtures.
  - `tools/` - standalone evidence finalizer utilities, including
    `go_evidence.py`.
  - `docs/status/` - current plans, recon receipts, evidence records, and
    release state.
- docs_read:
  - `AGENTS.md`
  - `rules/recon.md`
  - `rules/open-source-reuse.md`
  - `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
  - `docs/status/status-document-inventory.md`
  - `docs/status/reviewer-index.md`
  - `docs/status/recon-receipt-team-runtime.md`
  - `docs/status/recon-receipt-workflow-engine.md`
- examples_read:
  - `schemas/examples/review-governance/success.json`
  - `schemas/examples/review-governance/blocked.json`
  - `schemas/examples/review-governance/insufficient-evidence.json`
  - `schemas/examples/review-governance/missing-context.json`
- packages_apps_modules:
  - `control_plane/rdgoal.py`
  - `control_plane/rdgoal_cli.py`
  - `control_plane/orchestrator.py`
  - `control_plane/dispatch_packet.py`
  - `control_plane/worker.py`
  - `control_plane/go_dispatch.py`
  - `control_plane/team_runtime.py`
  - `control_plane/workflow_engine.py`
  - `control_plane/runtime_store.py`
  - `control_plane/runtime_digest.py`
  - `control_plane/runtime_contract_probe.py`
  - `control_plane/rdreview.py`
  - `control_plane/visual_state.py`
- runtime_entrypoints:
  - `devframe rdgoal`
  - `rdgoal`
  - `devframe go`
  - `devframe workflow`
  - `devframe atgo`
  - `devframe rdreview <work_item_id> <intent>` - prepare-only packet output,
    with no runtime writes.
  - `tools/go_evidence.py`
- ui_entrypoints:
  - `control_plane/dashboard.py`
  - `control_plane/visual_state.py`
  - T3/client projection files, including `client_manifest.py`,
    `t3_adapter.py`, and `t3_bridge_bundle.py`.
- service_entrypoints:
  - `control_plane/mcp_server.py`
  - `control_plane/mcp_live_probe.py`
  - `control_plane/provider_binding_probe.py`
  - `control_plane/web_ai_mcp_recorder.py`
- state_storage_locations:
  - `RuntimeStore` writes `rdgoal-events.jsonl` under the configured runtime
    directory.
  - `TeamRuntime` writes append-only `team-events.jsonl` under the configured
    runtime directory.
  - `go_dispatch` stores run metadata under the configured runtime directory.
  - Paper workflow state and test-frame outputs are separate domain state
    paths today.
  - Public repository state must not receive local runtime journals,
    browser profiles, evidence packs, or generated archives.
- external_integrations:
  - Web AI adapter contracts
  - MCP local server/probe paths
  - ACP/OpenCode integration paths
  - T3/client projection surfaces
  - Optional conceptual references only: CloudEvents-style event envelopes,
    OpenTelemetry-style observability boundaries, LangGraph-style persistence
    separation, JSON Schema contract validation.
- notable_generated_or_vendor_paths:
  - `.devframe-runtime/`
  - `.codegraph/`
  - `.pytest_cache/`
  - `.hypothesis/`
  - build, dist, egg-info, wheel, archive, browser-profile, and evidence-bundle
    outputs.
- license_files_found:
  - `LICENSE`

## Core Concepts

- concepts:
  - runtime governance layer
  - context packet
  - context ledger
  - run record
  - append-only events
  - artifact and evidence references
  - independent review
  - governance final verdict
  - projection/read model
- domain_terms:
  - `TaskSpec`, `DispatchPacket`, `RunRecord`, `EvidenceManifest`,
    `GateResult`, `FinalVerdict`, `ReviewGovernanceKernelPacket`,
    `TeamEvent`, `JournalEvent`
- architecture_style: contract-first adapter layer over existing primitives.
- execution_model: existing domain flows continue to execute separately until a
  later vertical slice proves a canonical run lifecycle.
- session_model: sessions and runs remain represented by existing rdgoal, go,
  workflow, paper, test-frame, MCP, ACP, and Web AI surfaces.
- review_model: executor success must not become independent review or final
  governance acceptance by itself.
- evidence_model: evidence is referenced by durable artifacts and manifests;
  report text is not evidence unless it is attached to a governed artifact.

## Core Data Models

- project/workspace:
  - `project_contract.py`
  - `schemas/project_contract.schema.json`
  - `schemas/review_governance_kernel.schema.json` `project`
- thread/session:
  - `cluster_run.py`
  - `acp_session.py`
  - Web AI binding and conversation records
  - visual-state session projections
- message/event:
  - `RuntimeStore` `JournalEvent`
  - `TeamRuntime` `TeamEvent`
  - OpenCode event ingestion
  - MCP/Web AI recorder events
- tool_call:
  - MCP consent and probe records
  - provider binding probes
  - workflow and go worker command invocations
- terminal_run:
  - `worker.py` command execution reports
  - `go_dispatch.py` worker status records
  - test-frame stage tool runs
- diff/checkpoint:
  - current public release verification records
  - review-governance kernel fixtures and validators
  - future ContextLedger amendments
- review/evidence:
  - `tools/go_evidence.py`
  - `schemas/agent-runtime/evidence-manifest.schema.json`
  - `schemas/agent-runtime/gate-result.schema.json`
  - `schemas/agent-runtime/final-verdict.schema.json`
  - `schemas/review_governance_kernel.schema.json`
- policy/rules:
  - `rules/recon.md`
  - `rules/open-source-reuse.md`
  - `rules/orchestration.md`
  - `control_plane/rules_config.py`
  - `control_plane/policy_escalation_validator.py`

## Status Vocabulary Inventory

This receipt does not normalize status values. It records the current split so
the next schema slice can define mappings instead of guessing.

- `tools/go_evidence.py`: `pass`, `blocked`, `fail`, `escalate`.
- `workflow_engine.py`: phase statuses such as `started`, `completed`, and
  reviewer verdicts `continue`, `revise`, `stop`.
- `schemas/agent-runtime/final-verdict.schema.json`: `final_ready`,
  `accepted_with_limitation`, `blocked`, `failed`, `deferred`.
- `schemas/agent-runtime/gate-result.schema.json`: `pass`, `fail`, `blocked`,
  `warning`, `skipped`.
- `schemas/review_governance_kernel.schema.json`: work item states `draft`,
  `ready`, `running`, `reviewing`, `blocked`, `insufficient_evidence`,
  `completed`, plus projection states `waiting_for_you` and `archived`.
- `packages/test-frame/`: common tool statuses `passed`, `failed`, `skipped`,
  `blocked`.
- `visual_state.py`: projection aliases map many raw statuses into dashboard
  terms such as `pending`, `running`, `completed`, `blocked`, `pass`, and
  `failed`.

Next rule: a later ContextPacket/ContextLedger/RunRecord schema must preserve
domain-native statuses while mapping them into one governance vocabulary. It
must not silently treat worker success as review pass or final readiness.

## Capability Matrix

- rdgoal dispatch and project governance
  - location: `rdgoal.py`, `orchestrator.py`, `dispatch_packet.py`,
    `worker.py`, `runtime_store.py`, `runtime_digest.py`
  - maturity: tested local governance substrate
  - reusable_as_is: partial
  - reusable_with_adapter: yes, as project/task/dispatch substrate
  - not_reusable: as a full final-verdict lifecycle
  - notes: lacks canonical context packet, independent review finalization, and
    shared run identity across other flows.
- go and team runtime
  - location: `go_dispatch.py`, `team_runtime.py`, `workflow_engine.py`
  - maturity: tested append-only team event substrate
  - reusable_as_is: partial
  - reusable_with_adapter: yes, as event journal and workflow phase evidence
  - not_reusable: as final review authority
  - notes: workflow review currently derives verdict from recorded task results.
- @go evidence finalizer
  - location: `tools/go_evidence.py`
  - maturity: useful fail-closed evidence finalizer
  - reusable_as_is: partial
  - reusable_with_adapter: yes, as a validator/finalizer input
  - not_reusable: as the only canonical evidence model
  - notes: output is Markdown-oriented and adjacent to go execution.
- agent-runtime schemas
  - location: `schemas/agent-runtime/`
  - maturity: public contract schema set
  - reusable_as_is: partial
  - reusable_with_adapter: yes, as canonical contract vocabulary inputs
  - not_reusable: until mirrored by semantic tests in Batch A
  - notes: existing schemas include EvidenceManifest, GateResult, FinalVerdict,
    TaskSpec, RunSpec, and related records.
- review-governance kernel packet
  - location: `schemas/review_governance_kernel.schema.json`
  - maturity: tested review-first contract slice
  - reusable_as_is: partial
  - reusable_with_adapter: yes, as authority-boundary precedent
  - not_reusable: as the whole runtime run envelope
  - notes: proves no new top-level governance objects and evidence-first
    completion rules.
- test-frame verdict and quality gates
  - location: `packages/test-frame/`
  - maturity: domain-specific test orchestration and aggregation
  - reusable_as_is: no
  - reusable_with_adapter: yes, as `/rdtest` domain adapter later
  - not_reusable: as shared runtime identity today
  - notes: has separate copied schema and verdict models that require sync
    policy before adoption.
- paper workflow state
  - location: `packages/ai-workflow-hub/`
  - maturity: domain-specific paper workflow substrate
  - reusable_as_is: no
  - reusable_with_adapter: yes, as a future paper domain adapter
  - not_reusable: as generic run lifecycle
  - notes: privacy and human-gate fields must remain explicit.
- visual read model
  - location: `visual_state.py`, `dashboard.py`
  - maturity: useful projection surface
  - reusable_as_is: projection only
  - reusable_with_adapter: yes, after canonical run records exist
  - not_reusable: as source of truth
  - notes: dashboard state must remain derived, not authoritative.

## Reuse Candidate List

- candidate: Existing rdgoal dispatch substrate
  - source: in-repo
  - exact_scope_to_reuse: project contracts, dispatch packets, TaskSpec
    generation, runtime journal, worker report ingestion.
  - expected_adapter_work: add context/run references in later contract slices.
  - blocking_constraints: no independent review or final verdict today.
  - decision: should_adapt.
- candidate: Existing TeamRuntime and workflow events
  - source: in-repo
  - exact_scope_to_reuse: append-only event journal and phase/task evidence.
  - expected_adapter_work: map team events into RunRecord/ContextLedger
    references.
  - blocking_constraints: worker success currently influences review projection.
  - decision: should_adapt.
- candidate: Existing agent-runtime JSON Schemas
  - source: in-repo
  - exact_scope_to_reuse: EvidenceManifest, GateResult, FinalVerdict, TaskSpec,
    RunSpec vocabulary.
  - expected_adapter_work: semantic mirror tests and examples for new Batch A
    schemas.
  - blocking_constraints: status vocabulary and schema authority are split.
  - decision: must_reuse as inputs, not copy blindly.
- candidate: Review-governance kernel packet
  - source: in-repo
  - exact_scope_to_reuse: authority-boundary patterns and negative fixtures.
  - expected_adapter_work: align RunRecord and ContextPacket with existing
    WorkItem, artifact, evidence, decision, principal, and projection objects.
  - blocking_constraints: current packet is review-slice-specific.
  - decision: should_adapt.
- candidate: test-frame aggregation and quality gate model
  - source: in-repo
  - exact_scope_to_reuse: later `/rdtest` domain adapter semantics.
  - expected_adapter_work: status and verdict mapping into canonical run
    envelope.
  - blocking_constraints: separate schema copies and separate run identity.
  - decision: defer implementation, inspect during status-vocabulary inventory.
- candidate: CloudEvents-style envelope
  - source: external conceptual pattern only
  - exact_scope_to_reuse: event metadata shape ideas, not source code.
  - expected_adapter_work: none in this slice.
  - blocking_constraints: no dependency or vendoring approved.
  - decision: conceptual reference only.
- candidate: OpenTelemetry-style observability boundary
  - source: external conceptual pattern only
  - exact_scope_to_reuse: trace/span separation ideas, not runtime dependency.
  - expected_adapter_work: none in this slice.
  - blocking_constraints: not required for Batch A.
  - decision: defer.
- candidate: LangGraph-style persistence separation
  - source: external conceptual pattern only
  - exact_scope_to_reuse: separation of graph execution from persisted state,
    not source code.
  - expected_adapter_work: none in this slice.
  - blocking_constraints: no orchestration rewrite approved.
  - decision: defer.

## Integration Risk Table

- risk: Batch A creates another parallel runtime instead of unifying current
  primitives.
  - type: coupling
  - severity: high
  - mitigation: contract-only schemas must reference existing rdgoal, go,
    workflow, evidence, paper, test-frame, and visual projection boundaries.
  - owner: planner/reviewer
- risk: worker status becomes review pass or final readiness.
  - type: security
  - severity: high
  - mitigation: FinalVerdict and GateResult must retain non-executor signer and
    evidence requirements.
  - owner: governance reviewer
- risk: context packets accidentally persist secrets, raw transcripts, browser
  profiles, or private local runtime state.
  - type: privacy
  - severity: high
  - mitigation: context packets reference redacted artifacts and source refs;
    public snapshot gate continues to reject private markers and generated
    runtime state.
  - owner: implementation worker and reviewer
- risk: status vocabulary mapping hides failures or loses domain nuance.
  - type: correctness
  - severity: medium
  - mitigation: status-vocabulary inventory must precede schema adoption and
    include negative fixtures for missing evidence, blocked review, and
    insufficient evidence.
  - owner: schema worker
- risk: external mature patterns become silent dependencies or vendored code.
  - type: license
  - severity: medium
  - mitigation: use external projects only as conceptual references until a
    separate license/source assessment approves adoption.
  - owner: planner
- risk: dashboard becomes a source of truth.
  - type: ux
  - severity: medium
  - mitigation: visual state remains projection-only until canonical
    RunRecord/ContextLedger artifacts exist.
  - owner: reviewer

## Build-vs-Buy Decision

- must_reuse:
  - `rdgoal` project contract, dispatch packet, TaskSpec, runtime journal, and
    worker report ingestion primitives.
  - `TeamRuntime` append-only event journal.
  - existing root `schemas/agent-runtime/` contract vocabulary.
  - review-governance kernel authority-boundary patterns and fixtures.
- should_adapt:
  - `workflow_engine.py` phase events as RunRecord evidence, not as final
    review authority.
  - `tools/go_evidence.py` fail-closed checks as evidence input.
  - test-frame aggregation and quality gates as later `/rdtest` domain adapter.
  - paper workflow state as later `/rdpaper` domain adapter.
  - visual read model as derived projection only.
- can_spike:
  - CloudEvents-style envelope naming.
  - OpenTelemetry-style trace concepts.
  - LangGraph-style persistence separation.
  - only as design references, with no vendoring or dependency addition.
- must_build_new:
  - minimal `ContextPacket`, `ContextLedger`, and `RunRecord` schemas.
  - positive and negative fixtures.
  - semantic schema-mirror verification tests.
  - status-vocabulary inventory that maps existing terms without erasing
    domain-native states.
- rationale: DevFrame already has tested execution, evidence, event, and
  projection primitives. The missing piece is a thin contract layer that binds
  them without inventing a new executor, dashboard authority, or evidence
  format.

## Unknowns / Questions

- unanswered_items:
  - Should canonical run IDs preserve readable prefixes or use UUIDs only?
  - Is every resume an `attempt_id`, or only resumes after terminal outcomes?
  - Are context packets immutable after dispatch, with amendments only in a
    ledger?
  - Which EvidenceManifest profiles are required for code, test, paper, review,
    and release?
  - Which producer roles may create governance records in unattended local
    runs?
  - Which legacy commands are public compatibility commitments?
- required_verification:
  - Compare current status vocabularies across rdgoal, go, workflow, paper,
    test-frame, evidence finalizer, review-governance kernel, and visual state.
  - Validate future schemas with positive and negative fixtures.
  - Run public snapshot checks after every docs/schema/test addition.
- experiments_needed:
  - prepare-only ContextPacket fixture
  - append-only ContextLedger amendment fixture
  - minimal RunRecord fixture proving worker success is not final acceptance
  - negative fixture for missing independent review evidence

## Recommended Next Slice

- smallest_safe_increment: Batch A contract package only:
  1. status-vocabulary inventory;
  2. ContextPacket and ContextLedger schemas;
  3. minimal RunRecord schema;
  4. positive and negative fixtures;
  5. semantic schema-mirror verification test;
  6. Reviewer Index update.
- worker_type_needed: schema/docs worker after this receipt is referenced in
  the task packet.
- files_or_modules_in_scope:
  - `docs/status/runtime-governance-status-vocabulary-inventory.md`
  - `schemas/runtime-governance/context-packet.schema.json`
  - `schemas/runtime-governance/context-ledger.schema.json`
  - `schemas/runtime-governance/run-record.schema.json`
  - `schemas/examples/runtime-governance/*.json`
  - `packages/control-plane/tests/test_public_snapshot.py`
  - `docs/status/reviewer-index.md`
- files_or_modules_out_of_scope:
  - workflow execution
  - slash-command routing
  - runtime file migration
  - dashboard authority changes
  - automatic retrieval
  - external dependency adoption
  - final acceptance or release readiness claims
- evidence_required_for_completion:
  - targeted schema/fixture tests
  - public snapshot verification
  - `git diff --check`
  - independent subagent review before commit
- review_gate_definition:
  - PASS only if schemas and fixtures encode the current authority boundaries:
    context is explicit, run success is not completion, report text is not
    evidence, gate pass requires evidence, final verdict is non-executor, and
    projections are derived.

## Stop Lines

- No write-capable runtime/evidence/review-gate worker before this receipt is
  referenced by the task.
- No new workflow engine, evidence format, dashboard authority, broker, SDK, or
  external dependency in Batch A.
- No migration of local runtime files into the public repository.
- No final acceptance claim without PR/CI/publication evidence and the required
  governance verdict artifacts.
