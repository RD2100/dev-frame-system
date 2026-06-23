# Reviewer Index

This index summarizes the current rdgoal/control-plane release slice for human
review. It is intentionally concise and points reviewers to the files and
commands that matter most.

## Changed File Groups

- Public overview and quickstart docs:
  `README.md`, `README.zh-CN.md`, `packages/control-plane/README.md`,
  `packages/control-plane/QUICKSTART.md`.
- Release and readiness docs:
  `docs/agent-runtime/rdgoal-total-control.md`,
  `docs/agent-runtime/dispatch-model-profiles.md`,
  `docs/agent-runtime/integration-contracts.md`,
  `docs/agent-runtime/rdpaper-workflow.md`,
  `docs/agent-runtime/runtime-invariants.md`,
  `docs/agent-runtime/visual-control-plane.md`,
  `docs/agent-runtime/web-ai-adapter-contract.md`,
  `docs/agent-runtime/project-local-skill-bindings.md`,
  `docs/status/release-readiness.md`, `docs/status/reviewer-index.md`.
- Verification scripts:
  `scripts/verify-public-snapshot.ps1`,
  `scripts/verify-control-plane-wheel.ps1`,
  `scripts/verify-release.ps1`,
  `packages/agent-acceptance/templates/ci-preflight/install.ps1`.
- CI entrypoint:
  `.github/workflows/release-verify.yml`.
- Control-plane rdgoal implementation:
  `packages/control-plane/setup.py`,
  `packages/control-plane/control_plane/agent_adapter.py`,
  `packages/control-plane/control_plane/backup_guard.py`,
  `packages/control-plane/control_plane/decision_engine.py`,
  `packages/control-plane/control_plane/dispatch_packet.py`,
  `packages/control-plane/control_plane/orchestrator.py`,
  `packages/control-plane/control_plane/project_contract.py`,
  `packages/control-plane/control_plane/rdgoal.py`,
  `packages/control-plane/control_plane/rdgoal_cli.py`,
  `packages/control-plane/control_plane/runtime_digest.py`,
  `packages/control-plane/control_plane/runtime_store.py`,
  `packages/control-plane/control_plane/visual_state.py`,
  `packages/control-plane/control_plane/worker.py`,
  `packages/control-plane/control_plane/dashboard.py`.
- Existing control-plane integration points:
  `packages/control-plane/control_plane/cli.py`,
  `packages/control-plane/control_plane/pipeline_runner.py`.
- ai-workflow-hub context adapter:
  `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters/zotero_web_metadata_pilot.py`.
- Starter project templates:
  `packages/control-plane/templates/code_project/*`,
  `packages/control-plane/templates/paper_iteration/PAPER_PROFILE.yaml`,
  `packages/control-plane/templates/paper_iteration/PAPER_STATE.yaml`,
  `packages/control-plane/templates/paper_iteration/*`,
  `packages/control-plane/templates/visual_control_plane/`,
  `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`,
  `packages/control-plane/templates/runtime-bootstrap/*`,
  `templates/runtime-bootstrap/bootstrap.ps1`.
- Public rules and schemas:
  `rules/orchestration.md`, `rules/project-contracts/_template.md`,
  `rules/web-ai-adapters.md`,
  `schemas/agent-runtime/memory-update-record.schema.json`,
  `schemas/project_contract.schema.json`,
  `schemas/rdgoal_dispatch_packet.schema.json`,
  `schemas/resource-integration/codegraph-index-record.schema.json`,
  `schemas/resource-integration/memory-context-record.schema.json`,
  `schemas/resource-integration/script-safety-record.schema.json`,
  `schemas/visual_control_plane_state.schema.json`,
  `schemas/web_ai_adapter.schema.json`,
  `packages/test-frame/schemas/agent-runtime/memory-update-record.schema.json`,
  `packages/test-frame/schemas/resource-integration/codegraph-index-record.schema.json`,
  `packages/test-frame/schemas/resource-integration/memory-context-record.schema.json`,
  `packages/test-frame/schemas/resource-integration/script-safety-record.schema.json`.
- Tests:
  `packages/control-plane/tests/test_rdgoal.py`,
  `packages/control-plane/tests/test_cli.py`,
  `packages/control-plane/tests/test_public_snapshot.py`, `pytest.ini`.
- Negative test fixtures:
  `docs/agent-runtime/negative-test-fixtures/NEG-017-write-outside-scope.json`,
  `docs/agent-runtime/negative-test-fixtures/NEG-024-path-traversal-read.json`.

