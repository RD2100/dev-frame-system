# Agent Note: Goal-round-driver teardown discards the not-yet-admitted queued round

Status: proposed

English | [中文](2026-09-05-goal-round-driver-teardown-queued-wake-window.zh.md)

## Problem

A goal-round reservation can sit in the agent inbox while `agent.status` still reports `idle`. `Agent.followup()` inserts the message and latches its wake whenever the agent cannot start a turn — currently a host-initiated `runMaintenance()` job. The queued round stays pending until the maintenance job finishes, and only then does the latched wake replay it into a turn.

The driver's teardown issues `cancel({ kind: 'parent' })` only when the agent reports `running`. Disposal that observes the maintenance window takes neither stop branch: the reservation stays queued, the driver's `agent/pre-step` validity fence is removed with its listeners, and the latched wake replays after the plugin unloads — a model request for the goal round runs with no reservation checks at all. The durable goal stays disarmed, but the round consumes its round number in the replay fold and reaches the model unfenced.

## Proposal

In the driver's teardown, when a reservation exists and the agent is not running, remove exactly the reserved round's message from the inbox with `Agent.inbox.remove(attempt.messageId)` instead of leaving it queued. Only the round's own message is removed, so unrelated pending input keeps its queue position and the latched wake replays into it alone; a wake whose message is gone opens an empty turn boundary with no model call. A failed removal (the discard appends a durable splice) is logged and does not fail the whole teardown, mirroring the existing `disarm()` containment.

The running branch keeps its current shape: cancel with the `parent` cause and await `whenIdle()`.

## Alternatives considered

**Wait for `whenIdle()` in the idle branch as well.** Rejected: the idle reading can hold while a host-owned maintenance job runs, and awaiting it would extend plugin unload by that job's duration. The discarded round leaves no driver-owned work behind: the wake replays into the remaining input or opens an empty boundary that spends no model call.

**Cancel without `keepInbox` regardless of phase.** Rejected: `cancel()` clears the whole inbox, discarding unrelated human or plugin input that happens to be pending; the defect only concerns the driver's own reservation.

**Hold disposal until the latched wake replays, then cancel.** Rejected: it keeps the plugin's listeners installed across an unbounded maintenance job, and the round would still be cancelled rather than durably withdrawn; removing the reservation releases the wake immediately.

**Treat the window as unreachable and keep the current code.** Rejected: maintenance is a host-owned phase the driver does not control, and the pre-step fence is gone exactly when the replayed round runs, so the failure is silent.

## Acceptance criteria

- Disposal while a reservation is queued behind a latched wake produces a durable canceled inbox splice, no model request, no admitted goal-round `user/message`, and leaves the goal active and disarmed, observed after the agent reaches quiescence.
- The same scenario with unrelated non-waking pending input (an `inject()` to next-step) still sends only that input to the model; the goal-round prompt never reaches a request and the input is not discarded by teardown.
- The existing teardown tests (running round cancelled and awaited; queued round observed) keep passing.

## Risks

- The discard appends a durable inbox splice during teardown; a persistence failure there is contained to a warning and leaves the round queued, which is the pre-fix behavior for that failure mode.
- A reservation already claimed or admitted is unaffected: `remove()` finds nothing pending and returns false, and the running branch continues to cancel and await.
- Queued input the host deliberately kept through a `keepInbox` cancellation on an idle agent can still run after unload when the host later wakes the agent; withdrawing driver reservations cannot cover input the host chose to preserve, and no driver fence exists to recheck it.
