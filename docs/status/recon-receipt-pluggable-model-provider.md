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
