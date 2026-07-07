# Runtime Governance Batch E: Chain Evidence Schema Compatibility

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing chain-evidence schema compatibility for @go evidence producers

Post-read action: Verify that the canonical and test-frame mirror `chain-evidence.schema.json` files validate current `go_evidence init` and `devframe atgo` output without turning metadata into acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch D: Independent Gate](runtime-governance-batch-d-independent-gate.md), [Runtime Governance Batch E: Atgo Prepare Finalizer Metadata](runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice resolves the Batch D documented gap where `schemas/agent-runtime/chain-evidence.schema.json` no longer matched the current `go_evidence init` shape.

Before this slice, the schema required legacy top-level fields such as `task_file`, `created_at`, and `producer`, while the current @go evidence producers write `task`, `timestamps.created_at`, `methodology`, `evidence_files`, and, for atgo prepare, `next_commands.finalize`.

After this slice:

- root `schemas/agent-runtime/chain-evidence.schema.json` accepts current `go_evidence init` output;
- `packages/test-frame/schemas/agent-runtime/chain-evidence.schema.json` remains a semantic mirror;
- `devframe atgo` chain evidence validates with structured finalizer guidance;
- `next_commands.finalize` is constrained to `authority: guidance_only`, `creates_acceptance: false`, and `requires_independent_review: true`;
- tests cover both real generation paths and the mirror contract.

This slice does not claim compatibility with the ai-workflow-hub paper/coding graph `nodes`-based chain evidence shape. That producer remains a separate domain adapter concern.

## Local Evidence

Focused tests added or updated:

- `tests/test_go_evidence.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_public_snapshot.py`

Required verification for this batch:

```powershell
python -m pytest tests\test_go_evidence.py::test_init_creates_chain_evidence -q
python -m pytest packages\control-plane\tests\test_cli.py::test_atgo_prepare_writes_methodology_to_chain_evidence -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py::test_agent_runtime_chain_evidence_schema_mirror_matches_semantically -q
python -m pytest tests\test_go_evidence.py packages\control-plane\tests\test_cli.py -q -k "atgo or chain_evidence or init_creates_chain_evidence"
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Schema compatibility does not create acceptance authority.
- `next_commands.finalize` remains guidance only.
- Final readiness still requires deterministic finalization plus independent review and passing gate evidence.
- Runtime data remains outside the public repository.

## Known Gaps

- ai-workflow-hub `nodes`-style chain evidence is not normalized by this slice.
- The finalizer still does not validate `chain-evidence.schema.json` as part of the pass/fail evidence gate.
