# Agent reliability service

English | [中文](agent-reliability.zh.md)

The agent-reliability subsystem carries the defensive-pattern practices agent work needs at its seams as one Cordis service: the DevFrame process-tree stop exposed as one serialized call that closes admission first, cancels only known descendants, and flushes before releasing the writer; a dispatch pre-step that rejects every operation whose work binding does not match the currently admitted identity; uncertain-call reconciliation that probes external state first and retries the original call at most once, only after the probe proved the effect absent; and a flush barrier that closes admission and retains write ownership when a flush fails. The [package README](../../packages/experimental/agent-reliability/README.md) owns the mount configuration and the model experience.

## Service surface

`ctx.agentReliability` is the reliability service. Its core operations:

- `openAdmission`, `closeAdmission`, and `assertAdmitted` — wire the dispatch pre-step; admission opens for exactly one work binding identity per dispatch generation, and a mismatched or stale binding is rejected before any model or tool work runs.
- `reconcileUncertainCall` — the probe checks external state first; the retry runs at most once and only after the probe returned `absent`, `confirmed` settles from the probe alone, and `still_uncertain` returns unresolved without resending.
- `flushBarrier` — a failed flush closes admission immediately and reports `writerRetained: true`; releasing write ownership is the host's move.
- `stopProject` — the DevFrame process-tree stop re-exported through the service untouched.

## Contracts

Pre-step rejections carry two separate stable codes on `AgentReliabilityError` — `AGENT_RELIABILITY_ADMISSION_CLOSED` and `AGENT_RELIABILITY_IDENTITY_MISMATCH` — so dispatch wiring can distinguish never admitted from wrong generation. Admission is process-local state that starts closed; a restart loses the admitted identity and every pre-step rejects until the host reopens admission explicitly. The reconciler holds no state between calls and trusts its probe; the service adds no durable stop state of its own, and no value reaches a model request, so no session events are added.

## Boundaries

The underlying practices are owned by [defensive patterns](../defensive-patterns.md), and the stop contract has one implementation and one test home in the [devframe package](../../packages/experimental/devframe/README.md). The [project task controller](project-controller.md) builds its dispatch-versus-recording split on this admission state, and the admitted identity is the goal binding identity the [goal](goal.md) subsystem persists. The service injects nothing and never blocks activation.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentreliability--agentreliability"></a>

### `ctx.agentReliability` — `AgentReliability`

The agent reliability service: stop productization, admission cutoff, reconciliation, flush barrier.

```ts cordis-catalog
/**
 * Open dispatch admission for exactly one work binding identity. Opening
 * replaces the whole generation — the identity AND the cutoff: passing no
 * `cutoff` clears a previous generation's deadline. A generation whose
 * deadline is already past opens fine; its first pre-step call rejects.
 * @param identity - The work binding every pre-step will require.
 * @param cutoff - Optional deadline bound for this generation, a wall-clock
 * epoch millisecond instant the pre-step reads via `Date.now()`. Supplying
 * `cutoff.stop` also schedules the native stop protocol. Reopen or explicit
 * closure disarms an untriggered timer; service disposal awaits a triggered stop.
 * @throws {@link AgentReliabilityError} with code
 * `AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID` when `cutoff.deadline`
 * is defined but not a finite epoch millisecond instant; nothing is
 * mutated in that case, or when the stop grace is invalid. Throws
 * `AGENT_RELIABILITY_STOP_IN_PROGRESS` if the old stop still owns cleanup;
 * reopening is allowed only after its result settles.
 */
openAdmission(identity: GoalBindingIdentity, cutoff?: AdmissionCutoff): void

/** Close dispatch admission; the identity is kept so stop flows can report it. */
closeAdmission(): void

/**
 * The dispatch pre-step: reject any operation whose work binding does not
 * match the currently admitted identity. Call this before dispatching
 * model or tool work; a rejection means the work never starts.
 * @param identity - Work binding carried by the proposed operation.
 * @throws {@link AgentReliabilityError} with code
 * `AGENT_RELIABILITY_ADMISSION_CLOSED` when admission is closed,
 * `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` when the current
 * generation's cutoff instant has passed, or
 * `AGENT_RELIABILITY_IDENTITY_MISMATCH` when another identity is admitted.
 * The checks run in that order: a passed deadline is a statement about the
 * window, not the identity, so it precedes the identity check.
 */
assertAdmitted(identity: GoalBindingIdentity): void

/**
 * Reconcile one uncertain call: probe external state first, and retry the
 * original call at most once and only after the probe proved the effect
 * absent. There is no blind-retry path by construction.
 * @param plan - The operation identity, its external-state probe, and its retry.
 * @returns the reconciliation outcome; `unresolved` leaves the decision to the caller.
 */
async reconcileUncertainCall<R>(plan: UncertainCallPlan<R>): Promise<ReconciledOutcome<R>>

/**
 * Run one flush barrier: on success the barrier reports a flushed log; on
 * failure it closes admission and retains write ownership — the writer is
 * never released on top of an unflushed log.
 * @param flush - Flush all participating Session state through native persistence.
 * @returns the barrier outcome with the failure, when one occurred.
 */
async flushBarrier(flush: () => Promise<void>): Promise<FlushBarrierResult>

/**
 * Run one serialized process-tree stop: close admission, cancel only known
 * descendants, flush, and release the writer only after confirmed cleanup.
 * The host serializes calls for the same writer and retains unresolved
 * identities across restart.
 * @param options - Native live handles and the owning project's durable state adapter.
 * @returns `stopped` only after confirmed cleanup and flush; otherwise retained ownership.
 */
async stopProject(options: StopProjectOptions): Promise<StopResult>
```

Source: [`packages/experimental/agent-reliability/src/service.ts`](../../packages/experimental/agent-reliability/src/service.ts)
<!-- END GENERATED cordis-surface -->