## Critical Code Paths

- `/rdgoal` and shell `rdgoal` routing:
  `setup.py` exposes `rdgoal=control_plane.rdgoal_cli:main`; `devframe rdgoal`
  remains available through `control_plane/cli.py` for compatibility.
- `/rdpaper` adapter contract:
  `docs/agent-runtime/rdpaper-workflow.md` defines the slash workflow, while
  `docs/agent-runtime/web-ai-adapter-contract.md`,
  `schemas/web_ai_adapter.schema.json`, and
  `packages/control-plane/templates/paper_iteration/WEB_AI_ADAPTER.yaml` define
  the browser and web AI adapter boundary.
- Future visual client boundary:
  `docs/agent-runtime/visual-control-plane.md` defines the governance-first
  object model for projects, provider bindings, agents, runs, evidence,
  reviews, gates, and controller decisions.
- Visual control-plane read model:
  `schemas/visual_control_plane_state.schema.json` and
  `packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml`
  define the first machine-readable state snapshot for a future GUI or CLI
  inspector.
- Project contract creation:
  `control_plane/rdgoal.py` writes project-local contracts by default under
  `<project>/rules/project-contracts/`.
- Bootstrap behavior:
  source checkout can run root bootstrap assets; wheel installs safely return
  `bootstrap_unavailable` while still producing a dispatch packet.
- Dispatch packet handoff:
  `control_plane/dispatch_packet.py` writes `packet.json`, `TASKSPEC.json`,
  and `TASKSPEC.md` into the runtime outbox.
- Snapshot guard:
  `control_plane/backup_guard.py` validates targets are inside the project
  before creating snapshot directories.
- Worker result semantics:
  `control_plane/worker.py` and `rdgoal_cli.py` keep `blocked`, `failed`, and
  unknown report states non-zero.
- Cross-process digest:
  `control_plane/runtime_store.py` and `runtime_digest.py` rebuild status from
  runtime files rather than process memory.
- Visual state export:
  `control_plane/visual_state.py` converts the persisted rdgoal digest into the
  Visual Control Plane read model, and `control_plane/cli.py` exposes it as
  `devframe visual-state` plus the focused `devframe actions` queue view. It
  can also render the same state as a static HTML dashboard snapshot.
  `control_plane/dashboard.py` serves the same model through
  a read-only local dashboard at `/`, `/state.json`, and `/actions.json`.
  Run summaries include
  TaskSpec paths, packet paths, report paths, and a copyable next command for
  read-only handoff/resume. The CLI refuses non-loopback dashboard binds unless
  `--allow-remote` is explicit. Paper iteration workspaces can be attached with
  `--paper-project <dir>` and appear as `rdpaper` runs with a privacy gate.

## Verification Evidence

Primary release gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The gate must pass all of the following:

- `python -m pytest -q`
- `powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\verify-control-plane-wheel.ps1`
- `git diff --check`

Additional targeted probes covered by tests:

- Generated `build` directories are rejected by the public snapshot checker.
- Public Markdown docs are UTF-8 readable and do not contain private path or
  mojibake markers.
- Blocked/failed rdgoal workers return non-zero.
- Command workers do not run held packets.
- Snapshot-backed actions reject targets outside the project root before
  creating snapshot directories.
- Dispatch packets and project contracts validate against public schemas.
- The default paper Web AI Adapter template validates against
  `schemas/web_ai_adapter.schema.json`.
- The default visual control-plane state template validates against
  `schemas/visual_control_plane_state.schema.json`.
- `devframe visual-state --runtime-dir <dir>` exports schema-valid JSON from a
  real rdgoal runtime directory.
- `devframe visual-state --format html --output <file>` writes a local static
  dashboard snapshot and escapes runtime text before rendering.
- The dashboard server serves the same state through real HTTP requests and
  rejects write methods with `405`.
- The Agent Registry joins agents to provider bindings so role, scope, provider,
  binding health, and agent status are visible in one table.
- Visual state run details expose TaskSpec/packet/report paths and next-command
  strings from a real rdgoal runtime.
- Run Details cards include the current controller decision and decision next
  action beside TaskSpec/evidence paths.
- The dashboard includes a `Gate Focus` section that promotes active gates
  before the full queue and tables, including the matching action id, resume
  filter, and served Markdown handoff link.
