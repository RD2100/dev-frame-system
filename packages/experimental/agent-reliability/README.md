---
description: "Cordis service productizing the defensive stop, admission cutoff, uncertain-call reconciliation, and flush-barrier patterns for agent work."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-reliability

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-reliability` mounts `ctx.agentReliability`, the Cordis service that carries the defensive-pattern practices agent work needs at its seams: the DevFrame process-tree stop exposed as one serialized call that closes admission first, cancels only known descendants, and flushes before releasing the writer; a dispatch pre-step (`assertAdmitted`) that rejects every operation whose work binding does not match the currently admitted identity and, when the generation is bounded by an epoch deadline, every dispatch from the deadline instant (inclusive) onward; uncertain-call reconciliation that probes external state first and retries the original call at most once, only after the probe proved the effect absent; and a flush barrier that closes admission and retains write ownership when a flush fails. Admission is process-local state that starts closed.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service anywhere in the plugin set; it injects nothing and owns only process-local admission state, so it never blocks activation.

```yaml
- name: '@deepseek-ai/dsh-experimental-agent-reliability'
```

### Wire the dispatch pre-step

Open admission for exactly one work binding identity when a dispatch generation starts, and make `assertAdmitted` the first step of every dispatch; a mismatched or stale binding is rejected before any model or tool work runs.

```ts
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'
import type { GoalBindingIdentity } from '@deepseek-ai/dsh-experimental-devframe/controller'

function startGeneration(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.openAdmission(identity)
}

function beforeDispatch(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.assertAdmitted(identity)
}
```

### Bound admission with a cutoff

Open admission with an epoch-millisecond deadline to bound the dispatch generation: the pre-step reads the wall clock (`Date.now()`) at every dispatch, and from the `deadline` instant (inclusive) it rejects with `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED`. Recovery is an explicit reopen with a fresh generation; a non-finite deadline fails loud at open without touching the current generation.

```ts
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'
import type { GoalBindingIdentity } from '@deepseek-ai/dsh-experimental-devframe/controller'

function startBoundedGeneration(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.openAdmission(identity, { deadline: Date.now() + 60_000 })
  // From the deadline (inclusive), assertAdmitted rejects dispatch.
}
```

### Reconcile an uncertain call

When a call's outcome is unknown, hand the plan to the reconciler: the probe checks external state first, and the retry runs at most once and only after the probe proved the effect absent.

```ts
import type {
  AgentReliability, ReconciliationProbe,
} from '@deepseek-ai/dsh-experimental-agent-reliability'

async function reconcileWorktree<R>(
  ctx: { agentReliability: AgentReliability },
  probeExternalState: () => Promise<ReconciliationProbe>,
  createWorktree: () => Promise<R>,
) {
  return await ctx.agentReliability.reconcileUncertainCall({
    operation: 'create-worktree',
    probe: probeExternalState,
    retry: createWorktree,
  })
}
```

### Barrier a flush

A failed flush closes admission and retains write ownership; the writer is never released on top of an unflushed log.

```ts
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'

async function flushBeforeRelease(
  ctx: { agentReliability: AgentReliability },
  flushSessions: () => Promise<void>,
  reportFlushFailure: (failure: unknown) => void,
) {
  const barrier = await ctx.agentReliability.flushBarrier(flushSessions)
  if (!barrier.flushed) reportFlushFailure(barrier.failure)
  return barrier
}
```

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **Productization, not duplication.** The process-tree stop is the DevFrame reliability module's `stopProject`, re-exported through the service untouched — the stop contract (admission first, record durable observations, quiescence before flush, writer released only after a clean log) has one implementation and one test home.
- **Fail-closed admission.** Admission starts closed in a fresh process and opens only for one explicit identity; the pre-step rejects closed admission and mismatched identities with separate stable codes, so dispatch wiring can distinguish "never admitted" from "wrong generation".
- **The probe owns the retry decision.** `reconcileUncertainCall` has no blind-retry path by construction: the retry is invoked at most once, and only after the probe returned `absent`. `confirmed` settles from the probe alone; `still_uncertain` returns unresolved without resending — the caller decides what an unresolved call means.
- **The flush barrier retains the writer.** A failed flush closes admission immediately and reports `writerRetained: true`; releasing write ownership is the host's move, and the barrier makes doing it on an unflushed log impossible through this seam.
- **The deadline seam is enforced at the pre-step, not in stored state.** `openAdmission` accepts a cutoff and fails loud on a non-finite deadline without touching the current generation; from the deadline instant (inclusive) the pre-step rejects with `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` before the identity check — a passed deadline is a statement about the window, not the identity. `admissionState` keeps reporting the stored `'closed' | 'open'` decision; the deadline lives only in the dispatch gate, and recovery is an explicit reopen with a fresh generation.

### Source map

| File | Role |
|---|---|
| [`src/service.ts`](src/service.ts) | The `ctx.agentReliability` service: pre-step, reconciler, flush barrier, stop delegation |
| [`src/errors.ts`](src/errors.ts) | `AgentReliabilityError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry, default export, and the stop contract re-export |

### Invariant

No runtime invariant companion is published: admission is one process-local pair of fields with no durable projection, the reconciler holds no state between calls, and the flush barrier's effects (admission closed, writer retained) are observable through the same service instance that produced them, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Agent reliability service

#### What the model sees

Nothing. The package registers no tools, no prompt sections, and no session events — no `ReconciledOutcome`, `FlushBarrierResult`, or `StopResult` value ever reaches a model request — so no request field carries its data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

These limits define when the service is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **Admission is process-local and fail-closed** — a restart loses the admitted identity and every pre-step rejects until the host reopens admission explicitly.
- **The reconciler trusts its probe** — `absent` and `confirmed` answers are only as sound as the external-state check the caller supplies; the service cannot verify the probe inspects the right resource.
- **The stop delegates to the DevFrame contract unchanged** — unresolved identities, retained writer ownership, and restart reconciliation follow the DevFrame stop semantics; the service adds no durable stop state of its own.
- **The deadline does not cancel in-flight work** — work that already passed the pre-step keeps running after the cutoff instant; the bounded-cancellation half of AT4-06 awaits semantics adjudication.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
