# Agent Note: Web session-id badge

Status: implemented
Archived: 2026-09-04

English | [中文](2026-09-04-web-session-id-badge.zh.md)

## Problem

`SessionId` is complete through the stack — branded in [`dsh-session`](../../../../packages/core/session/README.md), persisted in `SessionHeader`, carried by every Session Controller, SDK, and ACP wire frame, and used as the browser's own session-scope key — but the Web GUI never showed it to the human. The header rendered display titles only, so a user reporting a bug, correlating a JSONL log, or addressing a session over the SDK had no in-product way to learn which session they were looking at.

## Decision

[`@deepseek-ai/dsh-client-ui-session-id`](../../../../packages/client/ui-session-id/README.md) registers one `session-id-badge` entry (order `-10`, ahead of the download action) in the `conversation.session.header.utilities` list that [`dsh-client-ui-conversation`](../../../../packages/client/ui-conversation/README.md) already declares. The chip renders the standard session-scope `sessionId` prop verbatim in monospace, truncates long ids visually, and copies the full value through the shared `writeClipboard` helper with a one-second success state. No session id — the blank-session Hero — renders nothing.

No identity is minted, transformed, or duplicated anywhere in this change. The id the badge shows is the same value the API created, the header persisted, and the wire delivered; the package adds no RPC, no store, and no session-log event, so the model-visible surface is unchanged by construction.

The one-feature-package shape follows the sibling header actions ([`ui-jobs`](../../../../packages/client/ui-jobs/README.md), the session-log download entry): own locale namespace (`session-id`, zh source of truth), inert node half, and a `dsh.client` manifest row in `dsh-web-app`.

## Alternatives considered

**Show the id in each sidebar session row.** The list is a title tree; ids on every row are noise at tree density and still vanish once the user enters the conversation. Copying from the header of the open session covers the actual need.

**Occupy the `header.lineage` single seat or extend `ConversationSessionHeader` itself.** Both couple conversation-core rendering to one presentation feature and would force `ui-conversation` to grow a locale namespace it does not own. The utilities list exists for exactly this kind of right-aligned per-session info.

**A settings-page field.** Discoverable only by someone who already knows where to look; the value belongs at the surface where the session is being looked at.

## Testing

The browser-plugin spec registers against the real `SlotRegistry` (fiber teardown proves HMR-safe removal) and pins the dictionaries; the component spec pins verbatim id rendering, full-value copy, the one-second feedback window, the no-op on a refused write, and the null render without an id. `verify-client-ui-i18n` owns the locale-routing rule.

## Consequences

**The header grows a permanent element.** Sessions that never need the id still render its chip; the truncation and quiet styling are the accepted cost. If it reads as noise, hiding behind an existing details affordance is presentational only.

**Copy is best-effort.** A host that refuses both the async Clipboard API and `execCommand('copy')` leaves the id selectable but does not copy, and the UI must not claim success — the feedback state exists only after an accepted write.

**Fork and resume identities stay self-evident.** A forked child shows its own id, and a resumed session shows the same id it was persisted under, because the badge reads the live scope rather than cached history.
