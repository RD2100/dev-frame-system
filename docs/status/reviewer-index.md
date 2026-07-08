# Reviewer Index: Open-Source Release Batch 1

Lifecycle state: Current public-snapshot reviewer map

## Purpose

This is the reviewer map for the first open-source release batch. It focuses on what is currently proven and auditable in the repository: MCP/Web-AI intake, T3/native client projection, and governed visual state.

## In-Scope Review Surface

- `packages/control-plane`: runtime, entrypoints, probes, and client launch surfaces.
- `docs/agent-runtime`: interface contracts and operating model for MCP/Web-AI and visual control-plane behavior.
- `docs/status`: latest milestone decisions and state snapshots for this batch.
- `schemas/*`: state, bridge, and session contracts for reader-facing outputs.
- `scripts`: release and public-snapshot verification gates.

## First-Read Files

### Runtime Entry + Contracts
- `packages/control-plane/setup.py`
- `packages/control-plane/control_plane/cli/app.py` (router; domain handlers in `cli/_core.py`, `cli/_coding.py`, `cli/_webai.py`, `cli/_client.py`, `cli/_visual.py`)
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/agent-runtime/integration-contracts.md`

### MCP / Web-AI Path
- `packages/control-plane/control_plane/mcp_live_probe.py`
- `packages/control-plane/control_plane/provider_binding_probe.py`
- `packages/control-plane/control_plane/project_contract.py`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `rules/web-ai-adapters.md`
- `packages/control-plane/tests/test_mcp_live_probe.py`
- `packages/control-plane/tests/test_provider_binding_probe.py`

### Native / T3 Client Path
- `packages/control-plane/control_plane/client_launcher.py`
- `packages/control-plane/control_plane/client_manifest.py`
- `packages/control-plane/control_plane/t3_bridge_bundle.py`
- `packages/control-plane/control_plane/t3_adapter.py`
- `schemas/visual_client_manifest.schema.json`
- `schemas/t3_bridge_bundle.schema.json`
- `schemas/t3_client_shell.schema.json`
- `docs/agent-runtime/visual-control-plane.md`
- `docs/status/t3code-client-mainline-reuse-assessment.md`
- `docs/status/recon-receipt-local-agent-client-mainline.md`

### Governance + Visual Read Model
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/runtime_digest.py`
- `packages/control-plane/control_plane/orchestrator.py`
- `packages/control-plane/control_plane/workflow_engine.py`
- `packages/control-plane/control_plane/team_runtime.py`
- `packages/control-plane/control_plane/run_index.py`
- `packages/control-plane/control_plane/rdreview.py`
- `packages/control-plane/control_plane/evidence_gate.py`
- `packages/control-plane/control_plane/cli/_review.py`
- `packages/control-plane/control_plane/execution_plan.py`
- `tools/go_evidence.py`
- `schemas/visual_control_plane_state.schema.json`
- `schemas/review_governance_kernel.schema.json`
- `schemas/agent-runtime/chain-evidence.schema.json`
- `schemas/agent-runtime/evidence-manifest.schema.json`
- `schemas/agent-runtime/review.schema.json`
- `schemas/agent-runtime/final-verdict.schema.json`
- `schemas/agent-runtime/failure-record.schema.json`
- `packages/test-frame/schemas/agent-runtime/chain-evidence.schema.json`
- `schemas/runtime-governance/context-packet.schema.json`
- `schemas/runtime-governance/context-ledger.schema.json`
- `schemas/runtime-governance/run-record.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-packet.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-ledger.schema.json`
- `packages/test-frame/schemas/runtime-governance/run-record.schema.json`
- `schemas/examples/runtime-governance/context-packet-valid.json`
- `schemas/examples/runtime-governance/context-packet-stale-valid.json`
- `schemas/examples/runtime-governance/context-ledger-valid.json`
- `schemas/examples/runtime-governance/context-packet-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-packet-text-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-ledger-mutable-invalid.json`
- `schemas/examples/runtime-governance/run-record-review-pending-valid.json`
- `schemas/examples/runtime-governance/run-record-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/run-record-gate-pass-missing-evidence-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-projection-only-valid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-passed-missing-context-invalid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-code-review-pass-missing-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-final-report-pass-missing-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-paper-human-required-valid.json`
- `schemas/examples/runtime-governance/run-record-paper-blocked-chain-trusted-valid.json`
- `schemas/examples/runtime-governance/run-record-unknown-domain-status-valid.json`
- `schemas/examples/review-governance/success.json`
- `schemas/examples/review-governance/blocked.json`
- `schemas/examples/review-governance/insufficient-evidence.json`
- `schemas/examples/review-governance/missing-context.json`
- `packages/control-plane/control_plane/review_governance_validator.py`
- `packages/control-plane/control_plane/asset_utilization_validator.py`
- `packages/control-plane/control_plane/browser_transport_validator.py`
- `packages/control-plane/control_plane/client_governance_projection.py`
- `packages/control-plane/control_plane/docs_drift_validator.py`
- `packages/control-plane/control_plane/continuation_validator.py`
- `packages/control-plane/control_plane/document_authority.py`
- `packages/control-plane/control_plane/evaluation_integrity_validator.py`
- `packages/control-plane/control_plane/graph_projection_validator.py`
- `packages/control-plane/control_plane/mcp_utilization_validator.py`
- `packages/control-plane/control_plane/paper_workspace_validator.py`
- `packages/control-plane/control_plane/policy_escalation_validator.py`
- `packages/control-plane/control_plane/review_feedback_validator.py`
- `packages/control-plane/control_plane/skill_governance_validator.py`
- `packages/control-plane/control_plane/skill_usage_validator.py`
- `packages/control-plane/tests/test_review_governance_kernel.py`
- `packages/control-plane/tests/test_asset_utilization_validator.py`
- `packages/control-plane/tests/test_browser_transport_validator.py`
- `packages/control-plane/tests/test_client_governance_projection.py`
- `packages/control-plane/tests/test_continuation_validator.py`
- `packages/control-plane/tests/test_docs_drift_validator.py`
- `packages/control-plane/tests/test_document_authority.py`
- `packages/control-plane/tests/test_evaluation_integrity_validator.py`
- `packages/control-plane/tests/test_graph_projection_validator.py`
- `packages/control-plane/tests/test_mcp_utilization_validator.py`
- `packages/control-plane/tests/test_paper_workspace_validator.py`
- `packages/control-plane/tests/test_policy_escalation_validator.py`
- `packages/control-plane/tests/test_review_feedback_validator.py`
- `packages/control-plane/tests/test_skill_governance_validator.py`
- `packages/control-plane/tests/test_skill_usage_validator.py`
- `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`
- `packages/control-plane/tests/test_public_snapshot.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/tests/test_dashboard_actions.py`
- `packages/control-plane/tests/test_workflow_engine.py`
- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_rdreview.py`
- `packages/control-plane/tests/test_evidence_gate.py`
- `tests/test_go_evidence.py`
- `packages/control-plane/tests/test_execution_plan.py`
- `packages/control-plane/control_plane/review_governance_validator.py`
- `packages/control-plane/tests/test_review_governance_kernel.py`
- `schemas/review_governance_kernel.schema.json`
- `schemas/runtime-governance/context-packet.schema.json`
- `schemas/runtime-governance/context-ledger.schema.json`
- `schemas/runtime-governance/run-record.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-packet.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-ledger.schema.json`
- `packages/test-frame/schemas/runtime-governance/run-record.schema.json`
- `schemas/examples/runtime-governance/context-packet-valid.json`
- `schemas/examples/runtime-governance/context-packet-stale-valid.json`
- `schemas/examples/runtime-governance/context-ledger-valid.json`
- `schemas/examples/runtime-governance/context-packet-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-packet-text-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-ledger-mutable-invalid.json`
- `schemas/examples/runtime-governance/run-record-review-pending-valid.json`
- `schemas/examples/runtime-governance/run-record-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/run-record-gate-pass-missing-evidence-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-projection-only-valid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-passed-missing-context-invalid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-code-review-pass-missing-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-final-report-pass-missing-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-paper-human-required-valid.json`
- `schemas/examples/runtime-governance/run-record-paper-blocked-chain-trusted-valid.json`
- `schemas/examples/runtime-governance/run-record-unknown-domain-status-valid.json`
- `schemas/examples/review-governance/success.json`
- `schemas/examples/review-governance/blocked.json`
- `schemas/examples/review-governance/insufficient-evidence.json`
- `schemas/examples/review-governance/missing-context.json`
- `schemas/resource-integration/script-safety-record.schema.json`
- `schemas/resource-integration/memory-context-record.schema.json`

### Customization / Model Provider / Cluster Surface
- `packages/control-plane/control_plane/scoped_store.py`
- `packages/control-plane/control_plane/scope_resolver.py`
- `packages/control-plane/control_plane/custom_skills.py`
- `packages/control-plane/control_plane/rules_config.py`
- `packages/control-plane/control_plane/run_defaults.py`
- `packages/control-plane/control_plane/memory_prefs.py`
- `packages/control-plane/control_plane/model_providers.py`
- `packages/control-plane/control_plane/cluster_control.py`
- `packages/control-plane/control_plane/cluster_run.py`
- `packages/control-plane/control_plane/task_proposals.py`
- `packages/control-plane/control_plane/writeback.py`
- `schemas/custom_skills.schema.json`
- `schemas/custom_rules.schema.json`
- `schemas/run_defaults.schema.json`
- `schemas/preferences.schema.json`
- `schemas/project_memory.schema.json`
- `schemas/cluster_roster.schema.json`
- `packages/control-plane/tests/test_scope_resolver.py`
- `packages/control-plane/tests/test_scope_resolver_properties.py`
- `packages/control-plane/tests/test_custom_skills.py`
- `packages/control-plane/tests/test_rules_config.py`
- `packages/control-plane/tests/test_run_defaults.py`
- `packages/control-plane/tests/test_memory_prefs.py`
- `packages/control-plane/tests/test_model_providers.py`
- `docs/status/recon-receipt-customization-layer.md`
- `docs/status/recon-receipt-pluggable-model-provider.md`
- `packages/control-plane/tests/test_cluster_control.py`
- `packages/control-plane/tests/test_cluster_run_manage.py`
- `packages/control-plane/tests/test_task_proposals.py`
- `packages/control-plane/tests/test_writeback.py`

### MCP / ACP / OpenCode Event Surface
- `packages/control-plane/control_plane/mcp_consent.py`
- `packages/control-plane/control_plane/mcp_server.py`
- `packages/control-plane/control_plane/acp_client.py`
- `packages/control-plane/control_plane/acp_session.py`
- `packages/control-plane/control_plane/opencode_events.py`
- `packages/control-plane/control_plane/worktree.py`
- `docs/status/recon-receipt-mcp-consent.md`
- `docs/status/recon-receipt-devframe-mcp-server.md`
- `docs/status/recon-receipt-acp-backbone.md`
- `docs/status/recon-receipt-opencode-event-integration.md`
- `docs/status/recon-receipt-parallel-write-isolation.md`
- `packages/control-plane/tests/test_mcp_consent.py`
- `packages/control-plane/tests/test_mcp_server.py`
- `packages/control-plane/tests/test_acp_client.py`
- `packages/control-plane/tests/test_acp_session.py`
- `packages/control-plane/tests/test_go_acp_driver.py`
- `packages/control-plane/tests/test_opencode_events.py`
- `packages/control-plane/tests/test_go_opencode_events.py`
- `packages/control-plane/tests/test_worktree.py`
- `packages/control-plane/tests/test_go_worktree.py`

### Current State Evidence Files
- `docs/status/LAUNCH_NOW.md`
- `docs/status/status-document-inventory.md`
- `docs/status/governance-spine-and-document-coordination.md`
- `docs/status/unified-object-model-decision-record.md`
- `docs/status/governance-contradiction-matrix.md`
- `docs/status/governance-rules-spec.md`
- `docs/status/context-noise-governance-and-automation-plan.md`
- `docs/status/model-knowledge-gap-governance-plan.md`
- `docs/status/project-and-cross-project-memory-harness-governance-plan.md`
- `docs/status/goal-bound-evidence-gate-plan.md`
- `docs/status/paper-claim-integrity-gate-to-cluster-plan.md`
- `docs/status/human-attention-governance-and-automation-maturity-plan.md`
- `docs/status/early-adopter-user-asset-governance-plan.md`
- `docs/status/competitive-moat-and-user-demand-critical-review.md`
- `docs/status/document-driven-transformation-master-plan.md`
- `docs/status/document-driven-transformation-final-plan-20260705.md`
- `docs/status/review-governance-kernel-completion-20260706.md`
- `docs/status/design-coverage-gap-remediation-plan.md`
- `docs/status/review-first-governance-kernel-contraction-plan.md`
- `docs/status/review-first-governance-kernel-implementation-spec.md`
- `docs/status/reuse-first-constraint-governance-implementation-plan.md`
- `docs/status/skill-asset-utilization-plan.md`
- `docs/status/current-coverage-audit-evidence-20260704.md`
- `docs/status/working-tree-cleanup-inventory-20260705.md`
- `docs/status/asset-utilization-inventory-20260705.md`
- `docs/status/browser-automation-transport-roadmap.md`
- `docs/status/paper-knowledge-base-iteration-mvp-plan.md`
- `docs/status/graph-projection-knowledge-canvas-plan.md`
- `docs/status/recon-receipt-local-agent-client-mainline.md`
- `docs/status/t3code-client-mainline-reuse-assessment.md`
- `docs/status/release-readiness.md`
- `docs/status/workflow-consolidation-and-command-plan.md`
- `docs/status/context-management-architecture-plan.md`
- `docs/status/context-led-model-performance-control-plan.md`
- `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
- `docs/status/runtime-governance-status-vocabulary-inventory.md`
- `docs/status/runtime-governance-batch-a-contract-completion.md`
- `docs/status/runtime-governance-batch-b-read-only-run-index.md`
- `docs/status/runtime-governance-batch-c-rdreview-prepare-only.md`
- `docs/status/runtime-governance-batch-d-independent-gate.md`
- `docs/status/runtime-governance-batch-e-workflow-review-pending.md`
- `docs/status/runtime-governance-batch-e-paper-trust-fail-closed.md`
- `docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md`
- `docs/status/runtime-governance-batch-e-team-context-refs.md`
- `docs/status/runtime-governance-batch-e-team-review-verdict-events.md`
- `docs/status/runtime-governance-batch-e-go-evidence-team-runtime-finalization.md`
- `docs/status/runtime-governance-batch-e-final-verdict-lifecycle.md`
- `docs/status/runtime-governance-batch-e-final-verdict-supersession-projection.md`
- `docs/status/runtime-governance-batch-f-sealed-context-artifacts.md`
- `docs/status/runtime-governance-batch-g-generic-go-opt-in-finalization.md`
- `docs/status/runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md`
- `docs/status/runtime-governance-batch-i-generic-go-prepare-evidence.md`
- `docs/status/runtime-governance-batch-j-automatic-superseding-final-verdict.md`
- `docs/status/runtime-governance-batch-e-atgo-runtime-finalize-command.md`
- `docs/status/runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md`
- `docs/status/runtime-governance-batch-e-chain-evidence-schema-compatibility.md`
- `docs/status/runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md`
- `docs/status/recon-receipt-runtime-governance-unification.md`
- `docs/status/evaluation-feedback-learning-governance-plan.md`
- `docs/status/total-control-policy-engine-and-human-escalation-governance-plan.md`
- `docs/status/documentation-management-audit-and-plan.md`
- `docs/status/documentation-management-detailed-rollout-plan.md`
- `docs/status/reviewer-index.md` (this file)

