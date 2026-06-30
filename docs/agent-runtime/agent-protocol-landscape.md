# Agent Protocol Landscape (living, cited)

Durable, source-cited record of the protocols that matter for "web AI as a
governed local agent cluster", so the same blind spot is not rediscovered each
time. **This is fast-moving; every claim carries a source and the verification
date. Re-verify before relying on it.**

Last verified: 2026-06-26.

## Three protocols, three different jobs

- **MCP (Model Context Protocol)** — connects a *model/host* to *tools and
  data* (MCP servers). Direction: AI -> tools. It gives a "brain" hands.
- **ACP (Agent Client Protocol)** — connects a *code editor/client* to a
  *coding agent*. Direction: client -> agent. Created by Zed, released
  2025-08; JSON-RPC 2.0 over stdin/stdout; described as "the LSP for AI coding
  agents" ([morphllm](https://www.morphllm.com/agent-client-protocol)). The
  client launches and supervises the agent as a subprocess and drives it via
  JSON-RPC with capability negotiation at init
  ([grida ACP doc](https://grida.co/docs/wg/ai/agent/acp)).
- **A2A (Agent-to-Agent, Google)** — agent<->agent coordination; peripheral to
  the current client/executor design.

Key correction recorded here on purpose: a coding agent (Codex, OpenCode,
Claude Code) is **driven via ACP/CLI, not "called as an MCP tool"**. MCP and ACP
are orthogonal and complementary: ACP governs "how a client commands many
agents"; MCP governs "how each agent/brain reaches tools".

## Who can act as a web/app MCP client (connect MCP servers from the chat UI)

- **ChatGPT web** — yes, via Developer Mode / "apps" (connectors renamed to
  apps 2025-12-17). Full MCP incl. write actions on Business/Enterprise/Education;
  Plus/Pro get read-only custom connectors; rolling out gradually
  ([OpenAI help](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt),
  [Boomi](https://help.boomi.com/docs/Atomsphere/Platform/Connect_chatgpt_setup)).
- **Claude.ai web** — yes, via custom connectors; requires Pro/Max (not free);
  one connector infra spans Claude.ai, Desktop, mobile, Claude Code, Cowork
  ([claude.com docs](https://claude.com/docs/connectors/building/authentication),
  [FullEnrich](https://help.fullenrich.com/en/articles/14595910-connect-fullenrich-mcp-to-claude)).
- **Desktop / IDE clients** — Claude Desktop, Cursor, VS Code (Copilot),
  Windsurf, Cline, Claude Code, Goose are strong MCP clients
  ([apigene](https://apigene.ai/blog/mcp-client)). Note: these are themselves
  local agents already.
- **Chinese consumer web (Doubao, DeepSeek web, Wenxin)** — no web MCP-client
  entry in the consumer chat (observed; ByteDance's MCP story lives on the
  Volcengine/Coze developer side).

Shared gotcha: ChatGPT and Claude web connect to **remote** MCP servers
(HTTPS URL + OAuth). To expose a **local** DevFrame tool server to them you need
an HTTPS tunnel + auth — a real security boundary, and the long-standing
"real ... HTTPS tunnel" gap in the recon receipts.

## ACP-capable coding agents (can be driven by an ACP client)

Claude Code, Codex, Copilot, Qwen Code, Gemini CLI, OpenCode, Kiro, OpenClaw and
more ([vscode-acp client](https://marketplace.visualstudio.com/items?itemName=foxweimin.vscode-acp-client)).
Codex specifically: a bridge `codex-acp` exposes the OpenAI Codex runtime to ACP
clients over stdio ([cola-io/codex-acp](https://github.com/cola-io/codex-acp));
Gemini CLI has an explicit ACP mode ([geminicli](https://geminicli.com/docs/cli/acp-mode/)).
T3Code calls itself "a minimal web GUI for using coding agents like Codex and
Claude" ([T3Code AGENTS.md](https://raw.githubusercontent.com/pingdotgg/t3code/refs/heads/main/AGENTS.md)).

## Function-calling via API (build your own tool/MCP loop)

Models without a web MCP client still support function calling through their
APIs, so your code can run the tool loop:
- **DeepSeek** — OpenAI-compatible API with function calling
  ([DeepSeek docs](https://api-docs.deepseek.com/guides/function_calling/));
  also runnable as a local model (e.g., via Ollama).
- **Qwen, Mistral, Llama** — support the standard tools/function-calling format
  via API ([runcrate](https://www.runcrate.ai/ai-agents-api)). **Doubao** is
  reachable via the Volcengine API; verify its current tool-calling surface
  before relying on it (register A5).

## DevFrame integration tiers (which protocol each uses)

- **Tier A — API / local model** (DeepSeek API or local, Qwen, Doubao API,
  OpenAI API): truly local, headless, autonomous. Uses API function-calling;
  your code owns the tool loop. The backbone for unattended autonomy.
- **Tier B — web/app MCP client** (ChatGPT, Claude.ai; or desktop/IDE agents):
  the AI calls local tools via MCP connectors; for local tools needs an HTTPS
  tunnel. Gated by paid plan.
- **Tier C — web-only, no MCP/API** (Doubao/DeepSeek consumer web): not a local
  agent; a tethered external brain, attended/low-frequency only.
- **Execution of coding work** in all tiers is best done by an **ACP-driven
  coding agent** (Codex/OpenCode/Claude Code) launched as a subprocess; DevFrame
  wraps governance around the ACP session. ACP is the multi-agent backbone; MCP
  supplies each agent/brain its tools.

## Critical-path scan (2026-06-26)

Scoped scan tied to roadmap modules M1-M5. Decision-driven, not exhaustive.

### ACP capability surface (M2)
ACP runs over stdin/stdout, HTTP, or WebSocket; lifecycle is
`initialize -> session/new -> session/prompt`, with streaming `session/update`
notifications for tool calls, text chunks, and agent thoughts, plus a permission
flow for safe tool execution; capabilities are negotiated at init (incl. whether
the agent supports MCP) ([ACP TS SDK](https://www.mintlify.com/agentclientprotocol/typescript-sdk/concepts/protocol-overview),
[lobehub](https://lobehub.com/skills/adambossy-ai-skills-library-acp-agent),
[ex_mcp ACP](https://hexdocs.pm/ex_mcp/ExMCP.ACP.Agent.html)). An ACP agent is
"the ACP counterpart to an MCP server": it serves `session/new`/`session/prompt`,
streams updates, and may request client-side filesystem/terminal/permission ops.

Reuse note: headless ACP clients already exist (`acp-cli`/`acpx` in Rust,
`vscode-acp`, ExMCP adapters) — so DevFrame may reuse a headless ACP client
instead of writing one ([acpx](https://acpx.sh/),
[lib.rs acp-cli](https://lib.rs/crates/acp-cli)).

### ACP agent readiness (M2)
Codex has multiple ACP bridges incl. an official one that "exposes Codex CLI
functionality" ([agentclientprotocol/codex-acp](https://github.com/agentclientprotocol/codex-acp),
[zed-industries/codex-acp](https://github.com/zed-industries/codex-acp)); Zed
documents External Agents over ACP ([Zed](https://zed.dev/docs/ai/external-agents));
OpenCode/Claude Code/Gemini are ACP-reachable ([vscode-acp client](https://marketplace.visualstudio.com/items?itemName=foxweimin.vscode-acp-client)).
Drift to verify: Gemini CLI was reportedly renamed Antigravity CLI by mid-2026
([sanj.dev](https://sanj.dev/post/comparing-ai-cli-coding-assistants/)).

### Local-MCP-over-tunnel now has official options (M5) — updates prior gap
Web connectors reach your MCP server from the vendor's IP, so localhost is not
reachable without a tunnel ([localcan](https://www.localcan.com/blog/test-local-mcp-server-in-claude-ai)).
Official tunnels now exist: OpenAI's **Secure MCP Tunnel** (its `tunnel-client`
README states it connects a localhost MCP server to ChatGPT/Codex/Responses/
AgentKit while keeping the server off the public internet
([openai/tunnel-client](https://raw.githubusercontent.com/openai/tunnel-client/master/README.md))),
and Anthropic's **MCP tunnels** in the Claude Console
([Claude MCP tunnels](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/quickstart)).
Those off-public-internet guarantees are **vendor claims, not yet independently
verified here** (register A2). If they hold, they reduce the long-standing
"real ... HTTPS tunnel" gap and are preferable to raw ngrok/cloudflared — but
confirm the guarantee before relying on it.

### Orchestration engines (M3)
2026 orchestration falls into five patterns: sequential, parallel, hierarchical,
state-graph (LangGraph), swarm ([groovyweb](https://www.groovyweb.co/blog/multi-agent-orchestration-patterns-supervisor-router-pipeline-swarm-2026)).
Frameworks: LangGraph (state-graph, production standard), CrewAI (role teams,
fast prototype), AutoGen (reportedly maintenance mode), plus OpenAI Agents SDK /
Claude Agent SDK / Google ADK ([marsdevs](https://www.marsdevs.com/compare/langgraph-vs-crewai-vs-autogen)).
DevFrame already embeds LangGraph in ai-workflow-hub -> consolidate around it
rather than add a new framework. Sober caution to keep: single-agent fits ~80%
of cases; do not reach for multi-agent just because it sounds capable
([daily.dev](https://daily.dev/blog/ai-agents-guide-for-developers-langchain-crewai/)).

### Multi-agent coordination standard: A2A (M1)
A2A (Google, Apr 2025; donated to the Linux Foundation; 150+ orgs incl. AWS,
Microsoft, Salesforce, SAP, ServiceNow; production use) is the emerging standard
for agents to discover each other, exchange messages, and delegate tasks across
ownership/trust boundaries ([Linux Foundation](https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year),
[letsdatascience](https://letsdatascience.com/blog/a2a-protocol-agent-to-agent)).
Rule of thumb: agents use A2A for coordination and MCP for tool access
([Oracle](https://blogs.oracle.com/developers/the-agent-communication-matrix-when-mcp-a2a-and-plain-rest-each-win)).
But A2A pays off mainly when agents are independent systems with their own trust
boundaries; for local agents DevFrame owns, a simpler message queue (at-least-once
delivery, dead-letter, back-pressure) may suffice ([glukhov](https://www.glukhov.org/ai-systems/comparisons/a2a-protocol-2026-adoption/),
Oracle). This is an open M1 decision (see unknowns register).

## Sources note

Content above is paraphrased from the linked public sources and may be out of
date; vendor plan gating and protocol support change frequently. Re-verify the
specific claim you depend on before committing architecture to it.