- `devframe visual-state --paper-project <dir>` and
  `devframe dashboard serve --paper-project <dir>` expose paper iteration
  workspaces as read-only `rdpaper` runs and surface their `WEB_AI_ADAPTER.yaml`
  provider binding health and manual fallback instructions through a matching
  provider safety gate with a next action.
- Visual state includes a read-only `next_actions` queue derived from gates,
  runs, and decisions. `devframe actions` prints that queue directly, and the
  HTML dashboard renders it as `Action Queue`. The actions CLI can filter by
  status, priority, source type, source id, and action id; `--fail-on-match` is
  a read-only gate that returns non-zero when the filtered queue is not empty.
  Text output, Markdown handoff packets, and the dashboard Action Queue include
  action ids plus copyable `--action-id` resume filters so single-action exports
  remain traceable. It can also write a Markdown handoff packet for manual
  resume or Web AI continuation. The same filtered queue is available from the
  read-only dashboard at `/actions.json` and as a Markdown handoff view at
  `/actions.md`;
  invalid filter values return `400`. The served dashboard homepage links to
  `/state.json`, `/actions.json`, `/actions.md`, and per-action Markdown
  handoffs, while static HTML snapshots do not claim live endpoints.
- `devframe run --pipeline <path> --execute --project <dir>` passes the project
  directory into the stage executor, so dashboard next-command strings point at
  a real CLI path.
- `devframe dashboard serve --host 0.0.0.0` is rejected unless the user passes
  `--allow-remote`.
- The wheel smoke test runs JSON and HTML `devframe visual-state` exports plus
  filtered `devframe actions` JSON and Markdown handoff output after
  `rdgoal worker` and `rdgoal digest`, checks packaged rdgoal and rdpaper run
  details, checks the installed `devframe --help`, `devframe run --help`, and
  `devframe dashboard --help` first-use entrypoints, then imports the packaged
  dashboard server, binds it to a temporary local port, checks homepage endpoint
  links, and probes both `/actions.json` and `/actions.md`, including action-id
  filtering.
- Negative test fixtures validate write-outside-scope and path-traversal-read
  behavior.
- New resource-integration and agent-runtime schemas validate private-path and
  script-safety records.

## Generated Artifacts

The release gate may temporarily create:

- `packages/control-plane/build`
- `packages/control-plane/devframe_control_plane.egg-info`
- temporary wheel smoke directories under the OS temp directory

The wheel smoke script removes these artifacts in `finally`. A clean final
state has no `build`, `dist`, `*.egg-info`, or `public-snapshot-probe*`
directories in the repository.

## Known Gaps

- The wheel distribution intentionally does not include the full repository
  root bootstrap assets. This is documented as `bootstrap_unavailable` behavior.
- Real external AI/browser dispatch is outside this release slice; the current
  worker path proves packet handoff, local dry-run, command worker, and aihub
  adapter invocation semantics.
- `/rdpaper` provider automation is contract-first. Chrome plus ChatGPT is a
  reference path, while DeepSeek, Doubao, Kimi, internal web AIs, and manual
  mode are documented extension points rather than guaranteed built-ins.
- GitHub CI/PR state is not represented by local verification alone. Reviewers
  should run or add CI before merging if this becomes a remote release.

## Suggested Review Focus

- Confirm no private runtime state, evidence packs, generated archives, or
  local browser/agent state were added.
- Confirm release verification runs from a fresh checkout on Windows PowerShell.
- Confirm `.github/workflows/release-verify.yml` invokes the same release gate.
- Confirm worker failure semantics cannot produce fake green results.
- Confirm source checkout and wheel install paths both match the documented
  rdgoal behavior.
- Confirm Chrome and ChatGPT are documented as defaults, not hard-coded
  architecture boundaries.
- Confirm browser profiles, cookies, real paper full text, PDFs, and external
  service calls remain human-gated by the adapter contract.
- Confirm docs are understandable for a new open-source reader without internal
  project history.
- Confirm the new control-plane doc sharpens product boundaries instead of
  drifting toward a generic single-model chat client.
- Confirm the `stepfun/step-3.7-flash` profile documents its intended narrow
  use case and the external evidence-dir permission limitation.
- Confirm private-path sanitization is enforced by runtime invariants and covered
  by the new negative test fixtures.
- Confirm `integration-contracts.md` and `project-local-skill-bindings.md` keep
  adapter and skill-binding scope explicit.
- Confirm new resource-integration and agent-runtime schemas validate private-path
  and script-safety records.