## Critical Paths to Verify

- `devframe` bootstrap to governance surface:
  - `setup.py` exposes `devframe` and installs `control_plane/cli/` command handlers.
  - CLI must route MCP, T3 client, visual-state/actions, and rdgoal entrypoints through current, tested code paths.
- MCP/Web-AI intake and provider binding:
  - `provider_binding_probe.py` and `mcp_live_probe.py` should accept reference-safe summaries and reject unsafe session data.
  - Tests above should cover negative cases and session summaries.
- Native/T3 read model contract:
  - `client_manifest.py` exposes `/client-manifest.json`, `/client-plan.json`, `/t3-bridge.json`, `/t3-shell.json`.
  - `t3_bridge_bundle.py` builds installable bridge artifacts and launch helpers.
  - `t3_adapter.py` maps DevFrame state to `t3_shell` snapshots with action overlays.
- Visual control-plane outputs:
  - `dashboard.py` and `visual_state.py` must keep mutation points constrained and endpoints read-only by default.
  - Action queue filtering (`--status`, `--priority`, `--source-type`, `--source-id`, `--action-id`) must remain deterministic.
- Customization and project-scoped config:
  - `scoped_store.py` must keep runtime config writes outside the public repository.
  - Scope resolution must remain deterministic, most-specific-wins for records, and most-restrictive-wins for capability flags.
  - Project-level overrides must not silently weaken P0 rules or executor constraints.
