# Runtime Governance Batch E: Go Evidence TeamRuntime Finalization

Lifecycle state: Local implementation audit

Reader: DevFrame maintainers reviewing @go evidence finalization and TeamRuntime journal linkage

Post-read action: Verify that the deterministic evidence finalizer can opt into recording TeamRuntime review and final-verdict events without changing legacy finalize behavior.

Related docs: [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Reviewer Index](reviewer-index.md)

## Scope

This Batch E slice connects the existing @go evidence finalizer to the explicit TeamRuntime review/final-verdict events added in the previous slice.

Before this slice, `tools/go_evidence.py finalize` wrote machine artifacts but did not record TeamRuntime events.

After this slice:

- `tools/go_evidence.py finalize --team-runtime-dir <dir>` records `review_ref` and `final_verdict_ref` events after a passing evidence gate;
- default `finalize <evidence_dir>` behavior remains unchanged and writes no TeamRuntime journal;
- blocked or failed evidence finalization still writes machine artifacts and, when
  `--team-runtime-dir` is provided, records non-final-ready TeamRuntime
  visibility; invalid or self-review blockers record artifact evidence refs only;
- TeamRuntime refuses to write the journal inside the public repository through the existing `repo_root` guard;
- same-verdict finalization reruns reuse the existing machine artifact
  timestamp and do not append duplicate TeamRuntime final-ready references;
- RunIndex can project the opt-in finalizer events into a schema-valid `final_ready` RunRecord only after validating the referenced FinalVerdict artifact.

This slice does not automatically run evidence finalization. The user or caller must opt in by passing `--team-runtime-dir`.

## Local Evidence

Focused tests added or updated:

- `tests/test_go_evidence.py`

Required verification for this batch:

```powershell
python -m pytest tests\test_go_evidence.py::test_finalize_rerun_is_idempotent_for_machine_artifacts tests\test_go_evidence.py::test_finalize_team_runtime_recording_is_idempotent_for_same_verdict -q
python -m pytest tests\test_go_evidence.py::test_finalize_records_blocked_team_runtime_refs_without_final_ready tests\test_go_evidence.py::test_finalize_records_only_evidence_refs_for_self_review_blocker -q
python -m pytest tests\test_go_evidence.py packages\control-plane\tests\test_run_index.py packages\control-plane\tests\test_team_runtime.py -q
python -m pytest packages\control-plane\tests\test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --check
```

## Preserved Stop Lines

- Legacy `finalize <evidence_dir>` remains compatible.
- Worker/executor authored reviews remain blocked by the evidence gate and RunIndex.
- FinalVerdict JSON remains the gate fact source for RunIndex projection.
- Blocked or failed evidence cannot create TeamRuntime final-ready events.
- Invalid, corrupt, or self-review finalization blockers must not create
  authoritative `review_ref` or `final_verdict_ref` events.
- Markdown `final-report.md` remains a deterministic summary, not acceptance
  authority.
- Runtime data remains outside the public repository.

## Known Gaps

- `devframe atgo --execute --auto-finalize` now runs the finalizer only when
  required review evidence already exists; default atgo/code/go dispatch still
  does not create finalization attempts automatically.
- The follow-up
  [Runtime Governance Batch E: Final Verdict Lifecycle Metadata](runtime-governance-batch-e-final-verdict-lifecycle.md)
  slice extends the FinalVerdict schema with append-only superseding metadata.
  `go_evidence finalize` still does not automatically create superseding
  FinalVerdict records for divergent reruns.
