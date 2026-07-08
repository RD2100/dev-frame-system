# Runtime Governance Batch I: Generic Go Prepare Evidence

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers extending generic `go` / `code execute` evidence
production without granting acceptance authority.

Post-read action: Use `--prepare-evidence-dir` only as a draft evidence
preparation primitive; run explicit independent review and `--auto-finalize`
before any final-ready state.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch G: Generic Go Opt-In Finalization](runtime-governance-batch-g-generic-go-opt-in-finalization.md), [Reviewer Index](reviewer-index.md)

## Scope

Batch G added explicit opt-in finalization for generic `go` / `code execute`
runs when an operator supplies a reviewed evidence directory. Batch I adds the
bounded preparation half of that workflow.

After this slice, `devframe go execute` / `devframe code execute` accepts:

```powershell
--prepare-evidence-dir <dir>
```

The option writes a draft evidence directory containing:

- `chain-evidence.json`;
- `evidence-manifest.json` with `verdict_eligibility.status =
  needs_more_evidence`;
- finalizer guidance that is explicitly `guidance_only`,
  `creates_acceptance: false`, and `requires_independent_review: true`.

The option is mutually exclusive with `--auto-finalize` and `--evidence-dir`.
It does not create `review.yaml`, `final-verdict.json`, or final-ready
TeamRuntime state.

## Local Evidence

Focused verification:

```powershell
python -m pytest packages\control-plane\tests\test_cli.py::test_go_execute_prepare_evidence_dir_generates_draft_and_can_be_finalized_later -q
python -m pytest packages\control-plane\tests\test_cli.py::test_go_execute_auto_finalize_requires_evidence_dir packages\control-plane\tests\test_cli.py::test_go_execute_auto_finalize_records_reviewed_evidence_real_path packages\control-plane\tests\test_cli.py::test_code_execute_help_is_available -q
```

Observed local result on 2026-07-08:

```text
1 passed
3 passed
```

## Preserved Stop Lines

- Prepare-only evidence is draft evidence, not acceptance.
- The draft manifest remains `needs_more_evidence`.
- The generated finalizer command is guidance only.
- Independent `review.md` and `review.yaml` are still required before
  `--auto-finalize` can produce final-ready state.

## Known Gaps

- Default generic `go` automatic finalization remains out of scope.
- Default automatic production of complete review evidence remains out of
  scope.
- Paper-domain adapters, automatic superseding FinalVerdict generation,
  storage migration, and dashboard authority changes remain separate slices.
