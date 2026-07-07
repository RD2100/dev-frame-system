# DevFrame Documentation

This directory contains the public documentation map for dev-frame-system.

Start here when you need to understand which document is authoritative, which documents are planning records, and which ones are historical evidence.

## Read First

| Need | Read |
|---|---|
| Understand the product and install path | [Repository README](../README.md) |
| Understand the runtime model | [Agent Runtime Operating Model](agent-runtime/operating-model.md) |
| Understand the main review and acceptance discipline | [Reviewer Playbook](agent-runtime/reviewer-playbook.md) |
| Understand current release scope | [Release Readiness](status/release-readiness.md) |
| Navigate every `docs/status` record by authority level | [Status Document Inventory](status/status-document-inventory.md) |
| Understand the current review map | [Reviewer Index](status/reviewer-index.md) |

## Stable Runtime Docs

Use [agent-runtime](agent-runtime/) for durable operating rules, contracts, and explanations.

Important entry points:

- [Operating Model](agent-runtime/operating-model.md)
- [Runtime Invariants](agent-runtime/runtime-invariants.md)
- [Verification Gates](agent-runtime/verification-gates.md)
- [Tool Policy](agent-runtime/tool-policy.md)
- [Agent Coding Discipline](agent-runtime/agent-coding-discipline.md)
- [Dispatch Model Profiles](agent-runtime/dispatch-model-profiles.md)
- [Web AI Adapter Contract](agent-runtime/web-ai-adapter-contract.md)
- [Visual Control Plane](agent-runtime/visual-control-plane.md)
- [rdgoal Total-Control Orchestration](agent-runtime/rdgoal-total-control.md)
- [rdpaper Workflow](agent-runtime/rdpaper-workflow.md)
- [Methodology Skills Registry](agent-runtime/methodology-skills.md)

## Functional Map

Use this section when you need to find the project subsystem behind a product
capability instead of reading every status document.

This map is maintained as the first stop for future agents. It lists subsystem
entry points, not every file under `docs/status`.

Directory reliability rule: when adding a new public subsystem, stable runtime
contract, deferred module, or important control-plane plan, update the matching
entries in this functional map, `status/status-document-inventory.md`,
`status/reviewer-index.md`, and the master plan if it changes phase order,
scope, or deferral status.

