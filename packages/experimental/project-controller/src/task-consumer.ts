/** Root-controller task planning and development admission over the existing project service. */
import type { Context } from '@deepseek-ai/cordis'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-worktree-registry'
import type {} from './controller.ts'

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
        if (stopped) throw new Error('project_task consumer is stopped')
        if (agent === undefined || ctx.agents.get(agent.id) !== agent) throw new Error('project_task requires the actual live root controller')
        const root = ctx.agentBindings.find(agent.session.id)
        if (root?.role !== 'controller' || root.parentSessionId !== undefined || root.agentId !== agent.id
          || root.sessionId !== agent.session.id || root.worktreeId === undefined || root.worktreePath === undefined
          || agent.session.header.cwd !== root.worktreePath) throw new Error('project_task requires the registered root controller worktree')
        const state = ctx.sessionProjections.stateOf(agent.session, 'devframe')
        const goal = state?.bindings.at(-1)
        if (state === undefined || state.failure !== null || goal?.lifecycle !== 'admission_open'
          || (state.lifecycle !== null && state.lifecycle.binding.goalId === goal.goalId && state.lifecycle.state !== 'admission_open')
          || String(goal.controllerSessionId) !== String(root.sessionId)
          || !goal.taskIds.some(id => String(id) === String(taskId))) throw new Error('project_task requires the task in the current open Goal')
        const rows = ctx.workspaceRegistry.list().flatMap(workspace => ctx.worktreeRegistry.list(workspace.id))
        const target = rows.find(row => row.id === root.worktreeId)
        if (target === undefined || target.path !== root.worktreePath || String(target.lockedBy) !== String(root.sessionId)
          || String(target.workspaceId) !== String(goal.workspaceId)) throw new Error('project_task requires the controller writer lock in the Goal workspace')
        return { root, rows, target }
      }
      const run = async () => {
        const initial = authority()
        if (args.action === 'plan') {
          if (title === undefined || pluginId === undefined) throw new Error('project_task plan requires title and pluginId')
          const task = await ctx.projectController.createTask({ taskId, title, pluginId }, { beforePersist: authority })
          return { taskId: String(taskId), state: task.state, briefingQueued: false }
        }
        const task = ctx.projectController.find(taskId)
        if (task === undefined || (task.state !== 'planned' && task.state !== 'assigned')) throw new Error('project_task start requires a planned or assigned task; a started task cannot be re-briefed')
        const workers = ctx.agentBindings.list().filter(binding => binding.role === 'worker' && binding.taskId === taskId && binding.pluginId === task.pluginId)
        const worker = workers[0]
        if (workers.length !== 1 || worker === undefined) throw new Error('project_task start requires exactly one registered task Worker')
        const lead = worker.parentSessionId === undefined ? undefined : ctx.agentBindings.find(worker.parentSessionId)
        const workerAgent = ctx.agents.get(worker.agentId)
        const source = initial.rows.find(row => row.id === worker.worktreeId)
        const reviewer = initial.rows.find(row => row.id === lead?.worktreeId)
        if (lead?.role !== 'lead' || lead.parentSessionId !== initial.root.sessionId || lead.pluginId !== task.pluginId
          || workerAgent === undefined || workerAgent.session.id !== worker.sessionId
          || workerAgent.session.header.cwd !== worker.worktreePath
          || source === undefined || reviewer === undefined || source.path !== worker.worktreePath || reviewer.path !== lead.worktreePath
          || source.workspaceId !== initial.target.workspaceId || reviewer.workspaceId !== initial.target.workspaceId
          || String(source.lockedBy) !== String(worker.sessionId) || String(reviewer.lockedBy) !== String(lead.sessionId)
          || new Set([initial.target.id, source.id, reviewer.id]).size !== 3
          || new Set([initial.target.path, source.path, reviewer.path]).size !== 3) throw new Error('project_task start requires independent registered controller, lead, and live Worker worktrees with writer locks')
        const signature = JSON.stringify({ root: initial.root, target: initial.target, worker, lead, source, reviewer })
        const unchanged = () => {
          const current = authority()
          const nextWorker = ctx.agentBindings.find(worker.sessionId)
          const nextLead = ctx.agentBindings.find(lead.sessionId)
          if (ctx.agents.get(worker.agentId) !== workerAgent || JSON.stringify({
            root: current.root, target: current.target, worker: nextWorker, lead: nextLead,
            source: current.rows.find(row => row.id === worker.worktreeId), reviewer: current.rows.find(row => row.id === lead.worktreeId),
          }) !== signature) throw new Error('project_task ownership changed during start; inspect task state before retrying')
        }
        if (task.state === 'planned') await ctx.projectController.assign(taskId, worker.sessionId, { beforePersist: unchanged })
        else if (task.assigneeSessionId !== worker.sessionId) throw new Error('project_task assigned Worker does not match the registered task Worker')
        unchanged()
        const started = await ctx.projectController.startDevelopment(taskId, { beforePersist: unchanged })
        unchanged()
        if (briefing !== undefined) workerAgent.followup(createUserMessage({ content: [{ type: 'text', text: briefing }], source: { kind: 'plugin', plugin: 'project-task' } }))
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
