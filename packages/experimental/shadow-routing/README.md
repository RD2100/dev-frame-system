---
description: "Service Definition for the shadow routing seam (ctx.shadowRouter): the abstract router contract, routing vocabulary, and the shadow/delivery-received event — no provider, tools, or storage."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-routing

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-routing` is the Service Definition of the shadow routing capability seam: it declares the `ctx.shadowRouter` context key, the abstract `ShadowRouter` service contract, and the vocabulary every shadow family member compiles against — the branded request, message, and acceptance-hash ids; the controller-binding, delivery, and request-record types with their provisioning and delivery state machines; the bounded request/receipt shapes; the stable `ShadowRouterError` and its `SHADOW_*` code union; and the `shadow/delivery-received` observe-only event fired when a delivery durably enters `received`. The package has no implementation, no model-facing tool, and no storage: the Service Provider is `@deepseek-ai/dsh-experimental-shadow-router`, and Consumers (the shadow bridge and controller) depend on this package only.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Import the vocabulary from this package in any code that types, consumes, or implements shadow routing, and mount the provider package in compositions that need the router itself.

### Consume the contract without the provider

Tests, host bridges, and Remote owners import the abstract `ShadowRouter` type, the record shapes, and the brand factories from this package instead of the provider, so they never load the implementation:

```ts
import type { ShadowRouter, ShadowDeliveryRecord } from '@deepseek-ai/dsh-experimental-shadow-routing'

function forwardable(delivery: ShadowDeliveryRecord, router: ShadowRouter): boolean {
  const binding = router.findBinding(delivery.workspaceId)
  return binding !== undefined
    && binding.state === 'ready'
    && delivery.state === 'received'
    && delivery.goalId === binding.activeGoalId
}
```

The brand factories validate at the boundary: `ShadowRequestId`, `ShadowMessageId`, and `AcceptanceHash` brand a bounded token and throw `ShadowRouterError` with code `SHADOW_INVALID_REQUEST` on anything else.

### Implement the contract

A Service Provider extends `ShadowRouter`, implements every abstract method, and loads as a plugin — it registers as `ctx.shadowRouter` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior). The provider also owns `static Config` with the defaults and the `ShadowRouterConfig` type, which lives in the provider package because a plugin's config type must live in its own package. The shipped provider is `@deepseek-ai/dsh-experimental-shadow-router`.

### React to deliveries through the event

`shadow/delivery-received` is an observe-only typed event: the provider emits it after a queued delivery's durable target-acceptance write commits, carrying the workspace id and the frozen record snapshot as it entered `received`. It fires on the send path and on recovery convergence that lands a queued row on `received`; a listener mounted after a transition (or after a process restart) reconciles through the provider's read face instead, because the event is never replayed. Listener failures are contained and logged; they never fail the routing operation.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the seam and points at the code that realizes them; the observable behavior is covered in [Use this package](#use-this-package).

### Design concept

The seam exists to keep the shadow family's words in one ownerless place: the abstract class and vocabulary change when the contract changes, while the provider changes when persistence, provisioning, or tooling change. It follows the `dsh-subprocess` / `dsh-shell` Service Definition template — abstract class plus types, no runtime behavior beyond the brand validators and the event dispatch — and owns the event dispatch with per-listener containment so a broken consumer cannot fail a routing operation.

### Source map

| File | Role |
|---|---|
| [`src/service.ts`](src/service.ts) | Abstract `ShadowRouter`, the `ctx.shadowRouter` augmentation, the `shadow/delivery-received` event, and the contained emit helper |
| [`src/types.ts`](src/types.ts) | Vocabulary: records, state machines, and request/receipt shapes |
| [`src/ids.ts`](src/ids.ts) | Branded request, message, and acceptance-hash id factories with their boundary validation |
| [`src/errors.ts`](src/errors.ts) | `ShadowRouterError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry and default export |
| — | No runtime invariant companion is published: the seam owns no state, so no owned relationship can diverge. |

</details>

-----

<a id="model-experience"></a>
## Model Experience

None, as the Service Definition registers no tool, prompt section, or model-visible request content of its own; the provider owns the four project tools and every model-visible effect.

#### KV Cache effect

No direct invalidation; the provider package owns the tool schemas' request-prefix effect, and this package's declarations never enter a model request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits define when the seam is a poor fit or leaves work to its provider and consumers. They are current package constraints, not a backlog.

- **No provider ships here** — a composition that loads only this package has no `ctx.shadowRouter`; the Service Provider (`@deepseek-ai/dsh-experimental-shadow-router`) owns persistence, provisioning, and the tool whitelist.
- **The event is observe-only and never replayed** — a consumer mounted after a transition, or after a restart, converges through the provider's read face; the seam adds no delivery event history.
- **Private experimental contract** — the vocabulary can change without a support promise, and nothing outside the shadow family should import it.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
