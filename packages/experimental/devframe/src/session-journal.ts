/** Serialized, schema-checked DevFrame writes over native Session persistence. */

import type {
  Session,
  SessionEvent,
  SessionEventMap,
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
 * admitting work against state that may not be on disk.
 */
export class DevFrameSessionJournal {
  private readonly tails = new WeakMap<Session, Promise<void>>()
  private readonly failures = new WeakMap<Session, DevFramePersistenceError>()

  /**
   * @param flush - Native `ctx.sessions.flush`-compatible durability callback.
   */
  constructor(private readonly flush: DevFrameFlush) {}

  /**
   * Validate, append, and durably flush one DevFrame event in order.
   * @param session - Controller Session that owns the event.
   * @param type - DevFrame event name.
   * @param data - Event payload to validate before appending.
   * @returns The accepted event after the durability checkpoint completes.
   * @throws {@link DevFramePersistenceError} when persistence is unavailable,
   * failed, or was previously latched failed for this Session.
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
