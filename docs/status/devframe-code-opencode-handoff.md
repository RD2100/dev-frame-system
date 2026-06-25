# DevFrame Code / Local Agent Control Plane Handoff

Date: 2026-06-23
Branch: `codex/go-concurrent-dispatch`

## Final Target

The final target is not only an OpenCode wrapper.

The target is to turn the old "external brain in a web AI conversation" workflow
into a local, web-facing Agent control plane:

```text
Visual Client
  -> Project Governance Protocol
  -> Agent Registry
  -> Session / Conversation Pages
  -> Run Controller
  -> Evidence Ledger
  -> Local Tool Gateway
```

`devframe code` should become the OpenCode-first local programming entrypoint,
with a stronger governance layer than a raw coding CLI:

- Web AI conversations become local `Agent` / `Session` objects.
- Each session can become a local web page instead of only a TUI/chat thread.
- Sessions carry messages, tool calls, diffs, token/cost, gates, and evidence.
- Runs are governed by TaskSpec, ExecutionReport, Review, Evidence, Gate, and
  Action Queue records.
- OpenCode is the only built-in worker profile today. Other local tools can
  still be routed later through explicit custom commands or a Local Tool
  Gateway, but they are not default built-in worker choices.

OpenCode is therefore the current built-in hand of the system, not the system
itself.

## Mental Model To Preserve

OpenCode already has many `session` objects. In the desired devframe product,
those sessions should eventually surface as local web pages:

```text
Project
  -> Agent
     -> Session / Conversation
        -> Messages
        -> Tool Calls
        -> Diff
        -> Evidence
        -> Gates
        -> Actions
```

That means the next architecture slice should not only ask "can OpenCode run a
task?" It should also ask "how do provider-native sessions map into
DevFrameSession pages?"

## Current Committed Baseline

Already pushed on `codex/go-concurrent-dispatch` before the current uncommitted
work:

- Dashboard English/Chinese language switching exists.
- `devframe code` is positioned as the primary coding CLI.
- `devframe code workers` reports local worker availability.
- `/go` can prepare concurrent coding-agent packets.
- `devframe code status` inspects prepared runs without spending worker tokens.
- `devframe code execute` reuses prepared packets and skips already passed
  agents unless `--rerun-passed` is set.
- Go-run cards in the dashboard show copyable status and execute commands.
- Worker launch failures are reported through `ExecutionReport.md` and
  `worker-output.txt`.

Relevant pushed commits:

- `53f76cf Report worker launch failures cleanly`
- `99ab10f Make code CLI the primary entrypoint`
- `5f47fdd Add coding worker availability probe`
- `2f1ad13 Add coding worker profiles`

## Current Uncommitted Worktree

The worktree contains in-flight OpenCode readiness work, the first
Local Agent Control Plane session surface, public documentation alignment, and
this handoff file. Review it before committing; do not discard it blindly.

Key modified areas:

- Public copy now describes `devframe code` as OpenCode-first, with only
  `--worker opencode` as the built-in worker option.
- `packages/control-plane/control_plane/cli.py` exposes
  `devframe code session [latest|<go-run-id>] [--format text|json]`.
- `packages/control-plane/control_plane/cli.py` also exposes
  `devframe sessions`, `devframe web-ai import`, and
  `devframe web-ai probe` for summary-only session import/probe flows.
- `packages/control-plane/control_plane/dashboard.py` exposes read-only
  `/sessions.json`.
- `packages/control-plane/control_plane/visual_state.py` now includes
  `sessions` in the read model and dashboard.
- `devframe web-ai import` accepts UTF-8, UTF-8 BOM, and Windows PowerShell
  UTF-16 BOM JSON summaries, then rewrites the imported runtime copy as UTF-8.
- `packages/control-plane/control_plane/dispatch_packet.py` sanitizes natural
  ExecutionReport changed-file bullets so reviewer notes do not become file
  paths.
