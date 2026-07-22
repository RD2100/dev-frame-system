# Recon Receipt: pluggable model provider

> Governs write-capable work for the `pluggable-model-provider` spec, per
> `rules/recon.md` recon-001/005 and `rules/open-source-reuse.md` reuse-002/003.
> Public spec summary: this receipt. Local draft source, if present, is kept
> under the ignored `.kiro/specs/pluggable-model-provider/` workspace area and is
> not part of the public distribution snapshot.

## Target
- user_goal: Let the user pick the model source behind OpenCode (paid API, local
  model, or web-AI shim) per task, with one unified session and informed labels.
- current_slice_goal: Provider registry + informed selection + `--model-provider`
  wiring into the unified DevFrameSession; web-shim live backend deferred.
- requested_outcome: Light tasks can use free providers, heavy tasks use reliable
  ones; default path unchanged; all gates green; no tokens spent in verification.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner unified on the design and authorized automated execution
  plus an independent sub-agent acceptance review.

## Reuse boundary
- OpenCode stays the executor ("hand"); it is replaceable (reuse-002). The model
  source is the only thing this feature makes pluggable.
- DevFrameSession stays provider-neutral; providers differ only by id + labels.
- Local model (Ollama) and paid API are real, ready backends. The web-shim
  backend (driving a web AI session as an OpenAI-compatible endpoint) is a
  **profile only**; its live browser automation is deferred behind a future
  receipt because of ToS risk and the inability to verify it without a real
  logged-in session and spent tokens.

## Capability matrix
- model provider selection
  - current production level: L1 (single hard-coded OpenCode-API path).
  - target level: L2 (registry + selector + unified-session projection).
  - gap: no provider abstraction exists; model source is fixed in
    `_opencode_command`.

## Integration risk table
- risk: changing dispatch wiring regresses the default OpenCode-API path.
  - type: correctness | severity: medium
  - mitigation: default provider keeps byte-identical worker command; full
    pytest + wheel smoke are the gate.
- risk: web-shim profile is mistaken for a working live backend.
  - type: safety/ux | severity: high
  - mitigation: profile carries `live_backend=deferred`, `tos_risk=elevated`;
    no live browser automation is added; degradation notes surfaced; no fake
    green.
- risk: schema `additionalProperties:false` rejects new fields.
  - type: correctness | severity: medium
  - mitigation: add optional `model_provider` to `go_run`/`go_agent`; omit when
    empty (same pattern as `methodology`).
- risk: ToS violation by automating a web AI as a model backend.
  - type: license/compliance | severity: high
  - mitigation: live backend deferred; the only sanctioned web-AI path remains
    MCP/connector (separate work); this feature ships labels and plumbing, not
    automation.

## Build-vs-buy decision
- must_reuse: OpenCode as executor; stdlib only; no new dependency.
- should_adapt: a provider registry + selector that shapes the worker command
  and records the provider on the unified session.
- must_build_new: the `ModelProvider` registry and its CLI/projection wiring.
- deferred: live web-shim browser backend; local-model end-to-end execution
  (real Ollama run) is verifiable by the user but not spent in automation.
- rationale: the value is user-chosen, labeled model sourcing on one session;
  the risky/ToS-bound part (web automation) is explicitly held back.

## Evidence required for completion
- hermetic `tests/test_model_providers.py` and `tests/test_go_model_provider.py`
  pass; full `python -m pytest -q` stays green; `verify-public-snapshot.ps1` and
  `verify-control-plane-wheel.ps1` stay green; independent sub-agent review
  records a verdict.

## Deferred (requires updated receipt)
- Live web-shim backend (browser/CDP driving a web AI session as an
  OpenAI-compatible endpoint), including ToS assessment and real verification.
- Web-AI-as-MCP-client coordinator path (architecture B), tracked separately.

## Security amendment: external-secret execution boundary

- receipt_id: `recon-opencode-external-secret-boundary-2026-07-22`
- date: 2026-07-22
- approval: The user authorized the P0 containment and fail-closed provider
  remediation after independent metadata-only verification and security review.
- scope: AI Workflow Hub OpenCode process launch, readiness, evidence, and
  acceptance paths. Control-plane dispatch is a later slice because its current
  `go_dispatch.py` ownership conflicts with unrelated work.

### Resource map

- process client: `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_client.py`
- readiness probe: `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_readiness.py`
- one-shot execution: `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_slice0.py`
- serve execution: `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_serve_slice1.py`
- acceptance gate: `packages/ai-workflow-hub/src/ai_workflow_hub/acceptance.py`
- configuration loader: `packages/ai-workflow-hub/src/ai_workflow_hub/config_loader.py`
- existing environment contract: `OPENCODE_API_KEY`, optional
  `OPENCODE_API_BASE`, `OPENCODE_BIN`, and `OPENCODE_MODEL_OVERRIDE`
- state/evidence sinks: process results, readiness errors, execution reports,
  and persisted stdout/stderr produced by the paths above
- local configuration boundary: root `opencode.config.json` is local-only and
  was removed from tracking by the accepted containment slice; its contents are
  not an implementation or test input

### Capability matrix and reuse decision

- external secret injection
  - existing capability: environment propagation through the current config
    loader and process launcher
  - decision: reuse; do not add a credential store, JSON secret parser, or new
    configuration format
- paid OpenCode execution
  - existing gap: some paths can reach process or artifact creation without a
    verified required secret
  - decision: add one shared, minimal fail-closed check within the existing
    AI-hub boundary before process or artifact creation
- local/no-key execution
  - existing capability: provider contracts may explicitly identify a local
    backend
  - decision: preserve only when the current contract can distinguish it
    without guessing; otherwise fail closed and return for a narrower contract
- output handling
  - existing gap: stdout, stderr, exceptions, timeouts, and persisted reports
    can carry inherited process text
  - decision: reuse current result/evidence objects and sanitize at their
    existing capture boundaries; do not introduce a second evidence store

### Integration risks

- secret disclosure (P0): process output or exception text may contain an
  injected value. Mitigation: sentinel-based negative tests across every
  capture/persistence path; errors name environment variables only.
- spawn-before-validation (P0): a paid path may start work before validating
  configuration. Mitigation: prove subprocess and artifact writers are not
  called when the external secret is missing.
- local-provider regression (P1): a blanket key requirement could disable a
  legitimate local backend. Mitigation: preserve only an existing explicit
  local/no-key contract; do not infer one from labels or command presence.
- scope collision (P1): control-plane dispatch currently overlaps unrelated
  dirty work. Mitigation: keep this amendment's first write slice inside the
  AI Workflow Hub exact paths below.

### Recommended next slice

- exact write set:
  - `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_client.py`
  - `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_readiness.py`
  - `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_slice0.py`
  - `packages/ai-workflow-hub/src/ai_workflow_hub/opencode_serve_slice1.py`
  - `packages/ai-workflow-hub/src/ai_workflow_hub/acceptance.py`
  - `packages/ai-workflow-hub/tests/test_opencode_security.py`
- required evidence: synthetic REDs for missing-secret pre-spawn failure and
  sentinel removal from all returned/persisted error paths; focused existing
  slice0/serve regressions; no live provider call or real credential read
- review gate: independent security reviewer verifies P0/P1, exact scope,
  fail-closed ordering, local-provider compatibility, and absence of sentinel
  text in results and artifacts
- out of scope: credential rotation/revocation, history rewriting, provider
  live calls, control-plane dispatch, global configuration, and deployment
