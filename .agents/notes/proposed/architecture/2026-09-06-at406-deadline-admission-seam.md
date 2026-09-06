# Agent Note: Deadline-bounded admission for agent-reliability

Status: proposed

English | [中文](2026-09-06-at406-deadline-admission-seam.zh.md)

## Problem

AT4 delivery registered GAP AT4-06: a short deadline's expiry must close admission and cancel bounded work, but the agent-reliability src had no deadline implementation seam. The only deadline in the tree was the DevFrame stop's internal grace bound, which is not wired to admission, and the anchor-matrix likewise noted "no cases, assigned to P06". A dispatch generation could therefore run unbounded: the pre-step checked only closed admission and identity, so a window that was supposed to end at an instant kept admitting work forever.

## Proposal

`openAdmission` gains an optional second parameter, the `AdmissionCutoff` request `{ deadline }` — an epoch-millisecond instant. Opening replaces the whole generation, identity AND cutoff; passing no cutoff clears a previous deadline. A non-finite deadline fails loud at open with `AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID` before anything is mutated, so the current generation survives a rejected open untouched. A generation whose deadline is already past opens fine; its first pre-step call reports the dead window.

`assertAdmitted` checks, in order: closed admission (`AGENT_RELIABILITY_ADMISSION_CLOSED`), then the deadline — when `Date.now() >= deadline` it rejects with `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` ("admission deadline has passed; dispatch rejected") — then identity (`AGENT_RELIABILITY_IDENTITY_MISMATCH`). The deadline instant itself is inclusive. The order is deliberate: a passed deadline is a statement about the window, not the identity, so it precedes the identity check and the three rejections stay distinguishable. Recovery is only an explicit reopen with a fresh generation. `admissionState` keeps its stored two-value `'closed' | 'open'` union; the deadline is enforced at the pre-step, the single dispatch gate, and a new `admissionCutoff` getter reports the stored instant of the current generation.

Two items are explicitly left open for adjudication, and this note claims neither: (1) the deadline time source is the wall-clock epoch read via `Date.now()` at the pre-step; a monotonic duration is the alternative. (2) In-flight work that already passed the pre-step is NOT auto-canceled at the deadline — the bounded-cancellation half of AT4-06 stays open pending controller semantics; the seam cuts only work that has not started.

## Alternatives considered

**Eager timer flipping admission state on expiry.** Lost: it puts a timer inside the service, makes stored state time-dependent between calls, and the pre-step is already the single dispatch gate — a second enforcement point could disagree with it.

**A third `deadline_closed` value in the `ReliabilityAdmission` union.** Lost: external consumers pattern-match the two-value union, and the error code already distinguishes why a dispatch died, so the union would duplicate that routing for every consumer.

**Monotonic duration instead of a wall-clock instant.** Deferred to adjudication, not silently chosen: a duration changes the API shape (open-time anchor vs checked instant) and the clock-jump risk profile.

**Rejecting already-past deadlines at open.** Lost: it needs a clock read at open and races with the caller's clock, and an immediately-dead window is a valid state that the pre-step reports at the first dispatch.

## Acceptance criteria

- The new spec's eight cases are green (`tests/at4-06-admission-deadline-closed.spec.ts`): inclusive deadline instant, three distinguishable rejections, the non-finite guard leaving the generation untouched, stored state pinned against pre-step enforcement, reopen recovery, the no-cutoff regression guard, reconciler retry composition, and `ADMISSION_CLOSED` precedence after a failed flush.
- The existing package suite stays at zero regression, and `tsc -b packages/experimental/agent-reliability` is clean.
- README (English and Chinese) and JSDoc contracts describe the seam together: the `openAdmission` cutoff, the `admissionCutoff` getter, the two new error codes, and the stored-state vs pre-step split.

## Risks

Wall-clock jumps: a host clock change closes or extends windows early or late. That is acceptable for process-local admission — the window bounds one process's dispatch generation, not a cross-process contract — but it is flagged for adjudication together with the monotonic-duration alternative. The stored-state/effective-state split could confuse hosts that read `admissionState` without running the pre-step; the split is documented on the getter and pinned by a test. The bounded-cancellation half of AT4-06 remains open: work that already passed the pre-step is not canceled by the deadline, and semantics for that await controller adjudication.
