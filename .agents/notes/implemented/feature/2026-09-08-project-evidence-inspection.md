# Agent Note: Lead inspection of authoritative project evidence

Status: implemented

English | [中文](2026-09-08-project-evidence-inspection.zh.md)

## Problem

An independent Lead needs the delivered source revision and actual check results before recording a review. Task state and Worker completion messages do not provide that evidence. Requiring the model to discover private projection caches couples its review to storage layout and consumes requests without establishing whether the records belong to the current assignment and Goal. A findings parameter that hides its array and object structure also leaves the model without the JSON fields the review executor requires.

## Decision

The [delivery consumer](../../../../packages/experimental/project-controller/README.md#deliver-and-review-work) exposes `project_evidence` to the task's actual parent Lead. The tool takes only `taskId`; current bindings, role policy, Goal admission, and registered worktree ownership determine access. It reads the controller's existing DevFrame projection and shares the delivery tools' per-task serial queue. It creates no second evidence store and writes no delivery, verification, review, or task state.

The result identifies the current task and Goal, latest delivery, actual check results, and existing review. Missing and stale evidence have explicit results. A matching delivery requires a clean, unchanged Worker source observation, followed by revalidation of authority and selected records. A dirty or unobservable source refuses inspection. Reading evidence grants no review or integration authority: each later operation checks its own current admission.

The complete rendered content, including its text wrapper and JSON escaping, uses the configured `checkMaxOutputBytes` UTF-8 byte limit. An oversized result refuses rather than presenting incomplete evidence as sufficient for review. The `project_review` tool schema declares findings as an array of objects with required identifiers, severity, and messages; the executor continues to reject JSON-encoded strings.

## Alternatives considered

**Read private projection caches from model code.** Cache discovery does not establish current Goal, assignment, source, or policy authority. A task-scoped tool keeps that validation with the controller that owns the evidence.

**Use task state or Worker completion as review evidence.** Neither identifies the checked source or reports actual check results. Independent review needs the persisted delivery and verification records.

**Accept JSON-encoded findings strings.** This gives one input two representations and leaves the model-facing schema ambiguous. The structural schema describes the array already required by the executor.

## Consequences

Leads can inspect persisted evidence through an ordinary logged tool result, including after the delivery consumer reloads. Inspection adds bounded conversation content and may require the host to raise the output limit for large checksets. It does not replace independent source review, rerun checks, integrate work, or complete a Goal.

The [integration recovery decision](../architecture/2026-09-07-controller-git-integration-recovery.md), [Worker commit decision](2026-09-08-project-commit-consumer.md), and [dispatch settlement decision](../architecture/2026-09-08-dispatch-settlement-wake.md) retain their separate responsibilities for admission and recovery, authorized commits, and parent notification. Evidence retrieval does not supersede them.

## Verification

The [Loader tests](../../../../packages/experimental/project-controller/tests/task-consumer-loader.spec.ts) cover Lead authority, missing and stale records, failed checks, read-only inspection, consumer reload, complete output-byte limits, and array-valued review findings. They assert the exact `review_ready` delivery and check records in a scripted Lead's logged result and restore equal evidence through a new Loader with real JSONL and storage providers. The tests use real local Git and registries.

The [recorded-session scenario](../../../../snapshots/session/project-evidence-authority/snapshot.yml) verifies tool definitions, named authority refusals, rejection of string findings, and acceptance of array findings through schema validation before authority refusal. Windows refresh and replay pass. POSIX expected output is mechanically projected and has not been replayed. Scripted model responses do not establish real-provider task completion.
