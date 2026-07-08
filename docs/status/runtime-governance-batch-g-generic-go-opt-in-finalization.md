# Runtime Governance Batch G: Generic Go Opt-In Finalization

Lifecycle state: Evidence record

This Batch G slice adds a bounded finalization path for prepared generic
`devframe go` / `devframe code` runs. It does not make go execution finalization
automatic by default. Finalization only runs when the operator explicitly passes
`--auto-finalize` together with `--evidence-dir <dir>` to `devframe go execute`
or `devframe code execute`.

## Scope

- `devframe go execute` and `devframe code execute` reject `--auto-finalize`
  without `--evidence-dir`.
- When explicitly enabled, the command reuses the existing
  `tools/go_evidence.py finalize <evidence-dir> --team-runtime-dir <runtime>`
  path.
- The evidence directory must already contain independent review inputs:
  `diff.patch`, `test-output.md`, `safety-report.json`, `review.md`,
  `review.yaml`, and `chain-evidence.json`.
- The finalizer can then record TeamRuntime review/final-verdict refs and
  RunIndex can project `final_ready` only through the existing review, gate,
  FinalVerdict, and sealed-context checks.

## Local Evidence

```powershell
python -m pytest packages\control-plane\tests\test_cli.py::test_code_execute_help_is_available packages\control-plane\tests\test_cli.py::test_go_execute_auto_finalize_requires_evidence_dir packages\control-plane\tests\test_cli.py::test_go_execute_auto_finalize_records_reviewed_evidence_real_path -q
python -m pytest packages\control-plane\tests\test_cli.py -q
```

Observed local result on 2026-07-08:

- `3 passed`
- `117 passed`

## Stop Lines

- Plain `devframe go execute` and `devframe code execute` remain execution-only.
- This slice does not synthesize review evidence, safety evidence, or
  `chain-evidence.json`.
- This slice does not bypass sealed ContextPacket/ContextLedger requirements
  added by Batch F.
- This slice does not add default automatic finalization, dashboard authority
  changes, storage migration, paper adapters, or ai-workflow-hub normalization.

## Reviewer Focus

- Confirm `--auto-finalize` requires `--evidence-dir`.
- Confirm the implementation reuses `tools/go_evidence.py finalize` instead of
  duplicating final-verdict logic.
- Confirm the real-path CLI test reaches `final_ready` through TeamRuntime and
  RunIndex, not just by checking generated files.
