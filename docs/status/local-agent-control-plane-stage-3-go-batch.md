# Local Agent Control Plane Stage 3 `/go` Batch

Date: 2026-06-23
Depends on: Stage 2 accepted
Status: `verified`

This file is the prepared execution package for the next automation stage. It
keeps the `/go` work split into independent modules so multiple coding agents
can work without stepping on the same files.

## Start Rule

Stage 2 has been accepted by the human owner. Stage 3 preview/preparation can
continue on this branch.

Before starting Stage 3:

```powershell
git status --short --branch
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Expected result:

- branch/checkpoint is understood,
- Stage 2 verification is green,
- no generated probe, wheel, browser, runtime, or evidence artifacts appear in
  `git status --short`.

Stop only when a shard needs browser profile access, credentials, live provider
calls, external side effects, release publication, deployment, or irreversible
actions.

## Batch Strategy

Use preview mode first to estimate the split without writing packets:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "<goal>" --project . --agents 1 --target "<path>" --preview
```

Then use prepare mode to write runnable packets without spending worker tokens:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "<goal>" --project . --agents 1 --target "<path>"
```

After reviewing the prepared packet, run:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code execute latest
```

If one shard fails after others pass, rerun only failed work with:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code execute latest
```

Use `--rerun-passed` only when the reviewer intentionally wants a full rerun.
The default executor should skip already passed agents.

## Shards

### Shard A: Session Detail Surface

Goal:

```text
Extend the read-only Local Agent Control Plane session detail surface. Keep it
inspection-only. Do not add mutating dashboard controls.
```

Allowed targets:

- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/visual_state.py`
- `schemas/visual_control_plane_state.schema.json`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_rdgoal.py`

Preview command:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "Extend the read-only Local Agent Control Plane session detail surface. Keep it inspection-only. Do not add mutating dashboard controls." --project . --agents 1 --target packages/control-plane/control_plane/dashboard.py --preview
```

Hard stop:

- Stop before adding any dashboard action that mutates local files, runtime
  state, browser state, credentials, or external services.

### Shard B: Provider Binding Adapters

Goal:

```text
Advance provider binding adapter validation for summary-only Web AI bindings.
Keep probes local and credential-free. Do not access live browser profiles.
```

Allowed targets:

- `packages/control-plane/control_plane/provider_binding_probe.py`
- `packages/control-plane/tests/test_provider_binding_probe.py`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/agent-runtime/visual-control-plane.md`

Preview command:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "Advance provider binding adapter validation for summary-only Web AI bindings. Keep probes local and credential-free. Do not access live browser profiles." --project . --agents 1 --target packages/control-plane/control_plane/provider_binding_probe.py --preview
```

Hard stop:

- Stop before reading browser profiles, cookies, account state, tokens, or
  credential stores.
- Stop before making a live provider request.

### Shard C: OpenCode Readiness And Local Tool Gateway Evidence

Goal:

```text
Strengthen OpenCode readiness and Local Tool Gateway evidence while keeping all
real probe artifacts outside the public repository.
```

Allowed targets:

- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_slice0.py`
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_serve_slice1.py`
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_client.py`
- `packages/ai-workflow-hub/tests/test_opencode_slice0.py`
- `packages/ai-workflow-hub/tests/test_opencode_serve_slice1.py`
- `schemas/agent-runtime/opencode-readiness-report.schema.json`

Preview command:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "Strengthen OpenCode readiness and Local Tool Gateway evidence while keeping all real probe artifacts outside the public repository." --project . --agents 1 --target packages/ai-workflow-hub/src/ai_workflow_hub/opencode_serve_slice1.py --preview
```

Hard stop:

- Stop before running real OpenCode probes in the repository root.
- Stop before committing JSONL, temp workspaces, generated reports, or raw
  worker output from real projects.

### Shard D: Public Docs And Release Hygiene

Goal:

```text
Keep the Stage 3 public documentation, reviewer index, and release hygiene
aligned with the Local Agent Control Plane roadmap.
```

Allowed targets:

- `README.md`
- `README.zh-CN.md`
- `docs/agent-runtime/*.md`
- `docs/status/*.md`
- `scripts/verify-public-snapshot.ps1`
- `scripts/verify-release.ps1`

Preview command:

```powershell
$env:PYTHONPATH="packages/control-plane;packages/ai-workflow-hub/src"
python -m control_plane.cli code "Keep the Stage 3 public documentation, reviewer index, and release hygiene aligned with the Local Agent Control Plane roadmap." --project . --agents 1 --target docs/status --preview
```

Hard stop:

- Stop before adding internal delivery logs, private absolute paths, evidence
  archives, browser profiles, generated wheels, build folders, or raw JSONL.

## Execution Status

Batch run:

- `go_run_id`: `go-dev-frame-system-1782224326109-52d92b`
- agents: 4
- final `/go` status: `passed`
- note: Shard C first failed because the worker wrote its first report to the
  wrong path; `devframe code execute` was run again and skipped the already
  passed shards, then Shard C passed.

| Shard | Focus | Status |
|---|---|---|
| A | Session detail/page surface | `passed` |
| B | Provider binding adapters | `passed` |
| C | OpenCode readiness and Local Tool Gateway evidence | `passed_after_retry` |
| D | Public docs and release hygiene | `passed` |

See `docs/status/local-agent-control-plane-stage-3-execution-report.md` for the
orchestrator summary.

## Shard Report Requirements

Each shard must write or update a reviewer-facing report with:

- changed files,
- commands run,
- exact output summary,
- generated artifacts and cleanup status,
- known gaps,
- suggested reviewer focus,
- `passed`, `failed`, `blocked`, or `human_required` verdict.

## Merge Gate

The orchestrator may merge Stage 3 shard output only after:

```powershell
git diff --name-status
python -m pytest packages\ai-workflow-hub\tests -q
python -m pytest packages\control-plane\tests -q
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The merge verdict should be `pass` for low-risk read-only/local work with green
verification. Use `human_required` only if a shard touches live Web AI binding,
browser state, credentials, external services, release publication, or
deployment-sensitive behavior.

Current merge verdict: `pass` on the local worktree after Stage 3 verification.
