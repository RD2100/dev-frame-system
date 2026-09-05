# Agent Note: Event-gated goal round continuation

Status: implemented

English | [中文](2026-09-05-event-gated-goal-round-continuation.zh.md)

## Problem

The same-session goal-round driver scheduled its next round unconditionally: every idle transition of an agent holding an active, armed goal with remaining capacity reserved and queued one more `<goal_round>` prompt. In orchestration sessions the model ends a round after delegating work to background subagents, with nothing else pending; the driver immediately burned the next round, the model could only answer that it was waiting for events, and the cycle repeated — one full model request per idle with zero progress until a settlement happened to land. The waste scaled with context size and delegation depth.

## Decision

The driver now gates each reservation on an event budget, `eventPending`, tracked per agent lifecycle inside the driver state (`packages/goal/goal-round-driver/src/index.ts`). Three sources grant the budget, one point consumes it, and the reservation path checks it:

- A non-goal message inserted into the agent's `next-turn` inbox queue grants the budget (pending user input, plugin injections, subagent settlement notices, scheduled deliveries — including quiet ones that do not wake the agent).
- A `goal/changed` edge whose current view is active and armed grants the budget, preserving the existing create/edit/resume behavior of rounding at the next idle.
- An `agent/status` idle edge that did not just settle an admitted goal round grants the budget, covering wakes that open a turn without an inbox message (background job completions, steered turns).
- Admitting a reserved round (the round's goal-sourced `user/message`) consumes the budget.
- The reservation path in `drive()` returns before rendering a prompt when no budget is pending. The check sits after the round-cap block, so a cap-exhausted goal still records its `round-limit` blocker immediately, independent of events.

Holding costs no durable state: the goal stays active and armed, and the next event re-enters through the existing wake → turn → idle-edge → `requestDrive` chain. All event sources observed in the repository satisfy the grant contract (every settlement, completion wake, or scheduled delivery either inserts an inbox message or opens a turn).

## Alternatives considered

- **Pause/resume the durable goal phase while waiting.** Rejected: pausing writes a `paused` phase into the session log and disarms activation, and automatic re-arming on events would break the documented boundary that the driver never revives a goal on its own — activation would flap in the UI and the log for pure scheduling reasons.
- **Disarm and re-arm the process-local activation per idle.** Rejected for the same activation-semantics reason: `armed` currently means a human- or tool-authorized continuation edge that persists until a lifecycle event, and per-idle flapping would erode that meaning while adding churn to every observer of `goal/changed`-adjacent state.
- **Query live background work (running subagents, jobs, timers) at the reservation point.** Rejected for this slice: it needs new cross-package service seams (subagent continuation manager, `dsh-tool-jobs`, `dsh-schedule`) and still misses "the model wants its own next round"; the event budget needs no new seams and subsumes the same cases, because every one of those surfaces delivers its outcome as an event.

## Consequences

The waste the gate targets is gone: a settled round with nothing pending queues nothing, and multi-round continuation now requires an event between rounds. The trade is deliberate: a goal whose model keeps ending rounds with no pending event makes no progress until an input, settlement, or wake arrives — models are expected to keep working within a round, delegate to background work whose settlements are events, schedule a wake, or complete, pause, or block the goal (README Known Limitations documents this). The gate trusts the delivery contract above; a future event source that neither inserts a message nor opens a turn would stall until the next event. Goal state-machine invariants are untouched: `roundsStarted` still advances only on admitted goal rounds, blocker codes and the blocked threshold stay event-independent, and the race fences, durability checkpoints, and fail-closed teardown are unchanged.

## Related

The driver's original race and lifecycle rationale: [same-session goal round driver](2026-07-19-same-session-goal-round-driver.md).
