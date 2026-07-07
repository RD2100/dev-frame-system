# Runtime Governance Batch E: AI Workflow Hub Chain Evidence Classification

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing ai-workflow-hub chain evidence
classification and fail-closed governance summaries

Post-read action: Verify that ai-workflow-hub `nodes`-style chain evidence is
visible in governance summaries without becoming canonical acceptance evidence.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: Chain Evidence Schema Compatibility](runtime-governance-batch-e-chain-evidence-schema-compatibility.md), [Runtime Governance Batch E: Paper Trust Fail Closed](runtime-governance-batch-e-paper-trust-fail-closed.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice classifies the existing ai-workflow-hub `nodes`-style
`chain-evidence.json` shape on the read side.

Before this slice, Batch E documentation named the `nodes`-style file as a
separate adapter concern, but `summarize_run_governance()` did not expose the
shape. Reviewers could see that chain trust was false, but not whether a
non-canonical chain evidence file was present.

After this slice:

- `summarize_run_governance()` reports `chain_evidence_shape`;
- ai-workflow-hub `nodes` payloads are classified as
  `ai_workflow_hub_nodes`;
- governance summaries include a diagnostic saying that nodes-style evidence is
  visible but is not canonical acceptance evidence;
- `chain_trusted` still comes only from explicit boolean state, not from file
  shape or terminal run status;
- `_write_chain_evidence()` writes the nodes-style file as
  `UNTRUSTED_NODES_STYLE` and leaves `chain_trusted=false`;
- stale state claiming `chain_trusted=true` is overridden when the corresponding
  `chain-evidence.json` is nodes-style.

This slice does not change the canonical root
`schemas/agent-runtime/chain-evidence.schema.json` contract and does not make
`nodes` payloads valid @go evidence for deterministic finalization.

## Local Evidence

Focused tests added or updated:

- `packages/ai-workflow-hub/tests/test_run_governance.py`

Required verification for this batch:

```powershell
python -m pytest packages\ai-workflow-hub\tests\test_run_governance.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- A `nodes`-style file is not acceptance authority.
- Terminal run status still cannot infer chain trust.
- `chain_trusted` remains fail-closed unless explicit state says boolean
  `true` and the file is not nodes-style.
- The root @go chain-evidence schema remains scoped to `go_evidence init` and
  `devframe atgo` producers.

## Known Gaps

- ai-workflow-hub `nodes`-style chain evidence is classified, not normalized
  into the canonical @go schema.
- Full paper workflow and ai-workflow-hub domain adapters remain future work.
