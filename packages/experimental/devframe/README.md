---
description: "Coordinate the first DSH-native DevFrame project boundaries: preserve one work identity and stop owned execution only after quiescence and persistence."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-devframe

English | [中文](README.zh.md)

## Summary

`dsh-experimental-devframe` provides the small library contracts used by a DSH-native project controller. A caller can carry one workspace, Goal, acceptance, and source identity across dispatch, evidence, and completion. A caller can also stop owned agents, jobs, and process handles while retaining writer ownership until cleanup and the final persistence flush finish. It also fixes the three-tier spawn policy — controller builds leads, a lead builds workers, a worker builds nothing — as detached delegation-request overrides. The package is a private experimental library: it registers no Cordis plugin and does not provide a model-facing tool.

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

### Assemble the three-tier spawn policy

Spread `devframeSpawnOverrides(tier)` into the delegation request when a DevFrame parent spawns a child. A lead carries only the depth budget; a worker also loses the delegation tool, and the child's own executor refuses it (`UNKNOWN_TOOL`) while the durable descriptor reapplies the filter on cold resume.

```ts
import { devframeSpawnOverrides } from '@deepseek-ai/dsh-experimental-devframe'

// { maxDepth: 2, toolFilter: { deny: ['subagent'] } } spread into the
// delegation request; devframeSpawnOverrides('lead') is { maxDepth: 2 }.
const overrides = devframeSpawnOverrides('worker')
const request = { prompt: [], parent: leadAgent, ...overrides }
```

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>

<summary>Implementation internals — click to expand</summary>

`stopProject` is a bounded orchestration helper. It uses the native Agent, Goal, Job, subprocess, and timeout seams supplied by the caller. It records `stopping` before cancellation, records either `quiesced` or `needs_attention` after draining, then flushes before releasing the writer. It never infers quiescence from a lost in-memory mutex or from an unverified process identity.

The shared types keep the project binding, configuration confirmation, lifecycle state, and persistence seam in one package. They do not add a Run database or copy native task, transcript, or Goal state.

### Completion admission gates the native Goal lifecycle

`GoalBindingController.complete` is the production call point for completion: it resolves an exact binding, closes admission for the attempt, and runs the fixed evidence-chain evaluation — the fingerprint match first against the binding's own recorded fingerprint, the required checks second against the store-registered configuration, and the authorized review last. A rejection is returned as data with the native Goal untouched, and continuing work requires a human-authorized resume. An admission completes the native Goal through the `NativeGoalPort` seam — `GoalServicePort` delegates every verb to the live `ctx.goals` service on its bound Agent — and persists the binding at the revision the service returned. Structural failures, including unusable fingerprints, unregistered digests, foreign identities, and review evidence attributed to another Goal, throw fail-loud and are never converted into rejections.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Library entry for stop and shared contracts |
| [`src/controller/goal-binding.ts`](src/controller/goal-binding.ts) | Goal binding controller, completion admission conjunction, and the production native Goal service port |
| [`src/goal-binding-file-store.ts`](src/goal-binding-file-store.ts) | File-backed goal binding store: the durable controller-session binding and workspace current JSON ledger |
| [`src/hierarchy/index.ts`](src/hierarchy/index.ts) | Per-tier spawn overrides for the controller → lead → worker tree |
| [`src/permissions/events.ts`](src/permissions/events.ts) | Persisted role and policy identity event contract |
| [`src/reliability/stop.ts`](src/reliability/stop.ts) | Admission cutoff, owned cancellation, bounded drain, and writer release |
| [`src/required-checks-file-store.ts`](src/required-checks-file-store.ts) | File-backed required-checks registration store: the durable digest → configuration JSON ledger |
| [`src/required-checks.ts`](src/required-checks.ts) | Required-checks configuration schema, canonical digest, completion verdicts, and the digest → configuration registration store |
| [`src/shared/types.ts`](src/shared/types.ts) | Branded work identities and binding persistence interfaces |
| [`src/source-fingerprint.ts`](src/source-fingerprint.ts) | Read-only worktree fingerprint engine and its explicit verify comparison |
| [`tests/hierarchy-roles.spec.ts`](tests/hierarchy-roles.spec.ts) | Per-tier spawn-override policy coverage |
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
- **Completion verdicts are not journaled** — the controller returns the admission verdict to its caller; recording the verdict or a completion receipt, and the host command surface composing `GoalServicePort`, remain deferred host-composition work.
- **Process handles must be verified** — a missing or uncertain handle is retained as `needs_attention`; the helper never kills by executable name or reused PID.
- **Single-process coordination** — the contracts do not provide cross-process locking, distributed delivery, or hostile-code isolation.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

This package is the first shared boundary for the experimental single-project workflow. Controller, permission, and lifecycle groups consume these contracts from their own modules; profile composition and user commands remain separate work.

</details>
