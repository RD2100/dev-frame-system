# Runtime Governance Batch H: AI Workflow Hub Chain Evidence Adapter

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers extending runtime-governance evidence adapters.

Post-read action: Treat ai-workflow-hub `nodes` chain evidence as a
non-authoritative normalized candidate, not as acceptance authority.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: AI Workflow Hub Chain Evidence Classification](runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md), [Reviewer Index](reviewer-index.md)

## Scope

Batch E made ai-workflow-hub `nodes`-style `chain-evidence.json` visible and
fail-closed. This slice adds a bounded adapter view on top of that
classification.

After this slice, `summarize_run_governance()` still keeps nodes-style evidence
untrusted, but it also returns `chain_evidence_adapter` metadata with:

- the detected source shape;
- normalization status;
- an explicit `acceptance_candidate: false` safety flag;
- a normalized in-memory candidate containing run id, executor id, task,
  worker-result summaries, evidence file references, and timestamps.

The CLI and Markdown governance renderers show the adapter status. No runtime
file is rewritten, no chain trust is inferred, and no final-ready projection is
created.

## Local Evidence

Focused verification:

```powershell
python -m pytest packages\ai-workflow-hub\tests\test_run_governance.py -q
```

Observed local result on 2026-07-08:

```text
16 passed
```

## Preserved Stop Lines

- A normalized adapter candidate is diagnostic data only.
- `acceptance_candidate` is always false for this adapter.
- Terminal status, file shape, and worker success still cannot create
  `chain_trusted=True`.
- Invalid, missing, and unknown chain evidence continue to block
  normalization and cannot preserve stale `chain_trusted=True`.

## Known Gaps

- The adapter does not write canonical chain-evidence JSON back to disk.
- Paper-domain normalization, default evidence production, automatic
  superseding FinalVerdict generation, storage migration, and dashboard
  authority changes remain separate slices.
