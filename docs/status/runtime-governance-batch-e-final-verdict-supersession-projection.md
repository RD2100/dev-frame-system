# Runtime Governance Batch E: Final Verdict Supersession Projection

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing read-only FinalVerdict supersession
projection

Post-read action: Verify that RunIndex exposes append-only supersession metadata
from a validated FinalVerdict artifact without treating the metadata as
acceptance evidence.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: Final Verdict Lifecycle Metadata](runtime-governance-batch-e-final-verdict-lifecycle.md), [Runtime Governance Batch E: Team Review Verdict Events](runtime-governance-batch-e-team-review-verdict-events.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice makes FinalVerdict supersession metadata visible in the
read-only RunIndex projection.

Before this slice, `schemas/agent-runtime/final-verdict.schema.json` accepted
optional `supersedes` metadata, and RunIndex validated the referenced
FinalVerdict artifact, but `final_verdict_ref` only exposed the current verdict
identifier, state, URI, review reference, and gate references.

After this slice:

- `schemas/runtime-governance/run-record.schema.json` accepts optional
  `final_verdict_ref.supersedes`;
- `packages/test-frame/schemas/runtime-governance/run-record.schema.json`
  remains a semantic mirror;
- `packages/control-plane/control_plane/run_index.py` copies `supersedes` from
  the already validated FinalVerdict artifact into the read model;
- the projected supersession link carries the prior verdict id, URI, and
  governance reason;
- final readiness still depends on the existing independent review, passing
  gate references, and validated FinalVerdict artifact.

This slice does not make `go_evidence finalize` generate divergent superseding
verdicts automatically and does not make supersession metadata acceptance
evidence.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_run_index.py -q -k final_verdict
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q -k runtime_governance_schema_mirrors
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Supersession metadata is lifecycle visibility, not acceptance authority.
- RunIndex remains read-only and does not create new FinalVerdict artifacts.
- `final_ready` still requires a valid FinalVerdict artifact plus passing
  independent review and gate references.
- Worker or executor output still cannot create final acceptance.

## Known Gaps

- `go_evidence finalize` still does not automatically create superseding
  FinalVerdict records for divergent reruns.
- RunIndex exposes only the direct superseded verdict link on the current
  FinalVerdict reference; it does not yet resolve or traverse historical
  supersession chains.
