# Agent Note: The Expert center exposes a usable mounted-expert catalog

Status: implemented

English | [中文](2026-09-16-expert-center-ui.zh.md)

## Problem

The sidebar entry exposed only a compact status view, so users could not browse the experts that the Host had actually mounted or inspect an expert's assigned phases and tools. The reference interaction also reserves top-level Skills and Connectors destinations, while this package has no Remote source for either domain.

## Decision

The Web entry renders an Expert center inside the existing modal lifecycle. The Experts tab flattens `ExpertTeamView.experts` from the Host snapshot into cards, searches name, role, id, and team metadata, filters by mounted team, and sorts by the Host order or expert name. Selecting a card opens its team, mode, assigned phases, human-review gates, and declared tools; the catalog keeps the full available width until a detail view is selected. The center also renders the latest six current-process run records from the same snapshot. Skills and Connectors are visible tabs with explicit not-connected-yet messaging until a Host data source exists. The center remains orchestration-read-only: card and detail actions hand off through the separate new-session selection flow recorded in [the summon handoff note](2026-09-16-expert-center-summon.md).

## Alternatives considered

**Invent skill or connector records in the client.** Rejected: an empty or guessed inventory would make the catalog disagree with the Host and hide the missing capability source.

**Call orchestration mutations from the catalog.** Rejected: this package consumes a read-only Remote view; orchestration and gate ownership remain in the Host/model boundary.

**Keep the compact panel and add more status text.** Rejected: status text does not provide the browse, search, filter, and detail affordances needed to discover a mounted expert.

## Consequences

The sidebar entry now provides the catalog navigation and discovery flow without a second source of truth. The visible placeholder tabs make the reference layout extensible while stating the current integration boundary. The catalog remains orchestration-read-only, while summon actions can stage a selected expert and prompt in a normal blank conversation; its run history remains limited to the current Host process. Future skill or connector Remote views can populate the existing tab slots.

## Testing

The focused Expert center test covers opening the mounted catalog, search, team filtering, name sorting, expert details, summon actions, unavailable capability tabs, Remote failure, and close behavior. The selection tests cover asynchronous blank-session handoff and chip removal. TypeScript compilation, client UI i18n verification, the package bundle, the Web build, and the live DevFrame browser flow were also run; the live snapshot displayed two mounted teams, fifteen experts, a staged prompt, and the selected-expert chip.

## Related

[The client package contract](../../../../packages/experimental/client-ui-expert-team/README.md) owns the user-facing behavior; [the summon handoff note](2026-09-16-expert-center-summon.md) owns the new-session interaction; [the M4 expert-team note](2026-09-15-expert-team-m4.md) owns the Host snapshot and run-history foundation.
