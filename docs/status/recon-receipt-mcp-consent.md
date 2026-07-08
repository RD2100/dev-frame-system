# Recon Receipt: MCP connect-time consent + connection governance (Phase 0)

> Governs write-capable work on the DevFrame MCP server's authorization layer (a
> mature capability domain: MCP bridge / access control) per `rules/recon.md`
> recon-001/005/009. Implements Phase 0 of
> `docs/status/design-orchestration-mcp.md`. Owner decisions recorded there §7.

## Target
- user_goal: Any AI that can call MCP may connect, but it gets access ONLY after
  the human explicitly Allows it in a local prompt; once allowed it can read most
  (non-core-sensitive) info; the owner can review/revoke connections; everything
  is audited.
- current_slice_goal: Phase 0 = the safe door (consent gate + connection
  registry + audit + reachability token), no new orchestration tools yet.
- date: 2026-06-28 | planner_agent_id: kiro

## Resource Map (verified)
- `control_plane/mcp_server.py` — `handle_mcp_jsonrpc` (initialize / tools/list /
  tools/call), `resolve_mcp_token`, tool handlers. Today every authenticated
  caller is fully trusted — no per-connection consent.
- `control_plane/dashboard.py` — `POST /mcp` (loopback + optional token), other
  gated POST endpoints (`/api/t3/approval-response`, `/api/t3/writeback-propose`)
  with loopback + loopback-origin guards; `_read_body`, `_send_text`.
- MCP fact: the server issues `MCP-Session-Id` on `initialize` and the client
  echoes it on later requests (works even for `auth=None` clients) → a per-
  connection handle exists without a pre-shared per-AI secret.
- Runtime state dir (outside repo) holds tokens/proposals; consent grants + audit
  will live there too.

## Design (Phase 0)
- **Connection registry** (`control_plane/mcp_consent.py`): a connection is keyed
  by `MCP-Session-Id`; on `initialize` it is recorded `pending` with the client's
  self-reported `clientInfo.name` + a fingerprint. Statuses: pending / authorized
  / denied / revoked. A durable **"allow always" grant** keyed by fingerprint
  lets a returning client auto-authorize without re-prompting. Stored under the
  runtime dir; decisions + tool calls appended to a durable audit jsonl.
- **Gating in `mcp_server`**: `initialize` and `tools/list` are open (discovery is
  harmless); **`tools/call` requires an authorized connection**. A call from a
  pending connection records/refreshes a pending authorization request and
  returns `authorization_pending` (the AI should retry). Denied/revoked → blocked.
- **Human decision surface** (the "popup"): a pending/active connection list +
  Allow-once / Allow-always / Deny / Revoke. Phase 0 exposes this as (a) a
  loopback dashboard list + decision endpoint and (b) a `devframe mcp
  connections` CLI. A native desktop toast/dialog is a thin presentation layer on
  top (follow-on) — the decision data + endpoint are the testable core.
- **Default scope** when authorized: read most info; **core sensitive excluded**
  (secrets/`.env*`/credentials/profiles) regardless of consent.
- **Reachability token** (existing `resolve_mcp_token`): kept as the thin "can you
  knock" layer for public exposure; consent is the "are you allowed in" layer;
  per-action human gate stays the "can you change things" layer.

## Risks / mitigations
- popup-spam/DoS on a public endpoint → reachability token + per-connection +
  global pending-request rate cap.
- consent persistence vs session rotation → "allow always" durable grant by
  fingerprint; "allow once" is session-scoped.
- client "pending→retry" behavior varies by AI → documented interop caveat;
  fallback is human-authorize-first then the AI calls. Verify per real client.
- spoofed clientInfo (an AI can claim any name) → the human sees the name + origin
  and decides; consent is not identity proof, it is human authorization. Audit
  records what was claimed.
- no T3 source vendored; consent state stays outside the public repo.

## Recommended slice / evidence
- files_in_scope: `mcp_consent.py` (+tests), `mcp_server.py` (gating+audit),
  `dashboard.py` (pass session id + list/decide endpoints), a `mcp` CLI command;
  manifest/launcher note for the new endpoints.
- evidence: `pytest` green incl. consent tests (pending blocks tools/call; allow
  unblocks; deny/revoke blocks; allow-always persists; audit recorded);
  `verify-public-snapshot.ps1` exit 0; independent review.
- review_gate: reviewer confirms (1) `tools/call` is impossible without human
  Allow, (2) revoke takes effect immediately, (3) core-sensitive never returned,
  (4) every call + decision audited, (5) loopback/token posture intact, (6) no T3
  source vendored.
