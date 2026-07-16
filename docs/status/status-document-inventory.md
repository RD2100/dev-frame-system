# Status Document Inventory

Lifecycle state: Draft active coordination record

Reader: DevFrame maintainers trying to understand which `docs/status` files are current guidance, which are evidence, and which are historical context.

Post-read action: choose the right status document for the question at hand, and avoid treating every file in `docs/status` as equally authoritative.

Related docs: [Documentation Management Audit and Plan](documentation-management-audit-and-plan.md), [Documentation Management Detailed Rollout Plan](documentation-management-detailed-rollout-plan.md), [Governance Spine And Document Coordination](governance-spine-and-document-coordination.md), [Reviewer Index](../status/reviewer-index.md)

## Purpose

`docs/status` is valuable because it preserves planning decisions, recon receipts,
release state, stage evidence, and handoff material. It is also risky because all
of those records currently sit at the same directory level.

This inventory does not move files. It gives the folder a working control map so
future planning can distinguish current authority from historical traceability.

## First-Read Path

For current governance planning, read in this order:

1. [docs/README.md](../README.md)
2. [Status Document Inventory](status-document-inventory.md)
3. [Governance Spine And Document Coordination](governance-spine-and-document-coordination.md)
4. [Reviewer Index](../status/reviewer-index.md)
5. The specific active plan or recon receipt that matches the task.

For release review, start with [Launch Now](LAUNCH_NOW.md), then
[Release Readiness](../status/release-readiness.md) and
[Reviewer Index](../status/reviewer-index.md) before reading planning material.

## Document States

Use these states when reading or editing files in this folder:

| State | Meaning | Default action |
|---|---|---|
| `current-entry` | Navigation or reviewer map for the current public snapshot | Keep linked from `docs/README.md` |
| `active-plan` | Current architectural direction, not yet a stable runtime contract | Use for planning; do not claim as implemented behavior |
| `deferred-module-plan` | A named module or capability path that is intentionally after the current implementation slice | Keep discoverable; do not schedule as current work unless the master plan is updated |
| `recon-receipt` | Scoped pre-work, reuse assessment, and decision record | Treat as authority only for its bounded scope |
| `release-state` | Current release boundary or readiness state | Keep exact and evidence-backed |
| `evidence-record` | Proof of a run, probe, audit, or live integration | Preserve for traceability; do not generalize beyond its scope |
| `handoff` | Continuation prompt or next-agent package | Useful during transition; not a durable product contract |
| `historical-stage` | Previous stage execution report or milestone trace | Preserve, but do not use as current authority without a newer link |
| `source-material` | External or exploratory research distilled into planning docs | Distill before promotion; do not make it normative directly |

## Current Entry Records

| File | Role | Notes |
|---|---|---|
| `LAUNCH_NOW.md` | Current launch-control entrypoint | Shortest go/no-go decision, blockers, and evidence map |
| `status-document-inventory.md` | Current status-folder control map | This file |
| `governance-spine-and-document-coordination.md` | Current cross-plan synthesis | Explains the governance sequence and next document writes |
| `reviewer-index.md` | Public-snapshot reviewer map | Should list active status docs that matter to review |
| `release-readiness.md` | Current release boundary | Use before judging release claims |

## Observed File Classification Snapshot

Observed on 2026-07-04, with review-governance completion status added on
2026-07-06, runtime-governance Batch A planning and contract evidence added on
2026-07-07, Batch B through Batch E implementation audit records added on
2026-07-08, Batch F sealed context artifact evidence added on 2026-07-08, and
Batch G generic go opt-in finalization evidence added on 2026-07-08, Batch H
ai-workflow-hub chain-evidence adapter evidence added on 2026-07-08, and Batch I
generic go prepare-evidence evidence added on 2026-07-08, and Batch J automatic
superseding FinalVerdict evidence added on 2026-07-08.
Update this snapshot when adding or retiring status documents.