- `scripts/verify-control-plane-wheel.ps1` now checks the OpenCode-first help
  text and the dashboard session endpoint link.
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_client.py` no longer
  contains a machine-private OpenCode fallback path; use `OPENCODE_BIN`, common
  user locations, or `PATH`.
- OpenCode Slice 0/Slice 1 readiness probes live under
  `packages/ai-workflow-hub` with the readiness schema under
  `schemas/agent-runtime/`.

Current untracked public-surface candidates visible in `git status` include
this handoff file, the OpenCode readiness probe modules/tests/schema, and the
provider binding probe module/test. The root `chatgpt-summary.json` file is a
local demo import artifact and is ignored by `.gitignore`; convert it into a
sanitized test fixture under `packages/` only if it is intentionally needed.
A previously mentioned `rules/project-contracts/dev-frame-system.md` file was
not present during the current review.

New CLI commands in the in-flight diff:

- `devframe code session`
- `devframe sessions`
- `devframe web-ai import`
- `devframe web-ai probe`
- `aihub opencode-slice0`
- `aihub opencode-serve-slice1`

## Commit Boundary

Include in the current product slice:

- CodeGraph cost-control rules and `.codegraph/` ignore/public-snapshot handling.
- OpenCode-first `devframe code` public copy and worker-profile narrowing.
- `DevFrameSession` read model, CLI session surfaces, dashboard session export,
  and action queue projection for imported web AI session summaries.
- Summary-only web AI import/probe code and tests, including PowerShell
  UTF-16 JSON import compatibility.
- OpenCode Slice 0/Slice 1 readiness probe modules, tests, readiness schema,
  and wheel/public-snapshot verification updates.
- Dispatch/report parsing fixes that keep reviewer prose from becoming fake
  changed-file paths.
- This handoff document if it is accepted as public reviewer guidance for the
  current slice.

Exclude from the current product slice:

- `chatgpt-summary.json`; it is a local demo import input and is ignored.
- Any `.codegraph/`, `.ai/`, `.codex/`, `.opencode/`, browser profile, runtime,
  evidence archive, report dump, probe workspace, or generated wheel/build
  output.
- Raw OpenCode JSONL from real projects, raw browser transcripts, cookies,
  paper full text, private runtime state, or temporary `%TEMP%` probe outputs.
- Any Codex/Claude built-in worker profile restoration; custom commands remain
  possible through explicit `--command` only.

## OpenCode Readiness Evidence

Real local probes were run against temporary git repositories outside the repo.
Do not commit their artifacts.

Slice 0, `opencode run`:

- Verdict: `passed`
- OpenCode version: `1.17.9`
- OpenCode resolved to a local Windows `.cmd` executable; use the current probe
  output for the exact machine-specific path.
- It wrote `slice0-marker.txt` with matching content in a temporary git repo.
- JSONL had 6 events and observable session/token/cost/tool fields.
- Probe artifacts were written under a disposable temp directory matching
  `opencode-slice0-*/slice0-report.json`; do not commit them.

Slice 1, `opencode serve` + HTTP/SSE + `prompt_async`:

- Functional execution chain: passed.
- Overall verdict: `passed`
- Partial type: `(none)`
- Health endpoint was healthy.
- SSE was subscribed before `prompt_async`; `server.connected` was observed.
- `prompt_async` returned HTTP 204.
- Marker file landed on disk and content matched.
- SSE/message evidence included tool/write and `step-finish reason=stop`.
- No permission/question blocker was observed.
- `OPENCODE_CONFIG_CONTENT permission=allow` was enough for this probe.
- `/instance/dispose` returned successfully. On native Windows with OpenCode
  `1.17.9`, the process can exit with code 1 after a clean dispose; the probe
  now accepts this only when stderr has no error signals such as
  `level=ERROR`, `panic`, `traceback`, or `database is locked`.
- Probe artifacts were written under a disposable temp directory matching
  `opencode-serve-slice1-*/serve-slice1-report.json`; do not commit them.

Decision from this evidence:

- OpenCode `run` mode can remain a candidate for experimental low-cost worker
  execution.
- OpenCode `serve` mode has current passed readiness evidence under the
  clean-nonzero shutdown policy above.
- A non-zero serve shutdown is still a failure when dispose did not complete or
  the stderr log contains an error signal.
- This does not change the final product target; it only classifies one Local
  Tool Gateway backend.

## Verification Already Run

Current in-flight work was verified with:

```powershell
python -m pytest packages\ai-workflow-hub\tests -q
```

Result: `14 passed`.

```powershell
python -m pytest packages\control-plane\tests -q
```

Result: `138 passed`.

```powershell
python -m pytest packages\control-plane\tests\test_cli.py -k web_ai_import -q
```

Result: `6 passed`.

PowerShell UTF-16 import probe:

- Reproduced the failure with a JSON summary written through
  `Set-Content -Encoding Unicode`.
- After the fix, `devframe web-ai import` imported the file successfully and
  wrote the normalized runtime copy as UTF-8 JSON.

Real `/go` run against this repository:

- Preview split the landing work into 3 OpenCode shards.
- Initial `--execute` launched all 3 shards with
  `opencode run -m stepfun/step-3.7-flash --dangerously-skip-permissions
  --agent build`.
- One shard initially failed with `database is locked`; the prepared run was
  resumed with `devframe code execute <go-run-id>`, which skipped passed shards
  and reran only the failed shard.
- Final `/go` status: `passed`, 3/3 OpenCode worker shards passed.
- `devframe code session <go-run-id> --format json` showed 3 passed sessions
  with clean file-path-only `changed_files`.

Real Slice 1 probe was also re-run against a disposable temp git repository.
Result: `passed`; `server_stopped` detail recorded
`disposed=True returncode=1 clean_nonzero=True error_signals=0`.

```powershell
python -m pytest -q
```

Result: `152 passed`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Result: `[OK] Release verification passed.`

The release gate also ran public snapshot validation, control-plane wheel smoke,
and `git diff --check`.

Verification note: do not run `python -m pytest -q` and
`python -m pytest packages\control-plane\tests -q` concurrently. The public
snapshot negative tests create and remove temporary probe directories, so
parallel suites can race each other and produce a false `Get-ChildItem` failure.
Run the broad suite and package-specific suites serially when collecting final
evidence.

## OpenCode Wrapper / Fork Decision

Keep wrapper-first.

- Do not fork OpenCode yet.
- Do not rebuild an OpenCode-like engine inside devframe yet.
- Do not make OpenCode the product identity.
- Use OpenCode as a local execution backend only after readiness evidence and
  policy gates say it is safe enough.

License note:

- `anomalyco/opencode` is MIT licensed.
- Forking, modifying, commercial use, and redistribution are allowed if the MIT
  copyright and license notice are preserved when distributing copied source or
  substantial portions.
- Avoid naming a devframe product with `opencode` in the name or implying
  official affiliation.

## Recommended Next Actions

### 1. Review and commit the current control-plane slice

The current worktree now contains:

- the first provider-neutral `DevFrameSession` read model,
- opencode-only built-in `/go` worker selection,
- the first manual session surfaces: `devframe code session` and
  `/sessions.json`,
- real OpenCode Slice 0 and Slice 1 readiness probes,
- worker/report parsing fixes from real `/go` execution,
- documentation updates for the Local Agent Control Plane target.

Review the diff as a product slice, not only as OpenCode plumbing.

### 2. Review and commit readiness probes if acceptable

Review:

- public-surface safety,
- path hygiene,
- prompt/log redaction,
- Windows process cleanup,
- readiness report schema,
- tests staying hermetic by default.

Then re-run:

```powershell
python -m pytest packages\ai-workflow-hub\tests -q
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

