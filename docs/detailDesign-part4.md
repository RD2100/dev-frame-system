---
description: Proposed recovery, cancellation, budgets, and operational acceptance for daily DSH use.
---

# Detailed Design Part 4: Reliability and Daily Operation

English | [中文](detailDesign-part4.zh.md)

## Summary

This reference owns reliability mechanisms used from the first single-project pilot onward, not a final stage postponed until after memory. DSH supplies sessions, goals, tools, jobs, and persistence; DevFrame must implement their admission, ownership, and recovery integration. The design distinguishes cancellation requested from execution stopped and targets the supported Windows path. It does not claim distributed high availability or hostile-code isolation.

## Table of Contents

- [Requirements](#requirements)
- [Recovery and continuation](#recovery)
- [Stopping and writer ownership](#stopping)
- [Limits and budgets](#limits)
- [Observability and release handling](#operations)

<a id="requirements"></a>

## Requirements

Use the [native goal state](../packages/goal/goal/README.md), [goal driver](../packages/goal/goal-round-driver/README.md), and [defensive lifecycle guidance](defensive-patterns.md) as implementation references. The feature must remain understandable through existing DSH task and session views.

| ID | Required behavior | Acceptance owner |
| --- | --- | --- |
| `R4.1` | Reconcile durable state without silently restarting unauthorized or ambiguous work. | [AT4-01, AT4-02](testAndAcceptance.md#part4) |
| `R4.2` | Stop the selected project's processes and retain writer ownership until confirmed quiescence. | [AT4-03, AT4-04](testAndAcceptance.md#part4) |
| `R4.3` | Enforce bounded admission, concurrency, retries, and spending controls without sibling races. | [AT4-05, AT4-06](testAndAcceptance.md#part4) |
| `R4.4` | Preserve diagnosable logs and recoverable data when plugins fail or versions change. | [AT4-07, AT4-08](testAndAcceptance.md#part4) |

<a id="recovery"></a>

## Recovery and continuation

Recovery begins by reading state, not by issuing model requests. Validate the pinned DSH version, configured feature policy, workspace identity, controller binding, and role descriptors before admitting any new mutation. Missing or inconsistent identity produces a visible `needs_attention` result.

Native goal persistence and automatic continuation are separate concerns. Resumed and forked goals are not automatically armed by the native driver; preserve that behavior. A human resume action identifies the project/run and approved limits. It does not grant broader permissions or erase previous usage.

Install `agent/pre-step` admission checks before restored sessions can run, covering the controller and children, queued follow-ups, delivery retries, and callbacks. Reject a closed or mismatched work binding, call `next()` for admissible work, and preserve downstream rejection. `tools.guard()` protects tool execution but cannot by itself stop a model request; disarming only the root Goal also cannot stop an independent child.

A native rejected pre-step closes that turn and does not automatically return claimed messages to the inbox. Avoid waking work while admission is closed. If a race or recovery reaches rejection, retain its original goal/task/operation and input references in session state before returning rejection. Only a claimed input for which no model or tool step has executed may be classified as `not_started` and explicitly reissued after authorized resume. If any model or tool step has executed, retain that fact and reconcile it as interrupted work; if execution cannot be established, keep it `ambiguous`. Neither interrupted nor ambiguous work may be downgraded to `not_started` and replayed. `AT4-01` tests both no unauthorized execution and no lost accepted work.

| Recovered condition | Action |
| --- | --- |
| Binding provisioned, target session absent | Reconcile or finish creation using the same reserved ID after authorization; do not allocate a replacement silently. |
| Target accepted a message, sender receipt missing | Recover the target receipt by message ID; do not enqueue duplicate model-visible input. |
| Execution may have started, terminal result absent | Inspect owned job/process evidence and source state; mark `ambiguous` if the result cannot be established. |
| Source changed after prior tests/review | Invalidate affected evidence and rerun required checks after the user resumes. |
| Role, policy, or required event decoder unavailable | Remain read-only or refuse resume with a diagnostic; never fall back to unrestricted defaults. |

There is no blanket exactly-once guarantee for shell commands, network calls, or user-facing external effects. Idempotent delivery prevents duplicate input; an uncertain irreversible operation needs inspection and a human decision. The initial workflow does not authorize automatic publication or deployment at all.

<a id="stopping"></a>

## Stopping and writer ownership

A stop operation targets the selected project and its known descendants, never every job in the DSH process. Use native subprocess ownership and process-tree handles; do not kill by executable name or an unverified reused PID.

1. Close new work admission, disarm continuation, and record the stop request.
2. Abort active model/tool operations and cancel the project's owned jobs and child process trees.
3. Wait for tool callbacks, streams, jobs, and child processes to finish cleanup within the configured grace period.
4. Flush the final observed state; release writer ownership only after quiescence is confirmed.

On timeout, return `needs_attention` with the remaining owned work and keep the project unavailable for a new writer. A new process after restart must reconcile old execution before granting a writer lease; losing an in-memory mutex does not prove an old subprocess stopped. If process identity cannot be established safely, require manual resolution.

Plugin disposal follows the same ownership rules: remove listeners, cancel only owned timers and work, drain callbacks, and leave no live writer behind. Tests run against real owned subprocesses as well as deterministic fakes; no test may target unrelated user processes.

<a id="limits"></a>

## Limits and budgets

These are proposed initial profile values, not measured capacity or current DSH defaults. Implement deployment-varying values as validated Cordis plugin config. Smaller test values exercise exhaustion paths without costly runs; memory-specific limits remain in [Part 3](detailDesign-part3.md#tools).

| Control | Proposed initial value | Meaning |
| --- | --- | --- |
| Concurrent active projects | 2 | A third project remains unstarted until capacity is available. |
| Writers per physical project root | 1 | Covers all mutating tools and their surviving jobs. |
| Concurrent model requests, host-wide | 3 | Includes Shadow, controllers, workers, and reviewers. |
| Team roster lifetime limit | 8 | Use native `maxMembers`; includes failed entries and does not reset per task. |
| Repair rounds per task | 2 | After the first review, allow at most two correction/retest/review cycles. |
| Model attempts per project run | 80 | Count controller and descendants together, including retry attempts. |
| Model attempts per Shadow user turn | 20 | Prevent an orchestration loop from consuming unbounded requests. |
| Project run wall-clock limit | 30 minutes | Close admission and begin cancellation when exhausted. |
| Pending messages / message size | 32 per target / 16 KiB UTF-8 | Reject before enqueue; use references for larger artifacts. |
| Transient delivery/memory attempts | 3 total, delays 1 second then 3 seconds | Persist the count; restart does not reset it. |
| Stop grace period | 5 seconds | Expiry requires attention; it does not prove termination. |

A project run uses the [Part 1 work identity](detailDesign-part1.md#work-identity), not a new Run database. Charge controller and child attempts to the captured `(controllerSessionId, goalId)` in native session events. Restore used and outstanding reservations before admission; pause/resume, changed checks, retries, and process restart do not reset them. A late result settles its original Goal's reservation, never the current Goal's.

Reserve request and concurrency capacity atomically before each outbound attempt; release concurrency when it settles and retain consumed attempts even on failure. Hidden provider retries must be exposed or disabled before claiming a hard attempt cap. The initial deadline is persisted from the first start and includes paused/downtime elapsed time; a human may explicitly revise limits, but not erase consumed usage. A new budget starts only with a separately authorized new Goal.

Record actual token usage when available, but distinguish measured usage, estimated usage, and unknown usage. A hard token or currency cap additionally requires a provider-supported upper bound and reservation for all in-flight calls; keep uncertain reservations charged until reconciled. Without that support, expose request/time limits and an estimate, not a false hard money limit.

The native Goal Round cap is a separate loop safeguard, not a token, currency, or wall-clock budget. Permission denial, persistent-state failure, and a critical process leak stop the run independently of remaining budget. Automatic retry never creates a new Goal to reset limits.

<a id="operations"></a>

## Observability and release handling

Use existing DSH events and artifacts. New records need only project/workspace identity, session/run identity, role, operation/message ID when applicable, source snapshot, timing, outcome, and a sanitized error. Do not add a telemetry database, copy full prompts into diagnostic logs, or store raw runtime evidence in the source repository.

The UI distinguishes queued, received, executing, awaiting review, blocked, and stopped work, with a concrete last error and next allowed action. Repeated unchanged status does not create new model requests or repetitive notifications. Evidence includes the effective provider/model configuration; report identity as unverified if the runtime cannot attest it.

Pin the DSH prerelease and the feature profile together. Validate a new version against role restoration, delivery, cancellation, and the keyless native regression command in the [acceptance reference](testAndAcceptance.md#baseline) before using existing runtime data. This design promises no automatic compatibility across arbitrary prereleases.

Disable new work to roll back a feature deployment, drain owned execution, and retain the last compatible profile and event readers. DSH can reject unknown required session events; removing the plugin that decodes them is not a safe rollback by itself. Never delete or rewrite session logs to make an older build open them; provide a compatible read/export path or leave the data untouched with a clear diagnostic.

Any new public session-event types must follow DSH's typed-event and consumer-projection requirements, with scoped effects and relevant snapshots. Do not mark permission, completion, or delivery state ignorable merely to make rollback appear successful.

The [delivery table](testAndAcceptance.md#delivery) selects the early single-project stop/recovery and budget cases. Keep broader multi-project and version-upgrade fault matrices with their later candidate features; the file number does not defer basic safety until a fourth milestone.

## Dev Note

Operational acceptance is not a full-suite percentage or a successful happy-path demo. [AT4-*](testAndAcceptance.md#part4) must exercise real restart and process behavior, and any unsupported environment remains an explicit release limitation.
