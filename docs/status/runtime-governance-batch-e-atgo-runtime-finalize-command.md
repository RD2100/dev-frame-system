# Runtime Governance Batch E: Atgo Runtime Finalize Command

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing @go prepare output and evidence finalization linkage

Post-read action: Verify that `devframe atgo` prints a runtime-aware finalizer command without automatically creating acceptance events.

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

The runtime root is already known to `cmd_atgo`, and the finalizer remains the existing manual follow-up command.

This slice does not automatically run the finalizer, does not create a final verdict, and does not change `tools/go_evidence.py finalize <evidence_dir>` compatibility.

## Local Evidence

Focused tests added or updated:

- `packages/control-plane/tests/test_cli.py`

Required verification for this batch:

```powershell
python -m pytest packages\control-plane\tests\test_cli.py -q -k atgo
python -m pytest tests\test_go_evidence.py packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- `devframe atgo` prepare remains prepare-first.
- Printed finalize guidance may point to the TeamRuntime journal, but final readiness still requires the deterministic evidence gate to pass.
- Blocked or failed evidence cannot create TeamRuntime final-ready events.
- Runtime data remains outside the public repository.

## Known Gaps

- Full go dispatch automation still does not run finalization automatically.
- The printed command follows existing CLI path-rendering style and does not introduce a new quoting policy.
