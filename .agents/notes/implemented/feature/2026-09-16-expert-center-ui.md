# Agent Note: The capability center exposes a usable mounted-expert catalog

Status: implemented

English | [中文](2026-09-16-expert-center-ui.zh.md)

## Problem

The sidebar entry exposed only a compact status view, so users could not browse the experts that the Host had actually mounted or inspect an expert's assigned phases and tools.

## Decision

The Web entry renders a Capability center inside the existing modal lifecycle. Its Experts tab flattens `ExpertTeamView.experts` from the Host snapshot into cards, searches name, role, id, and team metadata, filters by mounted team, and sorts by the Host order or expert name. Selecting a card opens its team, mode, assigned phases, human-review gates, and declared tools; the catalog keeps the full available width until a detail view is selected. The center also renders the latest six current-process run records from the same snapshot. Skills, Connectors, and Library pages are contributed by their owning UI packages through the keyed root slot described in [the capability-center note](2026-09-25-capability-center.md). The center remains orchestration-read-only: card and detail actions hand off through the separate new-session selection flow recorded in [the summon handoff note](2026-09-16-expert-center-summon.md).

## Alternatives considered

**Invent skill or connector records in the client.** Rejected: an empty or guessed inventory would make the catalog disagree with the Host and hide the missing capability source.

**Call orchestration mutations from the catalog.** Rejected: this package consumes a read-only Remote view; orchestration and gate ownership remain in the Host/model boundary.

**Keep the compact panel and add more status text.** Rejected: status text does not provide the browse, search, filter, and detail affordances needed to discover a mounted expert.

## Consequences

The sidebar entry now provides catalog navigation and discovery within the shared Capability center without a second source of truth. The catalog remains orchestration-read-only, while summon actions can stage a selected expert and prompt in a normal blank conversation; its run history remains limited to the current Host process. The owning packages provide the other capability pages independently.

## Testing

The focused Capability center tests cover the mounted catalog, search, team filtering, name sorting, expert details, summon actions, capability-tab dispatch and fallback, Remote failure, close behavior, and keyboard tab navigation. The selection tests cover asynchronous blank-session handoff and chip removal. Package and bundle evidence is recorded with the current implementation in [the capability-center note](2026-09-25-capability-center.md).

## Related

[The client package contract](../../../../packages/experimental/client-ui-expert-team/README.md) owns the user-facing behavior; [the capability-center note](2026-09-25-capability-center.md) owns the four-tab composition; [the summon handoff note](2026-09-16-expert-center-summon.md) owns the new-session interaction; [the M4 expert-team note](2026-09-15-expert-team-m4.md) owns the Host snapshot and run-history foundation.
