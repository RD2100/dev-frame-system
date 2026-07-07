# Runtime Governance Batch E: Workflow Review Pending

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing runtime-governance workflow integration

Post-read action: Verify that worker execution success remains review-pending until an independent review or final verdict artifact exists.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

Batch E applies the first fail-closed workflow integration slice:

- worker task results remain execution outcomes only;
- successful worker results open review gates instead of passing them;
- workflow all-worker-success records `awaiting_review`, not `continue`;
- visual and T3 read models show passed go-run execution as an open review gate.

This batch does not rename legacy commands, move runtime storage, create a writable canonical run registry, or implement live external review submission.

## Changed Runtime Semantics

Before this slice, a worker report with `Status: pass` could flow through go-run metadata into TeamRuntime review gates and visual go-run outcome gates as `pass`. The workflow engine could also derive a reviewer-style `continue` verdict directly from worker status.

After this slice:

- `workflow_engine.py` returns `awaiting_review` when all workers succeeded;
- the recorded workflow review phase is owned by the controller and says independent review is required;
- `team_runtime.py` maps worker success to an open acceptance gate with an explicit independent-review-required reason;
- `visual_state.py` maps terminal passed go-runs to an open go-run outcome gate.

Failed and blocked worker/run states continue to project as failed or blocked.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_workflow_engine.py`
- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_go_team_runtime.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/tests/test_t3_adapter.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_workflow_engine.py packages\control-plane\tests\test_team_runtime.py packages\control-plane\tests\test_go_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_rdgoal.py packages\control-plane\tests\test_t3_adapter.py -q
python -m pytest packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- No worker or executor result may satisfy independent review.
- No read model may convert execution success into review pass.
- No workflow verdict may claim final readiness without a FinalVerdict artifact.
- Existing `devframe go`, `devframe workflow`, and dashboard commands remain compatibility surfaces.

## Known Gaps

- Independent review and final verdict events are covered by the follow-up
  [Runtime Governance Batch E: Team Review Verdict Events](runtime-governance-batch-e-team-review-verdict-events.md)
  slice and the @go finalization slices.
- Legacy context refs on task lifecycle events are handled in
  [Runtime Governance Batch E: Team Context Refs](runtime-governance-batch-e-team-context-refs.md);
  sealed ContextPacket production remains deferred.
- Paper workflow trust inference is handled in
  [Runtime Governance Batch E: Paper Trust Fail Closed](runtime-governance-batch-e-paper-trust-fail-closed.md).