| State | Files |
|---|---|
| `current-entry` | `LAUNCH_NOW.md`, `status-document-inventory.md`, `governance-spine-and-document-coordination.md`, `reviewer-index.md`, `release-readiness.md` |
| `active-plan` | `workflow-consolidation-and-command-plan.md`, `context-management-architecture-plan.md`, `context-noise-governance-and-automation-plan.md`, `context-led-model-performance-control-plan.md`, `model-knowledge-gap-governance-plan.md`, `project-and-cross-project-memory-harness-governance-plan.md`, `goal-bound-evidence-gate-plan.md`, `paper-claim-integrity-gate-to-cluster-plan.md`, `documentation-management-audit-and-plan.md`, `documentation-management-detailed-rollout-plan.md`, `runtime-governance-and-evidence-closure-transformation-plan.md`, `runtime-governance-status-vocabulary-inventory.md`, `evaluation-feedback-learning-governance-plan.md`, `total-control-policy-engine-and-human-escalation-governance-plan.md`, `human-attention-governance-and-automation-maturity-plan.md`, `early-adopter-user-asset-governance-plan.md`, `competitive-moat-and-user-demand-critical-review.md`, `unified-object-model-decision-record.md`, `governance-contradiction-matrix.md`, `governance-rules-spec.md`, `document-driven-transformation-master-plan.md`, `document-driven-transformation-final-plan-20260705.md`, `design-coverage-gap-remediation-plan.md`, `review-first-governance-kernel-contraction-plan.md`, `review-first-governance-kernel-implementation-spec.md`, `reuse-first-constraint-governance-implementation-plan.md`, `skill-asset-utilization-plan.md` |
| `deferred-module-plan` | `browser-automation-transport-roadmap.md`, `paper-knowledge-base-iteration-mvp-plan.md`, `graph-projection-knowledge-canvas-plan.md` |
| `area-plan` | `product-maturity-roadmap.md`, `local-agent-cluster-roadmap.md`, `cluster-coordinator-design-and-roadmap.md`, `phase-1-global-coordinator-conversation-plan.md`, `launch-cutover-checklist.md`, `agent-cluster-unknowns-register.md`, `global-lifecycle-gsd-superpowers-assessment.md`, `design-orchestration-mcp.md`, `design-devframe-mcp-orchestrator-surface.md` |
| `reuse-assessment` | `t3code-client-mainline-reuse-assessment.md`, `local-agent-control-plane-stage-8-open-source-reuse-visual-mvp.md` |
| `recon-receipt` | `recon-receipt-acp-backbone.md`, `recon-receipt-cli-decomposition.md`, `recon-receipt-cluster-control-surface.md`, `recon-receipt-customization-layer.md`, `recon-receipt-devframe-mcp-server.md`, `recon-receipt-go-dispatch-claim-propagation.md`, `recon-receipt-global-coordinator-conversation-mainline.md`, `recon-receipt-local-agent-client-mainline.md`, `recon-receipt-mcp-consent.md`, `recon-receipt-mcp-live-probe-sse.md`, `recon-receipt-obsidian-stage3.md`, `recon-receipt-obsidian-stage4-sync.md`, `recon-receipt-opencode-event-integration.md`, `recon-receipt-paper-pdf-fulltext-segmentation.md`, `recon-receipt-parallel-write-isolation.md`, `recon-receipt-pluggable-model-provider.md`, `recon-receipt-rd-code-prod-launch.md`, `recon-receipt-rdcode-bridge-data.md`, `recon-receipt-rdcode-writeback.md`, `recon-receipt-runtime-governance-unification.md`, `recon-receipt-t3-rebrand-i18n.md`, `recon-receipt-team-runtime.md`, `recon-receipt-team-runtime-claims.md`, `recon-receipt-team-runtime-messages.md`, `recon-receipt-workflow-engine.md` |
| `handoff` | `continue-global-coordinator-conversation-mainline.md`, `next-agent-global-coordinator-prompt.md`, `devframe-code-opencode-handoff.md` |
| `historical-stage` | `local-agent-control-plane-stage-2-acceptance.md`, `local-agent-control-plane-stage-2-precommit-review.md`, `local-agent-control-plane-stage-3-execution-report.md`, `local-agent-control-plane-stage-3-go-batch.md`, `local-agent-control-plane-stage-4-web-ai-binding.md`, `local-agent-control-plane-stage-5-closed-loop.md`, `local-agent-control-plane-stage-6-release-prep.md`, `local-agent-control-plane-stage-7-final-precommit-review.md` |
| `evidence-record` | `current-coverage-audit-evidence-20260704.md`, `working-tree-cleanup-inventory-20260705.md`, `asset-utilization-inventory-20260705.md`, `current-dirty-tree-batch-map-20260708.md`, `review-governance-kernel-completion-20260706.md`, `runtime-governance-batch-a-contract-completion.md`, `runtime-governance-batch-b-read-only-run-index.md`, `runtime-governance-batch-c-rdreview-prepare-only.md`, `runtime-governance-batch-d-independent-gate.md`, `runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md`, `runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md`, `runtime-governance-batch-e-atgo-runtime-finalize-command.md`, `runtime-governance-batch-e-chain-evidence-schema-compatibility.md`, `runtime-governance-batch-e-explicit-team-evidence-events.md`, `runtime-governance-batch-e-final-verdict-lifecycle.md`, `runtime-governance-batch-e-final-verdict-supersession-projection.md`, `runtime-governance-batch-e-go-evidence-team-runtime-finalization.md`, `runtime-governance-batch-e-paper-trust-fail-closed.md`, `runtime-governance-batch-e-team-context-refs.md`, `runtime-governance-batch-e-team-review-verdict-events.md`, `runtime-governance-batch-e-workflow-review-pending.md`, `runtime-governance-batch-f-sealed-context-artifacts.md`, `runtime-governance-batch-g-generic-go-opt-in-finalization.md`, `runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md`, `runtime-governance-batch-i-generic-go-prepare-evidence.md`, `runtime-governance-batch-j-automatic-superseding-final-verdict.md`, `evidence-web-ai-mcp-live-roundtrip.md`, `legacy-submodule-baseline.json` |
| `external-recon` | `codexpro-devspace-mcp-recon.md` |

