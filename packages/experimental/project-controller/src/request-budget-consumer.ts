/** Persistent precharge for model sending attempts in one host-selected project hierarchy. */
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-llm'
import type {} from './controller.ts'

/** Loader namespace for the project-wide model attempt budget. */
export const name = 'project-request-budget'
/** Live identity and durable accounting owners. */
export const inject = ['llm', 'agents', 'agentBindings', 'projectController']
/** Host-selected project root; unrelated traffic needs a separate plugin scope. */
export interface Config {
  /** Durable root Session identity selected by the host, never by model arguments. */
  controllerSessionId: string
}
/** Require an explicit project identity before accepting requests. */
export const Config: z<Config> = z.object({ controllerSessionId: z.string().min(1) })

/**
 * Precharge each admitted stream, including retries. Charged attempts are not refunded on cancellation or adapter failure.
 * Counts describe sending admission, not supplier billing. Disposal drains admission; the Agent owns already-admitted streams.
 * @param ctx - Context dedicated to the configured project hierarchy.
 * @param config - Host-selected root identity sharing this controller's durable budget.
 */
export function apply(ctx: Context, config: Config): void {
  if (config.controllerSessionId.trim() !== config.controllerSessionId) throw new Error('project request budget controllerSessionId must be trimmed')
  const lifetime = new AbortController()
  const active = new Set<Promise<void>>()
  ctx.on('llm/stream', (options, next) => {
    const agent = ctx.agents.currentInitiator()
    const signal = options.signal === undefined ? lifetime.signal : AbortSignal.any([options.signal, lifetime.signal])
    const authority = () => {
      signal.throwIfAborted()
      if (agent === undefined || ctx.agents.get(agent.id) !== agent || options.sessionId !== agent.session.id) {
        throw new Error('project request budget requires the actual live initiating Agent and matching request Session')
      }
      const binding = ctx.agentBindings.find(agent.session.id)
      const lead = binding?.role === 'worker' && binding.parentSessionId !== undefined
        ? ctx.agentBindings.find(binding.parentSessionId) : binding?.role === 'lead' ? binding : undefined
      const root = binding?.role === 'controller' ? binding
        : lead?.parentSessionId === undefined ? undefined : ctx.agentBindings.find(lead.parentSessionId)
      if (binding === undefined || root?.role !== 'controller' || root.parentSessionId !== undefined
        || String(root.sessionId) !== config.controllerSessionId
        || (binding.role !== 'controller' && (lead?.role !== 'lead' || lead.pluginId === undefined))
        || (binding.role === 'worker' && (binding.taskId === undefined || binding.pluginId !== lead?.pluginId))) {
        throw new Error('project request budget requires the configured root, its Lead, or that Lead’s scoped Worker')
      }
      for (const row of [binding, lead, root]) {
        if (row === undefined) continue
        const live = ctx.agents.get(row.agentId)
        if (live === undefined || live.session.id !== row.sessionId
          || (row === binding && live !== agent)) throw new Error('project request budget hierarchy contains a stale Agent binding')
      }
      return JSON.stringify([binding, lead, root])
    }
    return (async function* () {
      const done = Promise.withResolvers<void>()
      active.add(done.promise)
      try {
        const identity = authority()
        const unchanged = () => {
          if (authority() !== identity) throw new Error('project request budget hierarchy changed while admitting a request')
        }
        await ctx.projectController.chargeModelRequest({ beforePersist: unchanged })
        unchanged()
      } finally {
        active.delete(done.promise)
        done.resolve()
      }
      yield* next()
    })()
  })
  ctx.effect(() => async () => {
    lifetime.abort(new Error('project request budget consumer disposed'))
    await Promise.allSettled(active)
  })
}
