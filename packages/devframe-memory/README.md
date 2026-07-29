# DevFrame Memory MCP

This package exposes DevFrame's existing project-scoped Obsidian memory through
an on-demand MCP subprocess. The client starts `devframe memory mcp-stdio` in
the current project and stops it with the session. No HTTP daemon or Codex
`config.toml` entry is required.

## Prerequisite

Install `packages/control-plane` so the `devframe` console command is available,
and configure the existing `DEVFRAME_OBSIDIAN_MEMORY_ROOT` environment variable
or runtime bootstrap for the private Vault.

## Clients

- Codex can load this directory as a plugin. Its companion `.mcp.json` uses
  Codex's direct server-map format.
- Claude Code can use the repository template at
  `templates/runtime-bootstrap/devframe-memory.mcp.json` as a project MCP
  configuration in Claude's wrapped `mcpServers` format.
- Any MCP client that supports stdio can launch `devframe` with arguments
  `memory`, `mcp-stdio`.

The process derives project identity from its startup directory. Tool schemas
do not accept a project root or Vault path. Explicit cross-project identifiers
are rejected, writes remain create-only or human-gated, and
`DEVFRAME_OBSIDIAN_MEMORY_READ_ONLY=true` removes write tools from discovery.
