# Runtime Governance Status Vocabulary Inventory

Lifecycle state: Draft active plan support record

Reader: DevFrame maintainers preparing the Batch A runtime-governance contract
schemas.

Post-read action: design ContextPacket, ContextLedger, and RunRecord status
fields without treating legacy pass/completed terms as final acceptance.

Related docs: [Runtime Governance and Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Recon Receipt](recon-receipt-runtime-governance-unification.md), [Reviewer Index](reviewer-index.md)

## Purpose

The runtime-governance plan requires a status-vocabulary inventory before the
ContextPacket, ContextLedger, and RunRecord schemas are written. This document
records the current status families that matter to runtime governance, evidence,
review, and projections.

This is not a canonical schema. It is a factual mapping record so the next
contract slice can preserve domain-native terms while preventing unsafe status
promotion.

## Scope

In scope:

- current control-plane execution, evidence, review, gate, final-verdict, paper,
  test-frame, and visual projection status families;
- status words that could affect run lifecycle, review, evidence, or acceptance;
- mapping risks and stop lines for the next schema slice.

Out of scope:

- changing runtime behavior;
- changing CLI routing;
- normalizing code paths;
- changing dashboard badges;
- changing paper or test-frame execution;
- declaring a canonical RunRecord schema complete.

## Required Lifecycle Axes

The future RunRecord must not use one overloaded status field. The runtime plan
already separates these axes:

| Axis | Question Answered | Must Not Mean |
|---|---|---|
| `phase` | Where is the run in the lifecycle? | Whether the work succeeded |
| `outcome` | What happened mechanically? | Whether the work is accepted |
| `review_state` | Has an independent review happened? | Worker self-approval |
| `gate_state` | What did a verification gate decide? | Governance final verdict |
| `acceptance_state` | What may be claimed externally? | Test pass or worker completion |
| `projection_state` | What should a UI or read model display? | Source-of-truth authority |

## Status Families

