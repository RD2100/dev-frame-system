# Runtime Governance Batch C: rdreview Prepare-Only Path

Lifecycle state: Local Batch C completion audit

## Purpose

Batch C proves a prepare-only `/rdreview` vertical slice over the existing
review-governance packet and the Runtime Governance contracts.

The slice prepares a bounded review package. It does not execute code, perform
automatic retrieval, submit to a browser or Web AI, invoke a live reviewer,
evaluate a gate, or create a governance final verdict.

## Scope

Changed implementation surface:

- `packages/control-plane/control_plane/rdreview.py`
- `packages/control-plane/control_plane/cli/_review.py`
- `packages/control-plane/tests/test_rdreview.py`

Changed documentation surface:

- `docs/status/runtime-governance-batch-c-rdreview-prepare-only.md`
- `docs/status/reviewer-index.md`

## Delivered Contract Chain

`devframe rdreview` keeps the legacy packet output as the default format.

`devframe rdreview ... --format bundle` emits a prepare-only bundle containing:

- the legacy review-governance packet;
- a schema-valid Runtime Governance `ContextPacket`;
- a schema-valid Runtime Governance `ContextLedger`;
- a schema-valid Runtime Governance `RunRecord`;
- a schema-valid `TaskSpec`;
- an evidence inventory with omitted required references;
- read-only inspect output;
- manual-only resume output;
- preserved stop lines.

The bundle records missing independent-review and execution evidence as
limitations instead of promoting the run to acceptance.

## Stop Lines

- No automatic retrieval in Batch C.
- No browser submission in Batch C.
- No live external reviewer in Batch C.
- No runtime execution in Batch C.
- No governance acceptance claim from prepare output.

## Verification

Local verification:

```powershell
python -m pytest packages\control-plane\tests\test_rdreview.py -q
```

Observed result:

```text
19 passed
```

Covered assertions:

- legacy packet mode remains schema-valid and remains the CLI default;
- bundle mode validates ContextPacket, ContextLedger, RunRecord, and TaskSpec;
- prepare output keeps review, gate, and acceptance pending;
- missing independent-review and execution evidence are visible;
- inspect output is read-only;
- resume output is manual-only;
- top-level `devframe rdreview --help` exposes `--format packet|bundle`;
- top-level `devframe rdreview ... --format bundle` routes through the real CLI
  entrypoint;
- prepare output does not create a final verdict reference.

## Known Gaps

- No external reviewer is invoked in this phase.
- No EvidenceManifest or deterministic finalizer is connected yet.
- No writable canonical registry is introduced; Batch B RunIndex remains
  read-only projection authority only.
- No dashboard or visual read-model integration is included.

## Reviewer Focus

Reviewers should verify that `--format bundle` does not alter the legacy packet
contract, does not produce final acceptance authority, and does not hide missing
review or execution evidence.