- Cluster / workflow / team runtime:
  - `workflow_engine.py` should record plan -> execute -> review phases as durable team events.
  - `team_runtime.py` should project real task, message, conflict, review, and evidence objects without executor self-approval.
  - Cluster dispatch must keep dashboard monitoring separate from inline human authorization.
- MCP / ACP / OpenCode event integration:
  - MCP consent and server paths must stay loopback/origin gated and safe-tool constrained.
  - ACP live-driving claims must stay bounded to the current receipt and tests; deferred behavior must not be presented as complete.
  - OpenCode event ingestion should enrich session fields without converting missing event data into a passing claim.
- Review-governance completion status:
  - `docs/status/review-governance-kernel-completion-20260706.md` reports P3-2 graph projection as local GPT-equivalent review PASS, committed in `2725227d`, and local branch-level review PASS at `bd73d6bc`; keep it out of public-release-ready claims unless release evidence includes PR CI, main CI, merge, and GitHub Release publication.
- Runtime-governance RunRecord contract:
  - Worker outcome is mechanical only and must not satisfy independent review.
  - `gate_passed` requires gate evidence references.
  - `final_ready` requires a FinalVerdict plus independent review and gate evidence.
  - Executor/fixer/coder/worker-authored review or final verdict must fail.
  - Projection state is display-only and cannot create acceptance authority.