### 3. Continue the product spine

After the current slice is committed or intentionally parked, continue with the
Local Agent Control Plane path:

- session list page,
- session detail page,
- action queue controls,
- agent registry display,
- mapping provider-native sessions into DevFrameSession,
- then Local Tool Gateway execution integration.

### 4. Next `/go` parallel shards after this slice is closed

Do not start these on top of the current uncommitted slice. Start them only
after the current boundary is committed or intentionally parked.

| Shard | Owner focus | Allowed paths | Hard stop |
|---|---|---|---|
| A | Session detail/page surface | `packages/control-plane/control_plane/dashboard.py`, `packages/control-plane/control_plane/visual_state.py`, `schemas/visual_control_plane_state.schema.json`, matching control-plane tests | Stop before adding mutating dashboard controls |
| B | Provider binding adapters | `packages/control-plane/control_plane/provider_binding_probe.py`, `packages/control-plane/tests/test_provider_binding_probe.py`, web-ai docs/tests | Stop before live browser/profile access or credential handling |
| C | OpenCode readiness and Local Tool Gateway evidence | `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_*.py`, `packages/ai-workflow-hub/tests/`, `schemas/agent-runtime/opencode-readiness-report.schema.json` | Stop before running probes in the repo root or committing probe artifacts |
| D | Public docs and release hygiene | `README*.md`, `docs/agent-runtime/*.md`, `docs/status/*.md`, `scripts/verify-*.ps1` | Stop before adding internal delivery logs or private paths |

