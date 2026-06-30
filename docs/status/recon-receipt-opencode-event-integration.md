# Recon Receipt: OpenCode event integration (reuse-depth L1 -> L2)

> Governs write-capable work that raises the OpenCode worker integration from a
> subprocess black box (L1) to a structured-event adapter (L2), per
> `rules/recon.md` recon-001/005 and `docs/agent-runtime/reuse-depth-review-method.md`.

## Target
- user_goal: Make the OpenCode worker deliver real structured execution data
  (session id, token/cost, tool calls, changed files) instead of discarding it.
- target_repo_or_kb: dev-frame-system (control-plane package).
- current_slice_goal: Parse `opencode run` JSONL events and surface real
  per-agent session/token/cost/tool/changed-file data through the go-run record
  and `DevFrameSession`.
- requested_outcome: Eliminate the "hollow projection" where DevFrameSession
  cost/tokens/tool_calls fields are always empty; keep all tests green; no new
  runtime dependency; no spent worker tokens during automated verification.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner authorized the P0 reuse-depth plan and full automation.

## Resource Map
- production integration point: `control_plane/go_dispatch.py`
  (`_opencode_command` uses `--format default`; `_execute_parallel` ->
  `_run_one_agent` -> `CommandWorker`), `control_plane/worker.py`
  (`CommandWorker` stores stdout in `worker-output.txt`, status from
  `ExecutionReport.md`), `control_plane/dispatch_packet.py`
  (`ExecutionReportSummary`).
- read model: `control_plane/visual_state.py` (`_go_agent_state`,
  `_go_methodology_state`), `control_plane/cli/_coding.py` (`_public_sessions`),
  `schemas/visual_control_plane_state.schema.json` (`go_agent`).
- existing probe (reuse reference): `ai_workflow_hub/opencode_slice0.py`
  (`parse_jsonl`, `_collect_keys`) proved `opencode run --format json` emits
  JSONL with session/token/cost/tool candidate fields. The probe only detects
  field presence; it does not extract values.
- cross-package boundary: control-plane does not depend on ai-workflow-hub
  (worker.py calls it only via subprocess). The new parser must live in
  control-plane and be independently implemented, reusing the probe's robustness
  approach, not importing it.

## Capability Matrix
- opencode event parsing
  - current production level: L1 (stdout discarded as text; changed files parsed
    from the agent's hand-written ExecutionReport.md markdown).
  - highest proven level: L2 (slice0 probe parsed real JSONL with the candidate
    fields present).
  - gap: production never consumes the JSONL; it requests `--format default`.

## Reuse Candidate
- candidate: OpenCode `run --format json` JSONL output.
  - source: locally installed OpenCode (`opencode` on PATH); MIT.
  - exact_scope_to_reuse: the JSONL event stream and its session/token/cost/
    tool/file fields.
  - expected_adapter_work: a tolerant control-plane parser that extracts values
    (not just presence), plus wiring into the go-run record and DevFrameSession.
  - blocking_constraints: OpenCode event schema is unstable -> parser must be
    defensive; do not import the ai-workflow-hub probe across the package
    boundary.
  - decision: should_adapt.

## Integration Risk Table
- risk: changing `--format default` -> `--format json` breaks behavior.
  - type: correctness | severity: medium
  - mitigation: existing tests assert only `worker_command[:4]` and the
    `opencode run -m <model>` substring, not the format flag; full pytest is the
    regression gate.
- risk: schema `additionalProperties:false` rejects new go_agent fields.
  - type: correctness | severity: medium
  - mitigation: add the optional fields to `go_agent` in the schema and keep
    them omitted when empty (same pattern used for `methodology`).
- risk: real token/cost values can only be confirmed by spending OpenCode
  tokens.
  - type: verification | severity: medium
  - mitigation: hermetic fixture tests cover parsing and wiring; the real-value
    claim is verified by the user running OpenCode, recorded as a documented
    manual step. Per the reuse-depth method, a mock test must not masquerade as
    proof of the real-value claim.

## Build-vs-Buy Decision
- must_reuse: OpenCode JSONL event stream (no new dependency, subprocess kept).
- should_adapt: a defensive control-plane JSONL parser + go-run/DevFrameSession
  wiring.
- must_build_new: nothing beyond the parser and wiring; do not fork OpenCode,
  do not switch to serve/SSE in this slice.
- rationale: the value is real execution data, reachable by parsing output we
  already throw away. Serve/SSE (a further L3 step) is deferred.

## Recommended Slice (this receipt unlocks)
1. New `control_plane/opencode_events.py`: tolerant `parse_opencode_run_jsonl`
   returning a structured summary (session_id, model, tokens, cost, tool_calls,
   changed_files, error signals). Pure function, fixture-tested.
2. `_opencode_command`: `--format default` -> `--format json`.
3. `GoAgentDispatch`: add optional `session_id`, `tokens`, `cost`,
   `tool_calls` fields; populate them after the worker runs by parsing
   `worker-output.txt` when the worker is OpenCode.
4. `schemas/visual_control_plane_state.schema.json` `go_agent`: add the optional
   fields; `visual_state._go_agent_state` and `cli/_coding._public_sessions`
   surface them, omitting when empty.
- files_out_of_scope: serve/SSE integration, T3 client, MCP bridge, ai-workflow-hub.
- evidence_required_for_completion: new hermetic parser/wiring tests pass; full
  `python -m pytest -q` stays green; `verify-public-snapshot.ps1` and
  `verify-control-plane-wheel.ps1` stay green.
- manual real-value verification (documented, not run in automation):
  `devframe code "<goal>" --execute` against a throwaway repo, then
  `devframe code session <id> --format json` shows non-empty tokens/cost/tool
  data sourced from OpenCode JSONL.

## Deferred (requires updated receipt)
- OpenCode `serve` + SSE streaming (L3), live progress, session resume.
- Worktree isolation / write-set serialization (separate P0-2 receipt).
