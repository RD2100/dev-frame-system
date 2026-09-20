/** Root-controller task planning and development admission over the existing project service. */
import type { Context } from '@deepseek-ai/cordis'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-worktree-registry'
import type {} from './controller.ts'
import { resolveControllerAuthority, resolveTaskStartAuthority, taskStartUnchanged } from './start-authority.ts'

/** Loader namespace name; the project controller service is mounted separately. */
export const name = 'project-task-tool'
/** Live authorities required for task planning and Worker admission. */
export const inject = ['tools', 'agents', 'sessions', 'sessionProjections', 'projectController', 'agentBindings', 'workspaceRegistry', 'worktreeRegistry']

/**
 * Register root-only planning and start actions; neither action records completion or review.
 * @param ctx - Host context with the existing project controller and live authorities.
 */
export function apply(ctx: Context): void {
  let stopped = false
  const tails = new Map<string, Promise<unknown>>()
  ctx.effect(() => async () => {
    stopped = true
    await Promise.allSettled(tails.values())
    tails.clear()
  })
  ctx.tools.register(defineTool({
    name: 'project_task',
    description: 'Plan a task in the current authorized Goal, or start its already registered Worker. Only the actual root controller may call this tool. Plan requires title and pluginId. Start derives the Worker from registered task bindings and may queue one briefing after development admission succeeds. Repeated starts refuse without re-sending the briefing. This tool does not complete, review, or submit work.',
    parameters: {
      action: { type: 'string', required: true, description: 'plan or start.' },
      taskId: { type: 'string', required: true, description: 'Task id already authorized by the current Goal.' },
      title: { type: 'string', description: 'Required for plan: non-empty task title.' },
      pluginId: { type: 'string', description: 'Required for plan: plugin scope.' },
      briefing: { type: 'string', description: 'Optional for start: instructions queued once to the registered Worker after admission.' },
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {
        taskId: { type: 'string', required: true }, state: { type: 'string', required: true },
        briefingQueued: { type: 'boolean', required: true },
      } },
      render: (_args, value) => [{ type: 'text', text: `Task ${value.taskId}: ${value.state}; briefing queued: ${value.briefingQueued}.` }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (args.action !== 'plan' && args.action !== 'start') throw new Error('project_task action must be plan or start')
      const trimmed = (value: string | undefined, label: string): string => {
        if (value === undefined || value.length === 0 || value.trim() !== value) throw new Error(`project_task ${label} must be non-empty and trimmed`)
        return value
      }
      const taskId = TaskId(trimmed(args.taskId, 'taskId'))
      const title = args.action === 'plan' ? trimmed(args.title, 'title') : undefined
      const pluginId = args.action === 'plan' ? PluginId(trimmed(args.pluginId, 'pluginId')) : undefined
      if (args.action === 'plan' && args.briefing !== undefined) throw new Error('project_task plan does not accept briefing')
      if (args.action === 'start' && (args.title !== undefined || args.pluginId !== undefined)) throw new Error('project_task start derives title and plugin from the task')
      const briefing = args.briefing === undefined ? undefined : trimmed(args.briefing, 'briefing')
      const agent = exec.agent
      const authority = () => {
        exec.signal.throwIfAborted()
        return resolveControllerAuthority(ctx, agent, taskId, () => stopped)
      }
      const run = async () => {
        if (args.action === 'plan') {
          if (title === undefined || pluginId === undefined) throw new Error('project_task plan requires title and pluginId')
          const task = await ctx.projectController.createTask({ taskId, title, pluginId }, { beforePersist: authority })
          return { taskId: String(taskId), state: task.state, briefingQueued: false }
        }
        const start = resolveTaskStartAuthority(ctx, agent, taskId, () => stopped)
        const unchanged = taskStartUnchanged(ctx, start, () => stopped)
        if (start.task.state === 'planned') {
          await ctx.projectController.assign(taskId, start.worker.sessionId, { beforePersist: unchanged })
        } else if (start.task.assigneeSessionId !== start.worker.sessionId) {
          throw new Error('project_task assigned Worker does not match the registered task Worker')
        }
        unchanged()
        const started = await ctx.projectController.startDevelopment(taskId, { beforePersist: unchanged })
        unchanged()
        if (briefing !== undefined) start.workerAgent.followup(createUserMessage({ content: [{ type: 'text', text: briefing }], source: { kind: 'plugin', plugin: 'project-task' } }))
        return { taskId: String(taskId), state: started.state, briefingQueued: briefing !== undefined }
      }
      const previous = tails.get(String(taskId)) ?? Promise.resolve()
      const pending = previous.then(run, run)
      tails.set(String(taskId), pending)
      try { return await pending } finally { if (tails.get(String(taskId)) === pending) tails.delete(String(taskId)) }
    },
    presentCall: args => ({ card: 'generic', title: `Task ${args.taskId}: ${args.action}` }),
    presentResult: () => ({ card: 'generic' }),
  }))
}
