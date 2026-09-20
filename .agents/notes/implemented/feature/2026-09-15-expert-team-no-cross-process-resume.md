# Agent Note: Expert-team runs do not resume across process restarts

Status: implemented

English | [中文](2026-09-15-expert-team-no-cross-process-resume.zh.md)

## Problem

expert-team run state lives in memory and is mirrored to `<artifactsDir>/<runId>/run-state.json` at every commit point. M1 design explicitly deferred cross-process resume — a process restart loses in-flight runs. M4 must make the final call: implement resume, explicitly reject it, or keep the current behavior.

## Decision

**No cross-process resume.** Run state is authoritative in memory; `run-state.json` is a mirror, not a recovery point. After a process restart, in-progress or gate-parked runs are considered terminated. Artifact files and `run-state.json` are retained for audit and manual reconstruction.

Rationale:
1. **No current consumer**: no deployment has requested cross-restart team execution; the storage seam is added only when a measured need appears.
2. **Memory + file mirror is sufficient**: `run-state.json` records the complete run story; project-memory's M2 recording provides additional artifact persistence across restarts.
3. **Resume semantics are complex**: cross-process resume requires handling partially-completed phases, allocated but unfinished agent sessions, pending gate states, and artifact/run-state consistency; the cost of solving these does not match current demand.
4. **Complementary to project-memory**: project-memory's MemoryReceiptStore persists through session logs, providing cross-restart artifact recording; expert-team does not need to duplicate that capability.

## Alternatives considered

**Implement cross-process resume.** Rejected: requires a new storage seam (storage-domain or session-log), session recovery, gate replay, and artifact consistency verification; no deployment needs this today, and resume semantics without real consumers tend toward over-engineering.

**Use run-state.json as a recovery point.** Rejected: run-state.json is a mirror, not a checkpoint — it does not contain enough runtime state (agent session handles, in-flight tool calls, gate wait queues) to support resume; upgrading it to a recovery point would require recording additional runtime state, contradicting the "memory is authoritative" design.

## Consequences

Gained: the runtime stays simple — one run has one lifecycle owner, no recovery, reconnection, or state-merging logic; `run-state.json` retains its audit purpose. Cost: a process restart loses in-progress runs; users must wait for runs to complete or manually handle parked runs. This limit is recorded in the README's Known Limitations and reflected in `expert_team_status` responses — parked runs do not appear in status queries after a restart.
