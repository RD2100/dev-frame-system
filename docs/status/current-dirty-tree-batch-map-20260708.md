# Current Dirty Tree Batch Map

Date: 2026-07-08

Lifecycle state: Executed release-state evidence record

Purpose: record how the reviewed dirty worktree was split into low-coupling
review and commit batches. This file is now historical execution evidence: the
batch commits were created and pushed to PR #4 before the later merge and
GitHub Release `v0.1.0`. Current release status is authoritative in
`LAUNCH_NOW.md`.

## Summary

The reviewed worktree was committed as five batches:

1. Status document entrypoints and release evidence.
2. AI Workflow Hub chain-evidence adapter.
3. Generic go/workflow sealed context projection.
4. Generic `go/code execute` explicit finalize and prepare-only CLI behavior.
5. `go_evidence` finalization lifecycle, supersedes, and context backfill.

Executed order: Batch 1 first, then Batches 2, 3, 4, and 5. Keep the owner
release gate separate from these review batches.

## Final Local Review Verdict

Verdict at this checkpoint: **PASS for local batch review and PR CI**. The
later merge and GitHub Release `v0.1.0` supersede the pre-release hold state
that originally followed this review.

Reviewer index:

- Changed files: the original 28 dirty paths are covered by the five batches
  below and have been converted into explicit commits.
- Critical code paths: AI Workflow Hub chain-evidence normalization, sealed
  go/workflow context projection, explicit CLI finalization, and go_evidence
  FinalVerdict supersession.
- Tests run: full local release verification passed with `1616 passed, 1
  skipped`, local strict public snapshot PASS, local control-plane wheel smoke
  PASS, and local `git diff --check` PASS.
- Generated artifacts: none retained in the working tree.
- Known gaps: paper-domain adapter and `/rdpaper` command closure remain
  deferred Phase 6 work. Merge and GitHub Release publication were completed
  after this batch checkpoint; PyPI publication remains outside this
  repository's defined release workflow.
- Review focus: treat this file as batch execution evidence, not as the current
  release-state authority.

Final batch review notes:

- Batch 1 documentation review found no release-overclaim, private-path leak,
  broken current-entry mapping, or stale latest test count.
- Batch 2 follow-up review found no remaining P1/P2 issue after fail-closed
  adapter fixes for mixed `nodes`, invalid `go_evidence_v1`, and missing
  `chain-evidence.json` payloads with stale trusted state.
- Batch 3 sealed-context review found no blocking correctness, security, or
  release-risk issue; the stricter legacy-run behavior is intentional.
- Batch 4 CLI review found the explicit finalize and prepare-only modes
  mutually exclusive and visible in help/usage after the follow-up fix.
- Batch 5 go_evidence review found FinalVerdict supersession idempotent after
  the follow-up fix for existing `supersedes` metadata.
- Dirty-tree boundary review found all 28 dirty paths covered, with no
  generated, temporary, private, build, or local-state files in the batch set.
- Staging list dry-run found the explicit batch file list exactly matched the
  live dirty set before commit: `expected=28 actual=28 missing=0 extra=0`.

## Batch 1: Status Documents

Changed files:

- `docs/status/LAUNCH_NOW.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md`
- `docs/status/status-document-inventory.md`
- `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
- `docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md`
- `docs/status/runtime-governance-batch-e-team-context-refs.md`
- `docs/status/runtime-governance-batch-e-team-review-verdict-events.md`
- `docs/status/runtime-governance-batch-e-workflow-review-pending.md`
- `docs/status/runtime-governance-batch-f-sealed-context-artifacts.md`
- `docs/status/runtime-governance-batch-g-generic-go-opt-in-finalization.md`
- `docs/status/runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md`
- `docs/status/runtime-governance-batch-i-generic-go-prepare-evidence.md`
- `docs/status/runtime-governance-batch-j-automatic-superseding-final-verdict.md`
- `docs/status/current-dirty-tree-batch-map-20260708.md`

Critical paths:

- `LAUNCH_NOW.md` must preserve the GitHub Release complete but PyPI-not-
  published boundary.
- `reviewer-index.md` and `status-document-inventory.md` must agree on current
  entrypoints and Batch F-J evidence records.

Tests to run:

- `python -m pytest packages/control-plane/tests/test_docs_drift_validator.py packages/control-plane/tests/test_public_snapshot.py -q`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-public-snapshot.ps1 -FailOnTrackedForbidden`
- `git diff --check`

Known gaps:

- This batch does not resolve the paper-domain adapter gap.
- This batch does not authorize PR, push, CI, or package publication.

Review focus:

- Check for stale release claims, broken links, and accidental "release ready"
  wording.

Human authorization: no, unless staging or publishing is requested.

## Batch 2: AI Workflow Hub Chain-Evidence Adapter

Changed files:

- `packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py`
- `packages/ai-workflow-hub/tests/test_run_governance.py`

Critical paths:

- Nodes-style chain evidence must normalize as a non-authoritative candidate.
- Unknown or invalid chain evidence must remain fail-closed.
- Missing chain evidence must not preserve stale `chain_trusted=True`.
- `acceptance_candidate` must not become release authority.

Tests to run:

- `python -m pytest packages/ai-workflow-hub/tests/test_run_governance.py -q`

Known gaps:

- Paper-domain normalization remains a separate slice.

Review focus:

- Confirm the adapter cannot turn a node summary into trusted acceptance.

Human authorization: yes before merging behavior changes.

## Batch 3: Generic Go Sealed Context Projection

Changed files:

