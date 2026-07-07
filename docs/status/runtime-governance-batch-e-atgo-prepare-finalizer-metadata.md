# Runtime Governance Batch E: Atgo Prepare Finalizer Metadata

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing @go prepare evidence metadata and RunIndex projection

Post-read action: Verify that `devframe atgo` records machine-readable finalizer guidance without converting prepare-only evidence into acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: Atgo Runtime Finalize Command](runtime-governance-batch-e-atgo-runtime-finalize-command.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice makes the manual atgo finalizer next step machine-readable.

Before this slice, `devframe atgo` printed the runtime-aware finalizer command, but the generated `chain-evidence.json` did not retain that command as structured metadata. A prepare-only atgo evidence directory without `review.yaml` also appeared to the read-only RunIndex as a missing-review failure rather than a normal review-pending prepare state.

After this slice:

- `devframe atgo` writes `next_commands.finalize` to `chain-evidence.json`;
- the finalizer command is marked as `authority: guidance_only`;
- the command metadata says `creates_acceptance: false` and `requires_independent_review: true`;
- RunIndex projects a prepare-only atgo evidence directory with `chain-evidence.json` but no `review.yaml` as a schema-valid, deferred RunRecord;
- final-ready acceptance remains impossible without a valid FinalVerdict event and independent review/gate evidence.

This slice originally did not validate or change the historical `chain-evidence.schema.json` contract. The follow-up [Runtime Governance Batch E: Chain Evidence Schema Compatibility](runtime-governance-batch-e-chain-evidence-schema-compatibility.md) slice now covers current `go_evidence init` and `devframe atgo` producers while preserving `next_commands.finalize` as guidance only.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_run_index.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_cli.py -q -k atgo
python -m pytest packages\control-plane\tests\test_run_index.py -q -k atgo
python -m pytest packages\control-plane\tests\test_public_snapshot.py::test_agent_runtime_chain_evidence_schema_mirror_matches_semantically -q
python -m pytest tests\test_go_evidence.py packages\control-plane\tests\test_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- A command string or command argv is guidance only, not acceptance evidence.
- Prepare-only atgo evidence remains `deferred` until independent review and deterministic finalization happen.
- Worker success still cannot satisfy review.
- Final readiness still requires a valid FinalVerdict artifact, passing independent review, and passing gate reference.

## Known Gaps

- Generic go dispatch automation still does not run finalization automatically;
  atgo execution has an explicit `--auto-finalize` follow-up that skips missing
  review evidence.
- ai-workflow-hub `nodes`-style chain evidence remains a separate domain adapter
  concern; the root schema currently targets `go_evidence init` and `devframe
  atgo` evidence producers.
