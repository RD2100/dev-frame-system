# Evidence: Web AI ↔ MCP live round-trip (M5, Tier A/local verified)

> Durable verification artifact per `rules/recon.md` recon-009 and the
> "no fake green" rule. Pairs with the roadmap (M5) and
> `docs/agent-runtime/agent-protocol-landscape.md`. Date: 2026-06-28.
> No secrets are recorded here (the CodexPro auth token stays in the user's
> `~/.codexpro` profile and was never printed or committed).

## What was verified (real, not projected)

DevFrame's own MCP client (`control_plane/mcp_live_probe.py`, exposed as
`devframe web-ai live-check`) completed a full Streamable-HTTP JSON-RPC
round-trip against a **live, running** CodexPro local MCP server:

- transport: `initialize` → `tools/list` → `tools/call`
- endpoint (local, same machine): `http://127.0.0.1:8787/mcp`
- auth: bearer token from the CodexPro workspace profile (`--token`, value not
  recorded)
- tool called: `server_config`
- result: `status: live_ok`, `health: ready`, `tool_called: server_config`,
  message "MCP live check succeeded."
- imported session (real evidence, outside repo):
  `.devframe-runtime/web-ai-sessions/codexpro-live-af9dde32-...json`

This is the concrete realization of the core promise — a web-AI-facing MCP
surface acting as a local agent entrypoint — verified end-to-end on the MCP
transport, not mocked (the test suite's `FakeMcpServer` was NOT involved).

## Environment facts

- `codexpro` CLI installed at `<local-tool-path>\codexpro.cmd` (package root
  `<local-tool-path>\node_modules\codexpro`); `codexpro doctor` healthy.
- `codexpro start` mode: agent, tools=standard, write=workspace, bash=safe,
  tunnel=cloudflare; local URL `http://127.0.0.1:8787/mcp`.
- `cloudflared` at `<user-home>\.codexpro\bin\cloudflared.exe`.
- The live ChatGPT tab is reachable via Chrome CDP at `http://<cdp-host>:<cdp-port>`
  and was bound earlier as a summary-only external-brain session
  (no transcript/cookie/profile captured).

## Tier B (ChatGPT Web ↔ MCP over a STABLE tunnel) — VERIFIED end-to-end

Date: 2026-06-28. The full web-AI round-trip is now confirmed from the ChatGPT
side, over a **permanent** Cloudflare named tunnel (no more rotating URL):

- stable hostname: `https://mcp.rd2100.uk/mcp` (Cloudflare named tunnel
  `codexpro-local`, tunnel ID d7be79c0-…, DNS routed via `cloudflared tunnel
  route dns`). Auth is via the URL query token `?codexpro_token=…`, so the
  ChatGPT connector uses **Authentication: None**.
- ChatGPT created the connector and ran `codexpro_self_test`: **9 checks passed,
  3 warnings, 0 failures**. ChatGPT really: read git status (58 changed
  entries), wrote the probe file `.ai-bridge/codexpro-self-test.md` into the
  workspace, registered 15 CodexPro tools, and confirmed safe-bash policy.
- the 3 warnings are benign/expected: standard tool mode (not elevated); the
  write/edit probe left the path clean (no stray change); safe-bash blocks env
  var expansion by design.

This realizes the core promise end-to-end: a web AI (ChatGPT) acting as a local
agent entrypoint into the DevFrame workspace via MCP, governed and read/write
scoped by CodexPro, over a stable URL.

### Root cause of the earlier `Connection failed`
Two compounding issues, both resolved:
1. Cloudflare **quick** tunnels rotate the public URL on every `codexpro start`,
   so the old ChatGPT connector URL went stale → fixed by switching to a
   **named** tunnel on `mcp.rd2100.uk` (permanent URL).
2. The `codexpro stable` process exited when launched without a real interactive
   console (its keypress prompt read EOF) → the tunnel dropped and ChatGPT hit
   Cloudflare error 1033/530 during connector creation → fixed by launching it
   in a real console window so it persists.

### Operational notes
- Persist the tunnel by running `codexpro stable --hostname mcp.rd2100.uk
  --tunnel-name codexpro-local --token <token>` in a real terminal (token kept
  in `~/.codexpro/mcp-token.txt`, never committed). The full connector URL is in
  `~/.codexpro/mcp-server-url.txt`.
- DevFrame's `live-check` validates the LOCAL endpoint with a bearer token
  (`live_ok`); it cannot probe the query-token public URL because `_safe_endpoint`
  rejects query strings — a known DevFrame limitation, not a CodexPro fault.
- Optional attended evidence capture once connected:
  `devframe web-ai record-mcp-result --conversation <chatgpt-url> --tool-name codexpro_self_test --status web_host_completed --provider chatgpt --project dev-frame-system --result "<summary>"`.
