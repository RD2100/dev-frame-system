# Agent Note: Web session-id row menu

Status: implemented

English | [中文](2026-09-05-web-session-id-row-menu.zh.md)

## Problem

The 2026-09-04 header badge ([archived](../../archived/feature/2026-09-04-web-session-id-badge.md)) made the `SessionId` visible, but as a permanently rendered chip in the session header's top-right utilities. The presentation requirement changed: the id must not occupy a persistent top-right slot; it belongs behind each session row's existing actions menu in the left session list, revealed on demand with an explicit copy flow.

## Decision

[`dsh-client-ui-workspace`](../../../../packages/client/ui-workspace/README.md) owns the presentation. `SessionNodeItem` gains a fourth actions-menu entry, `Session ID`, after rename/fork/archive. Selecting it opens `SessionIdDialog` (`src/client/rows/SessionIdDialog.tsx`), a `Modal` that renders the row's `SessionId` verbatim — no truncation, `word-break` plus `user-select` so every character stays visible and selectable. Both the id text (rendered as a button) and the explicit copy button write the full value through the shared `writeClipboard` helper. A `role="status"` line reports the outcome: the localized copied message on success, an explicit failure message on a refused write, and never a success claim when the host rejects the write. The copy button carries `autoFocus`, and the dialog closes through its own chrome (Escape, mask, close button).

The dialog state is row-local (`showId` per `SessionNodeItem`), so each row opens its own dialog bound to its own id; the value is read from the live session scope, not cached history, so refresh, session switching, restart, and cold restore all show the id the session was persisted under.

`@deepseek-ai/dsh-client-ui-session-id` is removed outright: the `cordis.patch.yml` plugin row, the `dsh-web-app` dependency, the `tsconfig.base.json` paths entry, the `tsconfig.client.json` reference, the module-graph catalogs, and the lockfile all drop the package, and its directory is deleted. No identity is minted, transformed, or duplicated anywhere: the dialog renders the same branded `SessionId` the API created and the JSONL `SessionHeader` persisted. No RPC, no store, no session-log event, so the model-visible surface is unchanged by construction.

### Predecessor: 2026-09-04 header badge (archived)

The [archived badge note](../../archived/feature/2026-09-04-web-session-id-badge.md) records the motivation this decision builds on: `SessionId` was complete through the stack — branded in `dsh-session`, persisted in `SessionHeader`, carried by every Session Controller, SDK, and ACP wire frame — but the GUI first showed it nowhere, and the badge fixed that with a `conversation.session.header.utilities` chip. The badge's copy semantics (full value, best-effort write, no success claim without an accepted write) carry over unchanged into the dialog. What no longer holds is the placement decision: a permanent chip conflicts with the requirement that the id not occupy persistent top-right space.

Alternatives to full removal were considered and declined: keeping both surfaces renders one value twice and keeps the rejected persistent chip; moving the chip into the row hover card is hover-only discovery with no keyboard path; a settings field is discoverable only by someone who already knows where to look. The capability given up is zero-interaction visibility of the id; reintroduce a persistent chip only if a requirement again demands always-visible ids — the `conversation.session.header.utilities` seat remains available.

## Alternatives considered

**A session-list-wide dialog owned by the browser root, like rename.** Rename needs a text draft that survives list re-renders, so it lives at the browser root. The id dialog is stateless — its only input is the row's id — so row-local state avoids threading a callback through both list bodies without losing anything.

**Rendering the id into the hover card.** One hover dwell for a copy action, no keyboard path to the value, and the card's content set is fixed; the actions menu is the row's existing keyboard-reachable verb surface.

**Reusing the removed package with a different slot registration.** The package existed to render one chip in one header slot; a menu entry inside another package's row component crosses that seam, and the slot machinery would carry a one-component package. `ui-workspace` already owns row menus and locale keys for row verbs.

## Testing

`tests/session-id-dialog.client.spec.tsx` pins: the menu entry appears without opening the session; the dialog shows the full id verbatim; copy works from both the id text and the explicit button; a refused write reports the failure message and never the success message; two rows show independent ids regardless of selection; and the new dictionary keys exist in both locales. The badge package's specs left with its directory. Web replay snapshots no longer contain the chip. `verify-client-ui-i18n` owns the locale-routing rule for the new keys.

## Consequences

**Discovering the id now takes two activations** (row menu, then the dialog) instead of zero; that is the accepted cost of removing the persistent chip. A session-list reorder that unmounts a row also closes its open dialog — the same lifetime the row menu already has.

**Copy stays best-effort.** A host that refuses both the async Clipboard API and `execCommand('copy')` leaves the id selectable but not copied, and the status line states the failure explicitly instead of claiming success.

## Related

The copy interaction described here is superseded by [Direct Session ID copying from row actions](2026-09-05-web-session-id-direct-copy.md). The row-menu placement and Session ID ownership remain current.
