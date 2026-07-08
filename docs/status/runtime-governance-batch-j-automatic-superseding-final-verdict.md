# Runtime Governance Batch J: Automatic Superseding FinalVerdict

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing append-only FinalVerdict lifecycle
behavior.

Post-read action: Treat superseding FinalVerdict generation as a governance
finalizer behavior only; do not let workers produce acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: FinalVerdict Lifecycle](runtime-governance-batch-e-final-verdict-lifecycle.md), [Runtime Governance Batch E: FinalVerdict Supersession Projection](runtime-governance-batch-e-final-verdict-supersession-projection.md), [Reviewer Index](reviewer-index.md)

## Scope

Earlier slices modeled FinalVerdict lifecycle metadata and read-only
supersession projection. Batch J adds the bounded write behavior in the
governance finalizer path.

When `tools/go_evidence.py finalize` finds an existing `final-verdict.json` and
the new evaluated verdict is materially different, it now:

- keeps identical reruns idempotent;
- archives the prior verdict as `final-verdict-prior*.json`;
- writes a new `final-verdict.json` with a `supersedes` link to the archived
  prior verdict;
- blocks finalization if the prior verdict is invalid or belongs to a different
  governance reference.

This remains append-only at the artifact level: the prior verdict is preserved
before the current verdict replaces the live filename. The behavior is limited
to the governance-owned finalizer path.

## Local Evidence

Focused verification:

```powershell
python -m pytest tests\test_go_evidence.py::test_finalize_rerun_archives_prior_final_verdict_with_supersedes tests\test_go_evidence.py::test_finalize_prior_final_verdict_governance_mismatch_blocks_supersede -q
python -m pytest tests\test_go_evidence.py -q
```

Observed local result on 2026-07-08:

```text
2 passed
35 passed
```

## Preserved Stop Lines

- Workers still cannot produce FinalVerdict authority.
- Invalid or mismatched prior verdicts fail closed.
- Historical verdict content is archived before replacement.
- Supersession metadata is not a dashboard authority source by itself.

## Known Gaps

- Complete cross-run supersession graph migration remains out of scope.
- Dashboard authority changes remain out of scope.
- Paper-domain adapters remain a separate slice.