- Runtime-governance schema mirrors:
  - `packages/test-frame/schemas/runtime-governance/*` must remain a semantic
    mirror of `schemas/runtime-governance/*`.
  - Mirror checks should ignore encoding, line-ending, and key-order noise while
    failing on JSON semantic drift.
- Runtime-governance Batch A completion audit:
  - `docs/status/runtime-governance-batch-a-contract-completion.md` records the
    local contract evidence and preserved stop lines.
  - The audit is not a release-ready, PR, CI, or publication claim.
- Runtime-governance Batch B read-only RunIndex:
  - `packages/control-plane/control_plane/run_index.py` projects legacy rdgoal,
    go-run, team-event, @go, paper, and test-run files into RunRecord-shaped
    records without changing legacy write authority.
  - `packages/control-plane/tests/test_run_index.py` should prove schema
    compatibility, unsafe-promotion blocking, and corrupt-record visibility.
  - `docs/status/runtime-governance-batch-b-read-only-run-index.md` records the
    local limitation set and preserved stop lines.
- Runtime-governance Batch C rdreview prepare-only bundle:
  - `packages/control-plane/control_plane/rdreview.py` preserves the legacy
    packet default while adding `--format bundle` through
    `packages/control-plane/control_plane/cli/_review.py`.
  - `packages/control-plane/tests/test_rdreview.py` should prove the bundle is
    schema-valid, review-pending, gate-not-evaluated, manual-only, and blocked
    from final acceptance authority.
  - `docs/status/runtime-governance-batch-c-rdreview-prepare-only.md` records
    the local limitation set and preserved stop lines.
- Runtime-governance Batch D independent gate:
  - `packages/control-plane/control_plane/evidence_gate.py` extracts reusable
    evidence validation and artifact generation behind a library interface.
  - `tools/go_evidence.py` keeps the existing CLI behavior while writing
    schema-valid `evidence-manifest.json`, `final-verdict.json`, and blocked
    `failure-record.json`.
  - `tests/test_go_evidence.py` and
    `packages/control-plane/tests/test_evidence_gate.py` should prove
    self-approval blocking, schema-valid machine artifacts, and final report
    consistency.
  - `docs/status/runtime-governance-batch-d-independent-gate.md` records the
    local limitation set and preserved stop lines.
- Runtime-governance Batch E workflow review-pending:
  - `packages/control-plane/control_plane/workflow_engine.py` must treat worker
    success as `awaiting_review`, not a reviewer pass or final-ready signal.
  - `packages/control-plane/control_plane/team_runtime.py` must map successful
    worker task results to open review gates until independent review exists.
  - `packages/control-plane/control_plane/visual_state.py` must keep passed
    go-run outcome gates open, with reason text that separates execution
    success from review pass.
  - `packages/control-plane/tests/test_workflow_engine.py`,
    `packages/control-plane/tests/test_team_runtime.py`, and
    `packages/control-plane/tests/test_go_team_runtime.py` should prove the
    former self-approval path now stays review-pending.
  - `docs/status/runtime-governance-batch-e-workflow-review-pending.md` records
    the local limitation set and preserved stop lines.
- Runtime-governance Batch E paper trust fail-closed:
  - `packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py` must never
    infer `chain_trusted=True` from terminal `passed` or `blocked` status.
  - `packages/ai-workflow-hub/src/ai_workflow_hub/cli.py` previously used
    `_write_chain_evidence()` as the explicit trust producer; the follow-up
    ai-workflow-hub chain evidence classification slice now keeps nodes-style
    evidence fail-closed.
  - `packages/ai-workflow-hub/tests/test_run_governance.py` should prove
    terminal paper status remains untrusted unless explicit non-nodes chain
    trust exists.
  - `docs/status/runtime-governance-status-vocabulary-inventory.md` should keep
    the paper run-governance vocabulary aligned with the fail-closed behavior.
  - `docs/status/runtime-governance-batch-e-paper-trust-fail-closed.md` records
    the local limitation set and preserved stop lines.
