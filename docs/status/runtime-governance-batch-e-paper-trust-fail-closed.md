# Runtime Governance Batch E: Paper Trust Fail Closed

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing runtime-governance paper integration

Post-read action: Verify that paper workflow terminal status does not create chain trust.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

This is the second Batch E slice. It removes the paper workflow fail-open trust inference called out in the transformation plan.

Before this slice, `summarize_run_governance()` treated a terminal `passed` or `blocked` run status as enough to set `chain_trusted=True` when the state did not already contain explicit chain trust.

After this slice:

- terminal status remains an execution outcome only;
- missing or unknown chain trust remains untrusted;
- explicit JSON boolean `chain_trusted=true` in state is preserved unless a
  follow-up shape classifier identifies the file as nodes-style evidence;
- `_write_chain_evidence()` originally wrote `chain-evidence.json` and recorded
  explicit trust state for `verify_run_evidence()` and `goal_runner`; the
  follow-up ai-workflow-hub chain evidence classification slice keeps that
  nodes-style file fail-closed;
- `summarize_run_governance(..., state=...)` uses the passed state before disk
  state so finalizer reports do not render stale governance fields;
- final reports and CLI summaries continue to render the chain status from the governance summary.

## Local Evidence

Focused tests added:

- `packages/ai-workflow-hub/tests/test_run_governance.py`

The tests cover direct `summarize_run_governance()` behavior, the real
`verify_run_evidence()` path over `runs/<project_id>/<run_id>/state.json`, and
stale-disk-state avoidance through the `state=` argument. A follow-up
classification slice covers `_write_chain_evidence()` fail-closed behavior for
nodes-style evidence.

Required verification for this batch:

```powershell
python -m pytest packages\ai-workflow-hub\tests\test_run_governance.py -q
python -m pytest packages\ai-workflow-hub\tests -q
python -m pytest packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- `passed`, `blocked`, or any other terminal status cannot create evidence trust.
- Unknown chain provenance remains unknown and blocks final readiness in later adapters.
- This slice does not change paper workflow storage, CLI command names, or final verdict contracts.

## Known Gaps

- Paper workflow still needs a full domain adapter over the canonical runtime lifecycle.
- Generic TeamRuntime review/final-verdict event ingestion is covered by the
  follow-up
  [Runtime Governance Batch E: Team Review Verdict Events](runtime-governance-batch-e-team-review-verdict-events.md)
  slice and the @go finalization slices. Paper-specific ingestion still belongs
  to the future paper domain adapter.