| Capability | Start here | Key implementation |
|---|---|---|
| CLI router and command families | [Repository README](../README.md) | `packages/control-plane/control_plane/cli/app.py`, `cli/_coding.py`, `cli/_visual.py`, `cli/_webai.py`, `cli/_mcp.py`, `cli/_client.py` |
| Main governed coding loop | [Repository README](../README.md) | `packages/control-plane/control_plane/cli/_coding.py`, `coding_dispatch.py`, `go_dispatch.py`, `schemas/agent-runtime/task-spec.schema.json` |
| Total-control dispatch | [rdgoal Total-Control Orchestration](agent-runtime/rdgoal-total-control.md) | `rdgoal.py`, `orchestrator.py`, `decision_engine.py`, `dispatch_packet.py`, `runtime_store.py`, `schemas/rdgoal_dispatch_packet.schema.json` |
| Team runtime and workflow phases | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `team_runtime.py`, `workflow_engine.py`, `cluster_run.py`, `schemas/visual_control_plane_state.schema.json` |
| Intent framing and ambiguity governance | [Document-Driven Transformation Master Plan](status/document-driven-transformation-master-plan.md) | `tools/skills/intent-framing-gate/SKILL.md`, planned fixture payload on existing governance objects |
| Methodology skills | [Methodology Skills Registry](agent-runtime/methodology-skills.md) | `skill_registry.py`, `methodology_dispatch.py`, `custom_skills.py`, `schemas/methodology-skill.schema.json`, `schemas/custom_skills.schema.json` |
| Project-scoped customization | [Methodology Skills Registry](agent-runtime/methodology-skills.md) | `scoped_store.py`, `scope_resolver.py`, `cluster_control.py`, `custom_skills.py`, `rules_config.py`, `run_defaults.py`, `memory_prefs.py` |
| Rules, tool policy, and runtime invariants | [Runtime Invariants](agent-runtime/runtime-invariants.md) | `rules_config.py`, `rules/`, `schemas/custom_rules.schema.json`, `agent-runtime/tool-policy.md` |
| Agent coding discipline | [Agent Coding Discipline](agent-runtime/agent-coding-discipline.md) | `AGENTS.md`, `tools/skills/*/SKILL.md`, `docs/status/skill-asset-utilization-plan.md`, planned review-governance fixtures |
| Evidence and acceptance | [Verification Gates](agent-runtime/verification-gates.md) | `tools/go_evidence.py`, `tools/skills/evidence-driven-acceptance/SKILL.md`, `schemas/agent-runtime/evidence-manifest.schema.json`, `schemas/agent-runtime/final-verdict.schema.json` |
| Review-first governance kernel | [Review-First Governance Kernel Implementation Spec](status/review-first-governance-kernel-implementation-spec.md) and [Review-Governance Kernel Completion Status](status/review-governance-kernel-completion-20260706.md) | `tools/skills/review-governance-kernel/SKILL.md`, `schemas/review_governance_kernel.schema.json`, `packages/control-plane/tests/test_review_governance_kernel.py`; latest P3-2 graph projection status is local GPT-equivalent review PASS, committed in `2725227d`, local branch-level review PASS at `bd73d6bc`, still pending PR/CI and publication evidence and not release-ready |
| Skill asset utilization | [Skill Asset Utilization Plan](status/skill-asset-utilization-plan.md) | `tools/skills/*/SKILL.md`, `skill_registry.py`, `methodology_dispatch.py`, `custom_skills.py`, `visual_state.py` |
| Visual control plane and dashboard | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `visual_state.py`, `dashboard.py`, `execution_plan.py`, `schemas/visual_control_plane_state.schema.json` |
| T3/RD-Code client bridge | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `client_manifest.py`, `client_launcher.py`, `t3_adapter.py`, `t3_bridge_bundle.py`, `schemas/t3_client_shell.schema.json`, `schemas/t3_bridge_bundle.schema.json` |
| Action queue and human approval | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `dashboard.py`, `execution_plan.py`, `task_proposals.py`, `/api/t3/approval-response`, `/api/t3/cluster-run` |
| Web AI external brain | [Web AI Adapter Contract](agent-runtime/web-ai-adapter-contract.md) | `web_ai_mcp_recorder.py`, `provider_binding_probe.py`, `chrome_binding_probe.py`, `conversation_binding.py`, `external_review_bundle.py`, `tools/skills/bind-chrome/SKILL.md`, `tools/skills/external-brain/SKILL.md`, `schemas/web_ai_adapter.schema.json`, `schemas/external_review_bundle.schema.json` |
| MCP consent and local MCP server | [Agent Protocol Landscape](agent-runtime/agent-protocol-landscape.md) | `mcp_consent.py`, `mcp_server.py`, `mcp_live_probe.py`, `cli/_mcp.py` |
| ACP/OpenCode execution bridge | [Agent Protocol Landscape](agent-runtime/agent-protocol-landscape.md) | `acp_client.py`, `acp_session.py`, `opencode_events.py`, `workflow_engine.py` |
| Handoff and live transfer | [Reviewer Index](status/reviewer-index.md) | `handoff_generator.py`, `handoff_verifier.py`, `live_handoff_transfer.py`, `schemas/handoff_evidence_map.schema.json` |
| Writeback proposals | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `writeback.py`, `dashboard.py` `/api/t3/writeback-propose` |
| Pipelines and staged execution | [Integration Contracts](agent-runtime/integration-contracts.md) | `pipeline_spec.py`, `pipeline_runner.py`, `stage_executor.py` |
| Worktree isolation | [Visual Control Plane](agent-runtime/visual-control-plane.md) | `worktree.py`, `cluster_run.py`, `go_dispatch.py` |
| Model providers and run defaults | [Context-Led Model Performance Control Plan](status/context-led-model-performance-control-plan.md) | `model_providers.py`, `run_defaults.py`, `schemas/run_defaults.schema.json` |
| Context pack building | [Context Management Architecture Plan](status/context-management-architecture-plan.md) | `tools/skills/context-pack-builder/SKILL.md`, `context-noise-governance-and-automation-plan.md` |
| Graph projection and knowledge canvas | [Graph Projection And Knowledge Canvas Plan](status/graph-projection-knowledge-canvas-plan.md) | Deferred read-only projection/context-navigation module after review-governance kernel and projection derivation |
| Paper workflow | [rdpaper Workflow](agent-runtime/rdpaper-workflow.md) | `packages/ai-workflow-hub/src/ai_workflow_hub/workflows/paper_graph.py`, `paper_workflow_state.py`, paper schemas under `schemas/` |
| Paper knowledge-base iteration | [Paper Knowledge Base Iteration MVP Plan](status/paper-knowledge-base-iteration-mvp-plan.md) | Deferred paper-domain fixture module after the review-governance kernel, using Obsidian/RAG/external-brain substrate |
| Documentation governance | [Documentation Management Audit and Plan](status/documentation-management-audit-and-plan.md) | `docs/README.md`, `status/status-document-inventory.md`, `status/governance-spine-and-document-coordination.md` |

