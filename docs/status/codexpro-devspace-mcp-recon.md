# CodexPro / DevSpace MCP Recon

## Purpose

DevFrame's target is Web GPT through MCP as a local agent entrypoint, not a
ZIP/report-based WebGPT review loop. This note records what CodexPro and
DevSpace do today so DevFrame can reuse the working MCP bridge patterns instead
of hand-rolling the wrong abstraction.

## Sources Inspected

- CodexPro: `https://github.com/rebel0789/codexpro`
  - inspected revision: `1480790c4a2d8f51af8bd5d24334c4264d17c66e`
- DevSpace: `https://github.com/Waishnav/devspace`
  - inspected revision: `65be2522c091c4b9f7fb61af8f624d1f82e6e682`
- DevSpace issue 10: `https://github.com/Waishnav/devspace/issues/10`
- DevSpace issue 11: `https://github.com/Waishnav/devspace/issues/11`

## Findings

### CodexPro

- Uses the official ChatGPT Developer Mode / MCP app path as the mainline.
- Exposes a bounded local workspace through MCP tools rather than uploading
  bundles to ChatGPT.
- Keeps tool catalog size configurable: minimal, standard, full.
- Removes dangerous tools from the advertised tool list when disabled:
  `write`/`edit` are hidden unless write mode is workspace, and `bash` is hidden
  when bash mode is off.
- Separates source writes from handoff writes:
  - `write`/`edit` are workspace source mutation tools.
  - `handoff_to_agent` writes bounded `.ai-bridge` handoff files and explicitly
    does not execute the local agent.
- Uses MCP annotations to tell ChatGPT the risk class:
  - read tools: `readOnlyHint: true`, `destructiveHint: false`
  - handoff writes: non-read-only but `destructiveHint: false`
  - source writes and bash: destructive / powerful
- Keeps fallback context generation separate from live MCP:
  `export_pro_context` is a fallback for model surfaces that cannot call MCP
  tools directly.

### DevSpace

- Uses a public HTTPS tunnel plus MCP endpoint and OAuth owner approval.
- Requires `open_workspace` first; later tools operate by `workspaceId`.
- Enforces configured allowed roots and workspace-relative paths.
- Supports managed Git worktrees for isolated or parallel coding sessions.
- Exposes explicit tools for read, write, edit, search, shell, and
  `show_changes`.
- Treats shell as powerful local access and requires trust in the connected MCP
  client.
- Documents that a visible ChatGPT app pill is not enough. The real proof is
  actual `openai-mcp` requests and tool calls reaching the local service.

### Safety Edge Case

DevSpace issue 10 is directly relevant to DevFrame's current block:

- ChatGPT successfully called `open_workspace`.
- It then refused to continue because the next file creation route was a
  generic overwrite-capable `write` tool.
- The proposed fix is a create-only tool with exclusive create semantics:
  non-destructive, fails if the file exists, and tells the model to use edit or
  overwrite only when explicitly intended.
- A local patch with that shape let ChatGPT continue with
  `open_workspace -> create_file`.

## DevFrame Implications

- The current Web GPT safety block is not a dead end. It means the advertised
  tool shape is too broad or too destructive for the active ChatGPT safety lane.
- DevFrame should not replace MCP with ZIP/report submission. ZIP/report remains
  fallback and external review evidence only.
- The next live MCP tool should be a non-destructive task-intake tool, not
  another workspace write/handoff tool:
  - requires a small title and task summary
  - accepts priority and suggested local agent
  - creates a new local intake/evidence record only
  - never overwrites source files
  - never runs OpenCode/Codex directly from the Web GPT call
  - returns a local task/session id and next local action
- Tool metadata should make risk explicit:
  - `readOnlyHint: false`
  - `destructiveHint: false`
  - `idempotentHint: false`
  - `openWorldHint: false`
- Real success must be judged by local service logs/evidence showing Web GPT
  called the MCP tool, not by the app pill being visible.

## Recommended Next Slice

Build a DevFrame-owned `task_intake` MCP tool/profile compatible with the
current Web GPT connector path.

Acceptance evidence:

- Web GPT can call `task_intake` with a minimized payload.
- Local runtime creates a `chatgpt-web-mcp` session, evidence file, and next
  action.
- The T3/native client can show the intake as a team workbench item.
- No source files are edited and no local coding agent is executed directly by
  the MCP call.
- If the active ChatGPT model lane cannot call tools, DevFrame records that as
  model-lane/tool-routing evidence instead of treating the connector as broken.
