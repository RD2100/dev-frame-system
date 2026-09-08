# Agent Note: Dispatch settlement notices wake the parent

Status: implemented

English | [中文](2026-09-08-dispatch-settlement-wake.zh.md)

## Problem

`agent_dispatch` reusing an existing child never delivered new instructions, and a dispatched child that finished a real turn never told its parent: a lead controller with no other pending event stayed asleep after its workers delivered, so multi-task chains stalled at review. Reusing a child also silently re-dispatched nothing, leaving callers unable to continue a settled child's work.

## Decision

The dispatch service mounts a settlement watch on every live dispatched child, including cold-recovered ones. When the child's own log records a terminal `turn/end` — completed, error, or aborted: the watch deliberately does not filter on the reason, because a failure-ended turn must still wake the chain — and that record flushes durably, the watch delivers a typed `dispatch-settled` notice to the parent as the parent's next ordinary turn (`followup()`): an idle parent opens a turn immediately, a busy parent claims the notice right after its in-flight turn ends. Steering is not used — a steered message targets a step boundary the turn may never reach and strands the notice.

Deduplication is layered. A per-live-child claim set, taken synchronously when the settlement is observed, stops concurrent watches from double-delivering; it is scoped to the exact Agent instance, so an independent context that reuses a session id holds its own claims. The parent's durable facts — the logged notice, or the queued one still parked in its inbox — stop re-delivery across remounts. A withheld delivery releases its claim and retries on the next idle edge.

A `followup: true` dispatch argument with a prompt now delivers explicit continuation instructions to the task's existing child and refuses a blind followup; a followup without a prompt also refuses instead of silently degrading; a fresh dispatch never queues a followup, and reuse without the field behaves exactly as before. Recovery without a prompt stays side-effect free.

## Alternatives considered

- Parent-side polling of child logs couples the parent to its children's persistence and multiplies log reads per turn boundary.
- One in-process string key such as `childId|turnIdentity` leaks across hosts: independent contexts reuse session ids and log sequences, so one context's claim would swallow another's notice.
- Marking the child as notified in service memory loses the account on restart; the parent's durable ledger is the only restart-safe authority.

## Consequences

Parents wake on real child settlements without any scripted re-prompt, and callers can continue a settled child explicitly. Every settlement opens one parent turn, so request budgets must cover wake-driven requests. Notice delivery failure is logged and dropped: the child is never retained to retry a notice, because the child's own log remains the durable record either way.
