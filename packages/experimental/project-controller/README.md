---
description: "Configure project task admission and controller-only Git integration with persisted verification, lead review, and explicit recovery."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-controller

English | [中文](README.zh.md)

## Summary

Track a task from assignment through review, integration, and completion, with an explicit recovery plan whenever work blocks or fails. Bound concurrent development without confusing task slots with model-request capacity. A registered root controller can integrate reviewed Worker commits through `project_integrate`; the tool checks current evidence and worktree ownership before a fast-forward. Interrupted operations retain an intent so the controller can inspect what Git actually changed before deciding whether to retry.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package for a project with one integration controller, plugin leads, and assigned Workers on registered worktrees. The host owns project admission, approved checks, and writer allocation.

### Composition and configuration

Mount `@deepseek-ai/dsh-experimental-project-controller` once for `ctx.projectController`, alongside storage-domain and session-identity. Mount `@deepseek-ai/dsh-experimental-project-controller/consumer` separately to expose the tool. The consumer uses the existing service; its Loader entry is a function-plugin namespace without a default export.

Integration also requires live sessions, the DevFrame session projection, workspace and worktree registries, and persisted verification and review evidence. The tool additionally requires the live Agent registry and tool runtime. The [real Loader test composition](tests/consumer-loader.spec.ts) supplies these prerequisites and exercises the two entries without making model requests.

| Entry | Field | Default | Meaning |
|---|---|---|---|
| Service | `maxActiveTasks` | `2` | Positive integer limit on tasks in `developing`. |
| Service | `requestBudget` | `1` | Positive integer cumulative model-request charge budget. |
| Consumer | `requiredChecksPath` | Required | Absolute path of the existing approved-checks registration ledger. |
| Consumer | `gitExecutable` | Required | Deployment-selected Git executable. |
| Consumer | `gitTimeoutMs` | Required | Positive integer timeout in milliseconds per Git subprocess. |
| Consumer | `gitMaxOutputBytes` | Required | Positive integer output limit in bytes per Git subprocess. |

The consumer reads the configured ledger; it does not approve checks or create a replacement ledger. Missing registrations and corrupt contents fail admission. The host's controller tool policy must allow `project_integrate`; leads and Workers must not receive it.

### Task admission and integration

A fresh service starts `stopped`. The host calls `startProject()` before creating or advancing tasks through `planned → assigned → developing → reviewing → submitted`. A `blocked` or `failed` move requires a reason, next action, and wake condition; `resume` clears those fields and returns the task to `assigned`.

The tool accepts only `taskId` and `action`. It derives the caller from the actual live Agent, verifies the root-controller binding and session directory, and resolves source and target paths through the assigned Worker and controller worktree records. Model arguments cannot supply another caller, paths, check results, or merge markers.

Admission requires a submitted task, a current Goal binding, matching persisted verification and independent plugin-lead review, approved required checks, and no failing task warning. All three hierarchy worktrees must be independent and belong to the same workspace. The Worker and controller must hold their respective source and target writer locks. Source fingerprint, exact Git commits, clean worktrees, and fast-forward ancestry are checked; evidence and ownership are rechecked before Git starts.

| Action | Behavior |
|---|---|
| `integrate` | Prepare a fresh intent, execute one fast-forward, and record `integrated` after observing the applied result. |
| `reconcile` | Observe a retained intent without repeating Git. An `applied` result can finish recording integration; `unchanged` does not advance the task; `ambiguous` requires investigation. |
| `retry` | Explicitly re-admit a prepared attempt only when its clean target still has the original HEAD. Current evidence and ownership must pass again. |

After interruption, reopen project admission and reconcile using the original controller identity and writer lock. An ordinary `integrate` call does not replace a retained intent. Neither a command error nor cancellation proves that Git left the target unchanged. An ignored local file that conflicts with incoming tracked content is preserved and causes the merge to fail.

A host consumer uses `requestMainTreeMerge(callerSessionId, taskId, request)`, then passes the returned marker directly to `integrate(taskId, marker)`. The request carries exact Git paths and commits, process limits, the approved-checks store, and optional `retryUnchanged` and cancellation signal. Markers are single-use object capabilities, not transferable JSON. The service's `reconcileMainTreeIntegration(callerSessionId, taskId, options)` reads the durable intent. Integration does not call `complete` automatically.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The controller serializes task mutations and integration attempts. Task records, cumulative request charges, and Git intents persist through the `project_tasks` domain; lifecycle state and marker capabilities remain process-local. An applied Git observation is persisted before the task becomes integrated, so a failed task write can be reconciled after restart.

Evidence comes from the existing DevFrame projection and three-level binding registry. The package does not add a reviewer role or a second evidence database. A marker does not replace execution-time admission: a newer review, verification, warning, or ownership record invalidates the prepared evidence.

| File | Responsibility |
|---|---|
| [`src/controller.ts`](src/controller.ts) | Task lifecycle, serialized admission, durable intent, and recovery. |
| [`src/consumer.ts`](src/consumer.ts) | Loader tool entry, caller authorization, and host configuration. |
| [`src/integration-evidence.ts`](src/integration-evidence.ts) | Exact task evidence and independent lead authority. |
| [`src/git-integration.ts`](src/git-integration.ts) | Bounded Git inspection, fast-forward, and outcome observation. |
| [`src/spec.ts`](src/spec.ts) | Versioned task, request-budget, and integration-intent storage. |

No runtime invariant companion is published: Git advancement and task persistence can differ after interruption, so reconciliation reports and resolves that recovery state rather than requiring continuous equality. The [controller recovery tests](tests/integration-controller.spec.ts) and [Loader tests](tests/consumer-loader.spec.ts) exercise these relationships; callers must reconcile uncertain outcomes.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Architecture and profiles](../../../docs/architecture.md): supported launch and composition.
- [Agent hierarchy](../agent-hierarchy/README.md): controller, lead, and Worker authority.
- [DevFrame](../devframe/README.md): Goal binding, checks, and review evidence.
- [Worktree registry](../../workflow/worktree-registry/README.md): registered worktrees and writer locks.

-----

<a id="model-experience"></a>
## Model Experience

### Project integration tool

#### What the model sees

Mounting the consumer exposes `project_integrate` with `taskId` and `action` parameters. Successful results contain the task id, task state, and integration observation; failures report the refusal through the tool runtime. The ordinary tool call/result log carries these model-visible values. Mounting the service alone does not expose a tool.

#### Token effect

The tool definition contributes request tokens when visible to the Agent, and each call adds its arguments and result to conversation history. This package has no measured fixed token cost.

#### KV Cache effect

A stable tool definition can remain in a reusable request prefix. Changing tool visibility or configuration of the surrounding tool policy can change that prefix; calls and results extend conversation history. Provider cache reuse is not measured by the package tests.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These constraints matter when choosing the composition and handling interrupted work.

- The lifecycle starts stopped after restart. The host must reopen admission and reassess restored in-flight tasks; process-local markers cannot survive restart.
- The version 3 storage domain rejects older layouts. Do not activate it against an existing version 2 domain or reset that domain as an implicit upgrade.
- Integration supports clean, independent worktrees in one repository and fast-forward updates only. It does not reset files, resolve conflicts, or automatically repeat uncertain commands.
- Writer locks require participating hosts to honor ownership. They do not fence unrelated filesystem writers or Git commands that bypass the registries.
- `maxActiveTasks` counts developing tasks, not live model requests. Request charges persist across restarts; account and provider limits remain deployment concerns.
- Loader and real-Git tests verify local composition. They do not establish a shipped-profile rollout, production activation, or real-model completion quality.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
