/** Serialized, schema-checked DevFrame writes over native Session persistence. */

import type {
  Session,
  SessionEvent,
  SessionEventMap,
  SessionId,
} from '@deepseek-ai/dsh-session'
import {
  decodeDevFramePayload,
  type DevFrameEventType,
  type DevFrameRepairCause,
} from './events.ts'
import type { GoalBindingIdentity, RepairRoundState } from './controller/goal-binding.ts'
import { assertRepairAdmission, foldDevFrameState, sameRepairCause } from './projection.ts'
import { evaluateRepairRoundAdmission, resolveRepairLimit, type RepairRoundAdmission } from './repair-limit.ts'

// Every journal using one live Session shares its write order and uncertain-flush latch.
const tails = new WeakMap<Session, Promise<void>>()
const failures = new WeakMap<Session, DevFramePersistenceError>()

type AppendDevFrameEvent = <T extends DevFrameEventType>(
  type: T,
  data: SessionEventMap[T],
) => SessionEvent<T>

/** Native durability callback used by the DevFrame event writer. */
export type DevFrameFlush = (session: Session) => Promise<boolean | void>

/** Checks executed inside the Session append queue before an event becomes visible. */
export interface DevFrameAppendOptions {
  /** Refresh asynchronous source observations while owning the append queue. */
  readonly prepare?: () => Promise<void>
  /** Recheck synchronous authority before preparation and immediately before append. */
  readonly beforeAppend?: () => void
}

/**
 * Reviewer authorization seam consulted before any `devframe/review` append.
 * Implementations resolve the submitted `reviewerSessionId` against the
 * deployed DevFrame role authority (the live role policy or the durable
 * role-policy assignments) and must reject any Session the policy has not
 * assigned the reviewer role with a stable machine-routable error.
 */
export interface DevFrameReviewGate {
  /**
   * Reject a review submission whose Session holds no reviewer role.
   * @param sessionId - Reviewer Session identity carried by the review payload.
   * @returns Nothing; a rejection throws before the event reaches the Session log.
   */
  requireReviewer(sessionId: SessionId): void
}

/** Structured failure that blocks later DevFrame mutations after a flush error. */
export class DevFramePersistenceError extends Error {
  /** Stable failure classification for host admission and diagnostics. */
  readonly code: 'unavailable' | 'failed' | 'blocked'

  /**
   * @param message - Human-readable persistence failure.
   * @param code - Stable failure classification.
   * @param options - Original backend failure, when one exists.
   */
  constructor(
    message: string,
    code: DevFramePersistenceError['code'],
    options?: ErrorOptions,
  ) {
    super(message, options)
    this.name = 'DevFramePersistenceError'
    this.code = code
  }
}

/**
 * Native Session writer for DevFrame records. One writer serializes appends per
 * Session and latches a failed durability checkpoint so callers cannot continue
 * admitting work against state that may not be on disk. Review events are
 * additionally cross-authorized through the required review gate, so a writer
 * cannot be built without wiring the deployed reviewer role authority.
 */
export class DevFrameSessionJournal {
  private readonly flush: DevFrameFlush
  private readonly reviewGate: DevFrameReviewGate

  /**
   * @param flush - Native `ctx.sessions.flush`-compatible durability callback.
   * @param reviewGate - Reviewer role authority consulted for every review append.
   */
  constructor(
    flush: DevFrameFlush,
    reviewGate: DevFrameReviewGate,
  ) {
    this.flush = flush
    this.reviewGate = reviewGate
  }

  /**
   * Validate, cross-authorize, append, and durably flush one DevFrame event in order.
   * @param session - Controller Session that owns the event.
   * @param type - DevFrame event name.
   * @param data - Event payload to validate before appending.
   * @param options - Source preparation and authority checks executed inside the append queue.
   * @returns The accepted event after the durability checkpoint completes.
   * @throws {@link DevFramePersistenceError} when persistence is unavailable,
   * failed, or was previously latched failed for this Session.
   * @throws The review gate's rejection when a review names a Session without
   * the reviewer role; the event is not appended and the failure does not latch.
   */
  append<T extends DevFrameEventType>(
    session: Session,
    type: T,
    data: SessionEventMap[T],
    options: DevFrameAppendOptions = {},
  ): Promise<SessionEvent<T>> {
    return this.enqueue(session, async () => {
      options.beforeAppend?.()
      if (options.prepare !== undefined) await options.prepare()
      options.beforeAppend?.()
      return await this.appendOwned(session, type, data)
    })
  }

  /**
   * Persist one correction admission, reusing the receipt for the same cause.
   * @param session - Live controller Session and sole durable log owner.
   * @param request - Exact Goal, existing failure evidence, and configured limit.
   * @param options - Authority and source checks executed in the shared append queue.
   * @returns An admitted round after flush, or exhaustion without an append.
   */
  admitRepair(session: Session, request: {
    readonly identity: GoalBindingIdentity
    readonly cause: DevFrameRepairCause
    readonly repairLimit: number
  }, options: DevFrameAppendOptions = {}): Promise<RepairRoundAdmission> {
    return this.enqueue(session, async () => {
      options.beforeAppend?.()
      if (options.prepare !== undefined) await options.prepare()
      options.beforeAppend?.()
      const repairLimit = resolveRepairLimit({ repairLimit: request.repairLimit })
      const state = foldDevFrameState(session.snapshotEvents(), session.header)
      if (state.failure !== null) throw new Error(`DevFrame projection is unavailable: ${state.failure}`)
      const current = state.bindings.at(-1)
      if (session.id !== request.identity.controllerSessionId || current?.goalId !== request.identity.goalId) {
        throw new Error('Repair admission requires the current controller Goal')
      }
      const admissions = state.repairAdmissions.filter(record => record.identity.goalId === request.identity.goalId)
      if (admissions.some(record => record.repairLimit !== repairLimit)) throw new Error('Repair limit changed for this Goal')
      const existing = admissions.find(record => sameRepairCause(record.cause, request.cause))
      if (existing !== undefined) return {
        kind: 'admitted', repairRound: existing.repairRound, remainingRepairRounds: repairLimit - existing.repairRound,
      }
      const verdict = evaluateRepairRoundAdmission({ repairLimit, consumedRepairRounds: admissions.length })
      if (verdict.kind === 'rejected') return verdict
      await this.appendOwned(session, 'devframe/repair-admission', {
        version: 1, identity: request.identity, cause: request.cause, repairRound: verdict.repairRound, repairLimit,
      })
      return verdict
    })
  }

