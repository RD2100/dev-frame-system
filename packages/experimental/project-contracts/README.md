---
description: "Shared type vocabulary for the pluginized DSH agent hierarchy: roles, task states, branded ids, binding and task records, creation intents, persistence seams, and stable error types."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-contracts

English | [中文](README.zh.md)

## Summary

`dsh-experimental-project-contracts` owns the cross-plugin type vocabulary of the pluginized agent hierarchy: the three roles (`controller`, `lead`, `worker`), the nine task states of the project board, the branded `PluginId` and `TaskId` identifiers, the durable `AgentBindingRecord` and `TaskRecord` shapes, the `CreationIntent` record every creation attempt carries, the minimal `BindingStore` and `TaskStore` persistence seams, closed-union guards, and the stable `ProjectContractsError` type. The package is a private experimental library of types and pure value helpers only: it registers no Cordis plugin, holds no live state, and provides no model-facing surface. Every sibling plugin — session-identity, agent-hierarchy, project-controller, agent-evidence, agent-reliability — imports its contracts from here instead of redeclaring them.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package when a pluginized-hierarchy plugin needs to agree with its siblings on roles, task states, ids, records, or store seams. It is the only cross-plugin source dependency among the new hierarchy plugins; release packages must not depend on it.

### Read and write the vocabulary

Import the types, guards, and factories from the package root. The factories validate before branding; the guards classify untrusted values at durable boundaries.

```ts
import { isTaskState, PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'

const pluginId = PluginId('agent-reliability')
const taskId = TaskId('task-7')
if (!isTaskState(rawState)) throw new Error('unknown task state')
```

### Implement a store seam

`BindingStore` and `TaskStore` fix only `read`, `write`, and `list`. An implementation lives with its owning plugin — JSON storage under the plugin's own storages directory for cold recovery, an in-memory store for tests — and answers `read` with `undefined` for a missing record instead of failing. Implementations validate records they read from disk and report failures through `ProjectContractsError`.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **One vocabulary, six consumers.** Roles, states, records, and errors are declared once here; the sibling plugins depend on this package rather than on each other's runtime exports.
- **Distinct brand strings.** `TaskId` brands `ProjectTaskId`, deliberately separate from the experimental DevFrame team-task brand, so the two task vocabularies cannot mix at the type level; `agentId` and `sessionId` reuse the host `SessionId` brand because local agents carry the same identity in both roles.
- **Validation at the boundaries that own it.** The id factories reject empty, whitespace-only, and padded values; the closed-union guards classify untrusted strings; record validation beyond that belongs to the store implementations that read durable bytes.
- **No state machine in the contracts.** The `TaskState` type documents the dispatch order and the recovery triple a `blocked` or `failed` task must carry, but transition enforcement is the project-controller's runtime job, not a contracts concern.

### Source map

| File | Role |
|---|---|
| [`src/types.ts`](src/types.ts) | Roles, task states, record shapes, creation intents, and the store seams — types only |
| [`src/ids.ts`](src/ids.ts) | The `PluginId` and `TaskId` brands and their validating factories |
| [`src/guards.ts`](src/guards.ts) | The frozen member tuples and the closed-union guards |
| [`src/errors.ts`](src/errors.ts) | `ProjectContractsError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry that re-exports the vocabulary |

### Invariant

No runtime invariant companion is published: the package holds no live state and asserts no relationship between independent observations — every export is a value type, a pure guard or factory, or an error type, so nothing can diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Contract vocabulary

#### What the model sees

Nothing. The package contributes no tools, no prompt sections, and no session events — no `AgentBindingRecord` or `TaskRecord` value ever reaches a model request — so no request field carries its data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

These limits define when the contracts are a poor fit or need special operational care. They are current package constraints, not a task backlog.

- **Store seams carry no record validation** — `BindingStore` and `TaskStore` fix operations only; each implementation must validate the records it reads from its own durable medium and report failures through `ProjectContractsError`.
- **`CreationIntent.pluginScope` is single-valued** — a creation attempt names at most one plugin scope; a child that would span several scopes needs a different intent shape and is not representable today.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
