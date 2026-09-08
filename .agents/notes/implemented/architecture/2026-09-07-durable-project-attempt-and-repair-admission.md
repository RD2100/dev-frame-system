# Agent Note: Durable Project Attempt and Repair Admission

Status: implemented

English | [中文](2026-09-07-durable-project-attempt-and-repair-admission.zh.md)

## Problem

A request counter cannot bound model traffic unless sending consumes it. A correction counter held by one controller object cannot bound repeated reviews across controller replacement or restart. Charging the same failure twice also consumes useful work capacity when durable evidence succeeds but the following task-state write fails.

## Decision

The [project request budget consumer](../../../../packages/experimental/project-controller/src/request-budget-consumer.ts) reserves a sending attempt before delegating the `llm/stream` waterfall. Its host-selected root scopes the actual live initiating Agent, its plugin Leads, and their Workers to one controller service budget. AgentLoop retries pass through the same admission. The service serializes charges and persists each count before returning; an uncertain write closes charging until service reload. Cancellation after persistence does not refund the reservation. The count describes sending admission, not supplier billing or proof of an HTTP request.

The [agent-dispatch consumer](../../../../packages/experimental/agent-dispatch/src/consumer.ts) awaits the nested request-budget plugin fiber whenever a candidate root is configured. Loader readiness therefore includes activation of the admission listener, and the dispatch tool is not published before the listener can charge the first stream.

The [DevFrame Session journal](../../../../packages/experimental/devframe/src/session-journal.ts) owns correction admission through `devframe/repair-admission`. Existing negative reviews and fail-graded task warnings share one allowance keyed by controller Session and Goal. A cause names the existing review identity or the task's unique durable warning. Identical retries return the original receipt; Goal revisions and human-authorized resume preserve consumption. A new Goal receives its own allowance, while a superseded Goal cannot reopen work through either a new cause or a historical receipt.

The configured positive integer `repairLimit` defaults to two and cannot change after that Goal records an admission. Journal instances using the same live Session share their queue and uncertain-flush latch. Authority is checked inside the queue, and the caller receives admission only after persistence. Review evidence, correction admission, and task-state advancement remain separate writes; recovery reuses their durable identities instead of assuming an error means no write occurred. Projection checkpoint version three rebuilds older checkpoints from the event log.

The [completion admission decision](2026-09-06-goal-completion-admission-seam.md) and [human command decision](2026-09-06-command-goal-binding-host-command-surface.md) retain their independent ownership of evidence-gated completion and command dispatch. This decision defines the accounting those consumers share.

## Alternatives considered

**Charge only reported supplier usage.** A response may never arrive after a sent request. Waiting for usage cannot enforce admission before traffic leaves the process, and local evidence cannot establish supplier billing.

**Count every negative review.** A review records evidence even when no correction is admitted. It cannot distinguish exhaustion or a failed subsequent task write, and it does not cover task-warning causes.

**Store rounds in the immutable Goal binding or a controller-local map.** A local map resets on replacement. Changing an immutable binding conflates authorized work identity with mutable consumption. The file binding store's whole-document rename protects readers from partial documents but provides no cross-process read-modify-write lock; a separate counter there would also require another log representation for reconstruction.

**Give each journal its own queue and failure latch.** Independent consumers of one live Session can race for the final allowance or keep writing after another consumer loses a flush acknowledgement. Sharing queue ownership by Session preserves serialization without introducing another project state service.

## Consequences

Local Loader tests observe actual loopback HTTP requests for shared root/Lead/Worker admission, retries, cancellation, and uncertain storage failures. Real Session tests cover shared-journal contention, idempotent causes, cold restore, fresh-Goal accounting, checkpoint replay, and authority revocation. Consumer tests exercise the delivery and command paths.

On Windows, both TypeScript SDK scenarios pass replay and all three corpus checks pass. The repair fixture modifies and commits real Worker files, records a negative review and an idempotent repair admission, then redelivers and records another review; the SDK model drives only `project_integrate`. Python source SDK checks through the built CLI pass both golden refresh and replay, establishing agreement between transported events, callbacks, and the durable log. Independent review by `/root/request_budget` passes. POSIX execution and an autonomous Worker/Lead development chain are not verified by these checks.

The deployment must give the request consumer a project-exclusive LLM scope and keep a single live writer for each Session. Neither the Session journal nor the controller's request queue provides cross-process compare-and-set. Provider-SDK retries below the adapter require separate verification. No shipped-profile activation or production rollout follows from these local checks.
