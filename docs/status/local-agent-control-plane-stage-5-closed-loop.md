# Local Agent Control Plane Stage 5 Closed Loop

Date: 2026-06-23
Branch: `codex/go-concurrent-dispatch`
Status: `verified_external_review_gate`

This report records the first closed-loop pass that uses the real Chrome plus
ChatGPT binding as an external-brain review source, then imports the result back
into the Visual Control Plane as a summary-only review gate.

## Loop Covered

This Stage 5 slice proves the following path:

```text
bounded Stage 5 task request
-> real ChatGPT external-brain review
-> summary-only runtime session import
-> Visual Control Plane acceptance gate
-> action queue projection
```

It does not claim full production dispatch, deployment, release publication, or
large-context task submission.

## External-brain Review

The user authorized full automatic Web AI binding for this stage. The agent sent
a compact Stage 5 review request to the already-bound ChatGPT tab. The request
included only stage status, the closed-loop goal, and safety constraints; it did
not include source files, secrets, private paths, browser profile data, cookies,
raw transcripts, or uploads.

Result summary:

- marker: `DEVFRAME_STAGE5_REVIEW_V1`
- verdict: `proceed_with_guarded_stage5_implementation`
- recommended loop: bounded task spec, local concurrent execution, summarized
  Web AI context, redacted evidence, review gate before state/action update
- top risks: transcript or private-path leakage, session misuse, conflicting
  state updates, and gate bypass

The provider conversation URL is stored only in the untracked local runtime
summary file, not in this public status document.

## Runtime Import Evidence

Runtime directory:

```powershell
$runtime = Join-Path $env:TEMP 'devframe-stage4-web-ai-runtime'
```

Imported files under the runtime:

```text
web-ai-sessions\chatgpt-chrome-binding.json
web-ai-sessions\devframe-stage5-web-ai-review-summary.json
```

Import command:

```powershell
python -m control_plane.cli web-ai import $summaryPath --runtime-dir $runtime
```

Visual-state check:

```powershell
python -m control_plane.cli visual-state --runtime-dir $runtime --format json
```

Result summary:

- session `stage5-web-ai-review-session` is imported as `status = completed`
- gate `stage5-web-ai-review-session-review-gate` is projected as
  `kind = acceptance`
- gate status is `pass`
- gate reason includes `DEVFRAME_STAGE5_REVIEW_V1`
- action queue projects the imported Stage 5 review actions

## Implementation Summary

New read-model behavior:

- Imported Web AI sessions may carry `native_refs.review_marker` and
  `native_refs.review_verdict`.
- When both are present, `devframe visual-state` projects a read-only
  acceptance gate for that imported review session.
- Positive verdict tokens such as `proceed`, `pass`, or `accepted` become
  `status = pass`.
- Stop/fail/block verdict tokens and negative phrases such as
  `do_not_proceed` become `status = blocked`.

This is intentionally a projection layer. It does not mutate source session
files, browser state, or external provider state.

## Verification

Targeted tests:

```powershell
python -m pytest packages\control-plane\tests\test_rdgoal.py::test_visual_control_plane_projects_web_ai_review_gate packages\control-plane\tests\test_rdgoal.py::test_visual_control_plane_blocks_negative_web_ai_review_gate packages\control-plane\tests\test_rdgoal.py::test_visual_control_plane_marks_default_chatgpt_binding_ready_from_import -q
```

Result:

- `3 passed`

Full release verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Result:

- `python -m pytest -q`: `160 passed`
- public snapshot: `[OK]`
- control-plane wheel smoke: `[OK]`
- `git diff --check`: `[OK]`
- final verdict: `[OK] Release verification passed.`

## Reviewer Index

Changed files for this stage:

- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `docs/agent-runtime/visual-control-plane.md`
- `docs/status/local-agent-control-plane-stage-2-acceptance.md`
- `docs/status/local-agent-control-plane-stage-5-closed-loop.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md`

Review focus:

- Imported review gates must remain read-only projections.
- Summary imports must not contain raw prompts, raw transcripts, cookies,
  browser profile data, or private paths.
- A positive Web AI verdict must not bypass local verification.
- External provider work must stay behind explicit summary/evidence boundaries.

## Current Verdict

Stage 5 is verified at the external-review-gate level. The remaining work before
calling the whole project locally release-prepared is Stage 6 stabilization:
final public surface review, final release verification, and optional commit/PR
preparation when explicitly requested.