- `packages/control-plane/control_plane/dispatch_packet.py`
- `packages/control-plane/control_plane/go_dispatch.py`
- `packages/control-plane/control_plane/run_index.py`
- `schemas/rdgoal_dispatch_packet.schema.json`
- `packages/control-plane/tests/test_go_team_runtime.py`
- `packages/control-plane/tests/test_run_index.py`

Critical paths:

- Dispatch should produce `context-packet.json` and `context-ledger.json`.
- Team events and RunIndex should project sealed context references.
- Final readiness must not be inferred without valid context evidence.

Tests to run:

- `python -m pytest packages/control-plane/tests/test_go_team_runtime.py packages/control-plane/tests/test_run_index.py -q`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-public-snapshot.ps1 -FailOnTrackedForbidden`

Known gaps:

- This batch does not enable generic go automatic finalization by default.

Review focus:

- Confirm context artifacts are evidence references, not acceptance authority by
  themselves.

Human authorization: yes before merging acceptance-threshold behavior changes.

## Batch 4: Generic Go CLI Finalize And Prepare-Only

Changed files:

- `packages/control-plane/control_plane/cli/_coding.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/tests/test_cli.py`

Critical paths:

- `--auto-finalize` must be explicit and require `--evidence-dir`.
- `--prepare-evidence-dir` must create draft evidence without final verdicts.
- The default CLI path must remain non-finalizing.

Tests to run:

- `python -m pytest packages/control-plane/tests/test_cli.py -q`

Known gaps:

- Prepare-only evidence still requires a later explicit finalizer/review path.

Review focus:

- Confirm help text, mutual exclusions, and real-path finalization behavior.

Human authorization: yes before merging CLI behavior changes.

## Batch 5: Go Evidence Finalization Lifecycle

Changed files:

- `tools/go_evidence.py`
- `tests/test_go_evidence.py`

Critical paths:

- Rerun finalization should archive prior compatible verdicts with
  `supersedes`.
- Incompatible prior verdicts should block superseding.
- Finalization should backfill go-run context refs only when sealed context is
  valid.

Tests to run:

- `python -m pytest tests/test_go_evidence.py -q`

Known gaps:

- Cleanup policy for archived incompatible verdict artifacts remains outside
  this batch.

Review focus:

- Confirm mismatch paths fail closed and do not produce misleading supersession
  chains.

Human authorization: yes before merging acceptance-lineage behavior changes.

## Global Verification

After reviewing or changing any behavior batch, rerun:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

GitHub Release `v0.1.0` has since been published after PR #4 merge and main CI
PASS. PyPI publication remains outside this repository's defined release
workflow.

## Executed Owner-Approved Staging Plan

These commands record the explicit staging plan that was executed after owner
approval. They intentionally enumerate files and should not be replaced with
`git add .` in future repeats.

If a batch has been staged but should not be committed, abort that batch with
`git restore --staged -- <same explicit file list>` before continuing.

### Batch 1: Status Documents

```powershell
git add -- docs/status/LAUNCH_NOW.md docs/status/release-readiness.md docs/status/reviewer-index.md docs/status/status-document-inventory.md docs/status/runtime-governance-and-evidence-closure-transformation-plan.md docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md docs/status/runtime-governance-batch-e-team-context-refs.md docs/status/runtime-governance-batch-e-team-review-verdict-events.md docs/status/runtime-governance-batch-e-workflow-review-pending.md docs/status/runtime-governance-batch-f-sealed-context-artifacts.md docs/status/runtime-governance-batch-g-generic-go-opt-in-finalization.md docs/status/runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md docs/status/runtime-governance-batch-i-generic-go-prepare-evidence.md docs/status/runtime-governance-batch-j-automatic-superseding-final-verdict.md docs/status/current-dirty-tree-batch-map-20260708.md
python -m pytest packages/control-plane/tests/test_docs_drift_validator.py packages/control-plane/tests/test_public_snapshot.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --cached --check
git commit -m "docs: close runtime governance launch state"
```

### Batch 2: AI Workflow Hub Chain-Evidence Adapter

```powershell
git add -- packages/ai-workflow-hub/src/ai_workflow_hub/run_governance.py packages/ai-workflow-hub/tests/test_run_governance.py
python -m pytest packages/ai-workflow-hub/tests/test_run_governance.py -q
git diff --cached --check
git commit -m "fix: keep ai workflow chain evidence fail closed"
```

### Batch 3: Generic Go Sealed Context Projection

```powershell
git add -- packages/control-plane/control_plane/dispatch_packet.py packages/control-plane/control_plane/go_dispatch.py packages/control-plane/control_plane/run_index.py schemas/rdgoal_dispatch_packet.schema.json packages/control-plane/tests/test_go_team_runtime.py packages/control-plane/tests/test_run_index.py
python -m pytest packages/control-plane/tests/test_go_team_runtime.py packages/control-plane/tests/test_run_index.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden
git diff --cached --check
git commit -m "feat: project sealed context into governance runs"
```

### Batch 4: Generic Go CLI Finalize And Prepare-Only

```powershell
git add -- packages/control-plane/control_plane/cli/_coding.py packages/control-plane/control_plane/cli/_usage.py packages/control-plane/tests/test_cli.py
python -m pytest packages/control-plane/tests/test_cli.py -q
git diff --cached --check
git commit -m "feat: add explicit go evidence finalization controls"
```

### Batch 5: Go Evidence Finalization Lifecycle

```powershell
git add -- tools/go_evidence.py tests/test_go_evidence.py
python -m pytest tests/test_go_evidence.py -q
git diff --cached --check
git commit -m "fix: make go evidence verdict supersession idempotent"
```

### Final Gate After Approved Commits

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-release.ps1
git status --short
```
