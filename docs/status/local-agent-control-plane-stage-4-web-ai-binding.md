# Local Agent Control Plane Stage 4 Web AI Binding

Date: 2026-06-23
Branch: `codex/go-concurrent-dispatch`
Status: `verified_summary_binding`

This report records the first real Chrome plus ChatGPT binding check for the
Local Agent Control Plane route. The check binds an already-open ChatGPT tab as
a summary-only Web AI session. It does not submit a prompt, capture a
transcript, read cookies, export a browser profile, or persist message text.

## Scope

Stage 4 proves that the control plane can observe a real browser-hosted Web AI
surface and import that observation into the Visual Control Plane read model.

In scope:

- read local Chrome CDP metadata from `http://<cdp-host>:<cdp-port>`,
- identify an already-open `https://chatgpt.com/` page tab,
- generate a summary-only `chatgpt` session,
- import it into a local runtime under `%TEMP%`,
- surface the session through `devframe sessions` and `devframe visual-state`.

Out of scope:

- submitting a task prompt to ChatGPT,
- reading raw conversation content,
- inspecting cookies, local storage, browser profiles, passwords, or account
  internals,
- uploading files or project-private context,
- publishing, deploying, or pushing changes.

## Implementation Summary

New reusable entrypoint:

```powershell
devframe web-ai bind-chrome --runtime-dir <runtime> --project <project-id> --cdp-endpoint http://<cdp-host>:<cdp-port>
```

The command writes:

```text
<runtime>\web-ai-sessions\chatgpt-chrome-binding.json
```

The imported summary uses:

- `provider = chatgpt`
- `status = active`
- `native_refs.runtime = chrome-cdp-binding` before import
- `native_refs.runtime = web-ai-import` in the Visual Control Plane read model
- `native_refs.provider_url = https://chatgpt.com/`

When an active imported ChatGPT session exists, the default `chatgpt-web`
provider binding is projected as `health = ready`.

## Real Binding Evidence

Chrome CDP check:

```powershell
Invoke-RestMethod -Uri 'http://<cdp-host>:<cdp-port>/json/version' -TimeoutSec 3
Invoke-RestMethod -Uri 'http://<cdp-host>:<cdp-port>/json' -TimeoutSec 3
```

Result summary:

- Chrome CDP responded as `Chrome/149.0.7827.155`.
- A `page` tab with URL `https://chatgpt.com/` was present.

Binding command:

```powershell
$env:PYTHONPATH='packages/control-plane;packages/ai-workflow-hub/src'
$runtime = Join-Path $env:TEMP 'devframe-stage4-web-ai-runtime'
python -m control_plane.cli web-ai bind-chrome --runtime-dir $runtime --project dev-frame-system --cdp-endpoint http://<cdp-host>:<cdp-port>
```

Result summary:

- `provider`: `chatgpt`
- `session_id`: `chatgpt-chrome-session`
- `project_id`: `dev-frame-system`
- `status`: `active`
- `provider_url`: `https://chatgpt.com/`
- summary-only safety line: no transcript, cookies, profile data, or message
  text captured

Control-plane read checks:

```powershell
python -m control_plane.cli sessions --runtime-dir $runtime
python -m control_plane.cli visual-state --runtime-dir $runtime --format json
```

Result summary:

- `devframe sessions` lists `chatgpt-chrome-session provider=chatgpt status=active`.
- `devframe visual-state` projects `chatgpt-web health=ready`.
- The imported agent `chatgpt-web-coordinator` is projected as `status=active`.

## Verification

Targeted tests:

```powershell
python -m pytest packages\control-plane\tests\test_chrome_binding_probe.py packages\control-plane\tests\test_provider_binding_probe.py packages\control-plane\tests\test_cli.py::test_web_ai_bind_chrome_help packages\control-plane\tests\test_cli.py::test_web_ai_bind_chrome_imports_runtime_session packages\control-plane\tests\test_rdgoal.py::test_visual_control_plane_state_reads_web_ai_sessions packages\control-plane\tests\test_rdgoal.py::test_visual_control_plane_marks_default_chatgpt_binding_ready_from_import -q
```

Result:

- `14 passed`

Full release gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Result:

- `python -m pytest -q`: `158 passed`
- public snapshot: `[OK]`
- control-plane wheel smoke: `[OK]`
- `git diff --check`: `[OK]`
- final verdict: `[OK] Release verification passed.`

## Reviewer Index

Changed files for this stage:

- `packages/control-plane/control_plane/chrome_binding_probe.py`
- `packages/control-plane/control_plane/cli.py`
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/tests/test_chrome_binding_probe.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/status/local-agent-control-plane-stage-2-acceptance.md`
- `docs/status/local-agent-control-plane-stage-4-web-ai-binding.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md`

Review focus:

- The binding command must stay summary-only.
- Failure to reach CDP, find a ChatGPT tab, or avoid a login/auth page must not
  be reported as pass.
- Browser profile data, cookies, local storage, raw transcripts, and message
  text must remain outside runtime summaries and the public repository.
- The real runtime artifact under `%TEMP%` must remain untracked.

## Current Verdict

Stage 4 is verified for real Chrome/ChatGPT binding at the summary-session
level. The next stage is a closed-loop control-plane run that uses the imported
Web AI session as governed context. Sending project context or task prompts to
ChatGPT remains a separate action-time decision because it transmits data to an
external provider.
