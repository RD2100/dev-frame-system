# Agent Note: Desktop capability management and Schedule controls

Status: implemented

English | [中文](2026-09-24-desktop-skill-mcp-schedule-management.zh.md)

## Problem

The Desktop settings surfaces exposed capability and schedule state without a complete user-owned mutation path. Skills could not be installed or toggled, MCP entries were memory-only from the browser's point of view, and schedule actions stopped at the read-only task center.

## Decision

The Host plugin-inventory Remote owns user Skill files and MCP configuration. Skills are authored as validated `SKILL.md` files below `$DSH_HOME/skills`, with enablement represented by the official invocation frontmatter fields. MCP entries are restored from `$DSH_HOME/storages/mcp-servers.json`, written through a serialized atomic replace, and projected with `env` and `headers` redacted. The Settings capability tab calls these Remotes for install, enable, disable, uninstall, add, edit, test, and remove operations; deployment-owned profile and preset composition remains read-only.

Schedule mutation belongs to the Schedule Host Remote. The Settings task center calls session-addressed pause, resume, run-now, and delete methods and reloads the Host projection after each result. The header catalog remains a read-only summary.

## Alternatives considered

**Keep browser-local capability state.** Rejected because it diverges from Loader state and disappears on reconnect or restart.

**Return MCP credentials to the browser for testing.** Rejected because redacted projections cannot safely reconstruct private transport values; the Host now probes an existing entry using its private stored configuration.

**Let the header catalog own Schedule mutations.** Rejected because the Settings task center has the space for action state and errors while the header remains a compact read view.

## Consequences

User Skill and MCP changes survive Host restart and are visible through the same Loader-backed projection. MCP configuration files are local durable state and must be protected by the DSH home boundary; secrets are omitted from Remote responses. Cold-restart Electron acceptance still needs a real packaged runtime run, while focused Host, Client, Schedule, and Typert checks cover the shipped seams.

## Testing

Focused Vitest suites cover Host Skill lifecycle, Settings Skill/MCP controls and failure redaction, browser plugin registration, and Schedule task actions. Host, Schedule, API Remote, and UI Schedule TypeScript builds pass; Typert artifacts regenerate successfully. The Settings package build still reports pre-existing `ui-approval` and `ui-chat` SessionStore declaration errors outside this change.
