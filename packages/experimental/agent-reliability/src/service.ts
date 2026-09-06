/**
 * The agent reliability service (`ctx.agentReliability`): the Cordis
 * productization of the defensive-pattern practices agent work needs at its
 * seams —
 *
 * - **Process-tree stop** from the experimental DevFrame reliability module,
 *   exposed as one serialized call that closes admission first, cancels only
 *   known descendants, flushes before releasing the writer, and reports
 *   unresolved identities instead of claiming settlement.
 * - **Admission cutoff wiring**: a dispatch pre-step
 *   {@link AgentReliability.assertAdmitted} rejects every operation whose
 *   work binding does not match the currently admitted identity, so a stale
 *   or mismatched dispatch fails before any model or tool work starts.
 * - **Deadline-bounded admission**: {@link AgentReliability.openAdmission}
 *   may bound a generation with an epoch deadline ({@link AdmissionCutoff});
 *   from that instant (inclusive) the pre-step rejects with
 *   `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED`, and recovery is only an
 *   explicit reopen (a new generation).
 * - **Uncertain-call reconciliation**: when a call's outcome is unknown, the
 *   probe runs first — an operation is retried only after the external state
 *   check proves its effect absent. There is no blind-retry path.
 * - **Flush barrier**: a failed flush closes admission and retains write
 *   ownership; the writer is never released on top of an unflushed log.
 *
 * Admission is process-local state that starts closed: a fresh process must
 * open admission explicitly, which keeps the fail-closed default.
 *
 * @module @deepseek-ai/dsh-experimental-agent-reliability/service
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import { stopProject as stopProjectProcessTree } from '@deepseek-ai/dsh-experimental-devframe/reliability'
import type { GoalBindingIdentity } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { StopProjectOptions, StopResult } from '@deepseek-ai/dsh-experimental-devframe/reliability'
import { AgentReliabilityError } from './errors.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentReliability: AgentReliability
  }
}

/** Whether dispatch may start work for the admitted identity. */
export type ReliabilityAdmission = 'closed' | 'open'

/** The admission cutoff request: dispatch is rejected from the `deadline` instant (inclusive) onward. */
export interface AdmissionCutoff {
  /** Epoch milliseconds; the instant the admission window closes (inclusive). */
  readonly deadline: number
}

/** External-state answer a reconciliation probe must return. */
export type ReconciliationProbe = {
  /** The operation's effect is durably present: settle without resending. */
  readonly status: 'confirmed'
} | {
  /** The operation's effect is provably absent: a retry cannot duplicate it. */
  readonly status: 'absent'
} | {
  /** External state could not answer; the operation stays unresolved. */
  readonly status: 'still_uncertain'
}

/** The plan one uncertain call hands to {@link AgentReliability.reconcileUncertainCall}. */
export interface UncertainCallPlan<R> {
  /** Stable operation identity for diagnostics and results. */
  readonly operation: string
  /** Check external state for the operation's effect; runs before any retry. */
  readonly probe: () => Promise<ReconciliationProbe>
  /** The original call; invoked at most once, only after an `absent` probe. */
  readonly retry?: () => Promise<R>
}

/** One reconciliation outcome; the caller decides what an unresolved call means. */
export type ReconciledOutcome<R> = {
  /** The effect is durably present — either observed directly or produced by the single retry. */
  readonly status: 'settled'
  /** How the effect became observable. */
  readonly via: 'probe' | 'retry'
  /** The settled result; present only when the retry produced it. */
  readonly result?: R
} | {
  /** The probe proved the effect absent and no retry was supplied. */
  readonly status: 'absent'
} | {
  /** External state could not answer; the call was never retried. */
  readonly status: 'unresolved'
}

/** The outcome of one flush barrier. */
export interface FlushBarrierResult {
  /** Whether the flush completed. */
  readonly flushed: boolean
  /** True when the barrier closed admission because the flush failed. */
  readonly admissionClosed: boolean
  /** True when write ownership must be retained; never released on a failed flush. */
  readonly writerRetained: boolean
  /** The flush failure; always `undefined` on a flushed barrier. */
  readonly failure: unknown
}

/** The agent reliability service: stop productization, admission cutoff, reconciliation, flush barrier. */
export class AgentReliability extends Service {
  private admission: ReliabilityAdmission = 'closed'
  private admittedWork: GoalBindingIdentity | undefined
  private admittedCutoff: number | undefined

  constructor(ctx: Context) {
    super(ctx, 'agentReliability')
  }