| Family | Source | Current Terms | Meaning Today | Batch A Mapping Note |
|---|---|---|---|---|
| Evidence finalizer verdict | `tools/go_evidence.py` | `pass`, `blocked`, `fail`, `escalate` | Review YAML verdicts and finalizer output for evidence directories | Input to `review_state` or `gate_state`; `pass` is not `final_ready` |
| Independent review schema | `schemas/agent-runtime/review.schema.json` | `pass`, `blocked`, `fail`, `escalate`; finding status `open`, `resolved`, `false_positive` | Machine-readable independent reviewer result | Valid reviewer input only when signer is not executor/fixer/coder |
| Gate result schema | `schemas/agent-runtime/gate-result.schema.json` | `pass`, `fail`, `blocked`, `warning`, `skipped` | A verification gate result considered by reviewers or final verdicts | `pass` supports a gate, not acceptance by itself |
| Final verdict schema | `schemas/agent-runtime/final-verdict.schema.json` | `final_ready`, `accepted_with_limitation`, `blocked`, `failed`, `deferred` | Governance-owned final claim | Only this family can drive `acceptance_state` |
| Evidence manifest eligibility | `schemas/agent-runtime/evidence-manifest.schema.json` | `eligible_clean`, `eligible_with_limitations`, `needs_more_evidence`, `not_eligible` | Evidence pack completeness and verdict eligibility | Eligibility is a precondition, not a verdict |
| Failure record schema | `schemas/agent-runtime/failure-record.schema.json` | `blocked`, `failed`, `warning`, `open`, `resolved` | Classified failure or blocker | Feeds failure evidence and gate decisions |
| Review-governance work item | `schemas/review_governance_kernel.schema.json` | `draft`, `ready`, `running`, `reviewing`, `blocked`, `insufficient_evidence`, `completed` | Review-first WorkItem lifecycle | Candidate source for `phase` and `projection_state`, not acceptance |
| Review-governance run | `schemas/review_governance_kernel.schema.json` | run status `prepared`, `running`, `succeeded`, `failed`, `blocked`; claimed result `success`, `failure`, `blocked`, `inconclusive` | Executor-side run facts and claims | `succeeded`/`success` remain mechanical until reviewed |
| Review-governance decision | `schemas/review_governance_kernel.schema.json` | `pass`, `fail`, `blocked`, `insufficient_evidence`, `human_required`, `hard_stop`, `pause` | Review, gate, or adoption decision | Requires evidence IDs for pass decisions |
| Review-governance projection | `schemas/review_governance_kernel.schema.json` | `draft`, `ready`, `running`, `reviewing`, `blocked`, `insufficient_evidence`, `completed`, `waiting_for_you`, `archived` | Derived read model status | Projection only; do not write back as source truth |
| Workflow engine phase/verdict | `packages/control-plane/control_plane/workflow_engine.py` | phase status `started`, `completed`; result status from go run; reviewer verdict `continue`, `revise`, `stop` | Recorded plan/execute/review phase loop | `continue` means controller next move, not acceptance |
| Workflow worker success set | `packages/control-plane/control_plane/workflow_engine.py` | `pass`, `passed`, `completed`, `verified`; failures `failed`, `fail`, `error` | Worker-status aggregation for workflow reviewer verdict | Aggregation cannot replace independent ReviewRecord |
| Go visual projection | `packages/control-plane/control_plane/visual_state.py` | go run `queued`, `running`, `passed`, `failed`, `blocked`, `review-pass`, `review-fail`, `verified`; aliases `pass`, `completed` -> `passed` | Dashboard/read-model normalization for go runs | Display only; `review-pass` requires source evidence before acceptance |
| Web AI review projection | `packages/control-plane/control_plane/visual_state.py` | positive tokens -> `pass`; negative tokens -> `blocked`; otherwise `open` | Imported Web AI review read model | Review import can open next action, not final local acceptance |
| Session projection | `packages/control-plane/control_plane/visual_state.py` | `completed`, `blocked`, `needs_human`, `active`, `idle`, `unknown` | UI/session display status | Session completion is not final verdict |
| Paper workflow state | `packages/ai-workflow-hub/src/ai_workflow_hub/workflows/paper_workflow_state.py` and `paper_graph.py` | acceptance status examples `accepted`, `accepted_with_limitation`, `blocked`, `human_required`; chain trust booleans | Paper-domain acceptance and governance summary | Domain adapter must preserve human/privacy gates |
| Paper run governance summary | `packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py` | run status `passed`, `blocked`, `unknown`; `chain_trusted` boolean | Legacy paper evidence summary and CLI/Markdown display | Batch E removed terminal-status trust fallback; only explicit JSON boolean `chain_trusted=true` is trusted |
| Paper runtime adapter | `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters/paper_runtime.py` | final status `completed`, `blocked`, `error`; task queue maps to `passed`, `blocked`, `failed` | Paper runtime bridge into task queue | `completed` maps to mechanical task pass, not general acceptance |
| Test-frame canonical status | `packages/test-frame/orchestrator/stage.py` and `packages/test-frame/orchestrator/gate.py` | `passed`, `failed`, `skipped`, `blocked`, `error`, `cancelled` | Test tool and stage result vocabulary | `passed` supports `outcome`, while `blocked/error/cancelled` must not be hidden |
| Test-frame aggregate status | `packages/test-frame/aggregator/report.py` | overall `passed`, `failed`, `blocked`; quality gate `passed` boolean; verdict `codeReview=PASS` default | Test aggregation summary and generated report verdicts | Passing aggregate or default code-review verdict is not a final verdict without evidence and review links |

## Unsafe Promotions

These mappings are forbidden in the next schema slice:

- lifecycle or queue states `queued`, `pending`, `prepared`, `ready`, `draft`,
  `started`, `running`, `active`, `leased`, or `dispatched` -> `pass` or
  `final_ready`;
