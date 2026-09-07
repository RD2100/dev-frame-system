# Agent Note: Controller Git integration recovery

Status: implemented

English | [中文](2026-09-07-controller-git-integration-recovery.zh.md)

## Problem

A task-state update cannot prove that Git changed the target checkout. Git and the task store cannot commit atomically, so a process interruption can leave a successful merge without its task receipt. Repeating an uncertain merge can act on a different target or overwrite the meaning of the original attempt.

## Decision

The [project controller](../../../../packages/experimental/project-controller/README.md) binds each admitted attempt to exact source and target commits, the registered controller and Worker worktrees, and persisted verification and independent review evidence. The latest Goal must have open admission and contain the task; passing evidence from a stopped or superseded Goal cannot authorize integration. It rechecks current evidence, ownership, locks, cancellation, and lifecycle immediately before spawning the fast-forward merge. The host retains exclusive target ownership through receipt recording; registry locks do not exclude unrelated external Git processes.

The controller persists a prepared intent before Git and an applied receipt before the integrated task state. Reconciliation observes the target and repairs recording after an applied merge without invoking merge again. An ambiguous observation requires attention. An unchanged target permits another attempt only through explicit retry with fresh admission; an old process-local marker cannot authorize that attempt. Cancellation does not prove that Git left the target unchanged.

The separate Loader consumer derives identities and checkout paths from host registries. Its model arguments contain only the task and the requested action. Git process limits and the checks ledger belong to host configuration. The consumer mounts beside the existing service instead of constructing a second controller.

Task planning and development admission use a separate root-only consumer over the same board. The host rechecks authority inside each serialized write, because authorization before queueing can expire while another task holds the queue. Development admission precedes briefing delivery; a partial failure leaves the board authoritative and does not permit an automatic repeat that could duplicate Worker instructions.

Task deliveries preserve the immutable Goal input binding and separately identify the output revision. Verification and independent lead review refer to the same latest delivery, so a developed commit cannot masquerade as a new Goal confirmation or borrow another task's passing evidence. Checks execute the approved registration; callers explicitly request reruns after failure or interruption. The evidence journal and task board cannot commit atomically, so an identical recorded review can repair task recording without constituting another approval.

## Alternatives considered

- A marker-only state transition proves authorization but not the filesystem result.
- Automatic retry after a timeout treats missing acknowledgment as proof of nonexecution.
- Persisting only the final task state loses the boundary needed to distinguish an applied merge from an unstarted attempt.
- Resetting the target to retry discards independent user or controller work.

## Consequences

The durable intent makes interrupted integration recoverable, but it does not make Git and storage atomic. Prepared intents and applied receipts with a submitted task are valid recovery states. The host must reconcile uncertainty before scheduling another target mutation. Only clean, independent checkouts are accepted. The mode boundary this note once named fast-forward-only has since been extended by the [parallel merge decision](2026-09-08-controller-parallel-branch-merge.md), and conflicts now report the explicit `conflicted` state.

The package's real Git and Loader tests cover authority rejection, changed evidence, explicit retry, ignored-file collision preservation, cancellation, disposal, and receipt/task-write interruptions. Recorded model-session coverage and deployment activation remain separate evidence from these tests. The versioned task domain rejects older formats; this decision does not authorize resetting an existing production domain.