## Active Planning Set

These files form the current planning spine. They should be read as design
direction, not as proof that the target system already exists.

For a shorter implementation entrypoint, use the implementation must-read pack
defined in `document-driven-transformation-master-plan.md` before opening the
full active planning set.

| File | Planning role |
|---|---|
| `workflow-consolidation-and-command-plan.md` | Normalizes user-facing commands and internal workflow layers |
| `context-management-architecture-plan.md` | Defines context planning, retrieval, budgeting, and context packets |
| `context-noise-governance-and-automation-plan.md` | Defines automated context-noise filtering for high-frequency agent work |
| `context-led-model-performance-control-plan.md` | Connects context quality to model performance and fair comparison |
| `model-knowledge-gap-governance-plan.md` | Defines how model assumptions, stale knowledge, and current-ecosystem gaps are checked before judgments guide implementation |
| `project-and-cross-project-memory-harness-governance-plan.md` | Defines project memory, cross-project memory hints, memory isolation, memory evaluation harnesses, and promotion boundaries |
| `goal-bound-evidence-gate-plan.md` | Defines goal-bound continuation as an evidence-backed gate decision rather than a broad Goal Supervisor runtime |
| `paper-claim-integrity-gate-to-cluster-plan.md` | Defines the paper-domain path from claim-level patch integrity gates to a later trusted paper R&D agent cluster |
| `documentation-management-audit-and-plan.md` | Defines the documentation content model and authority drift problem |
| `documentation-management-detailed-rollout-plan.md` | Turns documentation governance into rollout phases |
| `runtime-governance-and-evidence-closure-transformation-plan.md` | Defines the target runtime and evidence lifecycle |
| `runtime-governance-status-vocabulary-inventory.md` | Records current status families before Batch A schemas map them into separate lifecycle axes |
| `runtime-governance-batch-a-contract-completion.md` | Records local Batch A contract evidence without claiming release readiness |
| `runtime-governance-batch-b-read-only-run-index.md` | Records local Batch B read-only RunIndex evidence and remaining write-authority limits |
| `runtime-governance-batch-c-rdreview-prepare-only.md` | Records local Batch C prepare-only review evidence without external reviewer or final acceptance |
| `runtime-governance-batch-d-independent-gate.md` | Records local Batch D independent evidence-gate evidence and known runtime-journal gaps |
| `runtime-governance-batch-e-workflow-review-pending.md` | Records Batch E workflow behavior where worker success opens review but cannot pass acceptance |
| `runtime-governance-batch-e-paper-trust-fail-closed.md` | Records Batch E removal of terminal-status-to-chain-trust inference |
| `runtime-governance-batch-e-explicit-team-evidence-events.md` | Records Batch E explicit TeamRuntime evidence reference events |
| `runtime-governance-batch-e-team-context-refs.md` | Records Batch E legacy context reference visibility for TeamRuntime and RunIndex |
| `runtime-governance-batch-e-team-review-verdict-events.md` | Records Batch E independent review and final-verdict reference projection limits |
| `runtime-governance-batch-e-go-evidence-team-runtime-finalization.md` | Records Batch E opt-in TeamRuntime finalization references from go_evidence |
| `runtime-governance-batch-e-atgo-runtime-finalize-command.md` | Records Batch E manual atgo finalizer command guidance with runtime directory |
| `runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md` | Records Batch E guidance-only finalizer metadata in atgo prepare artifacts |
| `runtime-governance-batch-e-chain-evidence-schema-compatibility.md` | Records Batch E chain-evidence schema compatibility and guidance-only next commands |
| `runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md` | Records Batch E fail-closed ai-workflow-hub chain-evidence shape classification |
| `runtime-governance-batch-e-final-verdict-lifecycle.md` | Records Batch E FinalVerdict supersedes lifecycle metadata |
| `runtime-governance-batch-e-final-verdict-supersession-projection.md` | Records Batch E read-only FinalVerdict supersession projection and diagnostics |
| `runtime-governance-batch-f-sealed-context-artifacts.md` | Records Batch F sealed ContextPacket/ContextLedger production for go/workflow dispatch |
| `runtime-governance-batch-g-generic-go-opt-in-finalization.md` | Records Batch G explicit opt-in finalization for generic go/code execute runs |
| `runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md` | Records Batch H non-authoritative ai-workflow-hub chain-evidence adapter behavior |
| `runtime-governance-batch-i-generic-go-prepare-evidence.md` | Records Batch I prepare-only generic go/code evidence draft behavior |
| `runtime-governance-batch-j-automatic-superseding-final-verdict.md` | Records Batch J governance-finalizer automatic FinalVerdict superseding behavior |
| `evaluation-feedback-learning-governance-plan.md` | Defines evaluation, feedback, learning, and promotion boundaries |
| `total-control-policy-engine-and-human-escalation-governance-plan.md` | Defines policy decisions, escalation, and authority limits |
| `human-attention-governance-and-automation-maturity-plan.md` | Defines human attention as a governed resource and classifies automation maturity |
| `early-adopter-user-asset-governance-plan.md` | Defines how experienced users bring existing skills, prompts, MCP tools, rules, evidence recipes, and workflows into governed assets |
| `competitive-moat-and-user-demand-critical-review.md` | Critiques competitor features and separates real early-adopter needs from premature or false needs |
| `unified-object-model-decision-record.md` | Freezes the phase-one governance object kernel |
| `governance-contradiction-matrix.md` | Names and resolves cross-plan contradictions before integration |
| `governance-rules-spec.md` | Turns the object model into phase-one operational rules |
| `document-driven-transformation-master-plan.md` | Coordinates the document-driven transformation phases and stop lines |
| `document-driven-transformation-final-plan-20260705.md` | Coding-agent-facing final candidate that consolidates the current planning set into the next executable sequence |
| `design-coverage-gap-remediation-plan.md` | Turns cross-document coverage gaps into a prioritized remediation queue |
| `review-first-governance-kernel-contraction-plan.md` | Narrows the next implementation discussion to the review-first governance kernel |
| `review-first-governance-kernel-implementation-spec.md` | Defines the first fixture, contract, and test package for development |
| `reuse-first-constraint-governance-implementation-plan.md` | Plans how to reuse open-source patterns without hand-rolling or over-adopting dependencies |
| `skill-asset-utilization-plan.md` | Routes existing skills into governed work types and defers deeper skill telemetry until the kernel exists |