  /**
   * Open dispatch admission for exactly one work binding identity. Opening
   * replaces the whole generation — the identity AND the cutoff: passing no
   * `cutoff` clears a previous generation's deadline. A generation whose
   * deadline is already past opens fine; its first pre-step call rejects.
   * @param identity - The work binding every pre-step will require.
   * @param cutoff - Optional deadline bound for this generation, a wall-clock
   * epoch millisecond instant the pre-step reads via `Date.now()`.
   * @throws {@link AgentReliabilityError} with code
   * `AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID` when `cutoff.deadline`
   * is defined but not a finite epoch millisecond instant; nothing is
   * mutated in that case.
   */
  openAdmission(identity: GoalBindingIdentity, cutoff?: AdmissionCutoff): void {
    if (cutoff?.deadline !== undefined && !Number.isFinite(cutoff.deadline)) {
      throw new AgentReliabilityError(
        'admission deadline must be a finite epoch millisecond instant',
        'AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID',
      )
    }
    this.admittedWork = { controllerSessionId: identity.controllerSessionId, goalId: identity.goalId }
    this.admittedCutoff = cutoff?.deadline
    this.admission = 'open'
  }

  /** Close dispatch admission; the identity is kept so stop flows can report it. */
  closeAdmission(): void {
    this.admission = 'closed'
  }

  /** The current admission state and, when open, the admitted identity. */
  get admissionState(): ReliabilityAdmission {
    return this.admission
  }

  /**
   * The stored cutoff instant of the current generation; `undefined` when the
   * generation has no cutoff. Note: `admissionState` stays the stored
   * generation decision (`'closed' | 'open'` — the union does not change);
   * the deadline is enforced at the pre-step, the single dispatch gate.
   */
  get admissionCutoff(): number | undefined {
    return this.admittedCutoff
  }

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
  assertAdmitted(identity: GoalBindingIdentity): void {
    if (this.admission !== 'open' || this.admittedWork === undefined) {
      throw new AgentReliabilityError('admission is closed', 'AGENT_RELIABILITY_ADMISSION_CLOSED')
    }
    if (this.admittedCutoff !== undefined && Date.now() >= this.admittedCutoff) {
      throw new AgentReliabilityError('admission deadline has passed; dispatch rejected', 'AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED')
    }
    const admitted = this.admittedWork
    if (admitted.controllerSessionId !== identity.controllerSessionId || admitted.goalId !== identity.goalId) {
      throw new AgentReliabilityError(
        `work binding does not match the admitted identity; dispatch rejected`,
        'AGENT_RELIABILITY_IDENTITY_MISMATCH',
      )
    }
  }

  /**
   * Reconcile one uncertain call: probe external state first, and retry the
   * original call at most once and only after the probe proved the effect
   * absent. There is no blind-retry path by construction.
   * @param plan - The operation identity, its external-state probe, and its retry.
   * @returns the reconciliation outcome; `unresolved` leaves the decision to the caller.
   */
  async reconcileUncertainCall<R>(plan: UncertainCallPlan<R>): Promise<ReconciledOutcome<R>> {
    const probe = await plan.probe()
    if (probe.status === 'confirmed') return { status: 'settled', via: 'probe' }
    if (probe.status === 'still_uncertain') return { status: 'unresolved' }
    if (plan.retry === undefined) return { status: 'absent' }
    return { status: 'settled', via: 'retry', result: await plan.retry() }
  }

  /**
   * Run one flush barrier: on success the barrier reports a flushed log; on
   * failure it closes admission and retains write ownership — the writer is
   * never released on top of an unflushed log.
   * @param flush - Flush all participating Session state through native persistence.
   * @returns the barrier outcome with the failure, when one occurred.
   */
  async flushBarrier(flush: () => Promise<void>): Promise<FlushBarrierResult> {
    try {
      await flush()
      return { flushed: true, admissionClosed: false, writerRetained: false, failure: undefined }
    } catch (failure: unknown) {
      this.closeAdmission()
      return { flushed: false, admissionClosed: true, writerRetained: true, failure }
    }
  }

  /**
   * Run one serialized process-tree stop: close admission, cancel only known
   * descendants, flush, and release the writer only after confirmed cleanup.
   * The host serializes calls for the same writer and retains unresolved
   * identities across restart.
   * @param options - Native live handles and the owning project's durable state adapter.
   * @returns `stopped` only after confirmed cleanup and flush; otherwise retained ownership.
   */
  async stopProject(options: StopProjectOptions): Promise<StopResult> {
    return await stopProjectProcessTree(options)
  }
}
