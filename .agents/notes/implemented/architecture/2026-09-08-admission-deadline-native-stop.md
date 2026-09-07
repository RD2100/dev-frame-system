# Agent Note: Admission deadlines invoke native project stop

Status: implemented

English | [中文](2026-09-08-admission-deadline-native-stop.zh.md)

## Problem

A pre-step cutoff cannot cancel work already admitted. The [admission cutoff proposal](../../proposed/architecture/2026-09-06-at406-deadline-admission-seam.md) retains the cutoff-only contract and the wall-clock decision; its deferred cancellation scope needs live resource ownership to invoke the existing project stop protocol.

## Decision

`AdmissionCutoff.stop` optionally supplies native `StopProjectOptions` for one admission generation. The service schedules the epoch deadline, closes admission before invoking stop, and exposes the triggered result through `deadlineStopResult`. The existing stop protocol owns cancellation, identity checks, flush, and conditional writer release. Failed or uncertain cleanup remains `needs_attention`.

Reopen and explicit close disarm an untriggered deadline. Reopen is rejected while a triggered stop owns cleanup; disposal disarms the timer and awaits that cleanup. Long deadlines rearm within Node's timer limit and recheck the wall clock. A host supplies validated deployment configuration and adapters for its actual live resources. Omitting `stop` preserves pre-step-only enforcement.

## Alternatives considered

**A separate deadline cancellation protocol.** Duplicating stop would give deadline expiry different identity, persistence, and writer-release rules from explicit stop.

**Allow reopening during cleanup.** The old stop could release ownership after a new generation begins. Reopening waits for the old result instead.

## Consequences

Focused timer tests cover generation replacement, long delays, disposal, and failed cleanup. The process-tree journey uses a real clock and real child and grandchild processes to observe deadline-triggered cancellation and exit before release. These verify the service mechanism; full AT4-06 acceptance additionally requires the host's actual resource adapters, configuration, and project lifecycle.
