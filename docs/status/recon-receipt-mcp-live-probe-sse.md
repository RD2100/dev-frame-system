# Recon Receipt: MCP live-probe SSE / header-casing fix (M5)

> Governs a write-capable bug fix in the MCP bridge domain (`mcp_live_probe`),
> a mature capability area per `rules/recon.md` recon-001/005/009. Scoped, local,
> test-backed. Pairs with the roadmap M5 (web AI as cluster participant).

## Target
- user_goal: Make `devframe web-ai live-check` actually validate a real modern
  MCP server (CodexPro, the user's configured ChatGPT connector backend) so the
  Web-AI ↔ DevFrame round-trip can be proven with real evidence.
- target: `packages/control-plane/control_plane/mcp_live_probe.py`.
- current_slice_goal: fix the response parser so it handles the MCP Streamable
  HTTP transport (SSE `text/event-stream` responses) regardless of header casing.
- date: 2026-06-27 | planner_agent_id: kiro

## Verified facts (real, against a live server)
- Started CodexPro 0.28.5 locally (`codexpro start --tunnel none --no-auth
  --bash off`), MCP at `http://127.0.0.1:8787/mcp`. Real server, not a test fake.
- CodexPro responds to `initialize` with HTTP 200, `Content-Type:
  text/event-stream`, body `event: message\ndata: {"result":{...}}` (verified
  raw; valid for protocolVersion 2024-11-05 and 2025-06-18).
- `mcp_live_probe._post_json` returned `{"_raw": ...}` with no `result`, so the
  probe reported `unavailable: "initialize did not return a valid JSON-RPC
  result."` — a FALSE NEGATIVE; the server is healthy.
- Root cause: `_post_json` did `resp_headers.get("Content-Type", "")`, a
  case-sensitive lookup. `http.client.getheaders()` preserves the server's
  header casing (Node sent a differently-cased key), so the lookup returned the
  default `""`, the `text/event-stream` branch never ran, and the SSE-framed body
  was handed to `json.loads` as-is and failed. A case-insensitive `_header_value`
  helper already exists in the module but was not used here.

## Capability Matrix / decision
- capability: MCP client live-check (DevFrame is the MCP *client*).
  - reusable_as_is: NO (the SSE/header bug makes it fail on real Streamable-HTTP
    servers). must_fix in place. No new dependency; stdlib only.
- reuse: keep the existing stdlib transport; reuse the module's own
  `_header_value` for case-insensitive lookup; parse SSE per the spec (collect
  `data:` lines, take the first event that parses as JSON-RPC).
- must_NOT: add a heavy MCP SDK dependency for a one-line transport fix; fake a
  `live_ok` without a real parsed result.

## Integration Risk Table
- risk: SSE parsing edge cases (multi-line data, multiple events). type:
  correctness. severity: low. mitigation: collect consecutive `data:` lines,
  join with `\n`, pick first JSON-parseable event; add a regression test using a
  fake SSE server.
- risk: streaming servers that hold the connection open. type: performance.
  severity: low. mitigation: existing per-request timeout already bounds reads;
  out of scope for this slice (record as follow-up if observed).

## Recommended slice (this receipt unlocks)
- Fix `_post_json`: case-insensitive Content-Type via `_header_value`; robust
  SSE `data:` extraction. Add a regression test (fake `text/event-stream` server
  with mixed-case header). Re-run the live `live-check` against CodexPro and
  expect `status: live_ok` with `server_config` advertised.
- files_in_scope: `control_plane/mcp_live_probe.py`, `tests/test_mcp_live_probe.py`.
- files_out_of_scope: any public-tunnel exposure (separate, human-gated step);
  CodexPro itself (third-party).
- evidence_required: new test passes; full `pytest` green; live `live-check`
  returns `live_ok` against the real local CodexPro MCP server.
- review_gate: reviewer confirms no fake green (the `live_ok` comes from a real
  parsed server result), stdlib-only, and the SSE/header handling is correct.