- Runtime-governance Batch E explicit team evidence events:
  - `packages/control-plane/control_plane/team_runtime.py` should record
    `evidence_ref` events for worker report artifacts while preserving legacy
    `task_result.report_path` projection.
  - `packages/control-plane/tests/test_team_runtime.py` should prove explicit
    evidence folding, legacy journal compatibility, and no duplicate evidence.
  - `packages/control-plane/tests/test_go_team_runtime.py` should prove the
    real `run_go_dispatch(... execute=True)` and prepared resume paths record
    evidence refs, remain visual-state schema-valid, and project into T3.
  - `packages/control-plane/control_plane/run_index.py` and
    `packages/control-plane/tests/test_run_index.py` should prove explicit
    team evidence refs project into RunRecord evidence without breaking legacy
    `task_result.report_path` journals.
  - `packages/control-plane/control_plane/visual_state.py` should avoid
    re-adding recorded team evidence when the projected go-run report already
    names the same run and path.
  - `docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E team context refs:
  - `packages/control-plane/control_plane/team_runtime.py` should keep
    `context_refs` optional on task lifecycle events and project them only as
    provenance evidence, not acceptance authority.
  - `packages/control-plane/control_plane/go_dispatch.py` should pass sealed
    `context_packet`, `context_ledger`, and legacy packet/TaskSpec refs during
    execute and resume paths without treating context as acceptance authority.
  - `packages/control-plane/control_plane/run_index.py` should project team
    context refs as limitation-supporting context evidence and keep review/final
    readiness unchanged.
  - `packages/control-plane/tests/test_team_runtime.py`,
    `packages/control-plane/tests/test_go_team_runtime.py`, and
    `packages/control-plane/tests/test_run_index.py` should prove compatibility,
    real-path recording, schema validity, and no acceptance promotion.
  - `docs/status/runtime-governance-batch-e-team-context-refs.md` records the
    local limitation set and preserved stop lines.
- Runtime-governance Batch E team review verdict events:
  - `packages/control-plane/control_plane/team_runtime.py` should record
    `review_ref` and `final_verdict_ref` as explicit events with distinct
    message, evidence, gate, and event-log projections.
  - `packages/control-plane/control_plane/run_index.py` should project only
    valid independent reviews and governance final verdicts into RunRecord
    `review_refs`, `gate_refs`, and `final_verdict_ref`.
  - Worker task results should remain execution outcomes only; review-only
    runs remain `review_pending`, and `final_ready` requires a valid FinalVerdict
    artifact plus passing review and gate references.
  - `packages/control-plane/tests/test_team_runtime.py`,
    `packages/control-plane/tests/test_run_index.py`, and
    `packages/control-plane/tests/test_t3_adapter.py` should prove distinct
    event visibility, schema-valid final readiness, and fail-closed self-review
    or worker-final-verdict behavior.
  - `docs/status/runtime-governance-batch-e-team-review-verdict-events.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E go evidence TeamRuntime finalization:
  - `tools/go_evidence.py finalize --team-runtime-dir <dir>` should record
    TeamRuntime `review_ref` and `final_verdict_ref` events only after a passing
    deterministic evidence gate.
  - Default `finalize <evidence_dir>` behavior must remain compatible and write
    no TeamRuntime journal.
  - Blocked or failed evidence finalization must not create TeamRuntime
    final-ready events; valid non-pass finalization may record blocked/failed
    visibility, while invalid or self-review blockers must record artifact refs
    only.
  - Same-verdict finalization reruns must not rewrite divergent machine
    artifacts or append duplicate TeamRuntime review/final-verdict refs.
  - `tests/test_go_evidence.py` should prove opt-in event recording, RunIndex
    `final_ready` projection from the referenced FinalVerdict artifact,
    idempotent reruns, non-pass visibility, and no final-ready event recording
    for invalid or self-review blockers.
  - `docs/status/runtime-governance-batch-e-go-evidence-team-runtime-finalization.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E FinalVerdict lifecycle metadata:
  - `schemas/agent-runtime/final-verdict.schema.json` should accept optional
    append-only `supersedes` metadata with a previous verdict id, URI, and
    governance reason.
  - Superseding metadata must not weaken FinalVerdict producer role rules or
    create acceptance evidence by itself.
  - `packages/control-plane/tests/test_public_snapshot.py` should prove valid
    superseding metadata, incomplete superseding metadata rejection, and blocked
    worker-authored superseding verdicts.
  - `docs/status/runtime-governance-batch-e-final-verdict-lifecycle.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E FinalVerdict supersession projection:
  - `schemas/runtime-governance/run-record.schema.json` should accept optional
    `final_verdict_ref.supersedes` metadata and a bounded
    `final_verdict_ref.supersession_chain` copied from validated FinalVerdict
    artifacts.
  - `packages/test-frame/schemas/runtime-governance/run-record.schema.json`
    should remain semantically identical to the root RunRecord schema.
  - `packages/control-plane/control_plane/run_index.py` should project only the
    direct superseded verdict id, URI, reason, and best-effort bounded chain; it
    must not generate new verdicts or use supersession metadata as acceptance
    evidence.
  - Supersession-chain entries should expose diagnostic `resolution_state`
    values for resolved, missing, invalid, id-mismatch, cycle, and depth-limited
    outcomes without changing run acceptance axes.
  - `packages/control-plane/tests/test_run_index.py` and
    `packages/control-plane/tests/test_public_snapshot.py` should prove the
    real TeamRuntime projection path, missing/invalid/mismatched/cyclic/depth-
    limited historical artifact behavior, and schema mirror.
  - `docs/status/runtime-governance-batch-e-final-verdict-supersession-projection.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch F sealed context artifacts:
  - `packages/control-plane/control_plane/dispatch_packet.py` should create
    schema-compatible `context-packet.json` and `context-ledger.json` beside
    go/rdgoal worker packets.
  - `packages/control-plane/control_plane/run_index.py` should project sealed
    context packets as context evidence, context ledgers as artifacts, and
    block `final_ready` when a passed worker has no valid sealed context.
  - `tools/go_evidence.py finalize --team-runtime-dir <dir>` should backfill
    go-run context refs before recording review/final-verdict refs.
  - `docs/status/runtime-governance-batch-f-sealed-context-artifacts.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch G generic go opt-in finalization:
  - `packages/control-plane/control_plane/cli/_coding.py` should require
    `--evidence-dir` when `--auto-finalize` is passed to `devframe go execute`
    or `devframe code execute`.
  - The implementation should reuse `tools/go_evidence.py finalize` with
    `--team-runtime-dir`, not duplicate FinalVerdict logic.
  - `packages/control-plane/tests/test_cli.py` should cover the rejection path
    and a real prepared-go-run path that reaches RunIndex `final_ready`.
  - `docs/status/runtime-governance-batch-g-generic-go-opt-in-finalization.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E atgo runtime finalize command:
  - `devframe atgo` should print a finalizer command that includes
    `--team-runtime-dir <runtime_root>` so the manual follow-up can record
    TeamRuntime review/final-verdict refs after a passing evidence gate.
  - The command remains manual guidance by default; `devframe atgo` prepare and
    plain `--execute` must not create final acceptance events by themselves.
  - `devframe atgo --execute --auto-finalize` may run the same finalizer only
    when required review evidence already exists; missing review evidence must
    skip finalization rather than converting worker success into blocked or
    final-ready artifacts.
  - `packages/control-plane/tests/test_cli.py` should prove the printed atgo
    finalize command includes the runtime directory, missing review evidence is
    skipped, and reviewed evidence can produce TeamRuntime final-ready
    projection through the deterministic finalizer.
  - Printed finalizer guidance should remain copyable for ordinary paths with
    spaces while `command_args` remains the unquoted structured argv authority.
  - `docs/status/runtime-governance-batch-e-atgo-runtime-finalize-command.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E atgo prepare finalizer metadata:
  - `devframe atgo` should write `next_commands.finalize` metadata into
    `chain-evidence.json` with `authority: guidance_only`,
    `creates_acceptance: false`, and `requires_independent_review: true`.
  - RunIndex should project prepare-only atgo evidence with chain evidence but
    no `review.yaml` as deferred/review-pending preparation, not as final-ready
    acceptance or corrupt-record failure.
  - `packages/control-plane/tests/test_cli.py` and
    `packages/control-plane/tests/test_run_index.py` should prove the metadata
    shape and prepare-only projection.
  - `docs/status/runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E chain evidence schema compatibility:
  - `schemas/agent-runtime/chain-evidence.schema.json` should validate current
    `go_evidence init` and `devframe atgo` chain evidence output.
  - `packages/test-frame/schemas/agent-runtime/chain-evidence.schema.json`
    should remain semantically identical to the root schema.
  - `next_commands.finalize` schema fields must stay guidance-only and must not
    imply acceptance authority.
  - The deterministic evidence gate in `packages/control-plane/control_plane/evidence_gate.py`
    should validate `chain-evidence.json` against the schema before final-ready
    artifacts can be produced.
  - `tests/test_go_evidence.py`, `packages/control-plane/tests/test_cli.py`,
    `packages/control-plane/tests/test_evidence_gate.py`, and
    `packages/control-plane/tests/test_public_snapshot.py` should prove the
    generated artifacts, finalizer blocking behavior, and mirror contract.
  - `docs/status/runtime-governance-batch-e-chain-evidence-schema-compatibility.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch E ai-workflow-hub chain evidence classification:
  - `packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py` should
    classify `nodes`-style `chain-evidence.json` as visible but non-canonical
    acceptance evidence.
  - The classification must not infer `chain_trusted=True` from file shape or
    terminal run status.
  - `packages/ai-workflow-hub/tests/test_run_governance.py` should prove the
    untrusted classification path, stale trusted-state override for nodes-style,
    invalid, and unknown-shape files, and `_write_chain_evidence()` fail-closed
    path.
  - `docs/status/runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch H ai-workflow-hub chain evidence adapter:
  - `packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py` should
    expose `chain_evidence_adapter` for `nodes`-style evidence without changing
    `chain_trusted` or final-ready authority.
  - The adapter must set `acceptance_candidate=False`, keep invalid/missing/
    unknown evidence blocked, and treat normalized output as diagnostic data.
  - `packages/ai-workflow-hub/tests/test_run_governance.py` should prove the
    real-path nodes normalization candidate and fail-closed paths.
  - `docs/status/runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch I generic go prepare evidence:
  - `packages/control-plane/control_plane/cli/_coding.py` should accept
    `--prepare-evidence-dir` only as a draft evidence-production option.
  - The option must be mutually exclusive with `--auto-finalize` and
    `--evidence-dir`, must set manifest eligibility to `needs_more_evidence`,
    and must not create `review.yaml`, `final-verdict.json`, or final-ready
    state.
  - `packages/control-plane/tests/test_cli.py` should prove the real path:
    prepare-only draft first, then explicit independent review plus
    `--auto-finalize` can finalize the same directory.
  - `docs/status/runtime-governance-batch-i-generic-go-prepare-evidence.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance Batch J automatic superseding FinalVerdict:
  - `tools/go_evidence.py` should archive prior materially different
    `final-verdict.json` artifacts before writing a new final verdict with
    `supersedes` metadata.
  - Invalid or governance-reference-mismatched prior verdicts must fail closed
    as blocked final verdicts, not final-ready supersessions.
  - `tests/test_go_evidence.py` should prove rerun supersession, prior archive,
    and mismatch blocking behavior.
  - Follow-up hardening focus: `RunIndex` currently accepts a final-ready
    verdict when pass review, pass gate, and sealed context refs are present.
    Reviewers should decide in a later slice whether final-ready must also
    require an observable `task_result` event for every current path, or whether
    the existing finalizer backfill compatibility remains intentional.
  - `docs/status/runtime-governance-batch-j-automatic-superseding-final-verdict.md`
    records the local limitation set and preserved stop lines.
- Runtime-governance post-Batch-E status reconciliation:
  - `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
    should no longer present the original Batch A immediate-next language as
    current execution state.
  - Subsequent public-snapshot slices now project direct FinalVerdict
    supersession metadata, a bounded supersession chain, and diagnostic
    `resolution_state` values for resolved, missing, invalid, id-mismatch,
    cycle, and depth-limited links.
