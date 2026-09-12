# Agent Note: Reach the designated Shadow's conversation from the Web card

Status: implemented

English | [中文](2026-09-10-shadow-conversation-reachability.zh.md)

## Problem

The DevFrame Web profile composes the shadow-controller host layer, and `ctx.remote.shadow` already carries the conversation faces (`postMessage`, `readConversation`) — yet the human's GUI shows only a status panel: the shadow session never comes online, and no conversation surface exists at all. Four independent defects stack into that dead end:

- A hand-written record in the `session_identity` storage binds the designated shadow session as role `controller`. The agent-hierarchy `agent/created` listener then installs its tool restriction, but the standard-tool allowlist is session-scoped while the web host's tool registry is global, so `tools.restrict()` rejects the unknown names and `agents.create` rolls back — the shadow never exists.
- `ShadowAgent.ensureOnce()` requires the shadow router before the loader settles, so the startup ensure races sibling plugin mounts, fails against an unmounted router, and the web profile's missing logger exporter swallows the warn; no retry ever runs.
- The client card renders only the status and project surfaces; nothing in the GUI can post a message or read the conversation.
- The DevFrame profile omits a console logger exporter, so the failing ensure surfaces nowhere.

## Decision

The designated shadow session carries no durable role binding: its eight Agent-scoped, non-controlled tools run by designation, and the stale controller row was removed from `session_identity.json` — binding happens only through `bind()`, which requires the agent to exist first. `ensureOnce()` awaits the loader before requiring the router, so the startup ensure observes the completed composition; the conversation read paths still ensure, so a genuine absence retries and fails loud on the next conversation verb. The DevFrame profile composes the logger-console exporter as its first insert, so host warnings reach the console in web deployments.

The Shadow card carries the conversation surface. `ShadowConversationController` folds a tail load and incremental polls past the cursor into one snapshot store with the same superseded-read guard the status store uses; a failed read keeps the rows and publishes the failure. While the panel is open and the shadow is online the card loads the tail on open, polls every three seconds, and posts through `onPostMessage`; each row shows the role, the text, and a compact wall-clock time, and the panel renders the honest offline hint before online, the empty copy before any row, and read or send failures verbatim. Locales add the `chat.*` keys in both languages.

## Alternatives considered

**Bind the shadow session with an empty allowlist.** Rejected: the hierarchy guard treats a durable binding as the session's authority record, so an empty allowlist misstates its powers, and any later role adjustment re-enters the same restriction path that the global registry cannot serve. Unbound-by-default with designation as authority is the honest model for a non-controlled tool set.

**Hand-write the binding with the hierarchy's inherited allowlist.** Rejected: the failure is structural, not a matter of the right names — session-scoped standard tools are invisible to the web host's global registry, so no allowlist makes the restricted creation succeed there.

**Retry the ensure on a timer.** Rejected: a polling retry paints over the composition race instead of removing it. Awaiting the loader makes the startup call observe final composition; the read-path ensure keeps a retry available without a timer.

**Optimistic chat append after an accepted post.** Rejected: read rows carry no client-minted ids to dedupe against, so the optimistic row would duplicate the authoritative one. The accepted post followed by an immediate incremental poll lands the row from the session log.

## Consequences

The conversation is reachable end-to-end from the GUI: post, agent loop, reply on the persisted surface, and the card's incremental polls; the panel polls only while it is open and the shadow is online, so a closed panel never reads. Removing the hand-written binding also removes the shadow session from the hierarchy's restriction machinery entirely — restricting the shadow's tools, should that ever be wanted, belongs in session tool scoping, not a role binding. The landmine one step further stays: the router binds project controllers as role `controller` when a project opens, and in a web deployment those sessions hit the identical global-registry rejection on creation; that needs its own decision and is deferred, not fixed here.

## Testing

`shadow-agent.host.spec.ts` creates the session with no role binding while the hierarchy guard is active and dispatches a live `shadow_status` answer, and fails loud when a seeded binding drags a hierarchy tool face into creation. The profile and loader-composition suites pin the nine-row insert with logger-console first. The client suite covers the conversation store (tail load, incremental poll, cursor fallback, failure surface, latest-read ownership) and the card surface (tail render, empty and offline states, Enter submit, verbatim failures, the three-second poll while open and none after close) plus the mount wiring of the conversation face.