Each shard should produce its own `Reviewer Index`, exact verification command
output, and known gaps. The orchestrator should merge only after checking
`git diff --name-status`, public-surface safety, and `verify-release.ps1`.

## Readiness Gate For OpenCode As A Worker

OpenCode can move from experimental to supported low-cost worker only when
there is current evidence for all of the following:

- `opencode --version` succeeds and the version is recorded.
- `opencode run --dangerously-skip-permissions --format json` can write the
  marker file in a temporary git repository.
- JSONL output has stable enough fields to extract events, errors, tool calls,
  token/cost candidates, and session ids.
- `opencode serve` can start on loopback, accept a session, accept
  `prompt_async`, expose SSE events, and shut down under the explicit
  clean-nonzero policy.
- Permission or question blockers are detected and reported as `partial`, not
  mislabeled as pass.
- No probe output stores secrets, browser profile state, generated private
  runtime state, or real project JSONL inside the public repo.

If `run` passes but `serve` becomes partial again, keep OpenCode as an
experimental run worker and do not base `/go` concurrency on serve mode.

## Do Not

- Do not collapse the final goal back into "OpenCode worker integration."
- Do not add Codex or Claude built-in worker options back without an explicit
  product decision; the current public default is OpenCode only.
- Do not claim serve mode is pass from exit code alone; require clean dispose,
  no stderr error signals, file landing, event evidence, and terminal step
  evidence.
- Do not claim OpenCode parallel execution is fully solved; this run exposed a
  transient `database is locked` failure that recovered through
  `devframe code execute` retry of only the failed shard.
- Do not commit temporary probe workspaces, JSONL samples from real local
  projects, browser profiles, runtime directories, or evidence archives.
- Do not run real OpenCode probes in the repository root; use disposable temp
  git repositories.
- Do not bypass TaskSpec / ExecutionReport / Evidence / Gate to make a worker
  "simpler."
- Do not make UI controls that execute local side effects before the human gate
  and safety model are explicit.

## Reviewer Index

Final product spine:

- `docs/agent-runtime/visual-control-plane.md`
- `schemas/visual_control_plane_state.schema.json`
- `packages/control-plane/control_plane/visual_state.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/cli.py`
- `packages/control-plane/control_plane/go_dispatch.py`
- `packages/control-plane/control_plane/worker.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_rdgoal.py`

In-flight OpenCode readiness:

- `packages/ai-workflow-hub/src/ai_workflow_hub/cli.py`
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_slice0.py`
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_serve_slice1.py`
- `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_client.py`
- `packages/ai-workflow-hub/tests/test_opencode_slice0.py`
- `packages/ai-workflow-hub/tests/test_opencode_serve_slice1.py`
- `schemas/agent-runtime/opencode-readiness-report.schema.json`
- `pytest.ini`

Key review questions:

- Does the document preserve the real final target: local web Agent sessions?
- Are OpenCode probes treated as execution-backend evidence, not product
  architecture?
- Are partial states explicit enough to prevent fake-green promotion?
- Are default tests hermetic and cost-free?
- Are real probe artifacts outside the public repository?

Generated/local artifacts:

- `chatgpt-summary.json` is intentionally ignored and should stay out of the
  product slice.
- Real probe artifacts were written only under disposable temp directories and
  should not be copied into this repository.
- Wheel smoke outputs are generated under temp/build directories and cleaned by
  the verification script.

Known gaps:

- Imported web AI session summaries are still read-only local projections, not
  live browser conversations.
- `devframe web-ai probe` builds importable CodexPro/DevSpace probe shapes; it
  does not prove a live MCP/browser bridge yet.
- OpenCode parallel execution recovered from one transient `database is locked`
  case, so serve/run readiness is evidence for experimental support, not proof
  of all concurrency edge cases.
