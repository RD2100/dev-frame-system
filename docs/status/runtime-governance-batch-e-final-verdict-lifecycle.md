# Runtime Governance Batch E: Final Verdict Lifecycle Metadata

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing FinalVerdict lifecycle contract changes

Post-read action: Verify that FinalVerdict can reference a superseded verdict
without allowing executors to create acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch D: Independent Gate](runtime-governance-batch-d-independent-gate.md), [Runtime Governance Batch E: Go Evidence TeamRuntime Finalization](runtime-governance-batch-e-go-evidence-team-runtime-finalization.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice extends the canonical FinalVerdict schema with append-only
superseding metadata.

Before this slice, the schema had no explicit place for a later governance
verdict to say which previous FinalVerdict it superseded. The deterministic
finalizer therefore had to keep same-verdict reruns idempotent and defer any
divergent-verdict lifecycle record until the schema had a contract.

After this slice:

- `schemas/agent-runtime/final-verdict.schema.json` accepts an optional
  `supersedes` object;
- `supersedes.verdict_id`, `supersedes.uri`, and `supersedes.reason` are
  required when the lifecycle link is present;
- the previous verdict remains immutable; the newer verdict records why it
  replaces the earlier one;
- executor, fixer, coder, and worker producer roles remain rejected even on a
  superseding verdict.

This slice does not make `go_evidence finalize` automatically create
superseding verdicts. Same-verdict reruns remain idempotent, and any future
divergent-verdict behavior still needs explicit runtime logic and tests.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q -k final_verdict_schema
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Superseding metadata is a lifecycle link, not acceptance evidence.
- A superseding verdict must still be produced by governance or a human/main
  coordinator role.
- Worker or executor output still cannot create final acceptance.
- The deterministic finalizer must not invent a divergent lifecycle judgment
  without explicit governance logic.

## Known Gaps

- `go_evidence finalize` does not yet create superseding FinalVerdict records
  for divergent reruns.
- RunIndex currently validates and projects the referenced FinalVerdict artifact
  but does not yet expose supersession chains as a first-class read model.
