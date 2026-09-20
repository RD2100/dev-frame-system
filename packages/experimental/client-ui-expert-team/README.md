---
description: "Expert-center Web entry: a searchable catalog with new-session summon actions, live-process runs, and reserved skill and connector tabs."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-expert-team

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-expert-team` is the resident Web entry for the [expert-team core](../expert-team/README.md). It mounts the generated `ctx.remote.expertTeam` namespace and registers a sidebar trigger in the `sidebar.footer.action` seat. The trigger opens an Expert center with Experts, Skills, and Connectors tabs. The Experts tab projects mounted experts from the Host snapshot into searchable, team-filterable, name-sortable cards with detail, summon, and current-process run-history actions; summoning stages a user-editable prompt and selected-expert chip in a new blank conversation. The detail view distinguishes a direct "start pipeline" action (`startRun`) from a "consult expert" action (`consult`), bypassing the draft handoff path, and gated run rows expand to read the pending gate questions and record an approve/reject decision. The other tabs state clearly that their data source is not connected yet. Official releases exclude this package, so it is available only from a source checkout.

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

### Install into the DevFrame Web profile

The [DevFrame profile layer](../devframe-profile/README.md) already mounts the Host core with the paper and development packs, and this browser entry. For a manual composition, mount `@deepseek-ai/dsh-experimental-expert-team` on the Host and this package on the Web side; the package root is inert in headless compositions and the Web loader selects its `/client` export through the `dsh.client` manifest.

### What you get

- A resident sidebar trigger with an active count for runs that are `running` or `waiting-approval`.
- A catalog of every expert in the mounted teams, with search by name, role, id, or team, team filters, and recommended/name sorting.
- Card and detail actions that open the normal New Session flow, select the expert, and stage an editable prompt; the prompt is sent only when you submit it.
- A selected-expert detail view showing its team, run mode, assigned phases, gates, and declared tools; the catalog grid expands to the available width until a detail view is selected.
- Skills and Connectors tabs with explicit not-connected-yet messaging, rather than dead controls or fabricated inventory.
- A recent-run section showing the latest six current-process records, plus explicit refresh and close actions. A failed Remote read is shown as an error instead of being replaced with fabricated status.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) mounts the generated expert-team Remote contribution and delegates to [`mountExpertTeamUi`](src/client/mount.ts). The mount registers the English and Chinese `expert-team` dictionaries, injects the sidebar entry (id `expert-team`, order 20), and injects a session-scoped `conversation.input.left` chip. The card reads `ctx.remote.expertTeam.view()` and sends summon selections to `ExpertSelectionController`; that controller calls `uiWorkspace.startSession()`, waits for the blank Session, and writes the staged prompt through `ctx.conversation.input`. The Host gateway additionally exposes `startRun`, `consult`, `approve`, and `getRun`: the detail view starts pipeline runs and consults single experts through them, and gated run rows fetch the full snapshot via `getRun` and record human decisions via `approve` with an optional comment. The client flattens returned experts for search, filters, sorting, detail, and suggestion rendering, while stale reads, selection state, and product copy remain owned by their respective client surfaces.

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
- [DevFrame profile](../devframe-profile/README.md) — the source-checkout Web composition that mounts the Host and browser rows together.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

### Expert-team center

#### What the model sees

The center itself is browser-only and registers no tools or prompt sections. A summon action stages ordinary user-visible draft text and an expert chip in a blank Session; if the user submits that draft, the normal Conversation path sends it, and the mounted `expert_team_run` tool remains the model-visible orchestration surface.

#### Token effect

Summoning adds no automatic request. A submitted staged prompt contributes its visible text like any other user prompt.

#### KV Cache effect

The entry contributes no tool or schema content. Any cache effect comes from the user-submitted prompt text and follows normal Conversation behavior.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Conversation handoff, not direct orchestration** — summon actions stage a new conversation and never call run or approval mutations; starting runs and approving human gates remain model/Host operations.
- **Prompt is not auto-submitted** — after summoning, the user can edit or remove the expert chip before sending. If no workspace is available, the selection remains staged until a blank Session can be opened.
- **Mounted catalog only** — the Experts tab contains the teams and experts returned by the Host Remote. Skills and Connectors have visible tabs, but no Remote data source is connected for them yet.
- **Live-process history only** — the Host Remote projects the orchestrator's current in-memory run index. `run-index.json` remains an inspection mirror and is not a cross-process recovery source.
- **Refresh is explicit** — the card reads on mount and when opened or refreshed; it does not subscribe to every run transition.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
