/**
 * Host-assembly listener withdrawing automatic goal continuation from a
 * fail-graded memory degradation. When a `devframe/task-warning` event with
 * grade `fail` is appended — the task's real failure evidence whose
 * acceptance required the memory operation — the driving agent's armed active
 * goal is disarmed through the native goal port, the same face the
 * goal-round-driver obeys: no further automatic round is reserved, a queued
 * continuation loses its armed precondition at pre-step, and the durable goal
 * phase is preserved for the human-authorized resume. The consumption lives
 * here, in the devframe domain: the driver package stays unedited and keeps
 * reading the goal state this listener changes. Graded
 * `complete-with-warning` events are deliberately untouched — tolerated
 * degradations do not stop a task.
 * @module @deepseek-ai/dsh-experimental-devframe/task-fail-continuation
 */

import type { Context } from '@deepseek-ai/cordis'

/** Cordis plugin name. */
export const name = 'devframe-task-fail-disarm'
/** The listener reads the agent registry and the native goal port. */
export const inject: string[] = ['agents', 'goals']

/**
 * Install the fail-grade → disarm consumption.
 *
 * The disarm is contained: it runs synchronously inside the session append
 * dispatch that publishes the graded event, and a failure here must not abort
 * that append — the graded record is the durable evidence either way, and the
 * human-authorized resume remains the recovery path for a goal that stayed
 * armed.
 * @param ctx - The mounting context.
 * @returns The plugin disposer.
 */
export function apply(ctx: Context): () => void {
  const disposer = ctx.on('session/event', (session, event) => {
    if (event.type !== 'devframe/task-warning' || event.data.grade !== 'fail') return
    const agent = ctx.agents.get(session.id)
    if (agent === undefined) return
    try {
      const goal = ctx.goals.get(agent)
      if (goal === undefined || goal.phase !== 'active' || goal.activation !== 'armed') return
      ctx.goals.disarm(agent)
    } catch {
      // The native goal port moved or refused between the read and the
      // disarm inside this synchronous dispatch; aborting the append that
      // publishes the graded record would be worse, so the goal keeps its
      // state and the human-authorized resume stays the recovery path.
    }
  })
  return () => {
    void disposer()
  }
}
