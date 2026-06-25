# Reviewer Index: Open-Source Release Batch 1

## Purpose

This is the reviewer map for the first open-source release batch. It focuses on what is currently proven and auditable in the repository: MCP/Web-AI intake, T3/native client projection, and governed visual state.

## In-Scope Review Surface

- `packages/control-plane`: runtime, entrypoints, probes, and client launch surfaces.
- `docs/agent-runtime`: interface contracts and operating model for MCP/Web-AI and visual control-plane behavior.
- `docs/status`: latest milestone decisions and state snapshots for this batch.
- `schemas/*`: state, bridge, and session contracts for reader-facing outputs.
- `scripts`: release and public-snapshot verification gates.

## First-Read Files

### Runtime Entry + Contracts
- `packages/control-plane/setup.py`
- `packages/control-plane/control_plane/cli.py`
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/agent-runtime/integration-contracts.md`

### MCP / Web-AI Path
- `packages/control-plane/control_plane/mcp_live_probe.py`
- `packages/control-plane/control_plane/provider_binding_probe.py`
- `packages/control-plane/control_plane/project_contract.py`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `rules/web-ai-adapters.md`
- `packages/control-plane/tests/test_mcp_live_probe.py`
- `packages/control-plane/tests/test_provider_binding_probe.py`

### Native / T3 Client Path
- `packages/control-plane/control_plane/client_launcher.py`
- `packages/control-plane/control_plane/client_manifest.py`
- `packages/control-plane/control_plane/t3_bridge_bundle.py`
- `packages/control-plane/control_plane/t3_adapter.py`
- `schemas/visual_client_manifest.schema.json`
- `schemas/t3_bridge_bundle.schema.json`
- `schemas/t3_client_shell.schema.json`
- `docs/agent-runtime/visual-control-plane.md`
- `docs/status/t3code-client-mainline-reuse-assessment.md`
- `docs/status/recon-receipt-local-agent-client-mainline.md`

### Governance + Visual Read Model
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/runtime_digest.py`
- `packages/control-plane/control_plane/orchestrator.py`
- `schemas/visual_control_plane_state.schema.json`
- `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`
- `packages/control-plane/tests/test_public_snapshot.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `packages/control-plane/tests/test_dashboard_actions.py`
- `schemas/resource-integration/script-safety-record.schema.json`
- `schemas/resource-integration/memory-context-record.schema.json`

### Current State Evidence Files
- `docs/status/recon-receipt-local-agent-client-mainline.md`
- `docs/status/t3code-client-mainline-reuse-assessment.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md` (this file)

## Critical Paths to Verify

- `devframe` bootstrap to governance surface:
  - `setup.py` exposes `devframe` and installs `control_plane/cli.py` command handlers.
  - CLI must route MCP, T3 client, visual-state/actions, and rdgoal entrypoints through current, tested code paths.
- MCP/Web-AI intake and provider binding:
  - `provider_binding_probe.py` and `mcp_live_probe.py` should accept reference-safe summaries and reject unsafe session data.
  - Tests above should cover negative cases and session summaries.
- Native/T3 read model contract:
  - `client_manifest.py` exposes `/client-manifest.json`, `/client-plan.json`, `/t3-bridge.json`, `/t3-shell.json`.
  - `t3_bridge_bundle.py` builds installable bridge artifacts and launch helpers.
  - `t3_adapter.py` maps DevFrame state to `t3_shell` snapshots with action overlays.
- Visual control-plane outputs:
  - `dashboard.py` and `visual_state.py` must keep mutation points constrained and endpoints read-only by default.
  - Action queue filtering (`--status`, `--priority`, `--source-type`, `--source-id`, `--action-id`) must remain deterministic.

## Open-Source Review Checklist

1. Confirm MCP/Web-AI claims are tied to local public snapshot tests, not private runtime assumptions.
2. Confirm native-client surface is projection-based: DevFrame remains the governance source of truth.
3. Confirm native/T3 integration paths are manifest/bridge first and schema-validated.
4. Confirm generated/private directories are excluded by `verify-public-snapshot.ps1`.
5. Confirm local mutation endpoints stay explicit and loopback-limited.
6. Confirm stage-8 native reuse status is current and does not overclaim release/publish readiness.

## Public Surface File Index

This index ensures all required public snapshot paths are explicitly referenced for reviewer traceability.

- `README.md`
- `README.zh-CN.md`
- `.github/workflows/release-verify.yml`
- `docs/agent-runtime/rdgoal-total-control.md`
- `docs/agent-runtime/dispatch-model-profiles.md`
- `docs/agent-runtime/rdpaper-workflow.md`
- `docs/agent-runtime/visual-control-plane.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md`
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `packages/control-plane/setup.py`
- `packages/control-plane/control_plane/cli.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/templates/paper_iteration/PAPER_PROFILE.yaml`
- `packages/control-plane/templates/paper_iteration/PAPER_STATE.yaml`
- `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`
- `packages/control-plane/templates/paper_iteration/WEB_AI_ADAPTER.yaml`
- `packages/control-plane/control_plane/agent_adapter.py`
- `packages/control-plane/control_plane/backup_guard.py`
- `packages/control-plane/control_plane/decision_engine.py`
- `packages/control-plane/control_plane/dispatch_packet.py`
- `packages/control-plane/control_plane/orchestrator.py`
- `packages/control-plane/control_plane/project_contract.py`
- `packages/control-plane/control_plane/rdgoal.py`
- `packages/control-plane/control_plane/rdgoal_cli.py`
- `packages/control-plane/control_plane/runtime_digest.py`
- `packages/control-plane/control_plane/runtime_store.py`
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/control_plane/worker.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_public_snapshot.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `pytest.ini`
- `rules/orchestration.md`
- `rules/project-contracts/_template.md`
- `rules/web-ai-adapters.md`
- `schemas/project_contract.schema.json`
- `schemas/rdgoal_dispatch_packet.schema.json`
- `schemas/visual_control_plane_state.schema.json`
- `schemas/web_ai_adapter.schema.json`
- `scripts/verify-control-plane-wheel.ps1`
- `scripts/verify-release.ps1`

## Required Verification

At minimum, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

For the fuller gate, align with `docs/status/release-readiness.md`.
