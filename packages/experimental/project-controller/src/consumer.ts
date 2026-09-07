/** Controller-only integration tool; identities, worktrees, and checks resolve from host-owned records. */

import { execFile } from 'node:child_process'
import { isAbsolute } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-agent'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import type {} from '@deepseek-ai/dsh-worktree-registry'
import { FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {} from './controller.ts'

/** Loader namespace name; the controller service must be mounted separately. */
export const name = 'project-integration-tool'

/** Required host services; this consumer never constructs another project controller. */
export const inject = ['tools', 'agents', 'projectController', 'agentBindings', 'workspaceRegistry', 'worktreeRegistry']

/** Host configuration; model arguments cannot override process settings or the approved-checks ledger. */
export interface Config {
  /** Absolute path of the existing approved-checks registration ledger. */
  requiredChecksPath: string
  /** Git executable selected by the deployment. */
  gitExecutable: string
  /** Maximum elapsed milliseconds for each Git subprocess. */
  gitTimeoutMs: number
  /** Maximum captured bytes for each Git subprocess. */
  gitMaxOutputBytes: number
}

/** Validated deployment settings, all explicitly configured. */
export const Config: z<Config> = z.object({
  requiredChecksPath: z.string(),
  gitExecutable: z.string().min(1),
  gitTimeoutMs: z.number().min(1).max(Number.MAX_SAFE_INTEGER),
  gitMaxOutputBytes: z.number().min(1).max(Number.MAX_SAFE_INTEGER),
})

const execFileAsync = promisify(execFile)

/**
 * Register the controller's integration entry. A marker remains within one execution and is never model-visible.
 * @param ctx - Consumer context with the existing controller and authoritative registries.
 * @param config - Validated host process limits and checks ledger location.
 */
export function apply(ctx: Context, config: Config): void {
  if (!isAbsolute(config.requiredChecksPath)
    || !Number.isSafeInteger(config.gitTimeoutMs) || !Number.isSafeInteger(config.gitMaxOutputBytes)) {
    throw new Error('project integration requires an absolute checks ledger path and positive integer Git limits')
  }
  const options = {
    executable: config.gitExecutable,
    timeoutMs: config.gitTimeoutMs,
    maxOutputBytes: config.gitMaxOutputBytes,
  }
  const requiredChecksStore = new FileRequiredChecksConfigStore({ path: config.requiredChecksPath })

  async function head(path: string, signal: AbortSignal): Promise<string> {
    const env = Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
    const result = await execFileAsync(options.executable, ['-C', path, 'rev-parse', '--verify', 'HEAD'], {
      env, signal, windowsHide: true, encoding: 'utf8',
      timeout: options.timeoutMs, maxBuffer: options.maxOutputBytes,
    })
    return result.stdout.trim()
  }

  ctx.tools.register(defineTool({
    name: 'project_integrate',
    description: 'Integrate a submitted task from its registered Worker worktree into your controller worktree after persisted verification and independent lead review pass. Choose integrate for a fresh attempt, reconcile to observe an interrupted attempt without repeating Git, or retry to explicitly re-admit an earlier attempt only when its target is unchanged. Changed or ambiguous targets require reconciliation; this tool never resets files or resolves conflicts. Only the actual root controller may call it.',
    parameters: {
      taskId: { type: 'string', required: true, description: 'The submitted task id on the project task board.' },
      action: { type: 'string', required: true, description: 'integrate, reconcile, or retry. Retry rechecks all current evidence before another attempt.' },
    },
    output: {
      schema: {
        type: 'object', additionalProperties: false,
        properties: {
          taskId: { type: 'string', required: true },
          state: { type: 'string', required: true },
          observation: { type: 'string', required: true },
        },
      },
      render: (_args, value) => [{ type: 'text', text: `Task ${value.taskId}: ${value.state}; integration ${value.observation}.` }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (!['integrate', 'reconcile', 'retry'].includes(args.action)) {
        throw new Error('project_integrate action must be integrate, reconcile, or retry')
      }
      if (args.taskId.trim().length === 0 || args.taskId !== args.taskId.trim()) {
        throw new Error('project_integrate taskId must be a non-empty trimmed string')
      }
      const agent = exec.agent
      if (agent === undefined || ctx.agents.get(agent.id) !== agent) {
        throw new Error('project_integrate requires the actual live calling agent')
      }
      const callerId = agent.session.id
      const controller = ctx.agentBindings.find(callerId)
      if (controller?.role !== 'controller' || controller.parentSessionId !== undefined
        || controller.agentId !== agent.id || controller.sessionId !== callerId) {
        throw new Error('project_integrate requires the registered root controller')
      }
      if (controller.worktreePath === undefined || controller.worktreeId === undefined
        || agent.session.header.cwd === undefined
        || await realpathNormalize(agent.session.header.cwd) !== await realpathNormalize(controller.worktreePath)) {
        throw new Error('project_integrate requires the calling controller to own its session worktree')
      }
      const rows = ctx.workspaceRegistry.list().flatMap(workspace => ctx.worktreeRegistry.list(workspace.id))
      const target = rows.find(row => row.id === controller.worktreeId)
      if (target === undefined || target.path !== controller.worktreePath || String(target.lockedBy) !== String(callerId)) {
        throw new Error('project_integrate requires the controller worktree single-writer lock')
      }
      const taskId = TaskId(args.taskId)
      const task = ctx.projectController.find(taskId)
      if (task === undefined) throw new Error(`project_integrate task '${taskId}' is not on the project board`)
      exec.signal.throwIfAborted()
      if (args.action === 'reconcile') {
        const observation = await ctx.projectController.reconcileMainTreeIntegration(callerId, taskId, options)
        const current = ctx.projectController.find(taskId)
        if (current === undefined) throw new Error(`project_integrate task '${taskId}' is absent after reconciliation`)
        return { taskId: String(taskId), state: current.state, observation: observation.kind }
      }
      const worker = task.assigneeSessionId === undefined ? undefined : ctx.agentBindings.find(task.assigneeSessionId)
      const source = rows.find(row => row.id === worker?.worktreeId)
      if (worker?.role !== 'worker' || source === undefined || source.path !== worker.worktreePath
        || source.workspaceId !== target.workspaceId || String(source.lockedBy) !== String(worker.sessionId)) {
        throw new Error('project_integrate requires the assigned Worker worktree and its single-writer lock in this workspace')
      }
      const [sourceCommit, targetHead] = await Promise.all([head(source.path, exec.signal), head(target.path, exec.signal)])
      exec.signal.throwIfAborted()
      const marker = await ctx.projectController.requestMainTreeMerge(callerId, taskId, {
        git: { sourcePath: source.path, targetPath: target.path, sourceCommit, targetHead },
        options, requiredChecksStore, retryUnchanged: args.action === 'retry', signal: exec.signal,
      })
      exec.signal.throwIfAborted()
      const integrated = await ctx.projectController.integrate(taskId, marker)
      return { taskId: String(taskId), state: integrated.state, observation: 'applied' }
    },
    presentCall: args => ({ card: 'generic', title: `Integrate task ${args.taskId}: ${args.action}` }),
    presentResult: () => ({ card: 'generic' }),
  }))
}
