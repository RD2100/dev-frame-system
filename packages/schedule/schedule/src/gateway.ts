/** Session-addressed browser controls for durable Schedule records. */

import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import {
  foldScheduleEvents,
  renderEveryReminderBatchFraming,
  renderReminderFraming,
  resolveEveryOccurrence,
  ScheduleId as brandScheduleId,
} from './domain.ts'
import { flushSchedulePersistence } from './persistence.ts'
import { runScheduleTransaction } from './transaction.ts'
import type {
  ScheduleDeleteRemoteValue,
  SchedulePauseRemoteValue,
  ScheduleResumeRemoteValue,
  ScheduleRunRemoteValue,
  ScheduleSessionRequest,
} from './types.ts'
import type { ScheduleId } from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Session-addressed Schedule controls exposed to browser clients. */
    schedule: ScheduleGateway
  }

  interface Events {
    /** Wake the exact Schedule runtime after a browser mutation.
     * @mode emit
     * @param sessionId - Session whose Schedule runtime must recalculate.
     */
    'schedule/request-drive'(sessionId: SessionId): void
  }
}

interface SessionAgentResolver {
  resolveAgent(sessionId: SessionId): Promise<{ readonly agent: Agent } | { readonly error: Error }>
}

/** Host Remote owner for browser Schedule mutations. */
export class ScheduleGateway extends TypertRemoteService {
  static inject = ['agents', 'sessions']

  constructor(ctx: Context) {
    super(ctx, 'schedule')
  }

  /** Pause one active Schedule record. */
  @Remote('pause')
  pause(request: ScheduleSessionRequest): Promise<SchedulePauseRemoteValue> {
    return this.mutate(request, (agent, id) => {
      const folded = foldScheduleEvents(agent.session.ownEvents())
      const record = folded.active.find(item => item.id === id)
      if (record === undefined) throw new Error(`schedule record "${id}" was not found`)
      if (record.paused) throw new Error(`schedule record "${id}" is already paused`)
      agent.session.append('schedule/change', { version: 1, operation: 'pause', id })
      return { id, paused: true }
    })
  }

  /** Resume one paused Schedule record. */
  @Remote('resume')
  resume(request: ScheduleSessionRequest): Promise<ScheduleResumeRemoteValue> {
    return this.mutate(request, (agent, id) => {
      const folded = foldScheduleEvents(agent.session.ownEvents())
      const record = folded.active.find(item => item.id === id)
      if (record === undefined) throw new Error(`schedule record "${id}" was not found`)
      if (!record.paused) throw new Error(`schedule record "${id}" is already active`)
      agent.session.append('schedule/change', { version: 1, operation: 'resume', id })
      return { id, resumed: true }
    })
  }

  /** Delete one active Schedule record. */
  @Remote('delete')
  delete(request: ScheduleSessionRequest): Promise<ScheduleDeleteRemoteValue> {
    return this.mutate(request, (agent, id) => {
      const folded = foldScheduleEvents(agent.session.ownEvents())
      if (!folded.active.some(item => item.id === id)) throw new Error(`schedule record "${id}" was not found`)
      agent.session.append('schedule/change', { version: 1, operation: 'delete', id })
      return { id, deleted: true }
    })
  }

  /** Queue one immediate delivery for an active Schedule record. */
  @Remote('run')
  run(request: ScheduleSessionRequest): Promise<ScheduleRunRemoteValue> {
    return this.mutate(request, (agent, id) => {
      const folded = foldScheduleEvents(agent.session.ownEvents())
      const record = folded.active.find(item => item.id === id)
      if (record === undefined) throw new Error(`schedule record "${id}" was not found`)
      if (record.paused) throw new Error(`schedule record "${id}" is paused`)
      const now = Date.now()
      let acceptedAt: string | undefined
      const text = record.kind === 'every'
        ? (() => {
          const acceptedAtEpoch = Math.max(now, Date.parse(record.scheduledAt))
          acceptedAt = new Date(acceptedAtEpoch).toISOString()
          const occurrence = resolveEveryOccurrence(record, acceptedAtEpoch)
          return renderEveryReminderBatchFraming([{ record, occurrenceAt: occurrence.occurrenceAt }])
        })()
        : renderReminderFraming(record)
      agent.session.append('schedule/change', acceptedAt === undefined
        ? { version: 1, operation: 'dispatch', id }
        : { version: 1, operation: 'dispatch', id, acceptedAt })
      try {
        agent.followup(createUserMessage({
          content: [{ type: 'text', text }],
          source: { kind: 'schedule', scheduleIds: [id] },
        }))
      } catch (error: unknown) {
        try {
          agent.session.append('schedule/change', {
            version: 1,
            operation: 'result',
            id,
            outcome: 'failure',
            error: (error instanceof Error ? error.message : String(error)).slice(0, 240),
          })
        } catch {
          // The dispatch is durable; a failed receipt remains best effort.
        }
        throw error
      }
      return { id, started: true }
    })
  }

  private async mutate<T>(
    request: ScheduleSessionRequest,
    operation: (agent: Agent, id: ScheduleId) => T,
  ): Promise<T> {
    const id = request.id.trim()
    if (id.length === 0 || id !== request.id) throw new Error('Schedule id must be non-empty without surrounding whitespace')
    const agent = await this.resolveAgent(request.sessionId)
    return runScheduleTransaction(agent, async () => {
      const result = operation(agent, brandScheduleId(id))
      await flushSchedulePersistence(this.ctx, agent.session)
      this.ctx.emit('schedule/request-drive', request.sessionId)
      return result
    })
  }

  private async resolveAgent(sessionId: SessionId): Promise<Agent> {
    const live = this.ctx.agents.get(sessionId)
    if (live !== undefined) return live
    const controller = (this.ctx as unknown as { readonly sessionController?: SessionAgentResolver }).sessionController
    if (controller === undefined) throw new Error(`session "${sessionId}" is not live`)
    const resolved = await controller.resolveAgent(sessionId)
    if ('error' in resolved) throw resolved.error
    return resolved.agent
  }
}

export default ScheduleGateway
