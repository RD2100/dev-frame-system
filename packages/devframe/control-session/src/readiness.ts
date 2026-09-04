import type {
  DevFrameReadinessBlockedCode,
  DevFrameReadinessSnapshot,
} from './types.ts'

/** Maximum duration of one readiness long poll before returning unchanged state. */
export const DEVFRAME_READINESS_WAIT_MS = 20_000

interface GenerationRecord {
  readonly generation: number
  readonly abort: AbortController
}

type ReadinessUpdate =
  | { readonly status: 'starting'; readonly generation: number }
  | { readonly status: 'ready'; readonly generation: number; readonly sessionId: string }
  | {
    readonly status: 'blocked'
    readonly generation: number
    readonly code: DevFrameReadinessBlockedCode
  }
  | { readonly status: 'stopping'; readonly generation: number }

/** Generation ticket used by the bootstrap owner. */
export interface DevFrameReadinessGeneration {
  readonly generation: number
  readonly signal: AbortSignal
}

function snapshotCopy(snapshot: DevFrameReadinessSnapshot): DevFrameReadinessSnapshot {
  return { ...snapshot }
}

/**
 * Monotonic readiness state with generation fencing and cancellable long polls.
 * Old generations can finish, but can never publish over the current one.
 */
export class DevFrameReadinessState {
  private generation = 0
  private revision = 0
  private active?: GenerationRecord
  private value: DevFrameReadinessSnapshot = {
    status: 'blocked',
    generation: 0,
    revision: 0,
    code: 'BOOTSTRAP_NOT_STARTED',
  }

  private readonly waiters = new Set<() => void>()

  /**
   * Start a new generation and invalidate every older publisher.
   * @returns the generation ticket for the bootstrap owner.
   */
  begin(): DevFrameReadinessGeneration {
    this.active?.abort.abort()
    const active: GenerationRecord = {
      generation: ++this.generation,
      abort: new AbortController(),
    }
    this.active = active
    this.publish({ status: 'starting', generation: active.generation })
    return { generation: active.generation, signal: active.abort.signal }
  }

  /**
   * Publish a ready Session only when the caller still owns the generation.
   * @param generation - generation ticket number.
   * @param sessionId - durable Controller Session identifier.
   * @returns whether the update was accepted.
   */
  ready(generation: number, sessionId: string): boolean {
    if (!this.isCurrent(generation)) return false
    this.publish({ status: 'ready', generation, sessionId })
    return true
  }

  /**
   * Publish one bounded failure only when the caller still owns the generation.
   * @param generation - generation ticket number.
   * @param code - stable readiness failure code.
   * @returns whether the update was accepted.
   */
  blocked(generation: number, code: DevFrameReadinessBlockedCode): boolean {
    if (!this.isCurrent(generation)) return false
    this.publish({ status: 'blocked', generation, code })
    return true
  }

  /**
   * Stop admission and cancel in-flight work for the current generation.
   * @param generation - generation ticket number.
   * @returns whether the update was accepted.
   */
  stopping(generation: number): boolean {
    if (!this.isCurrent(generation)) return false
    this.publish({ status: 'stopping', generation })
    this.active?.abort.abort()
    return true
  }

  /**
   * Whether a generation may still publish and admit work.
   * @param generation - generation ticket number.
   * @returns whether the generation is still current.
   */
  isCurrent(generation: number): boolean {
    return this.active?.generation === generation && !this.active.abort.signal.aborted
  }

  /**
   * Detached current state for direct Host callers and tests.
   * @returns a copy of the current readiness snapshot.
   */
  snapshot(): DevFrameReadinessSnapshot {
    return snapshotCopy(this.value)
  }

  /**
   * Wait for a revision change, cancellation, or the bounded poll timeout.
   * A future/stale revision returns immediately so a reconnect can recover.
   * @param afterRevision - revision already observed by the caller.
   * @param signal - cancellation signal for the long poll.
   * @returns the latest readiness snapshot.
   */
  async wait(afterRevision: number, signal: AbortSignal): Promise<DevFrameReadinessSnapshot> {
    if (!Number.isSafeInteger(afterRevision) || afterRevision < -1) {
      throw new Error('DevFrame readiness revision must be an integer of at least -1')
    }
    if (afterRevision !== this.value.revision) return this.snapshot()
    if (signal.aborted) throw new Error('DevFrame readiness wait aborted')

    await new Promise<void>((resolve, reject) => {
      let settled = false
      const finish = (failure?: Error): void => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        signal.removeEventListener('abort', onAbort)
        this.waiters.delete(onChange)
        if (failure === undefined) resolve()
        else reject(failure)
      }
      const onChange = (): void => { finish() }
      const onAbort = (): void => { finish(new Error('DevFrame readiness wait aborted')) }
      const timer = setTimeout(onChange, DEVFRAME_READINESS_WAIT_MS)
      this.waiters.add(onChange)
      signal.addEventListener('abort', onAbort, { once: true })
    })
    return this.snapshot()
  }

  private publish(next: ReadinessUpdate): void {
    this.value = { ...next, revision: ++this.revision }
    for (const notify of [...this.waiters]) notify()
  }
}
