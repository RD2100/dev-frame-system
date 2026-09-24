---
description: "Loader inventory plus user Skill and MCP management Remotes for web GUI host clients."
kind: "package-reference"
---

# @deepseek-ai/dsh-host-plugin-inventory

English | [中文](README.zh.md)

## Summary

Clients and settings pages can inspect the host with `pluginInventory/list`, manage user-owned Skills with `listSkills`, `installSkill`, `setSkillEnabled`, and `removeSkill`, and manage MCP clients with `listMcp`, `createMcp`, `updateMcp`, `setMcpEnabled`, `testMcpEntry`, and `removeMcp`. Loader inventory remains a point-in-time projection; user Skills live under `$DSH_HOME/skills`, while MCP configuration is persisted in `$DSH_HOME/storages/mcp-servers.json`. Client packages consume the Remote through the explicit [`api-remotes`](../../api/remotes/README.md) assembly rather than importing the Host implementation.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Call `pluginInventory/list` when a client or settings page needs to show what is currently composed in the host — which plugins are loaded, enabled, and alive, and what each agent preset would give a session. The Remote is the only entry point: the service is Remote-only and deliberately declares no same-process Cordis `Context` merge.

### What a snapshot contains

Each row is one non-group Loader entry: its entry id, the exact module specifier, the effective enablement (including disabled ancestor groups), and the current root Fiber phase. `pending` means the entry waits to load, `loading` that it is being read, `active` that it is running, `failed` that its fiber rejected, and `unloading` that it is being torn down; `null` means no live root Fiber exists at all. Structural group rows are skipped.

### Per-preset compositions

With a roster composed, `agentPresets` carries one group per preset in roster order: its id, whether the deployment ships it or the user owns it (`trust`, which clients use to localize shipped names), published display name, whether a session naming no preset composes it, and flattened plugin rows — entry id (null when the file row declares none), module specifier, effective enablement, the row's own `!!js` disabled expression when it carries one, and a root-fiber phase when the composition is live. A preset some session already composed answers from its newest standing generation — even when its file has since broken, because the mount is what those sessions run; one never composed since boot answers from its composition file with disabled gates evaluated against the Loader context, and reading never mounts a preset. `conditional` enablement marks a gate the Host could not evaluate, and a broken preset nothing composed stays listed with its reason and no rows. Without a roster the field is absent.

### Inventory and management

The inventory is a snapshot for display and diagnostics. Management methods only operate on user-owned Skills and MCP entries; profile and preset composition rows remain read-only. Skill content is authored as `SKILL.md` through the Remote, and MCP secrets are never returned in projections. MCP edits replace the fields shown by the form while preserving stored transport options such as `args`, `cwd`, `env`, `headers`, and retry settings. The MCP store is local DSH-home state written with private file and directory modes where the host filesystem supports them. Because the service reads the Loader on every call, the answer reflects current composition rather than a cached view.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

### Design concept

The gateway keeps Loader state authoritative for inventory and live MCP mutations. User Skill files are validated at the managed-root boundary and rewritten with canonical invocation fields. MCP writes are serialized through an atomic temporary-file rename; startup restores persisted entries once before serving MCP reads or mutations. The agent-preset roster is an optional peer resolved per call through `ctx.get('agentPresets')`.

### The phase mapping

Fiber states map onto the public phase vocabulary, with `disposed` folding into `null` — an entry whose fiber is gone has no live root to report. The phase therefore never distinguishes why no live root exists: the entry may never have started, or its fiber may already have been disposed.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | `PluginInventoryGateway`: the `pluginInventory` Remote service and the Loader projection |
| [`src/types.ts`](src/types.ts) | Public payload types: `PluginInventoryEntry`, `PluginInventorySnapshot`, `PluginFiberPhase` |
| — | No runtime invariant companion is published; every snapshot is projected directly from Loader-owned state. |

Typert generates the Host and Client Remote artifacts exposed by `./typert` and `./remote`.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

Read these when the inventory contract is not enough: how the Remote reaches clients, then the Loader it projects and the surface that renders it.

- [Remote assembly](../../api/remotes/README.md) — how clients consume `pluginInventory/list` without importing the Host implementation.
- [Cordis plugin loader](../../../vendor/loader/README.md) — the Loader whose entries this package projects.
- [Plugin inventory settings surface](../../client/ui-settings-plugin-inventory/README.md) — the browser-side projection that renders the inventory.

-----

<a id="model-experience"></a>
## Model Experience

None, as this host-side management surface registers no model-facing content.

#### KV Cache effect

None; this package neither assembles nor sends a provider request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>


These limits define what a point-in-time inventory cannot tell a client. They are current package constraints, not a task backlog.

- **Point-in-time state only** — the result contains no durable failure history or subscription; a missing root Fiber is reported as `null`, regardless of why no live root exists.
- **Profile and preset rows remain read-only** — management is limited to user-owned Skill files and MCP entries created through this service.
- **Presets appear only with a roster** — a deployment without `dsh-agent-presets` serves Loader entries alone; the `agentPresets` field is absent rather than empty.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
