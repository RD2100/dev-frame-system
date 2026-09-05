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
} from './events.ts'

type AppendDevFrameEvent = <T extends DevFrameEventType>(
  type: T,
  data: SessionEventMap[T],
) => SessionEvent<T>

/** Native durability callback used by the DevFrame event writer. */
export type DevFrameFlush = (session: Session) => Promise<boolean | void>

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
  private readonly tails = new WeakMap<Session, Promise<void>>()
  private readonly failures = new WeakMap<Session, DevFramePersistenceError>()

  /**
   * @param flush - Native `ctx.sessions.flush`-compatible durability callback.
   * @param reviewGate - Reviewer role authority consulted for every review append.
   */
  constructor(
    private readonly flush: DevFrameFlush,
    private readonly reviewGate: DevFrameReviewGate,
  ) {}

  /**
   * Validate, cross-authorize, append, and durably flush one DevFrame event in order.
   * @param session - Controller Session that owns the event.
   * @param type - DevFrame event name.
   * @param data - Event payload to validate before appending.
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
  ): Promise<SessionEvent<T>> {
    const previous = this.tails.get(session) ?? Promise.resolve()
    let event: SessionEvent<T> | undefined
    const run = previous.then(async () => {
      const priorFailure = this.failures.get(session)
      if (priorFailure !== undefined) {
        throw new DevFramePersistenceError(
          `DevFrame Session "${session.id}" is blocked after a persistence failure`,
          'blocked',
          { cause: priorFailure },
        )
      }
      const decoded = decodeDevFramePayload(type, data)
      if (type === 'devframe/review') {
        // The discriminant check proves the decoded payload is a review event.
        const review = decoded as SessionEventMap['devframe/review']
        this.reviewGate.requireReviewer(review.reviewerSessionId)
      }
      // DevFrameEventType is a closed non-surface subset, but Session.append's
      // generic conditional cannot prove that fact through this class method.
      const append = session.append.bind(session) as unknown as AppendDevFrameEvent
      event = append(type, decoded)
      try {
        const durable = await this.flush(session)
        if (durable === false) {
          throw new DevFramePersistenceError(
            `DevFrame Session "${session.id}" has no active persistence backend`,
            'unavailable',
          )
        }
      } catch (error: unknown) {
        const failure = error instanceof DevFramePersistenceError
          ? error
          : new DevFramePersistenceError(
            `DevFrame Session "${session.id}" could not be persisted`,
            'failed',
            { cause: error },
          )
        this.failures.set(session, failure)
        throw failure
      }
    }, () => {
      const priorFailure = this.failures.get(session)
      if (priorFailure !== undefined) {
        throw new DevFramePersistenceError(
          `DevFrame Session "${session.id}" is blocked after a persistence failure`,
          'blocked',
          { cause: priorFailure },
        )
      }
      throw new DevFramePersistenceError(
        `DevFrame Session "${session.id}" has an unresolved earlier journal operation`,
        'blocked',
      )
    })
    this.tails.set(session, run.then(() => undefined, () => undefined))
    return run.then(() => {
      if (event === undefined) {
        throw new Error(`DevFrame journal completed without an event for Session "${session.id}"`)
      }
      return event
    })
  }

  /**
   * Whether this writer has blocked further mutations for one Session.
   * @param session - Session whose journal status is queried.
   * @returns Whether a persistence failure has been latched for the Session.
   */
  isBlocked(session: Session): boolean {
    return this.failures.has(session)
  }
}