## Deferred Module Planning Set

These files are part of the visible roadmap, but they are not the current
implementation target. Read them after the review-first governance kernel and
reuse-first constraints if the question is about later modules.

| File | Deferred role |
|---|---|
| `browser-automation-transport-roadmap.md` | Defines the later multi-browser transport path; current browser automation should keep using the CDP-family binding unless the master plan is revised |
| `paper-knowledge-base-iteration-mvp-plan.md` | Defines a later paper-domain fixture module for knowledge-base iteration after the review-governance kernel exists |
| `graph-projection-knowledge-canvas-plan.md` | Defines a later read-only graph projection and human-editable canvas layer for code, docs, and knowledge relationships |

The next implementation planning records should be derived from:

1. `document-driven-transformation-master-plan.md`
2. `document-driven-transformation-final-plan-20260705.md`
3. `unified-object-model-decision-record.md`
4. `governance-rules-spec.md`
5. `review-first-governance-kernel-contraction-plan.md`
6. `review-first-governance-kernel-implementation-spec.md`
7. `reuse-first-constraint-governance-implementation-plan.md`
8. `skill-asset-utilization-plan.md`
9. `model-knowledge-gap-governance-plan.md`
10. `context-noise-governance-and-automation-plan.md`
11. `project-and-cross-project-memory-harness-governance-plan.md`
12. `goal-bound-evidence-gate-plan.md`
13. `paper-claim-integrity-gate-to-cluster-plan.md`
14. `human-attention-governance-and-automation-maturity-plan.md`
15. `early-adopter-user-asset-governance-plan.md`
16. `competitive-moat-and-user-demand-critical-review.md`

