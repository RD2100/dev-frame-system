/**
 * Agent-scoped durable one-shot and fixed-rate reminders over the session event log.
 * @module @deepseek-ai/dsh-schedule
 */

import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { Session, SessionEvent } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-persistence'
// Type-only: resolves ctx.sessionProjections for the optional projection child.
import type {} from '@deepseek-ai/dsh-session-projection'
import { scheduleHistoryProjectionDefinition, scheduleProjectionDefinition } from './projection.ts'
import { ScheduleRuntime } from './runtime.ts'
import { registerScheduleTools } from './tools.ts'
import type { ScheduleId } from './types.ts'

export type * from './types.ts'
export { SCHEDULE_TEMPLATES } from './types.ts'
export {
  SCHEDULE_CHANGE_VERSION,
  MIN_EVERY_INTERVAL_SECONDS,
  ScheduleId,
  ScheduleDedupeKey,
  ScheduleInputError,
  ScheduleLogError,
  allocateScheduleId,
  createAfterScheduleRecord,
  createAtScheduleRecord,
  createEveryScheduleRecord,
  decodeScheduleChange,
  foldScheduleEvents,
  foldScheduleHistory,
  renderReminderFraming,
  renderEveryReminderBatchFraming,
  resolveEveryOccurrence,
  scheduleView,
} from './domain.ts'
export { registerScheduleTools } from './tools.ts'

/** Cordis function-plugin name. */
export const name = 'schedule'
/** Services required before future root agents can receive Schedule. */
export const inject = ['agents', 'sessions', 'tools', 'sessionPersistence']

type OwnerCleanup = () => void | Promise<void>

/** Install Schedule only for root agents published after this plugin loads. */
export function apply(ctx: Context): void {
  ctx.inject(['sessionProjections'], (projectionCtx) => {
    projectionCtx.sessionProjections.register(scheduleProjectionDefinition)
    projectionCtx.sessionProjections.register(scheduleHistoryProjectionDefinition)
  })

  const runtimes = new Map<Agent, OwnerCleanup>()
  const pending = new Map<Session, { turn: number; ids: Set<ScheduleId> }>()

  /** Record the terminal outcome for one automatically queued reminder turn. */
  const appendOutcomes = (session: Session, ids: readonly ScheduleId[], outcome: 'success' | 'failure' | 'cancelled', error?: string): void => {
    if (ids.length === 0) return
    queueMicrotask(() => {
      for (const id of ids) {
        try {
          session.append('schedule/change', {
            version: 1,
            operation: 'result',
            id,
            outcome,
            ...(error === undefined ? {} : { error: error.slice(0, 240) }),
          })
        } catch (appendError: unknown) {
          ctx.logger.warn(`schedule: outcome append failed: ${appendError instanceof Error ? appendError.message : String(appendError)}`)
        }
      }
    })
  }

  const stopOutcomes = ctx.on('session/event', (session: Session, event: SessionEvent) => {
    if (event.type === 'turn/start') {
      pending.set(session, { turn: event.data.turn, ids: new Set() })
      return
    }
    if (event.type === 'user/message' && event.data.source.kind === 'schedule') {
      const state = pending.get(session)
      if (state !== undefined) {
        for (const id of event.data.source.scheduleIds) state.ids.add(id)
      }
      return
    }
    if (event.type === 'turn/end') {
      const state = pending.get(session)
      if (state === undefined || state.turn !== event.data.turn) return
      pending.delete(session)
      const reason = event.data.reason.kind
      const outcome = reason === 'completed' ? 'success' : reason === 'aborted' || reason === 'interrupted' ? 'cancelled' : 'failure'
      appendOutcomes(session, [...state.ids], outcome, reason === 'completed' ? undefined : reason)
    }
  })
  const stopDiscarded = ctx.on('agent/inbox/discarded', ({ agent, message }) => {
    if (message.source.kind !== 'schedule') return
    appendOutcomes(agent.session, message.source.scheduleIds, 'cancelled', 'schedule message was discarded before execution')
  })
  let stopping = false

  ctx.effect(() => {
    const stopCreated = ctx.on('agent/created', ({ agent }) => {
      if (stopping || runtimes.has(agent) || !ctx.agents.roots().includes(agent)) return
      const runtime = new ScheduleRuntime(ctx, agent)
      const cleanup: OwnerCleanup = agent.ctx.effect(() => {
        const disposeTools = registerScheduleTools(ctx, agent.ctx, agent, () => { runtime.requestDrive() })
        const stopStatus = agent.ctx.on('agent/status', ({ status }) => {
          if (status === 'idle' && agent.session.snapshotEvents().some(event => event.type === 'schedule/change')) {
            runtime.requestDrive()
          }
        })
        runtime.start()
        return async () => {
          stopStatus()
          disposeTools()
          try {
            await runtime.dispose()
          } finally {
            if (runtimes.get(agent) === cleanup) runtimes.delete(agent)
          }
        }
      }, 'schedule.runtime()')
      runtimes.set(agent, cleanup)
    })

    return async () => {
      stopping = true
      stopOutcomes()
      stopDiscarded()
      pending.clear()
      stopCreated()
      const cleanups = [...runtimes.values()]
      runtimes.clear()
      await Promise.allSettled(cleanups.map(cleanup => Promise.resolve(cleanup())))
    }
  }, 'schedule.lifecycle()')
}