- Current remaining gaps are default generic `go` automatic finalization,
    complete automatic independent review evidence production, paper domain
    adapters, ai-workflow-hub canonical artifact writeback beyond the Batch H
    diagnostic adapter, and complete supersession-chain graph or migration
    resolution.
  - Reviewers should confirm this reconciliation does not change runtime
    behavior, schema contracts, adapter behavior, dashboard authority, or
    acceptance projection beyond the already audited read-only supersession
    projection.
  - Terminal status, file shape, `next_commands.finalize`, worker success, and
    projection or supersession-diagnostic status must remain non-authoritative
    for acceptance.

## Open-Source Review Checklist

1. Confirm MCP/Web-AI claims are tied to local public snapshot tests, not private runtime assumptions.
2. Confirm native-client surface is projection-based: DevFrame remains the governance source of truth.
3. Confirm native/T3 integration paths are manifest/bridge first and schema-validated.
4. Confirm generated/private directories are excluded by `verify-public-snapshot.ps1`.
5. Confirm local mutation endpoints stay explicit and loopback-limited.
6. Confirm stage-8 native reuse status is current and does not overclaim release/publish readiness.
7. Confirm customization, writeback, cluster, workflow, MCP, ACP, and OpenCode-event additions are covered by their matching Recon Receipts and tests.
8. Confirm deferred module plans stay discoverable without being presented as implemented runtime behavior.
9. Confirm P3-2 graph projection is not treated as release-ready from PR CI alone; main CI, merge, and GitHub Release publication evidence are required for GitHub release readiness.