## Recon Receipts

`recon-receipt-*.md` files are scoped pre-work records. They satisfy the
reuse-before-building discipline for a specific area, such as:

- ACP backbone;
- client and T3 bridge surfaces;
- cluster control;
- customization layer;
- DevFrame MCP server;
- global coordinator conversation mainline;
- local agent client mainline;
- MCP consent and live probe;
- OpenCode event integration;
- parallel write isolation;
- pluggable model provider;
- RDCode bridge data and writeback;
- runtime governance and evidence unification;
- team runtime;
- workflow engine.

Rule: a recon receipt may justify work in its own scope, but it should not be
used as the whole-platform architecture. If a later active plan supersedes part
of a receipt, link both documents and state the boundary explicitly.

## Stage And Evidence Records

The `local-agent-control-plane-stage-*.md` files, `evidence-*.md` files, and
similar execution records are historical evidence. They are useful for proving
how a capability matured, but they are not the first place to look for current
product direction.

`review-governance-kernel-completion-20260706.md` is the latest bounded
review-governance progress record: P1/P2/P3-1 are marked PASS, and P3-2 graph
projection has local GPT-equivalent review PASS and landed in commit
`2725227d`, with local branch-level review PASS at `bd73d6bc`. The current release route now has PR CI, main CI, merge, and GitHub Release evidence, but PyPI publication remains outside this repository's defined workflow. Do not use that record by itself as release readiness evidence.

Current rule:

- preserve them;
- avoid rewriting their original claims;
- add lifecycle labels when touched;
- link newer plans when a stage record is no longer the current authority.

## Handoff Records

Files such as `continue-global-coordinator-conversation-mainline.md`,
`next-agent-global-coordinator-prompt.md`, and
`devframe-code-opencode-handoff.md` are handoff material. They are valuable
because they make work transferable, but they should expire as authority after
their instructions are consumed into active plans, stable docs, or implemented
contracts.

Current rule: use handoff files for continuity, then retire their claims into a
decision record or stable doc before implementing major new behavior.

## Current Authority Rules

1. A status document is not authoritative merely because it exists.
2. Stable runtime behavior belongs in `docs/agent-runtime/` only after a vertical
   workflow proves it.
   `docs/agent-runtime/agent-coding-discipline.md` is explicitly an operating
   discipline and planning sidecar, not a stable runtime behavior claim.
3. Active plans may set direction, but they must not describe target behavior as
   implemented fact.
4. Recon receipts are scoped and cannot override newer cross-plan decisions.
5. RDCode/T3/client documents describe projection surfaces unless a backend
   governance document explicitly grants write authority.
6. External research must be distilled into a repo-local decision record before
   it becomes a planning dependency.
7. If two status documents conflict, the newer coordination record should name
   the conflict instead of silently choosing one side.
8. Any external-review export is disposable. It is not a source of truth.

## External Review Export Hygiene

Before any external or web-GPT consistency review:

1. create the export from the source documents in `docs/status/`;
2. keep the export temporary and at or below the upload limit;
3. verify every copied file has a matching source document or an explicit source
   note;
4. verify copied file hashes match the source files after refresh;
5. record the export time or state in the review prompt or handoff note;
6. block review upload if the export is stale.

The export package exists to make review convenient. It must not become a second
authority layer.

## Known Consolidation Work

The folder still needs these follow-up improvements:

- add lifecycle labels to older active and historical files when they are next
  edited;
- derive kernel fixtures and contracts from the master plan;
- promote proven runtime contracts out of `docs/status` only after tests and
  evidence exist;
- keep `docs/README.md`, this inventory, `reviewer-index.md`, and
  `document-driven-transformation-master-plan.md` synchronized whenever a new
  public subsystem or deferred module is added. This is now guarded by
  `packages/control-plane/control_plane/docs_drift_validator.py`,
  `packages/control-plane/tests/test_docs_drift_validator.py`, and the
  lightweight current-entry checks in
  `packages/control-plane/tests/test_public_snapshot.py`.