  /**
   * Read durable correction consumption without opening another accounting owner.
   * @param session - Live controller Session whose log owns the admissions.
   * @param identity - Exact Goal to inspect.
   * @param repairLimit - Configured correction limit, unchanged within the Goal.
   * @returns Consumption reconstructed from the Session log.
   */
  repairRoundState(session: Session, identity: GoalBindingIdentity, repairLimit: number): RepairRoundState {
    resolveRepairLimit({ repairLimit })
    if (failures.has(session)) throw new DevFramePersistenceError('Repair accounting is blocked after a persistence failure', 'blocked')
    const state = foldDevFrameState(session.snapshotEvents(), session.header)
    if (state.failure !== null) throw new Error(`DevFrame projection is unavailable: ${state.failure}`)
    if (identity.controllerSessionId !== session.id || !state.bindings.some(binding => binding.goalId === identity.goalId)) {
      throw new Error('Repair accounting requires a bound controller Goal')
    }
    const admissions = state.repairAdmissions.filter(record => record.identity.goalId === identity.goalId)
    if (admissions.some(record => record.repairLimit !== repairLimit)) throw new Error('Repair limit changed for this Goal')
    return { repairLimit, consumedRepairRounds: admissions.length, remainingRepairRounds: Math.max(0, repairLimit - admissions.length) }
  }

  /** Run an operation after earlier writers settle, preserving failures across journal instances. */
  private enqueue<T>(session: Session, operation: () => Promise<T>): Promise<T> {
    const previous = tails.get(session) ?? Promise.resolve()
    const run = previous.then(async () => {
      const priorFailure = failures.get(session)
      if (priorFailure !== undefined) {
        throw new DevFramePersistenceError(
          `DevFrame Session "${session.id}" is blocked after a persistence failure`,
          'blocked',
          { cause: priorFailure },
        )
      }
      return await operation()
    })
    tails.set(session, run.then(() => undefined, () => undefined))
    return run
  }

  /** Append while owning the Session queue; callers must not enqueue this operation again. */
  private async appendOwned<T extends DevFrameEventType>(session: Session, type: T, data: SessionEventMap[T]): Promise<SessionEvent<T>> {
    const decoded = decodeDevFramePayload(type, data)
    if (type === 'devframe/review') {
      // The discriminant selects the decoded review payload.
      this.reviewGate.requireReviewer((decoded as SessionEventMap['devframe/review']).reviewerSessionId)
    }
    if (type === 'devframe/repair-admission') {
      assertRepairAdmission(foldDevFrameState(session.snapshotEvents(), session.header), decoded as SessionEventMap['devframe/repair-admission'])
    }
    // Session.append's conditional type cannot prove this closed non-surface subset.
    const append = session.append.bind(session) as unknown as AppendDevFrameEvent
    const event = append(type, decoded)
    try {
      if (await this.flush(session) === false) throw new DevFramePersistenceError(
        `DevFrame Session "${session.id}" has no active persistence backend`, 'unavailable',
      )
    } catch (error: unknown) {
      const failure = error instanceof DevFramePersistenceError ? error : new DevFramePersistenceError(
        `DevFrame Session "${session.id}" could not be persisted`, 'failed', { cause: error },
      )
      failures.set(session, failure)
      throw failure
    }
    return event
  }

  /**
   * Whether this writer has blocked further mutations for one Session.
   * @param session - Session whose journal status is queried.
   * @returns Whether a persistence failure has been latched for the Session.
   */
  isBlocked(session: Session): boolean {
    return failures.has(session)
  }

  /**
   * Join prior evidence writes and flush the current Session before admission.
   * @param session - Session whose evidence must be durable.
   * @returns A synchronous guard refusing failure or any later queued evidence write.
   * @throws DevFramePersistenceError if the checkpoint fails or its guard is stale.
   */
  async checkpoint(session: Session): Promise<() => void> {
    const barrier = this.enqueue(session, async () => {
      try {
        if (await this.flush(session) === false) throw new DevFramePersistenceError('Completion persistence is unavailable', 'unavailable')
      } catch (error) {
        const failure = error instanceof DevFramePersistenceError ? error
          : new DevFramePersistenceError('Completion evidence could not be persisted', 'failed', { cause: error })
        failures.set(session, failure)
        throw failure
      }
    })
    const checkpoint = tails.get(session)
    await barrier
    return () => {
      if (failures.has(session) || tails.get(session) !== checkpoint) {
        throw new DevFramePersistenceError('Completion evidence changed or its durability failed after the checkpoint', 'blocked')
      }
    }
  }
}
