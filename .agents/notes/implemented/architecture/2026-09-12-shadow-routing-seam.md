# Agent Note: The shadow routing contract is its own Service Definition (`dsh-experimental-shadow-routing`)

Status: implemented

English | [中文](2026-09-12-shadow-routing-seam.zh.md)

## Problem

The shadow family's words lived inside its implementation package. `dsh-experimental-shadow-router` bundled four concerns that change for different reasons: the routing vocabulary (branded ids, binding/delivery records, the `SHADOW_*` error codes, the config type), the concrete service (durable binding store, two-write delivery, replay ledger), the model-facing tool whitelist, and the storage domain. Every family member — the bridge that forwards deliveries and the controller that owns the host Remote — imported the provider package to name a `ShadowDeliveryRecord` or type `ctx.shadowRouter`, so the consumers the architecture calls Consumers were compiled against a Service Provider. The delivery handoff had no seam either: the bridge learned about a `received` delivery only by polling the router's index, so recovery that landed a queued row on `received` after a restart was invisible until the next poll, and any future consumer would inherit the same cadence coupling.

## Decision

A new Service Definition package owns the shadow routing seam; the provider implements it; consumers stop needing the provider:

- **`@deepseek-ai/dsh-experimental-shadow-routing` (Service Definition)** — the abstract `ShadowRouter` class (every public method the concrete service had, as abstract members), the `ctx.shadowRouter` Context augmentation, and the full vocabulary: the `ShadowRequestId`/`ShadowMessageId`/`AcceptanceHash` brand factories with their boundary validation, the binding/delivery/request record types with their state machines, the request/receipt shapes, and `ShadowRouterError` with its `SHADOW_*` code union (migrated wholesale — the brand factories throw it, so a base-class split under the provider would have inverted the dependency). It also declares the typed `shadow/delivery-received` event and owns the contained `emitDeliveryReceived` dispatch, mirroring the [workflow seam's](../../../../packages/workflow/workflow/README.md) observe-only event pattern. No tools, no storage, no config: the `ShadowRouterConfig` type stays with the provider because the config catalog gate requires a plugin's config type to live in its own package.
- **`dsh-experimental-shadow-router` (Service Provider)** — the concrete `ShadowRouter` extends the seam class; it keeps the storage domain and schemas, provisioning side effects, the replay ledger, and the four project tools. `markDeliveryReceived` — the single internal helper every queued→received transition funnels through, on the send path and in `recoverDeliveries` convergence — emits the event once per real transition, after the durable write commits; a cold-restored row already `received` on disk is a reload, not a transition, and emits nothing. The provider re-exports the migrated vocabulary so the composition layer and profile tests keep one import root; the family's src imports name the definition package directly.
- **Consumers** — shadow-bridge, shadow-controller, and the client Shadow entry compile against the definition package: their src imports name the seam, and the provider is imported only by role — the Loader plugin values in tests and the composition rows. The bridge is event-driven in the same round: it forwards from `shadow/delivery-received`, with mount-time and loader-settled reconciliation polls plus a safety-net timer covering anything the event window missed.

## Alternatives considered

**Contracts-only split (types and ids without the abstract class).** Rejected: the ctx key and the method contract are the seam's load-bearing part — leaving the class in the provider would keep `ctx.shadowRouter` typed by the implementation package, and the next provider swap (or a second provider) would re-couple every consumer again.

**Keep the bridge polling and only add the event.** Rejected: an event with no forwarding listener would ship a dead channel while recovery-landed `received` rows stayed invisible until the next poll; the bridge moved to the event as its primary channel in the same round, with the reconciliation polls and the safety-net timer bounding anything the event window missed.

**Keep the vocabulary in the router and have consumers import it there.** Rejected: it is the status quo the round exists to fix — the error-code union and brand factories live with the words they validate, and a vocabulary provider cannot depend on a vocabulary consumer.

## Consequences

Bought: one owner for the shadow words; bridge/controller/entry src imports name the seam package directly; the delivery handoff is observable at the transition (`shadow/delivery-received`) instead of at the next poll; and the abstract class documents the semantics every implementation owes (operation-chain serialization, two-write delivery, post-commit emit, no reload emissions). The provider keeps its public face — same default export, same named exports, same `ctx` key — so the Loader, the module maps, and the composition rows are unchanged.

Cost: one more package; the router's index re-exports the definitions package, so the same types are nameable from two packages (the definition package is the owner; the re-export serves the composition layer and the profile tests); `ShadowRouter` now names the abstract seam and the concrete subclass that implements it (the subclass keeps the provider's name and default export, so the Loader and module maps are unchanged); and the emitted event must stay observe-only — a listener that mutated router state would break the post-commit, no-side-effect contract the containment helper documents.
