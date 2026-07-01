# Agent Cluster Unknowns & Decisions Register

A standing list of load-bearing assumptions and open architecture decisions for
the local agent cluster, so blind spots surface as tracked items instead of
silent assumptions. Pairs with `docs/agent-runtime/agent-protocol-landscape.md`
(facts) and `docs/status/local-agent-cluster-roadmap.md` (modules).

Status values: `open` (needs decision), `needs-verify` (fact to re-check),
`resolved` (decided, with link).

Last updated: 2026-06-26.

## Open decisions

| ID | Module | Decision needed | Options | Status |
|---|---|---|---|---|
| D1 | M2 | Build vs reuse the ACP client | Reuse a headless ACP client (`acp-cli`/`acpx`) or T3Code `effect-acp`, vs write our own | open |
| D2 | M1 | Coordination substrate for owned local agents | Adopt A2A vs a simpler internal message queue (at-least-once + DLQ) | open |
| D3 | M3 | Orchestration engine | Consolidate on LangGraph (already in ai-workflow-hub) vs keep two orchestrators | open (lean: consolidate on LangGraph) |
| D4 | M5 | Local-MCP exposure for web connectors | OpenAI Secure MCP Tunnel / Anthropic MCP tunnels (official, off-public-net) vs ngrok/cloudflared | open (lean: official tunnels) |
| D5 | M2 | OpenCode integration depth | Keep CLI-subprocess (L2 today) vs move to ACP session (live stream/permission) | open |

## Load-bearing assumptions to keep verified

| ID | Assumption | Why it matters | Status |
|---|---|---|---|
| A1 | Codex/OpenCode/Claude Code remain ACP-reachable via maintained bridges | M2 backbone depends on it | needs-verify |
| A2 | Official MCP tunnels keep the server off the public internet | Security boundary for M5 | needs-verify |
| A3 | ChatGPT/Claude web MCP plan gating (Business/Ent full; Plus/Pro read-only; Claude Pro/Max) is current | Tier B feasibility | needs-verify |
| A4 | Gemini CLI naming/identity (reported renamed Antigravity CLI) | Provider profile naming | needs-verify |
| A5 | Chinese consumer web (Doubao/DeepSeek) still expose no web MCP client | Forces Tier A (API/local) for them | needs-verify |

## Resolved

| ID | Decision | Resolution | Link |
|---|---|---|---|
| R1 | Coding agents are driven via ACP, not "called as MCP tools" | Confirmed; ACP = editor->agent, MCP = model->tools | agent-protocol-landscape.md |
| R2 | DeepSeek/Doubao integration path | Via API function-calling / local model, not web shim | agent-protocol-landscape.md |

## Process note

When any `needs-verify` item is relied upon for a write-capable decision, run a
live check and update the date here. New blind spots discovered during work are
added as rows, not fixed silently — an unverified load-bearing assumption is a
defect, like fake-green.
