# Runtime Governance Batch B Read-Only Run Index Audit

Lifecycle state: Evidence record for the first Batch B read-only registry slice

Reader: DevFrame maintainers reviewing whether the runtime-governance Batch B
RunIndex slice is locally useful without changing legacy runtime authority.

Post-read action: use this record to review the read-only adapter evidence; do
not treat it as release readiness, runtime migration, CLI/dashboard integration,
PR, CI, or publication evidence.

Related docs: [Runtime Governance and Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch A Contract Completion Audit](runtime-governance-batch-a-contract-completion.md), [Runtime Governance Status Vocabulary Inventory](runtime-governance-status-vocabulary-inventory.md), [Reviewer Index](reviewer-index.md)

## Scope Decision

Batch B starts with a small read-only RunIndex. It adapts legacy runtime files
into schema-compatible RunRecord projections, but it does not move runtime
files, change workflow execution, change slash-command routing, change
dashboard authority, create a writable registry, or claim final acceptance.

## Deliverable Evidence

| Deliverable | Evidence |
|---|---|
| Read-only RunIndex module | `packages/control-plane/control_plane/run_index.py` |
| Adapter coverage | rdgoal journal/report, go-run metadata, team events, @go review metadata, paper workspace state, and lightweight test-run metadata |
| Focused tests | `packages/control-plane/tests/test_run_index.py` |
| Contract authority | `schemas/runtime-governance/run-record.schema.json` remains the schema authority |

## Authority Boundaries Preserved

- Legacy runtime paths remain the source files; the RunIndex writes nothing.
- Every projected run carries `adapter_version`, `source_path`, source hash when
  file hashing is possible, and legacy IDs in `domain_refs`.
- Worker pass, go-run pass, team task result pass, test-frame aggregate pass,
  paper chain trust, and projection completion do not become `final_ready`.
- @go executor/fixer/coder/worker-authored review is blocked and recorded as a
  failure projection, not accepted as independent review.
- Corrupt JSON, YAML, and JSONL records produce blocked FailureRecord-compatible
  projections instead of being silently skipped.

## Known Limitations

- This is a projection API only; there is no CLI, dashboard, or storage-migration
  integration yet.
- The test-run adapter reads a lightweight `runtime/test-runs/*/test-run.json`
  shape for the first control-plane slice. Later phases should add a compatibility
  reader for current test-frame report artifacts.
- Paper support covers the control-plane paper workspace files used by the visual
  read model. Legacy ai-workflow-hub run-store state should be added before
  physical storage migration.
- Legacy context packet and context ledger IDs are placeholders
  (`cp-legacy-*`, `cl-legacy-*`) and do not claim that real ContextPacket or
  ContextLedger artifacts already exist.

## Verification Evidence

Local verification for this slice should include:

```powershell
python -m pytest packages\control-plane\tests\test_run_index.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Stop Lines Preserved

- No workflow execution behavior changed.
- No slash-command routing was added.
- No runtime files were moved into the public repository.
- No dashboard authority was changed.
- No automatic retrieval was added.
- No writable registry authority was introduced.
- No final acceptance, release-ready, PR, CI, or publication claim is made here.
