# Recon Receipt: DevFrame MCP server (governed AI operation surface)

> Governs write-capable work on a new mature capability domain — an MCP **server**
> exposing DevFrame operations to AI clients — per `rules/recon.md`
> recon-001/002/003/005/009 and `rules/open-source-reuse.md`. Pairs with the
> roadmap (M5/M8.2) and `docs/status/recon-receipt-rdcode-writeback.md`.

## Target
- user_goal: Expose an MCP so an AI can directly operate the editor/workspace —
  read the project and propose changes — through DevFrame's governed,
  human-gated write-back, without breaking the "no silent write" guarantee.
- target: `packages/control-plane/control_plane/` (public repo). Reuses the
  existing loopback dashboard HTTP server and the M8.2 write-back proposal store.
- current_slice_goal: a minimal DevFrame MCP server (Streamable HTTP JSON-RPC)
  on the loopback dashboard at `POST /mcp`, advertising read tools + a
  governed `propose_writeback` tool. Self-verifiable with DevFrame's own
  `mcp_live_probe` client.
- date: 2026-06-28 | planner_agent_id: kiro | authorization: human asked for an
  MCP that lets AI operate the editor directly; human gate on writes retained.

## Verified facts / Resource Map
- DevFrame is today an MCP **client** only: `control_plane/mcp_live_probe.py`
  speaks Streamable HTTP JSON-RPC (`initialize` → `tools/list` → `tools/call`),
  accepts JSON or SSE responses, reads the `MCP-Session-Id` header, treats
  `-32001..-32003` as auth errors and `-32700/-32600` as protocol errors. There
  is no DevFrame MCP **server** — this slice adds one.
- The loopback HTTP server (`dashboard.py` `do_POST`, loopback + origin guards,
  `_read_body`) is the natural host for a new `POST /mcp`.
- The governed write-back already exists: `writeback.py`
  `stage_writeback_proposal` / `resolve_writeback_proposal` (M8.2), and
  `dashboard._resolve_writeback_workspace_root` (server-side workspace root from
  an explicit project id; client paths never trusted).
- `tests/test_mcp_live_probe.py` `FakeMcpServer` is a reference for the exact
  wire protocol the probe expects (initialize/tools/list/tools/call shapes).

## Capability Matrix / Reuse decision
- MCP transport/protocol: BUILD NEW minimal stdlib server (no MCP SDK dep) that
  satisfies the protocol our own `mcp_live_probe` already speaks — keeps parity
  and zero new dependencies, matching the repo's stdlib-only style.
- read model: REUSE `build_t3_client_shell` / visual state.
- write path: REUSE the M8.2 governed proposal store. The MCP `propose_writeback`
  tool only STAGES a proposal (no write); approval stays human via
  `/api/t3/approval-response`. **The MCP server never writes to the workspace.**
- auth/confinement: REUSE loopback guard; the server binds loopback only.

## Build-vs-Buy
- must_reuse: dashboard HTTP host + loopback guards; write-back proposal store;
  read model; `mcp_live_probe` as the self-test client.
- must_build_new: a JSON-RPC dispatcher (`initialize`, `tools/list`,
  `tools/call`, `notifications/initialized`) + tool handlers
  (`server_config` read-only health, `read_project_shell`, `propose_writeback`,
  `list_pending_writebacks`).
- must_NOT_build: an MCP tool that writes or auto-approves. Approval is human.

## Integration Risk Table
- risk: an MCP write tool could bypass the human gate. type: security. severity:
  high. mitigation: the server exposes PROPOSE only; writes happen solely via the
  existing human approval endpoint; the proposal store re-runs full path safety.
- risk: exposing the MCP server beyond loopback. type: security. severity: high.
  mitigation: loopback-only guard reused from the dashboard; binding stays
  127.0.0.1. Public exposure (e.g. via a tunnel) would be a separate, explicit,
  human-gated decision.
- risk: protocol drift from real MCP clients (ChatGPT/Claude/Codex). type:
  coupling. severity: medium. mitigation: target the same protocol our probe
  speaks; respond in plain JSON; keep `initialize` capabilities minimal; add SSE
  later only if a real client requires it.
- risk: public-repo/fork boundary. type: license. severity: low. mitigation:
  server lives in the public repo (DevFrame governance); no T3 source vendored.

## Recommended slice (this receipt unlocks)
- smallest_safe_increment: `control_plane/mcp_server.py` (JSON-RPC dispatch +
  tools) + wire `POST /mcp` into the loopback dashboard + tests, including a real
  `mcp_live_probe` round-trip against the running server and a `tools/call
  propose_writeback` test that stages (but does not write) a proposal.
- files_in_scope: `mcp_server.py`, `dashboard.py` (route), tests; this receipt.
- files_out_of_scope: any auto-approve/auto-write tool; public tunnel exposure;
  the RD-Code in-editor UI.
- evidence_required: `python -m pytest -q` green incl. new MCP server tests;
  a live `mcp_live_probe` round-trip returning `live_ok`;
  `scripts/verify-public-snapshot.ps1` exit 0; independent review.
- review_gate_definition: reviewer confirms (1) the MCP server never writes
  (propose-only; approval stays human), (2) loopback-only, (3) path safety is
  enforced on proposals, (4) no new dependency, (5) no T3 source vendored.


## Review outcome (independent review: PASS-WITH-NITS)
Core guarantees confirmed: the MCP server never writes (propose-only; applying
stays human via `/api/t3/approval-response`); loopback-client guard blocks remote
direct connections; path safety enforced; no new dependency; no T3 source
vendored. A real `mcp_live_probe` round-trip returns `live_ok`. Two NITs, both
accepted as documented tradeoffs rather than blockers:

- **Origin guard on `/mcp` (deliberately omitted).** Unlike the other write POST
  routes, `/mcp` checks only loopback-client, not Origin. A strict loopback-Origin
  guard would risk rejecting a legitimate tunneled MCP client (e.g. ChatGPT) that
  sends a non-loopback `Origin`, which would defeat the stated goal of letting a
  web AI operate via MCP. The actual write-protection boundary is the human
  approval gate: a CSRF-style local browser request could at most stage a
  *proposal* (never apply it), and the cross-origin response is unreadable. Net
  risk is low. Follow-up: add Origin validation once a real tunneled client's
  Origin behavior is confirmed, so it can be tightened without breaking interop.
- **No SSE yet.** Responses are plain JSON (which our own probe and many clients
  accept). A real client that requires `text/event-stream` (possibly ChatGPT)
  would need an SSE response mode; add it only when a concrete client requires
  it, and verify against that client before relying on the tunnel path.
