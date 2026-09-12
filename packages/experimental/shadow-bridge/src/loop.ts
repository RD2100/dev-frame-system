/**
 * The bridge's safety-net timer: self-rescheduling reconciliation polls at
 * the configured cadence that never overlap, contain every failure as a
 * logged warning, and dispose to quiescence by awaiting the in-flight poll.
 * The router's `shadow/delivery-received` event is the primary trigger; this
 * timer only bounds how long work the event path missed may wait.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/loop
 */

/** Collaborators one safety-net loop needs; all structural, so tests can fake them. */
export interface PollLoopDeps {
  /** Milliseconds between the end of one safety-net poll and the start of the next. */
  readonly intervalMs: number
  /** One poll; failures reject and the loop contains them. */
  readonly run: () => Promise<void>
  /** Process-local warning sink for contained poll failures. */
  readonly log: (message: string) => void
}

/**
 * One self-rescheduling safety-net timer. Each tick runs after the previous
 * poll settled, so polls never overlap; disposal clears the armed timer and
 * awaits the in-flight poll, so teardown reaches quiescence instead of
 * abandoning a half-forwarded delivery.
 */
export class PollLoop {
  private readonly deps: PollLoopDeps
  private timer: ReturnType<typeof setTimeout> | undefined
  private active: Promise<void> | undefined
  private disposed = false

  /**
   * @param deps - Cadence, poll, and warning sink.
   */
  constructor(deps: PollLoopDeps) {
    this.deps = deps
  }

  /** Arm the first tick. */
  start(): void {
    this.schedule()
  }

  /**
   * Stop future polls and await the in-flight one. Idempotent; the returned
   * promise settles after the in-flight poll settles, whichever way.
   * @returns resolution after quiescence.
   */
  async dispose(): Promise<void> {
    this.disposed = true
    if (this.timer !== undefined) clearTimeout(this.timer)
    this.timer = undefined
    const pending = this.active
    if (pending !== undefined) await Promise.allSettled([pending])
  }

  /** Arm one tick unless disposed. */
  private schedule(): void {
    if (this.disposed) return
    this.timer = setTimeout(() => {
      this.timer = undefined
      this.active = this.drive()
    }, this.deps.intervalMs)
  }

  /** Run one contained poll, then rearm. Every failure logs and the loop continues. */
  private async drive(): Promise<void> {
    try {
      await this.deps.run()
    } catch (error: unknown) {
      this.deps.log(`delivery poll failed: ${error instanceof Error ? error.message : String(error)}`)
    }
    this.schedule()
  }
}
