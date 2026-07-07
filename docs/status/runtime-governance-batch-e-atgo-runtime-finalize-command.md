# Runtime Governance Batch E: Atgo Runtime Finalize Command

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing @go prepare output and evidence finalization linkage

Post-read action: Verify that `devframe atgo` prints a runtime-aware finalizer command and only runs opt-in finalization after required review evidence exists.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Runtime Governance Batch E: Go Evidence TeamRuntime Finalization](runtime-governance-batch-e-go-evidence-team-runtime-finalization.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice connects the `devframe atgo` prepare output to the opt-in TeamRuntime finalization flag added in the previous slice.

Before this slice, `devframe atgo` created an evidence directory and printed:

```powershell
tools/go_evidence.py finalize <evidence_dir>
```

After this slice, it prints:

```powershell
tools/go_evidence.py finalize <evidence_dir> --team-runtime-dir <runtime_root>
```

The runtime root is already known to `cmd_atgo`, and the default finalizer path remains the existing manual follow-up command.

After the follow-up slice, `devframe atgo --execute --auto-finalize` may run the
same finalizer command, but only when the atgo evidence directory already
contains the required review/evidence files. Missing review evidence skips
auto-finalization and keeps the manual finalize guidance visible. This does not
change `tools/go_evidence.py finalize <evidence_dir>` compatibility.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_cli.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_cli.py -q -k atgo
python -m pytest packages\control-plane\tests\test_cli.py::test_atgo_execute_auto_finalize_skips_without_review_evidence packages\control-plane\tests\test_cli.py::test_atgo_execute_auto_finalize_records_reviewed_evidence -q
python -m pytest tests\test_go_evidence.py packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- `devframe atgo` prepare remains prepare-first.
- `devframe atgo --execute` still does not finalize unless `--auto-finalize`
  is explicitly provided.
- `--auto-finalize` skips missing review evidence instead of generating blocked
  final artifacts from worker success alone.
- Printed finalize guidance may point to the TeamRuntime journal, but final readiness still requires the deterministic evidence gate to pass.
- Blocked or failed evidence cannot create TeamRuntime final-ready events.
- Runtime data remains outside the public repository.

## Known Gaps

- Generic go dispatch automation still does not run finalization automatically.
- The printed command follows existing CLI path-rendering style and does not introduce a new quoting policy.
