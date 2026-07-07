# Runtime Governance Batch D: Independent Gate

Lifecycle state: Local Batch D partial completion audit

## Purpose

Batch D starts connecting the existing @go evidence finalizer to the
machine-readable evidence, review, failure, and final-verdict contracts.

This slice keeps the existing `tools/go_evidence.py finalize` CLI compatible,
but extracts the deterministic gate logic into `control_plane.evidence_gate`.
The finalizer now writes schema-valid machine artifacts next to the existing
human-readable final report.

## Scope

Changed implementation surface:

- `packages/control-plane/control_plane/evidence_gate.py`
- `tools/go_evidence.py`

Changed tests:

- `packages/control-plane/tests/test_evidence_gate.py`
- `tests/test_go_evidence.py`

Changed documentation surface:

- `docs/status/runtime-governance-batch-d-independent-gate.md`
- `docs/status/reviewer-index.md`

## Delivered Contract Chain

`tools/go_evidence.py finalize <evidence-dir>` still returns the same pass or
blocked exit code behavior and still writes `final-report.md`.

It now also writes:

- `evidence-manifest.json`, validated against
  `schemas/agent-runtime/evidence-manifest.schema.json`;
- `final-verdict.json`, validated against
  `schemas/agent-runtime/final-verdict.schema.json`;
- `failure-record.json` on blocked or failed outcomes, validated against
  `schemas/agent-runtime/failure-record.schema.json`.

The gate validates `review.yaml` against
`schemas/agent-runtime/review.schema.json` before accepting reviewer evidence.
It also blocks reviewer/executor identity reuse even when the reviewer role is
spelled as `reviewer`.

## Stop Lines

- The finalizer summarizes validated inputs; it does not invent review
  judgment.
- Executor, fixer, coder, or worker roles cannot produce review or final
  verdict authority.
- Reviewer role values are normalized with whitespace and case folded before
  blocked-role checks.
- A reviewer identity equal to the executor identity blocks final readiness.
- Missing required evidence blocks final readiness.
- Open P0/P1 findings block final readiness.

## Verification

Local verification:

```powershell
python -m pytest tests\test_go_evidence.py -q
python -m pytest packages\control-plane\tests\test_evidence_gate.py -q
```

Observed result:

```text
tests/test_go_evidence.py and packages/control-plane/tests/test_evidence_gate.py: 22 passed
```

Covered assertions:

- pass finalization writes schema-valid EvidenceManifest and FinalVerdict;
- blocked finalization writes schema-valid FailureRecord and FinalVerdict;
- reviewer role self-review remains blocked;
- whitespace-padded and mixed-case executor/fixer/coder/worker review roles
  remain blocked;
- reviewer ID equal to executor ID is blocked on the real finalize path;
- blocked, fail, and escalate reviewer verdicts never produce `final_ready`;
- `evidence-manifest.json` reflects finalize-time machine artifacts;
- subprocess invocation of `tools/go_evidence.py finalize` writes machine
  artifacts on the real entry path;
- open P0 findings remain blocked;
- TDD red/green evidence requirements remain enforced.

## Known Gaps

- This slice does not yet write canonical runtime journal events.
- This slice does not yet connect TeamRuntime, workflow, dashboard, or RunIndex
  gate projections to the new artifacts.
- This slice does not yet make finalization idempotency explicit through a
  superseding-verdict record.
- Batch E updates `schemas/agent-runtime/chain-evidence.schema.json` to cover
  the current `go_evidence init` and `devframe atgo` shapes; ai-workflow-hub
  `nodes`-style chain evidence remains a separate domain adapter concern.

## Reviewer Focus

Reviewers should verify that finalizer output cannot convert missing or
executor-authored review evidence into `final_ready`, and that the generated
machine artifacts agree with `final-report.md`.
