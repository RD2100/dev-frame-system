---
name: review-governance-kernel
description: Review-first governance kernel implementation discipline. Use when user says "@review-kernel", "review governance kernel", "review-first kernel", "Phase 1A", "governance schema", "review-governance fixtures", or when implementing the next DevFrame governance slice that must stay limited to schema, fixtures, and negative tests.
---

# review-governance-kernel - Phase 1A Discipline

Role: implementation-boundary skill. Use it to keep the next governance work
small enough for a coding agent to complete and verify.

## Current Contract

Implement only the review-governance kernel contract slice:

```text
Project -> WorkItem(kind=review) -> Artifact(kind=context_snapshot) -> Run
-> Artifact(output) -> Evidence -> Decision(kind=review)
-> Decision(kind=gate) -> Projection(read-only status)
```

This is a schema, fixture, and negative-test slice. It is not a runtime
migration and not a product command.

## Allowed First-Package Files

- `schemas/review_governance_kernel.schema.json`
- `schemas/examples/review-governance/success.json`
- `schemas/examples/review-governance/blocked.json`
- `schemas/examples/review-governance/insufficient-evidence.json`
- `schemas/examples/review-governance/missing-context.json`
- `packages/control-plane/tests/test_review_governance_kernel.py`

Optional only if schema-only validation causes duplicated status logic:

- `packages/control-plane/control_plane/review_governance_kernel.py`

## Required Negative Cases

- Missing context snapshot cannot become ready.
- `Run.status=succeeded` cannot complete a work item without a gate decision.
- A review report without evidence references becomes `insufficient_evidence`.
- Projection cannot mark a work item `completed` without backend decisions.

## Verification

Run:

```powershell
python -m pytest packages/control-plane/tests/test_review_governance_kernel.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

## Compatibility References

Use these as references, not migration targets:

- `rdgoal` dispatch packets and runtime digest;
- `WorkflowEngine` phase language;
- `TeamRuntime` event/read-model lessons;
- visual state and T3 projection discipline;
- existing evidence schemas and finalizer behavior.

## Hard Stops

- Do not create a full `/rdreview` UX.
- Do not migrate runtime storage.
- Do not add coordinator autonomy, RDCode writeback, model routing, memory,
  LangGraph, Temporal, or a plugin marketplace.
- Do not add top-level `ContextPacket`, `Review`, `Verdict`,
  `HumanApproval`, `GoalSupervisor`, or `UserAsset` objects.
- Do not treat report text as evidence.
