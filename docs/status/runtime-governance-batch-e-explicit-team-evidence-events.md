# Runtime Governance Batch E: Explicit Team Evidence Events

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing runtime-governance team event integration

Post-read action: Verify that go-run execution reports are recorded as explicit team evidence events, not only inferred from task results.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice moves TeamRuntime evidence one step closer to the canonical runtime lifecycle.

Before this slice, a worker `task_result` event could carry `report_path`, and `build_team_runtime_view()` projected that field into `evidence_store`.

After this slice:

- `TeamRuntime.record_result(..., report_path=...)` records the worker result and appends an explicit `evidence_ref` event;
- `build_team_runtime_view()` folds `evidence_ref` events into `evidence_store`;
- old journals that only have `task_result.report_path` still project evidence for compatibility;
- new journals avoid double-counting the same report path when both events are present;
- `run_index` projects explicit team `evidence_ref` events into RunRecord evidence refs while preserving legacy `task_result.report_path` fallback;
- visual/T3 state avoids appending recorded team evidence when a projected go-run report already points at the same run and path;
- `run_go_dispatch(... execute=True)` and prepared go-run resume both record evidence refs on the real execution path.

This slice does not implement independent ReviewRecord ingestion, FinalVerdict ingestion, or sealed ContextPacket production for go/workflow task events.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_go_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_t3_adapter.py`
- `packages/control-plane/tests/test_workflow_engine.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_team_runtime.py packages\control-plane\tests\test_go_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_workflow_engine.py -q
python -m pytest packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_t3_adapter.py packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Evidence references remain artifact pointers, not acceptance authority.
- Worker task results still cannot pass review gates.
- Legacy team journals remain readable.
- Runtime data remains outside the public repository.

## Known Gaps

- Independent review and final verdict events remain later integration work.
- Sealed ContextPacket production for go/workflow task lifecycle events remains deferred.
