---
description: "Host-side function plugin that turns the shadow router's forwardable received work deliveries into the bound controller sessions' model-visible follow-ups, exactly once per delivery across restarts."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-bridge

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-bridge` closes the delivery loop of the pluginized Shadow hierarchy. It polls `ctx.shadowRouter`'s public read face and turns every `received` `work` delivery that still matches its binding's authorized open run into one durable follow-up on the live agent of the bound controller session, so delivered input finally reaches a model and enters the controller's session log as a `user/message` event. Each forwarded messageId is recorded in the package's own `shadow_bridge` storage domain and restored at start, so a restart re-forwards nothing. Forwarding never settles a delivery: `completed` remains a controller-side fact, and the router's rows remain the durable record of what was sent, received, and completed. The package registers no tools, no prompt sections, and no session events, so the TypeScript and Python SDK projections are untouched.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the plugin in a composition that already mounts the shadow router, the storage stack, and the agent registry; it hard-injects `ctx.agents` and `ctx.storageDomain`, and fails its load when either is absent. The router is read through `ctx.get('shadowRouter')` at each poll, so either mount order works, and a boot whose router mounts later simply polls nothing until it does.

```yaml
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
    shadowSessionId: session-shadow
- name: '@deepseek-ai/dsh-experimental-shadow-bridge'
  config:
    intervalMs: 2000
    followupMaxChars: 8000
```

### Config

| Field | Default | Meaning |
|---|---|---|
| `intervalMs` | Required | Positive safe integer: milliseconds between one delivery poll and the next. |
| `followupMaxChars` | Required | Positive safe integer: upper bound in characters on one forwarded follow-up text, header included. |

Both fields are required with no defaults: a row missing either fails the load.

### What reaches the controller

A forwardable delivery becomes one follow-up on the controller's live agent: a deterministic header naming the Shadow delivery and its workspace, then the verbatim delivery text, truncated from the tail when the total exceeds `followupMaxChars`. The follow-up enters the controller's inbox and becomes a `user/message` session event, so the model sees it on its next turn and the log records it. A delivery whose controller has no live agent is left for a later poll — the bridge never creates, resumes, or disposes agents. A delivery is forwardable only while its binding is not `stopping` or `stopped`, the binding still records an authorized open run, and the delivery's Goal and acceptance association equal that run's, so a Goal switch after receipt keeps the previous Goal's message out of the controller's current Goal. Forwarding never writes `completed`; a forwarded row stays `received` until the controller side settles it.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **The router's public read face is the only seam.** The poll reads `listDeliveries()` and `findBinding()` — no events, no writes into the router, no new router-side contract. Mount order and restart tolerance come from re-resolving the router per poll.
- **The detailed design's delivery gate, enforced again at forwarding.** The router already validates Goal ownership at admission; the bridge re-checks the current run before every forward, which is what keeps a delivery owned by a previous Goal out of a controller whose open run has since moved on.
- **Send, then mark.** The follow-up enters the controller's inbox first; only then is the marker row written. A crash between the two can forward one delivery twice after restart — a visible duplicate carrying the identical header — while the reverse order could silently lose input. Every follow-up or marker failure is contained per delivery and retried on a later poll.
- **One marker table, rebuilt at start.** The `shadow_bridge` domain's `forwarded` table is the only durable bridge state; the in-memory forwarded set is a write-through projection of it, restored at construction.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | The function-plugin face: config, injections, domain open, and the poll loop wiring |
| [`src/forwarder.ts`](src/forwarder.ts) | The delivery gate, live-agent resolution, follow-up send, and marker writes |
| [`src/text.ts`](src/text.ts) | The deterministic header and the bounded follow-up text |
| [`src/loop.ts`](src/loop.ts) | The self-rescheduling poll timer with contained failures and quiescing disposal |
| [`src/spec.ts`](src/spec.ts) | The `shadow_bridge` domain spec and the forwarded-record schema |

### Invariant

No runtime invariant companion is published: the forwarded set is a write-through projection of the one domain table and is rebuilt from it at start, and the router's delivery index is its own write-through projection, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Forwarded deliveries on controller sessions

#### What the model sees

The controller session receives one identified user-role message per forwarded delivery, sourced as `{ kind: 'plugin', plugin: 'shadow-bridge', form: 'relay' }` and carrying a bracketed header that names the Shadow delivery's messageId and workspace, followed by the verbatim delivery text. The message becomes an ordinary turn; the model cannot distinguish the transport beyond the header's own words.

#### Token effect

Each forwarded delivery adds one bounded user turn — header plus text, at most `followupMaxChars` characters — and its model response, both retained for the rest of the controller session. Polls that forward nothing add no requests and no tokens.

#### KV Cache effect

Append-only: each forwarded delivery extends the controller session's request prefix without invalidating the prefix before it, and the header is deterministic for a given delivery. The bridge adds no tool schemas and no prompt sections, so it never reshapes a reusable prefix by itself; provider cache availability and eviction remain outside this package's contract.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits define when the bridge is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **Live controllers only — no cold recovery** — the bridge resolves the binding's controller session through the live-agent registry and never creates, resumes, or adopts an agent; a controller its host never makes live never receives its deliveries, which stay `received` and visible in the router.
- **Forwarding does not settle deliveries** — `completed` is a controller-side durable fact; this package never calls the router's completion seam, so a forwarded delivery stays `received` until the host or a later round settles it through `completeDelivery`.
- **A crash between follow-up and marker can forward twice** — the marker is recorded after the follow-up enters the inbox, so an interrupted process re-forwards one delivery at the next start; the duplicate carries the identical header and messageId, and this order is chosen over one that could silently lose input.
- **`note` deliveries are not forwarded** — only `work` deliveries schedule follow-ups in this round; notes stay `received`.
- **Delivery latency is bounded by the poll** — input reaches the controller up to `intervalMs` late, and one poll forwards serially in the router's stable delivery order.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The next round's natural extensions: settling `completed` from a controller-side goal receipt, forwarding `note` deliveries as quiet input, and a host-side provisioner that brings controller agents live on their reserved sessions — the bridge deliberately owns none of these.

</details>