- worker or run-only `pass`, `passed`, `completed`, `verified`, `executed`, or
  `succeeded` -> `final_ready`;
- workflow `continue`, `revise`, or `stop` -> review `pass` or `final_ready`;
- gate `pass` -> `final_ready` without a valid FinalVerdict;
- evidence manifest `eligible_clean` -> review `pass`;
- projection `completed` -> source-of-truth completion;
- paper `completed` -> generic runtime acceptance;
- paper run status `passed` or `blocked` -> trusted chain or acceptance;
- test-frame `passed` -> governance final acceptance;
- test-frame default `codeReview=PASS` -> independent review pass;
- `skipped`, `warning`, `open`, `info`, `missing`, `unknown`, `unreadable`,
  `insufficient_evidence`, `human_required`, `waiting_for_you`, or
  `needs_human` -> `pass` or `final_ready`;
- `blocked`, `failed`, `fail`, `error`, or `cancelled` -> `pass` or
  `final_ready`;
- visual heuristic `approved`, `accepted`, or `proceed` -> `pass` or
  `final_ready`;
- unknown or unmapped statuses -> `pass`, `completed`, or `final_ready`.

The removed paper terminal-status chain trust fallback remains the reference
example of fail-open legacy behavior for future negative tests.

## Safe Mapping Direction

Batch A schemas should map legacy status into separate axes:

| Legacy Signal | Safe Axis | Safe Target |
|---|---|---|
| queued/prepared/ready/draft | `phase` | prepared/planned |
| running/active/reviewing | `phase` | running/reviewing |
| passed/pass/succeeded/completed/verified | `outcome` | succeeded or completed mechanically |
| failed/fail/error/cancelled | `outcome` | failed or interrupted |
| blocked/hard_stop | `outcome` or `gate_state` | blocked |
| skipped | `outcome` | skipped with limitation |
| pass from independent review | `review_state` | review_passed |
| blocked/fail/escalate from independent review | `review_state` | review_blocked/review_failed/escalated |
| pass from gate result | `gate_state` | gate_passed |
| warning/skipped from gate result | `gate_state` | gate_limited/gate_skipped |
| final_ready | `acceptance_state` | final_ready |
| accepted_with_limitation/deferred | `acceptance_state` | accepted_with_limitation/deferred |
| waiting_for_you/needs_human/human_required | `projection_state` or `gate_state` | human_required |

## Required Negative Cases For The Next Schema Slice

The first ContextPacket/ContextLedger/RunRecord fixtures should include:

1. worker `succeeded` with no review artifact -> not accepted;
2. gate `pass` with no evidence IDs -> invalid or blocked;
3. final report text says PASS but FinalVerdict JSON is missing -> blocked;
4. executor-authored review verdict `pass` -> rejected;
5. test-frame aggregate `passed` with missing context packet -> insufficient evidence;
6. test-frame generated `codeReview=PASS` with no independent review record -> not reviewed;
7. paper workflow `completed` with `acceptance_status=human_required` -> human required;
8. paper run status `blocked` without explicit boolean `chain_trusted=true` -> blocked, not trusted;
9. unknown domain adapter status -> explicit unknown mapping, no pass;
10. projection `completed` without source run/evidence links -> projection-only.

## Batch A Design Rules

- Preserve source-domain status terms in source references.
- Store normalized values in separate lifecycle axes.
- Require explicit evidence references before `review_state=review_passed`.
- Require FinalVerdict before `acceptance_state=final_ready`.
- Treat projections as derived and disposable.
- Treat missing, unknown, ambiguous, or unmapped statuses as blocked,
  insufficient evidence, or human-required.
- Keep public status inventory in `docs/status` until a vertical workflow proves
  the runtime contract and promotes it to stable `docs/agent-runtime`.

## Verification Notes

This inventory was built from the paths listed in the Status Families table and
from the current runtime-governance plan and recon receipt. The next schema
slice should cite this inventory when defining enum names, fixture expectations,
and negative tests.
