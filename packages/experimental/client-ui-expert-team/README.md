---
description: "Capability center with an expert catalog, skill and connector management, and the read-only library."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-expert-team

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-expert-team` is the resident Web entry for the [expert-team core](../expert-team/README.md). It mounts the generated `ctx.remote.expertTeam` namespace and registers a sidebar trigger in the `sidebar.footer.action` seat. The trigger opens a Capability center with Experts, Skills, Connectors, and Library tabs. The Experts tab projects mounted experts from the Host snapshot into searchable, team-filterable, name-sortable cards with detail, summon, and current-process run-history actions; summoning stages a user-editable prompt and selected-expert chip in a new blank conversation. The detail view distinguishes a direct "start pipeline" action (`startRun`) from a "consult expert" action (`consult`), bypassing the draft handoff path, and gated run rows expand to read the pending gate questions and record an approve/reject decision. The other tabs render the mounted skill, connector, and library management pages; a missing provider produces an explicit unavailable state. The package is published as a client plugin and depends only on DSH's public client slots and Remote contracts.

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

### Install into a DSH Web profile

Install this published client plugin together with the Host expert-team and its data-pack plugins in the profile's dependency set. Add the Host row with `packs` set to installed package names such as `@deepseek-ai/dsh-experimental-expert-pack-paper`; the expert-team plugin resolves those names from its own installation, so the composition does not depend on the launch directory or a source checkout. The package root is inert in headless compositions and the Web loader selects its `/client` export through the `dsh.client` manifest.

### What you get

- A resident sidebar trigger with an active count for runs that are `running` or `waiting-approval`.
- A catalog of every expert in the mounted teams, with search by name, role, id, or team, team filters, and recommended/name sorting.
- Card and detail actions that open the normal New Session flow, select the expert, and stage an editable prompt; the prompt is sent only when you submit it.
- A selected-expert detail view showing its team, run mode, assigned phases, gates, and declared tools; the catalog grid expands to the available width until a detail view is selected.
- Skills and Connectors tabs reuse the Host-backed management pages, and Library browses the configured Vault through its existing Remote.
- A recent-run section showing the latest six current-process records, plus explicit refresh and close actions. A failed Remote read is shown as an error instead of being replaced with fabricated status.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) mounts the generated expert-team Remote contribution and delegates to [`mountExpertTeamUi`](src/client/mount.ts). The mount registers the English and Chinese `expert-team` dictionaries, injects the sidebar entry (id `expert-team`, order 20) with the keyed `capabilities.center.tab` child, and injects a session-scoped `conversation.input.left` chip. The card reads `ctx.remote.expertTeam.view()` and sends summon selections to `ExpertSelectionController`; that controller calls `uiWorkspace.startSession()`, waits for the blank Session, and writes the staged prompt through `ctx.conversation.input`. The Host gateway additionally exposes `startRun`, `consult`, `approve`, and `getRun`: the detail view starts pipeline runs and consults single experts through them, and gated run rows fetch the full snapshot via `getRun` and record human decisions via `approve` with an optional comment. The client flattens returned experts for search, filters, sorting, detail, and suggestion rendering, while stale reads, selection state, and product copy remain owned by their respective client surfaces.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry and generated Remote binding |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount, locale registration, and sidebar contribution lifecycle |
| [`src/client/ExpertTeamCard.tsx`](src/client/ExpertTeamCard.tsx) | Resident trigger, catalog, detail actions, and prompt suggestions |
| [`src/client/ExpertSelectionChip.tsx`](src/client/ExpertSelectionChip.tsx) | Selected-expert chip in the blank-session composer |
| [`src/client/selection.ts`](src/client/selection.ts) | New-session handoff and staged-draft reconciliation |
| [`src/client/locales.ts`](src/client/locales.ts) | `expert-team` locale namespace and English/Chinese dictionaries |
| [`src/index.ts`](src/index.ts) | Inert Host-side package entry for profile compositions |
| — | No runtime invariant companion is published; the card is a pure consumer of the Host Remote snapshot. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Expert-team core](../expert-team/README.md) — pack loading, orchestration, gates, and the Host Remote owner.
- [Skills and connector management](../../client/ui-settings-plugin-inventory/README.md) — the Host-backed Skill and MCP management pages.
- [Library page](../client-ui-project-memory/README.md) — the read-only Vault browser and conversation references.
- [DevFrame profile](../devframe-profile/README.md) — an optional source composition for the broader stack.
- [Experimental packages](../README.md) — incubation status and package boundaries.

-----

<a id="model-experience"></a>
## Model Experience

### Capability center

#### What the model sees

The center itself is browser-only and registers no tools or prompt sections. A summon action stages ordinary user-visible draft text and an expert chip in a blank Session; if the user submits that draft, the normal Conversation path sends it, and the mounted `expert_team_run` tool remains the model-visible orchestration surface.

#### Token effect

Summoning adds no automatic request. A submitted staged prompt contributes its visible text like any other user prompt.

#### KV Cache effect

The entry contributes no tool or schema content. Any cache effect comes from the user-submitted prompt text and follows normal Conversation behavior.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Host-owned execution** — card summon actions stage a new conversation; detail consultation, pipeline starts, and approval controls call the Host Remotes.
- **Prompt is not auto-submitted** — after summoning, the user can edit or remove the expert chip before sending. If no workspace is available, the selection remains staged until a blank Session can be opened.
- **Mounted catalog only** — the Experts tab contains the teams and experts returned by the Host Remote. The other tabs require the inventory and library UI providers to be mounted; the center never fabricates their contents.
- **Live-process history only** — the Host Remote projects the orchestrator's current in-memory run index. `run-index.json` remains an inspection mirror and is not a cross-process recovery source.
- **Refresh is explicit** — the card reads on mount and when opened or refreshed; it does not subscribe to every run transition.
- **Optional providers** — the four tabs are independently contributed. Installing the center without the Skills, Connectors, or Library providers leaves those tabs in the documented unavailable state.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
