# Runtime Governance Batch E: Team Review Verdict Events

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing runtime-governance team review and final-verdict integration

Post-read action: Verify that TeamRuntime can record independent review and governance final-verdict events without promoting worker execution results to acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice adds explicit review and final-verdict event references to the TeamRuntime journal and the read-only RunIndex projection.

Before this slice, TeamRuntime could record task lifecycle, worker results, workflow events, context refs, and explicit evidence refs. Worker success opened a review gate but could not create a passing review or final-ready acceptance state.

After this slice:

- `TeamRuntime.record_review_ref(...)` records an independent review artifact reference as a `review_ref` event;
- `TeamRuntime.record_final_verdict_ref(...)` records a governance final verdict artifact reference as a `final_verdict_ref` event;
- `build_team_runtime_view()` projects review and final verdict events into distinct event log, message bus, evidence store, and gate objects;
- `run_index` projects only valid `review_ref` events into RunRecord `review_refs`;
- `run_index` projects final-ready acceptance only when a valid governance final verdict references a passing independent review and passing gate;
- invalid self-review, worker-authored final verdicts, missing final verdict artifacts, and schema-invalid final verdict artifacts become blocked failure refs.

This slice does not automatically create review or final-verdict artifacts. It records and projects validated references when an upstream evidence gate or governance finalizer has already produced them.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_t3_adapter.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_team_runtime.py packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_t3_adapter.py -q
python -m pytest packages\control-plane\tests\test_go_team_runtime.py packages\control-plane\tests\test_workflow_engine.py packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Worker task results remain execution outcomes only.
- A passed worker with no final verdict remains review-pending, not final-ready.
- Reviewer roles `executor`, `fixer`, `coder`, and `worker` cannot satisfy independent review.
- Producer roles `executor`, `fixer`, `coder`, and `worker` cannot satisfy final verdict authority.
- `final_ready` requires a valid FinalVerdict artifact, passing independent review, and passing gate reference.
- Runtime data remains outside the public repository.

## Known Gaps

- Go evidence finalization can now opt into TeamRuntime event recording with
  `--team-runtime-dir`, but full go dispatch automation remains later work.
- Sealed ContextPacket/ContextLedger production for go/workflow dispatch is now
  covered by
  [Runtime Governance Batch F: Sealed Context Artifacts](runtime-governance-batch-f-sealed-context-artifacts.md).
- Legacy atgo review projections remain read-only compatibility adapters rather than TeamRuntime events.
