/**
 * The bridge's timer loop: self-rescheduling polls that never overlap, run
 * outside any inherited agent-initiator boundary, contain every failure as a
 * logged warning, and dispose to quiescence by awaiting the in-flight poll.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/loop
 */

import type { AgentRegistry } from '@deepseek-ai/dsh-agent'

/** Collaborators one poll loop needs; all structural, so tests can fake them. */
export interface PollLoopDeps {
  /** Milliseconds between the end of one poll and the start of the next. */
  readonly intervalMs: number
  /** One poll; failures reject and the loop contains them. */
  readonly run: () => Promise<void>
  /** The agents registry's initiator-clearing boundary; the poll must not inherit an ambient initiator. */
  readonly withoutInitiator: Pick<AgentRegistry, 'withoutInitiator'>['withoutInitiator']
  /** Process-local warning sink for contained poll failures. */
  readonly log: (message: string) => void
}

/**
 * One self-rescheduling poll timer. Each tick runs after the previous poll
 * settled, so polls never overlap; disposal clears the armed timer and awaits
 * the in-flight poll, so teardown reaches quiescence instead of abandoning a
 * half-forwarded delivery.
 */
export class PollLoop {
  private readonly deps: PollLoopDeps
  private timer: ReturnType<typeof setTimeout> | undefined
  private active: Promise<void> | undefined
  private disposed = false

  /**
   * @param deps - Rhythm, poll, initiator boundary, and warning sink.
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
      await this.deps.withoutInitiator(() => this.deps.run())
    } catch (error: unknown) {
      this.deps.log(`delivery poll failed: ${error instanceof Error ? error.message : String(error)}`)
    }
    this.schedule()
  }
}