## Public Surface File Index

This index ensures all required public snapshot paths are explicitly referenced for reviewer traceability.

- `README.md`
- `README.zh-CN.md`
- `.github/workflows/release-verify.yml`
- `docs/agent-runtime/rdgoal-total-control.md`
- `docs/agent-runtime/dispatch-model-profiles.md`
- `docs/agent-runtime/rdpaper-workflow.md`
- `docs/agent-runtime/visual-control-plane.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/agent-runtime/agent-coding-discipline.md`
- `docs/status/release-readiness.md`
- `docs/status/LAUNCH_NOW.md`
- `docs/status/status-document-inventory.md`
- `docs/status/governance-spine-and-document-coordination.md`
- `docs/status/unified-object-model-decision-record.md`
- `docs/status/governance-contradiction-matrix.md`
- `docs/status/governance-rules-spec.md`
- `docs/status/model-knowledge-gap-governance-plan.md`
- `docs/status/goal-bound-evidence-gate-plan.md`
- `docs/status/paper-claim-integrity-gate-to-cluster-plan.md`
- `docs/status/human-attention-governance-and-automation-maturity-plan.md`
- `docs/status/early-adopter-user-asset-governance-plan.md`
- `docs/status/competitive-moat-and-user-demand-critical-review.md`
- `docs/status/document-driven-transformation-master-plan.md`
- `docs/status/document-driven-transformation-final-plan-20260705.md`
- `docs/status/review-governance-kernel-completion-20260706.md`
- `docs/status/design-coverage-gap-remediation-plan.md`
- `docs/status/review-first-governance-kernel-contraction-plan.md`
- `docs/status/review-first-governance-kernel-implementation-spec.md`
- `docs/status/reuse-first-constraint-governance-implementation-plan.md`
- `docs/status/skill-asset-utilization-plan.md`
- `docs/status/current-coverage-audit-evidence-20260704.md`
- `docs/status/working-tree-cleanup-inventory-20260705.md`
- `docs/status/asset-utilization-inventory-20260705.md`
- `docs/status/browser-automation-transport-roadmap.md`
- `docs/status/paper-knowledge-base-iteration-mvp-plan.md`
- `docs/status/graph-projection-knowledge-canvas-plan.md`
- `docs/status/workflow-consolidation-and-command-plan.md`
- `docs/status/context-management-architecture-plan.md`
- `docs/status/context-led-model-performance-control-plan.md`
- `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
- `docs/status/runtime-governance-status-vocabulary-inventory.md`
- `docs/status/runtime-governance-batch-a-contract-completion.md`
- `docs/status/runtime-governance-batch-b-read-only-run-index.md`
- `docs/status/runtime-governance-batch-c-rdreview-prepare-only.md`
- `docs/status/runtime-governance-batch-d-independent-gate.md`
- `docs/status/runtime-governance-batch-e-workflow-review-pending.md`
- `docs/status/runtime-governance-batch-e-paper-trust-fail-closed.md`
- `docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md`
- `docs/status/runtime-governance-batch-e-team-context-refs.md`
- `docs/status/runtime-governance-batch-e-team-review-verdict-events.md`
- `docs/status/runtime-governance-batch-e-go-evidence-team-runtime-finalization.md`
- `docs/status/runtime-governance-batch-e-final-verdict-lifecycle.md`
- `docs/status/runtime-governance-batch-e-final-verdict-supersession-projection.md`
- `docs/status/runtime-governance-batch-f-sealed-context-artifacts.md`
- `docs/status/runtime-governance-batch-g-generic-go-opt-in-finalization.md`
- `docs/status/runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md`
- `docs/status/runtime-governance-batch-i-generic-go-prepare-evidence.md`
- `docs/status/runtime-governance-batch-j-automatic-superseding-final-verdict.md`
- `docs/status/current-dirty-tree-batch-map-20260708.md`
- `docs/status/runtime-governance-batch-e-atgo-runtime-finalize-command.md`
- `docs/status/runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md`
- `docs/status/runtime-governance-batch-e-chain-evidence-schema-compatibility.md`
- `docs/status/runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md`
- `docs/status/recon-receipt-runtime-governance-unification.md`
- `docs/status/evaluation-feedback-learning-governance-plan.md`
- `docs/status/documentation-management-audit-and-plan.md`
- `docs/status/documentation-management-detailed-rollout-plan.md`
- `docs/status/reviewer-index.md`
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `packages/control-plane/setup.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/cli/_client.py`
- `packages/control-plane/control_plane/cli/_coding.py`
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/_mcp.py`
- `packages/control-plane/control_plane/cli/_visual.py`
- `packages/control-plane/control_plane/cli/_webai.py`
- `packages/control-plane/control_plane/cli/_writeback.py`
- `packages/control-plane/templates/paper_iteration/PAPER_PROFILE.yaml`
- `packages/control-plane/templates/paper_iteration/PAPER_STATE.yaml`
- `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`
- `packages/control-plane/templates/paper_iteration/WEB_AI_ADAPTER.yaml`
- `packages/control-plane/control_plane/agent_adapter.py`
- `packages/control-plane/control_plane/backup_guard.py`
- `packages/control-plane/control_plane/decision_engine.py`
- `packages/control-plane/control_plane/dispatch_packet.py`
- `packages/control-plane/control_plane/orchestrator.py`
- `packages/control-plane/control_plane/project_contract.py`
- `packages/control-plane/control_plane/rdgoal.py`
- `packages/control-plane/control_plane/rdgoal_cli.py`
- `packages/control-plane/control_plane/runtime_digest.py`
- `packages/control-plane/control_plane/runtime_store.py`
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/control_plane/worker.py`
- `packages/control-plane/control_plane/acp_client.py`
- `packages/control-plane/control_plane/acp_session.py`
- `packages/control-plane/control_plane/cluster_control.py`
- `packages/control-plane/control_plane/cluster_run.py`
- `packages/control-plane/control_plane/custom_skills.py`
- `packages/control-plane/control_plane/mcp_consent.py`
- `packages/control-plane/control_plane/mcp_server.py`
- `packages/control-plane/control_plane/memory_prefs.py`
- `packages/control-plane/control_plane/model_providers.py`
- `packages/control-plane/control_plane/opencode_events.py`
- `packages/control-plane/control_plane/rules_config.py`
- `packages/control-plane/control_plane/run_defaults.py`
- `packages/control-plane/control_plane/run_index.py`
- `packages/control-plane/control_plane/rdreview.py`
- `packages/control-plane/control_plane/evidence_gate.py`
- `packages/control-plane/control_plane/scope_resolver.py`
- `packages/control-plane/control_plane/scoped_store.py`
- `packages/control-plane/control_plane/task_proposals.py`
- `packages/control-plane/control_plane/team_runtime.py`
- `packages/control-plane/control_plane/workflow_engine.py`
- `packages/control-plane/control_plane/worktree.py`
- `packages/control-plane/control_plane/writeback.py`
- `packages/control-plane/control_plane/docs_drift_validator.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/conftest.py`
- `packages/control-plane/tests/test_public_snapshot.py`
- `packages/control-plane/tests/test_docs_drift_validator.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_rdreview.py`
- `packages/control-plane/tests/test_evidence_gate.py`
- `tests/test_go_evidence.py`
- `tools/go_evidence.py`
- `pytest.ini`
- `rules/orchestration.md`
- `rules/project-contracts/_template.md`
- `rules/web-ai-adapters.md`
- `schemas/project_contract.schema.json`
- `schemas/rdgoal_dispatch_packet.schema.json`
- `schemas/runtime-governance/context-packet.schema.json`
- `schemas/runtime-governance/context-ledger.schema.json`
- `schemas/runtime-governance/run-record.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-packet.schema.json`
- `packages/test-frame/schemas/runtime-governance/context-ledger.schema.json`
- `packages/test-frame/schemas/runtime-governance/run-record.schema.json`
- `schemas/examples/runtime-governance/context-packet-valid.json`
- `schemas/examples/runtime-governance/context-packet-stale-valid.json`
- `schemas/examples/runtime-governance/context-ledger-valid.json`
- `schemas/examples/runtime-governance/context-packet-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-packet-text-final-ready-invalid.json`
- `schemas/examples/runtime-governance/context-ledger-mutable-invalid.json`
- `schemas/examples/runtime-governance/run-record-review-pending-valid.json`
- `schemas/examples/runtime-governance/run-record-worker-final-ready-invalid.json`
- `schemas/examples/runtime-governance/run-record-gate-pass-missing-evidence-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-executor-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-invalid.json`
- `schemas/examples/runtime-governance/run-record-projection-completed-projection-only-valid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-passed-missing-context-invalid.json`
- `schemas/examples/runtime-governance/run-record-test-frame-code-review-pass-missing-review-invalid.json`
- `schemas/examples/runtime-governance/run-record-final-report-pass-missing-final-verdict-invalid.json`
- `schemas/examples/runtime-governance/run-record-paper-human-required-valid.json`
- `schemas/examples/runtime-governance/run-record-paper-blocked-chain-trusted-valid.json`
- `schemas/examples/runtime-governance/run-record-unknown-domain-status-valid.json`
- `schemas/visual_control_plane_state.schema.json`
- `schemas/web_ai_adapter.schema.json`
- `scripts/verify-control-plane-wheel.ps1`
- `scripts/verify-public-snapshot.ps1`
- `scripts/verify-release.ps1`

## Required Verification

At minimum, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

For the fuller gate, align with `docs/status/release-readiness.md`.
