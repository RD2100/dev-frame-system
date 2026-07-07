# Runtime Governance Batch E: Team Context Refs

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing runtime-governance team task lifecycle integration

Post-read action: Verify that go-run task lifecycle events record legacy context boundary references without claiming final acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice records the context boundary available to go workers when a task is created and claimed.

Before this slice, TeamRuntime task events recorded the run, agent, shard, and targets, but not the packet or TaskSpec path that bounded the worker's assigned context.

After this slice:

- `TeamRuntime.record_task_created(...)` and `record_task_claimed(...)` accept optional `context_refs`;
- `go_dispatch` passes each agent's legacy packet directory and `TASKSPEC.json` path into those lifecycle events during real execute and resume paths;
- `build_team_runtime_view()` projects those refs into `evidence_store` as provenance-only legacy context refs;
- `run_index` projects team context refs into RunRecord context evidence with `supports=limitation`;
- legacy team journals without `context_refs` remain readable.

This slice does not create a sealed Runtime Governance `ContextPacket`, does not validate context completeness, and does not change review, gate, or final-verdict authority.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_go_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_workflow_engine.py`
- `packages/control-plane/tests/test_t3_adapter.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_team_runtime.py packages\control-plane\tests\test_go_team_runtime.py packages\control-plane\tests\test_run_index.py -q
python -m pytest packages\control-plane\tests\test_workflow_engine.py packages\control-plane\tests\test_t3_adapter.py packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Legacy context refs are provenance, not proof of context completeness.
- No worker or executor event may satisfy independent review or final readiness.
- Missing context refs must not break legacy journals.
- Runtime data remains outside the public repository.

## Known Gaps

- Sealed ContextPacket/ContextLedger production for go/workflow remains later work.
- Independent ReviewRecord and FinalVerdict TeamRuntime events remain later integration work.
