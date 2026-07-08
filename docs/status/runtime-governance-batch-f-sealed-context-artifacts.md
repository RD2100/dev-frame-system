# Runtime Governance Batch F: Sealed Context Artifacts

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing go/workflow context artifact production

Post-read action: Verify that go task dispatch now creates sealed context artifacts and that final-ready projection remains fail-closed when sealed context is missing.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: Team Context Refs](runtime-governance-batch-e-team-context-refs.md), [Runtime Governance Batch E: Team Review Verdict Events](runtime-governance-batch-e-team-review-verdict-events.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch F slice turns Batch E context references from legacy provenance into
real, schema-compatible context artifacts for go/workflow task dispatch.

Before this slice, TeamRuntime could record packet and `TASKSPEC.json` paths as
legacy `context_refs`, but those refs did not prove a sealed Runtime Governance
`ContextPacket` or append-only `ContextLedger` existed.

After this slice:

- `DispatchPacketStore.write_packet(...)` creates `context-packet.json` and
  `context-ledger.json` beside every rdgoal/go dispatch packet;
- `DispatchPacketStore.ensure_context_artifacts(...)` backfills the same files
  for older prepared packets before execution/finalization paths need them;
- `go_dispatch` attaches `context_packet`, `context_ledger`,
  `legacy_context`, and `legacy_task_spec` refs to `task_created` and
  `task_claimed` events during execute and resume paths;
- `tools/go_evidence.py finalize --team-runtime-dir <dir>` can backfill those
  go-run context refs before recording review and FinalVerdict refs;
- `run_index` projects sealed context packets as context evidence, projects
  context ledgers as artifacts, and blocks `final_ready` if a passed worker has
  no valid sealed context packet plus context ledger.

This slice is still dispatch/context scoped. It does not add generic `go`
automatic finalization, paper or ai-workflow-hub domain adapters, automatic
superseding FinalVerdict generation, runtime storage migration, or dashboard
authority changes.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_go_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/tests/test_team_runtime.py`
- `packages/control-plane/tests/test_t3_adapter.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_go_team_runtime.py packages\control-plane\tests\test_team_runtime.py packages\control-plane\tests\test_run_index.py -q
python -m pytest packages\control-plane\tests\test_cli.py packages\control-plane\tests\test_rdgoal.py packages\control-plane\tests\test_t3_adapter.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py packages\control-plane\tests\test_docs_drift_validator.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- A sealed ContextPacket authorizes execution context only; it is not review
  approval.
- ContextLedger presence is artifact evidence, not acceptance authority.
- `final_ready` still requires a valid FinalVerdict artifact, passing
  independent review, passing gate reference, and sealed context for passed
  workers.
- Default generic go automatic finalization remains out of scope.
- Runtime data remains outside the public repository.

## Follow-Up Status

- Explicit opt-in generic `go` / `code execute` finalization is covered by
  [Runtime Governance Batch G: Generic Go Opt-In Finalization](runtime-governance-batch-g-generic-go-opt-in-finalization.md).
- Default generic `go` automatic finalization and automatic evidence production
  remain out of scope.
- Paper and ai-workflow-hub adapters still need canonical context normalization.
- Automatic superseding FinalVerdict generation remains deferred.
- Dashboard authority and runtime storage migration remain deferred.
