# Agent Note: The Shadow trigger opens the designated session

Status: implemented

English | [中文](2026-09-11-shadow-trigger-opens-designated-session.zh.md)

## Problem

The sidebar Shadow entry needs one unambiguous destination, and two implementations failed the human's intent: a hand-rolled popup chat panel is not the product's conversation surface, and a trigger that creates a fresh session per click litters the session list with an ungrouped "new conversation" row. The Shadow is one permanent independent agent, so its entry point is that agent's one durable conversation, rendered by the same surface the main chat uses.

The obvious wiring — create the designated session from the client when the trigger fires — cannot work. The host creates the designated session at boot through the agent path, and an agent-created session records no `cwd`; the `session/create` RPC's adopt path requires a session's recorded `cwd` to match the request, so it always answers `session/conflict` ("records no cwd and cannot be adopted"). A client that calls `create()` for the designated id therefore fails on every click, and the fire-and-forget `void onOpenConversation()` swallows the rejection, which reads to the human as a button that does nothing.

## Decision

The trigger opens the Shadow's designated session through the standard session surface. `onOpenConversation` reads `shadow/readStatus`, takes `shadowSessionId`, refreshes the Host-authoritative session list when that id is not yet listed, and calls `sessions.open(id)`; it never calls `sessions.create`, because opening is the only correct path for an agent-created session and `refresh()` covers the boot race where the host has not yet published the id. The card keeps the panel as a secondary surface behind a Manage button beside the trigger (wide sidebar only); the panel leads with the conversation view and holds the project management view behind a toggle.

## Alternatives considered

**Keep the hand-rolled popup chat panel as the trigger's destination.** Rejected: the Shadow renders in the same conversation surface as the main chat; a bespoke text-line panel with polling is a different product and the human rejected it outright.

**Create a fresh session on every click.** Rejected: it produces an ungrouped "new conversation" row per click in the session list, and every such conversation is empty — the opposite of one permanent agent.

**Point the trigger at the pre-existing designated session with its full history.** Rejected: the human asked for a fresh designated conversation, so the deployment's `shadowSessionId` was reset rather than reused.

**Call `sessions.create({ sessionId })` and treat the conflict as a retry trigger.** Rejected: the conflict is deterministic for an agent-created session, not transient, so the retry can never succeed; `open` is the correct path, with `refresh` covering only the list race.

**Record `cwd` on the designated session in the host so `create` can adopt it.** Deferred, not rejected: it would make `create` viable, but opening an existing session is the honest operation for a permanent conversation and needs no host change, so the host-side `cwd` gap stays a separate decision.

## Consequences

Clicking the Shadow always lands on the same durable conversation, and the session list gains no per-click rows. Keeping the designated session itself out of the session browser is [the internal-session classification](2026-09-11-internal-session-classification.md), which accompanies this change. An `open` that fails — a status read that fails, or a status that names no session — leaves the trigger visibly inert, and the fire-and-forget call surfaces the rejection only in the console, so user-visible error reporting remains open.

## Testing

`shadow-mount.client.spec.ts` pins the four `onOpenConversation` paths — status ok and listed (open only), status ok and not listed (`refresh` then `open`), a failed status read, and a status with no designated session — and asserts that no `sessions/create` call is made. `shadow-card.client.spec.tsx` pins the trigger click reaching `onOpenConversation` and the Manage button opening the panel.

## Related

[Reach the designated Shadow's conversation from the Web card](../bug-fix/2026-09-10-shadow-conversation-reachability.md) owns the conversation faces the panel and the standard surface read and write.
