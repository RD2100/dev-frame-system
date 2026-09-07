---
description: "Cordis service owning the project task board: TaskState transitions with recovery triples, a bounded developing-task budget, the project lifecycle, and the controller-only main-tree merge gate."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-controller

English | [中文](README.zh.md)

## Summary

`dsh-experimental-project-controller` mounts `ctx.projectController`, the Cordis service that owns the project task board. It moves tasks through the shared `TaskState` order (`planned → assigned → developing → reviewing → submitted → integrated → completed`), requires a reason, a next action, and a wake condition for every `blocked` or `failed` move, bounds the number of concurrently `developing` tasks through a validated `maxActiveTasks` config (default 2, aligned with the two-model-request account ceiling), runs the DevFrame project lifecycle (`admission_open → stop_requested → quiescence_confirmed → stopped`, with `needs_attention` and `ambiguous` side states), and gates main-tree integration: only a session bound as `controller` may mint a merge marker, and `integrate` consumes the marker exactly once. Task records persist through the `project_tasks` storage domain and are restored verbatim on start; the lifecycle itself is process-local run state that a fresh process opens explicitly with `startProject`.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service beside the storage stack and the session-identity registry; it hard-injects `ctx.agentBindings` (the merge gate verifies roles against it) and `ctx.storageDomain`, failing at activation when either is absent.

```yaml
- name: '@deepseek-ai/dsh-experimental-project-contracts'
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-project-controller'
  config:
    maxActiveTasks: 2
```

### Dispatch a task

Every move returns the updated record; an illegal move fails loud with a stable code instead of rewriting state.

```ts
controller.startProject()
await controller.createTask({ taskId, pluginId, title: 'Wire the gate' })
await controller.assign(taskId, workerSessionId)
await controller.startDevelopment(taskId)
await controller.beginReview(taskId)
await controller.submit(taskId)
const marker = await controller.requestMainTreeMerge(controllerSessionId, taskId)
await controller.integrate(taskId, marker)
await controller.complete(taskId)
```

A `blocked` or `failed` move must carry the full recovery triple; `resume` clears it and re-enters dispatch through `assigned`.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **Two-gate integration.** The merge gate mints a single-use, process-local marker only for a session whose binding carries the `controller` role; `integrate` validates the marker before the state check, so a consumed marker reports `MARKER_INVALID` even when the task has already moved on.
- **Budget at the developing edge.** The concurrency bound counts records in `developing` and is enforced exactly where a task would enter that state; leaving development (`beginReview`) frees the slot. The bound is a validated config field, not a constant.
- **Dispatch versus recording moves.** Dispatch-path moves (`assign`, `startDevelopment`, `beginReview`, `submit`, merges, `resume`, `createTask`) require `admission_open`; recording moves (`block`, `fail`, `complete`) stay available while the project has not stopped, so a stop can still record why work ended.
- **Verbatim cold restore.** The board returns exactly as persisted; in-flight records need host attention because their live workers died with the old process. Merge markers are process-local receipts and are never restored.

### Source map

| File | Role |
|---|---|
| [`src/controller.ts`](src/controller.ts) | The `ctx.projectController` service: lifecycle, task moves, budget, request charge (`chargeModelRequest` → `RequestChargeReceipt`), merge gate, restore |
| [`src/spec.ts`](src/spec.ts) | The `project_tasks` domain spec and the zod record schema bound to the shared contract type |
| [`src/errors.ts`](src/errors.ts) | `ProjectControllerError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry and default export |

### Invariant

No runtime invariant companion is published: the board is a write-through projection of one domain table rebuilt on start, the JSON backend refuses a second live handle on the same unit, and the lifecycle is process-local state with no second observer, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Project controller

#### What the model sees

Nothing. The package registers no tools, no prompt sections, and no session events — no `TaskRecord` value ever reaches a model request — so no request field carries its data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

These limits define when the controller is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **The lifecycle is process-local** — a restart loses `stop_requested`/`quiescence_confirmed` and starts `stopped`; the host re-opens admission explicitly and re-interprets restored in-flight records.
- **Merge markers die with the process** — a marker minted before a restart cannot integrate the task; the controller mints a fresh marker after the new process opens admission.
- **The budget bounds task states, not live model requests** — `maxActiveTasks` limits how many tasks may sit in `developing`; the actual model-request ceiling stays the deployment's account-level constraint.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
