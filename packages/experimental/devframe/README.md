---
description: "Coordinate the first DSH-native DevFrame project boundaries: preserve one work identity and stop owned execution only after quiescence and persistence."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-devframe

English | [中文](README.zh.md)

## Summary

`dsh-experimental-devframe` provides the small library contracts used by a DSH-native project controller. A caller can carry one workspace, Goal, acceptance, and source identity across dispatch, evidence, and completion. A caller can also stop owned agents, jobs, and process handles while retaining writer ownership until cleanup and the final persistence flush finish. The package is a private experimental library: it registers no Cordis plugin and does not provide a model-facing tool.

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

Use this library from a project controller that already owns native DSH sessions, Goals, jobs, and persistence. It supplies value types for the cross-module work binding and one stop operation; it does not create a project, mount a profile, or replace native state owners.

### Stop owned work

Pass the controller's live handles and ownership callbacks to `stopProject`. The function closes admission, requests cancellation, waits within the supplied grace period, flushes the observed state, and calls `releaseWriter` only after every required resource is settled.

```ts
import { stopProject, type StopProjectOptions } from '@deepseek-ai/dsh-experimental-devframe'

declare const options: StopProjectOptions
const result = await stopProject(options)
```

An unresolved process identity, timeout, failed operation, or failed flush returns `needs_attention` and leaves writer release to the owner. A successful result is therefore the only result that permits the caller to hand the project to another writer.

### Carry one work binding

Use the branded constructors when the host has validated the corresponding values. The binding is the same identity that dispatch, verification, review, and completion must receive.

```ts
import {
  AcceptanceHash, SourceFingerprint, WorkspaceId,
  type ProjectWorkBinding,
} from '@deepseek-ai/dsh-experimental-devframe'

const binding: ProjectWorkBinding = {
  workspaceId: WorkspaceId('workspace-1'),
  controllerSessionId,
  goalId,
  goalRevision: 1,
  acceptanceHash: AcceptanceHash('approved-config-digest'),
  sourceFingerprint: SourceFingerprint('source-digest'),
}
```

The host owns validation and persistence. A changed acceptance or source value is a different binding and must not reuse earlier evidence.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>

<summary>Implementation internals — click to expand</summary>

`stopProject` is a bounded orchestration helper. It uses the native Agent, Goal, Job, subprocess, and timeout seams supplied by the caller. It records `stopping` before cancellation, records either `quiesced` or `needs_attention` after draining, then flushes before releasing the writer. It never infers quiescence from a lost in-memory mutex or from an unverified process identity.

The shared types keep the project binding, configuration confirmation, lifecycle state, and persistence seam in one package. They do not add a Run database or copy native task, transcript, or Goal state.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Library entry for stop and shared contracts |
| [`src/permissions/events.ts`](src/permissions/events.ts) | Persisted role and policy identity event contract |
| [`src/reliability/stop.ts`](src/reliability/stop.ts) | Admission cutoff, owned cancellation, bounded drain, and writer release |
| [`src/shared/types.ts`](src/shared/types.ts) | Branded work identities and binding persistence interfaces |
| [`tests/reliability/stop.spec.ts`](tests/reliability/stop.spec.ts) | Unit and real owned-process stop coverage |
| [`../../experimental/agent-team/tests/devframe-composition.spec.ts`](../agent-team/tests/devframe-composition.spec.ts) | Real Team, Goal, dispatcher, and JSONL composition baseline |

No runtime invariant companion is published because this package registers no Cordis plugin and owns no independently observable runtime relation; direct event, projection, and lifecycle tests cover its library operations.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Single-project design](../../../docs/detailDesign-part1.md) — work identity, evidence, roles, and completion prerequisites.
- [Reliability design](../../../docs/detailDesign-part4.md) — stop, recovery, budgets, and writer ownership.
- [Team package](../agent-team/README.md) — native roster, mailbox, and task ownership.

-----

<a id="model-experience"></a>
## Model Experience

### Host-only project orchestration

#### What the model sees

Nothing. This library registers no model-facing tools, prompt sections, or model requests; `stopProject` and the shared bindings run on the host.

#### Token effect

Zero direct model tokens. The package adds no messages, tool schemas, or request fields.

#### KV Cache effect

None. Host-only calls leave the model request prefix unchanged.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Caller-owned admission and persistence** — the library does not discover project roots, create Goals, or append its own session events.
- **Process handles must be verified** — a missing or uncertain handle is retained as `needs_attention`; the helper never kills by executable name or reused PID.
- **Single-process coordination** — the contracts do not provide cross-process locking, distributed delivery, or hostile-code isolation.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

This package is the first shared boundary for the experimental single-project workflow. Controller, permission, and lifecycle groups consume these contracts from their own modules; profile composition and user commands remain separate work.

</details>