## Current Planning Docs

Use these documents to guide near-term architecture work:

- [Status Document Inventory](status/status-document-inventory.md)
- [Governance Spine And Document Coordination](status/governance-spine-and-document-coordination.md)
- [Unified Object Model Decision Record](status/unified-object-model-decision-record.md)
- [Governance Contradiction Matrix](status/governance-contradiction-matrix.md)
- [Governance Rules Spec](status/governance-rules-spec.md)
- [Context Noise Governance And Automation Plan](status/context-noise-governance-and-automation-plan.md)
- [Model Knowledge Gap Governance Plan](status/model-knowledge-gap-governance-plan.md)
- [Project And Cross-Project Memory Harness Governance Plan](status/project-and-cross-project-memory-harness-governance-plan.md)
- [Goal-Bound Evidence Gate Plan](status/goal-bound-evidence-gate-plan.md)
- [Paper Claim Integrity Gate To Cluster Plan](status/paper-claim-integrity-gate-to-cluster-plan.md)
- [Paper Knowledge Base Iteration MVP Plan](status/paper-knowledge-base-iteration-mvp-plan.md)
- [Human Attention Governance And Automation Maturity Plan](status/human-attention-governance-and-automation-maturity-plan.md)
- [Early Adopter User Asset Governance Plan](status/early-adopter-user-asset-governance-plan.md)
- [Competitive Moat And User Demand Critical Review](status/competitive-moat-and-user-demand-critical-review.md)
- [Document-Driven Transformation Master Plan](status/document-driven-transformation-master-plan.md)
- [Document-Driven Transformation Final Plan](status/document-driven-transformation-final-plan-20260705.md)
- [Design Coverage Gap Remediation Plan](status/design-coverage-gap-remediation-plan.md)
- [Review-First Governance Kernel Contraction Plan](status/review-first-governance-kernel-contraction-plan.md)
- [Review-First Governance Kernel Implementation Spec](status/review-first-governance-kernel-implementation-spec.md)
- [Reuse-First Constraint Governance Implementation Plan](status/reuse-first-constraint-governance-implementation-plan.md)
- [Skill Asset Utilization Plan](status/skill-asset-utilization-plan.md)
- [Workflow Consolidation and Command Plan](status/workflow-consolidation-and-command-plan.md)
- [Context Management Architecture Plan](status/context-management-architecture-plan.md)
- [Context-Led Model Performance Control Plan](status/context-led-model-performance-control-plan.md)
- [Graph Projection And Knowledge Canvas Plan](status/graph-projection-knowledge-canvas-plan.md)
- [Runtime Governance and Evidence Closure Transformation Plan](status/runtime-governance-and-evidence-closure-transformation-plan.md)
- [Runtime Governance Status Vocabulary Inventory](status/runtime-governance-status-vocabulary-inventory.md)
- [Evaluation, Feedback, and Learning Governance Plan](status/evaluation-feedback-learning-governance-plan.md)
- [Total-Control Policy Engine and Human Escalation Governance Plan](status/total-control-policy-engine-and-human-escalation-governance-plan.md)
- [Browser Automation Transport Roadmap](status/browser-automation-transport-roadmap.md)
- [Documentation Management Audit and Plan](status/documentation-management-audit-and-plan.md)
- [Documentation Management Detailed Rollout Plan](status/documentation-management-detailed-rollout-plan.md)

## Status And Evidence Records

Use [status](status/) for current release state, recon receipts, audit notes, and stage evidence.

Rules of thumb:

