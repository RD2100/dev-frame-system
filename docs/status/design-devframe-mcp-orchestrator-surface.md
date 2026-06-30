# Design: DevFrame MCP as an open, governed orchestrator remote-control

> Refines the DevFrame MCP server from a thin "edit-a-file" tool into the open,
> any-AI doorway that drives the EXISTING orchestrator (workflow engine + ACP +
> `/go` + team runtime), under a human-gated, attributable, fail-safe security
> model. Extends `docs/status/recon-receipt-devframe-mcp-server.md`. Pairs with
> the roadmap (M1/M2/M3 engine + M5/M8.2) and `rules/recon.md` (recon-001/005/008).

## Principle (the design rule that prevents re-building CodexPro)
The MCP door must expose the **orchestrator**, not the **executor**. An external
brain (any AI) connects to READ the governed state and PROPOSE/QUEUE governed
work; DevFrame's existing orchestrator drives the executors (Codex/OpenCode via
ACP). The door is a remote control for the coordinator, not a second file-editor.

Direction of control:
```
Any AI (MCP client)  --proposes/reads-->  DevFrame orchestrator (governed)
                                              --drives via ACP-->  Codex/OpenCode
                                              --writes via human gate-->  workspace
```

## A. Tool surface (mapped to EXISTING capabilities, not new execution)

Read tools (no side effects, scope-limited, redacted):
- `read_project_shell` (exists) — projects/threads snapshot.
- `list_runs` / `get_run_status` — `/go` runs + status, from the visual state
  `go_runs` / runtime journal.
- `get_team` — Agent Registry / Task Board / Message Bus / Event Log / Evidence
  / Review Gates / Conflict Control, from the M1 team runtime read model.
- `list_pending_gates` — human-decision gates awaiting action.
- `list_pending_writebacks` (exists) — staged file proposals.

Governed action tools (each produces a HUMAN-GATED queued item; none takes
effect by itself):
- `dispatch_task(projectId, goal, options)` — **propose** a governed `/go`
  coding run. Reuses `go_dispatch` in PREPARE-only mode → a queued run that
  surfaces as a `next_action`; a human approves execution via the existing
  `/actions/execute` (confirm=execute) gate. **Token-spending execution is never
  triggered by the AI alone.**
- `propose_writeback(...)` (exists) — propose a single-file edit; human approves
  via `/api/t3/approval-response`.
- `post_team_message(runId, summary)` — let a brain leave a coordination note in
  the Message Bus (read-model only; no execution).

Explicitly NOT offered as tools (stay human-only):
- approving/rejecting gates, applying writebacks, starting token-spending runs,
  reading sensitive files, changing auth/scope, exposing the endpoint publicly.

## B. Wiring to existing components (compose, don't duplicate)
- reads -> `build_visual_control_plane_state` + team runtime read model.
- `dispatch_task` -> `go_dispatch.run_go_dispatch(execute=False)` (prepare) ->
  queued go-run -> `next_action` -> existing `/actions/execute` confirm gate ->
  existing executor (OpenCode / `--driver acp`). Audit via existing action-runs.
- approvals -> existing `/api/t3/approval-response` (human).
- every MCP call -> recorded as a team event (who/when/tool/args-summary).

## C. Security model (fail-safe by default)

### C1. Identity & authentication
- **Per-AI tokens**, not one shared secret: each connected brain/AI gets its own
  token -> independent revocation + attribution. A revocation list is checked on
  every call.
- **Token transport**: prefer a non-`Authorization` custom header
  (`X-DevFrame-MCP-Token`) so tunnels/proxies that consume `Authorization` don't
  strip it; for public exposure, front with Cloudflare Access (real IdP) rather
  than a bare token. URL-embedded tokens are a last resort only and must be
  short-lived + rotated (they leak via logs/history/screenshots).
- **Rotation + expiry**: tokens carry an expiry; rotation is one command;
  revocation is immediate.

### C2. Authorization / scoping (least privilege)
- **Per-token scope**: `read` < `propose` < `dispatch`. New tokens default to
  `read` only. `dispatch` (token-spending) is opt-in per token.
- **Per-token project allowlist**: a token only sees/touches whitelisted
  projects.
- **Read scoping & redaction**: reads reuse the write-back sensitive-path rules
  (`.git`, `.env*`, key stores, runtime/state, `node_modules` never exposed);
  file contents are not dumped wholesale — summaries/targeted reads only;
  redaction of obvious secrets before content leaves the machine.

### C3. The human gate (unchanged, non-negotiable boundary)
- Writes, token-spending dispatch, and gate approvals ALWAYS require a human
  confirm through the existing endpoints. **There is no auto-approve tool and
  there never will be one.** The AI proposes; a human sees the proposal/diff and
  decides.

### C4. Attribution & audit (multi-AI accountability)
- Every MCP call is recorded: token id (which AI), timestamp, tool, argument
  summary, result, into the team Event Log. "Who proposed this" is always
  answerable. Audit records live outside the repo.

### C5. Prompt-injection & exfiltration defenses
- Reads are scoped + redacted (C2), so an injected "exfiltrate secrets" can't
  reach what isn't exposed.
- The human sees every proposal/diff before approval, so an injected
  "delete everything" proposal is visible and rejectable.
- **Per-token rate limits** (calls/min, pending-proposal cap) stop proposal spam
  / DoS / approval-fatigue attacks.

### C6. Network exposure (off by default)
- **Loopback-only by default.** No token configured = loopback-only.
- Public exposure (tunnel) is an explicit, per-session opt-in with a clear
  "you are exposing your machine" warning, and REQUIRES a token (and ideally
  Cloudflare Access in front).
- Bind 127.0.0.1; never 0.0.0.0 without `--allow-remote` + token.

### C7. Conflict control (multi-AI)
- When multiple AIs propose changes to the same file/area, the existing
  conflict-control / file-ownership model flags the overlap; proposals queue and
  a human resolves. No silent last-writer-wins.

### C8. Fail-safe defaults summary
read-only · loopback-only · no-token-no-access · sensitive paths hidden ·
nothing executes/writes without a human confirm · everything audited.

## D. Phased rollout (prove value before opening widely)
- **Phase 1 (compose existing, loopback, single token):** read tools +
  `dispatch_task` as a human-gated proposal + audit. Self-tested with
  `mcp_live_probe`. No public exposure. This makes the door drive the
  orchestrator we already have.
- **Phase 2 (security hardening for exposure):** per-AI tokens + scopes +
  revocation + custom-header/Access auth + rate limits + read redaction.
- **Phase 3 (open to multiple AIs / public):** conflict control + attribution at
  multi-AI scale; Cloudflare Access; per-token project allowlists enforced.

## E. Evidence required per phase
- Phase 1: `pytest` green incl. new orchestrator-tool tests; a live
  `mcp_live_probe` round-trip; `dispatch_task` produces a queued (not executed)
  run that still needs a human confirm; `verify-public-snapshot.ps1` exit 0;
  independent review confirming no tool executes/writes without a human gate.
- Phase 2/3: token-scope tests (read token cannot dispatch), revocation test,
  rate-limit test, redaction test, multi-token attribution test.

## F. Review gate
Reviewer must confirm: (1) no MCP tool writes, spends tokens, or clears a gate
without a human confirm; (2) least-privilege scopes enforced; (3) reads are
scope-limited + redacted; (4) every call is attributable + audited; (5)
loopback-only unless explicitly exposed with a token; (6) no T3 source vendored.
