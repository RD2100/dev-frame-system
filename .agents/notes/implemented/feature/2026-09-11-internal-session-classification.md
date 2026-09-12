# Agent Note: The internal-session classification

Status: implemented

English | [中文](2026-09-11-internal-session-classification.zh.md)

## Problem

The Shadow's designated session is host-created through the agent path and records no `cwd`, so it is not a browsable session in any sense the product means: it belongs to the one dedicated surface that opens it. The session browser derives its rows from the Host list alone, and a blank session becomes visible the moment it is selected — so clicking the Shadow surfaced the designated session as an ungrouped "new conversation" row, which the human read as a stray conversation the click had just created.

## Decision

A Session can be classified as belonging to a dedicated surface rather than the browsing list. `ISessions.markInternal(sessionId)` registers the classification and returns its disposer; `ClientSessions` stamps it onto the row as `SessionSummary.internal`, leaving the row in the list store, in `open`, in `refresh`, and in history exactly as before. The classification is client-local: it is not part of the Host list, it does not survive a reload, and it never touches the persisted session. The Workspace browser's `sessionVisible` derivation excludes internal rows from groups, the flat list, and search, so every browsing surface drops the row at once. The Shadow entry registers the designated id on each successful status read and withdraws it on unmount, so the row disappears for the web client that owns the entry, and a redeployed designation moves with it.

## Alternatives considered

**Extend the durable session `origin` classification with a `'shadow'` value.** Rejected: `origin` is a persisted header field, and the host *resumes* the already-persisted designated session rather than recreating it, so the marker could never reach the existing row without rewriting session headers on resume — far too much surface for a presentation fact.

**Reuse the registry-global archive set.** Rejected: archiving is a human verb with durable, user-visible meaning, and the archive set is Host-confirmed; a system classification riding on it would misreport the session as archived and could be undone from the same surface.

**Let the browsing package own the registry and have the Shadow entry inject it.** Rejected: it inverts the dependency (a sidebar card reaching into the browsing package), and every other consumer of the session list would still list the row.

**Have the Host omit the designated session from `session/list`.** Rejected: it would hide the row from every client at once, but `open()` requires a listed session, so it would break the trigger's only correct path — and it would make the sessions domain depend on the Shadow router's designation.

## Consequences

The session browser never grows a row for a session a mounted plugin owns elsewhere, and the Shadow's trigger and the sidebar now agree on what the designated session is. The classification lives exactly as long as the mounted entry: a web client without the Shadow entry package, or any non-web client, still lists the designated session as an ordinary row. Because the fact is client-local, the sessions domain keeps carrying the row — the store still lists every session it is told about, and filtering stays with the consuming surface.

## Testing

`tree.client.spec.ts` pins the internal row out of groups, the flat list, and both search paths, including while it is the current blank selection. `workspace-browser.client.spec.tsx` pins the rendered sidebar carrying no row for it in grouped and flat modes. `sessions-service.client.spec.ts` pins the stamp, its withdrawal, and a classification made before the row lands. `shadow-mount.client.spec.ts` pins the registration on each successful read, its withdrawal on unmount, and no registration at all when the read fails or names no session.

## Related

[The Shadow trigger opens the designated session](2026-09-11-shadow-trigger-opens-designated-session.md) owns the trigger, the create-conflict root cause, and the open-then-refresh path this classification accompanies.