- `release-readiness.md` explains the current release boundary.
- `status-document-inventory.md` explains how to read `docs/status/` without treating every file as current authority.
- `governance-spine-and-document-coordination.md` explains how the active plans fit into one governance sequence.
- `current-coverage-audit-evidence-20260704.md` records the bounded evidence snapshot behind the master plan's current coverage audit.
- `working-tree-cleanup-inventory-20260705.md` classifies the current dirty tree into cleanup batches before UI/product design proceeds.
- `asset-utilization-inventory-20260705.md` records current repository and local agent asset counts, including skills, MCP, plugins, and runtime evidence.
- `unified-object-model-decision-record.md`, `governance-contradiction-matrix.md`, and `governance-rules-spec.md` are the current foundations for `document-driven-transformation-master-plan.md`.
- `context-noise-governance-and-automation-plan.md` explains how automated context management filters stale, irrelevant, disposable, or misleading material for high-frequency use.
- `model-knowledge-gap-governance-plan.md` explains how to stop model common sense from becoming unverified product or architecture judgment.
- `project-and-cross-project-memory-harness-governance-plan.md` explains how project memory and cross-project hints are governed, evaluated, isolated, and promoted.
- `goal-bound-evidence-gate-plan.md` explains why goal-based continuation should first be an evidence-backed gate decision, not a broad autonomous supervisor.
- `paper-claim-integrity-gate-to-cluster-plan.md` explains when paper-domain governance can grow from claim-level patch gates into a real paper R&D agent cluster.
- `paper-knowledge-base-iteration-mvp-plan.md` explains how the paper knowledge-base loop can later become a paper-domain fixture module after the review-governance kernel proves its first slice.
- `human-attention-governance-and-automation-maturity-plan.md` explains why automation exists to protect scarce human attention.
- `early-adopter-user-asset-governance-plan.md` explains how early users bring existing workflow assets into governed customization.
- `competitive-moat-and-user-demand-critical-review.md` separates real early-adopter needs from generic plugin or competitor-parity distractions.
- `document-driven-transformation-master-plan.md` coordinates implementation phases, stop lines, and proof requirements.
- `document-driven-transformation-final-plan-20260705.md` is the coding-agent-facing final candidate that consolidates the current planning set into the next executable sequence.
- `review-governance-kernel-completion-20260706.md` records latest review-governance kernel progress through P3-2 local GPT-equivalent review PASS; P3-2 landed in `2725227d` and has local branch-level review PASS at `bd73d6bc`, but is still pending PR/CI and publication evidence, so it is not a release-ready record.
- `runtime-governance-status-vocabulary-inventory.md` records current status families before Batch A schemas map them into separate lifecycle axes.
- `design-coverage-gap-remediation-plan.md` turns the cross-document gap review into a prioritized repair queue with acceptance evidence.
- `browser-automation-transport-roadmap.md` defers multi-browser automation into a later module while keeping the current stable path on CDP-family evidence.
- `graph-projection-knowledge-canvas-plan.md` explains how relationship graphs can later become a read-only projection and context-navigation layer for humans and AI agents.
- `review-first-governance-kernel-contraction-plan.md` narrows the next slice to the review-first governance kernel.
- `review-first-governance-kernel-implementation-spec.md` turns the narrowed slice into fixture, contract, and test requirements.
- `reuse-first-constraint-governance-implementation-plan.md` decides how to borrow mature open-source patterns before hand-rolling.
- `skill-asset-utilization-plan.md` routes existing project, local, and plugin skills into governed work types without displacing Phase 1A.
- `reviewer-index.md` is the reviewer map for the current public snapshot.
- `recon-receipt-*.md` records scoped pre-work and reuse assessments.
- `local-agent-control-plane-stage-*.md` records historical stage evidence.
- Planning documents should stay in `status/` until promoted to stable runtime documentation.

## Examples And Assets

- [examples](examples/) contains small consumer-facing examples.
- [assets](assets/) contains images used by documentation and README files.
- [negative-test-fixtures](agent-runtime/negative-test-fixtures/) contains acceptance failure fixtures used to keep gates honest.

## Documentation Governance

The current documentation governance plan is:

1. Keep `README.md` focused on product entry and quick start.
2. Keep `docs/README.md` as the documentation map.
3. Keep durable runtime rules in `docs/agent-runtime/`.
4. Keep active plans, receipts, and release evidence in `docs/status/`.
5. Promote stable plans out of `docs/status/` only after implementation proves them.
6. Archive or supersede stale status records instead of letting them compete with current guidance.

For details, see [Documentation Management Audit and Plan](status/documentation-management-audit-and-plan.md).
For the execution sequence, see [Documentation Management Detailed Rollout Plan](status/documentation-management-detailed-rollout-plan.md).
