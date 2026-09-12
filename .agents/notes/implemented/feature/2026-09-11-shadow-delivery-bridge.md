# Agent Note: The shadow delivery bridge forwards received work into live controllers

Status: implemented

English | [中文](2026-09-11-shadow-delivery-bridge.zh.md)

## Problem

The Shadow router persists cross-root deliveries as durable rows and receipts, but its own contract stops at `received`: a bare mount leaves every controller's input invisible to models, because forwarding received input into the controller's session log is host work ([the router decision](../architecture/2026-09-05-shadow-router-project-tools-binding-store.md) names that gap). Without a forwarder, the closed loop the [detailed design promises](../../../../docs/detailDesign-part2.md#delivery) — a `work` message whose Goal and acceptance binding match an authorized open run schedules a follow-up on the bound controller — never runs, and delivered input piles up as `received` rows no model ever sees.

## Decision

`packages/experimental/shadow-bridge` is a host-side function plugin that forwards from the router's observe-only `shadow/delivery-received` event — the routing Service Definition's single `queued` → `received` transition signal ([the routing seam decision](../architecture/2026-09-12-shadow-routing-seam.md)) — and re-reads the router's public face (`listDeliveries`/`findBinding`) per forwarding unit. A mount-time and a loader-settled full reconciliation poll plus a low-frequency safety-net timer (`intervalMs`) cover deliveries that entered `received` outside the listener's window. Every unit passes the design's own gate: the binding is not `stopping` or `stopped`, the binding still records an authorized open run, and the delivery's Goal and acceptance association equal that run's — so a Goal switch after receipt keeps the previous Goal's message out of the controller's current Goal. All units, event-fed or polled, run on one serialized chain outside any inherited agent-initiator boundary. Forwarding is one durable follow-up (`agent.followup`) on the live agent the binding's controller session resolves to, carrying a deterministic header (source delivery id plus workspace) and the verbatim delivery text bounded by `followupMaxChars`; the content enters the controller's session log as a `user/message` event through the inbox, keeping the model-visible-implies-logged invariant. The messageId is then recorded in the package's own `shadow_bridge` storage domain, rebuilt into the forwarder's in-memory set at start, so a restart re-forwards nothing. v1 resolves live agents only and never settles `completed` — completion stays a controller-side fact, and provisioning live controller agents stays with the host composition ([package README](../../../../packages/experimental/shadow-bridge/README.md)).

## Alternatives considered

**Forward from the event alone and drop the polls.** Rejected: a listener mounted after a transition — a boot whose bridge mounts after the router recovered queued rows, or a restart whose listener was not yet registered — never sees that transition again; the reconciliation polls and the safety net are what make exactly-once forwarding survive mount order and restarts. The safety-net cadence stays a required config field with no default because the right rhythm is deployment-specific: the event carries live transitions, so the cadence only prices how long missed work may wait.

**Mark the delivery before sending, for at-most-once.** Rejected: a crash between the marker write and the follow-up would leave the delivery marked, unforwarded, and silently lost; send-then-mark accepts one visible duplicate (same header, same messageId) in that crash window instead, matching the design's rule that deduplication covers durable inbox input, never silence.

**Let the bridge create or resume missing controller agents.** Rejected for v1: agent lifecycle is host-owned, and neither registry entry can adopt a controller session the router already created and holds in the session store, so cold recovery would need new lifecycle machinery beyond this round; a delivery whose controller is not live simply waits for a later unit.

**Settle each delivery `completed` after forwarding.** Rejected: `completed` is the controller-side durable fact of finished work, and a forwarding receipt would claim work ran that has not.

## Consequences

Delivered `work` finally reaches a model: the bound controller's turns drive on Shadow input, and the loop the router left open closes at the follow-up seam. Live transitions forward on the event. The costs: work the event path misses waits for a reconciliation pass or the safety net; the crash window above can duplicate one delivery; `note` deliveries wait for a later round; and every deployment must bring its controller agents live itself, because the bridge never does.
