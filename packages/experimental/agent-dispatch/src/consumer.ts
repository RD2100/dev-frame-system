/**
 * The model-facing dispatch entry: the `agent_dispatch` tool over
 * `ctx.agentDispatch` — the daily delegation face — plus the formal host
 * bootstrap service (`ctx.projectRun`) the host drives before the chain
 * runs. The task lifecycle's delivery/review/integration moves are owned
 * downstream (project_task, the delivery tools, and the integration path);
 * this module registers only the dispatch tool and mounts both services.
 * Results ride the ordinary tool call/result session events, so no new
 * session event is owed.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/consumer
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolCallView } from '@deepseek-ai/dsh-tools'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AgentDispatch } from './service.ts'
import { AgentProjectRun } from './run.ts'
import { requireNonEmpty, resolveCaller } from './authorization.ts'

/** Cordis plugin name. */
export const name = 'agent-dispatch'

/** Plugin config. The formal bootstrap is explicit opt-in, so dispatch-only deployments load unchanged. */
export const Config: z<{ bootstrap?: boolean; checksLedgerPath?: string }> = z.object({
  bootstrap: z.boolean(),
  checksLedgerPath: z.string(),
})

/** Services required by the plugin; the hierarchy stack missing fails the load. */
export const inject = [
  'tools',
  'systemPrompt',
  'workspaceRegistry',
  'worktreeRegistry',
  'agentHierarchy',
  'agentBindings',
  'agents',
  'sessions',
] as const

const DISPATCH_DESCRIPTION = 'Dispatch a child agent for one task onto one registered git worktree: the controller dispatches a lead, and a lead dispatches workers inside its approved plugin scopes. Name the task id, the plugin scope, and the worktree id (get worktree ids from worktree_create or the host), and pass a briefing prompt for a fresh dispatch — the briefing is queued only after the child is published. Every result carries ack: what the child\'s own durable log proves about the task (briefed while pending, claimed while executing, terminal with the turn\'s recorded ending — completed means the task finished cleanly, dropped when the briefing was cancelled unrun). If this task already has a dispatched child, the tool refuses and names it: pass retry: true to reuse that child instead, which never re-delivers the briefing and reports the task\'s current ack. The engine owns the child\'s lifecycle and the hierarchy owns every denial; refusals name the cause and the fix.'

const GUIDANCE = 'The agent dispatch tool is the daily delegation entry over the agent hierarchy. The controller dispatches a lead per task onto its own registered worktree; the lead dispatches workers inside the plugin scopes approved for it in the deployment\'s leadPluginScopes. Every dispatch binds the worktree\'s single-writer lock to the new child for its whole life. A retried task reuses the existing child (retry: true) — never re-brief a running child.'

/** The tool names this plugin registers, in registration order. */
export const TOOL_NAMES = ['agent_dispatch'] as const

/** The plain pending-state card, titled from the call's arguments. */
function callCard(title: string, rawInput?: string): ToolCallView {
  return { card: 'generic', title, ...rawInput !== undefined ? { rawInput } : {} }
}

/** The ack shape the tool result carries: the derived state plus the flush verdict. */
interface DispatchAckValue {
  readonly state: string
  readonly durable: boolean
  readonly degraded?: boolean
  readonly completed?: boolean
  readonly reasonKind?: string
  readonly turn?: number
}

/**
 * Render one dispatch or reuse outcome, with the durable-acknowledgment
 * state the child's log proves. Reuse never re-briefs; its text tells the
 * model exactly where the task stands so the next decision (wait, recover,
 * or a new task) is grounded.
 */
function renderDispatchText(value: {
  childId: string
  role: string
  taskId: string
  worktreeId: string
  reused: boolean
  ack: DispatchAckValue
}): string {
  const head = value.reused
    ? `Reusing ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}`
    : `Dispatched ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}, bound as the worktree's single writer`
  const durability = value.ack.durable ? '' : value.ack.degraded === true
    ? ' The durability backend failed this check (degraded).'
    : ' No durability backend participated in the check.'
  const tail = !value.reused
    ? '.'
    : value.ack.state === 'terminal' && value.ack.completed === true
      ? '; the task\'s terminal state is durable (completed).'
      : value.ack.state === 'terminal'
        ? `; the claiming turn ended without completing (reason: ${value.ack.reasonKind ?? 'unknown'}, turn ${String(value.ack.turn ?? '?')}); recover the child or dispatch a new task.`
        : value.ack.state === 'claimed'
          ? '; the child is executing the briefing, its terminal state is not recorded yet.'
          : value.ack.state === 'dropped'
            ? '; the briefing was cancelled unrun, dispatch a new task.'
            : value.ack.state === 'unbriefed'
              ? '; no briefing for this task is recorded in the recovered session.'
              : value.ack.state === 'unavailable'
                ? '; the child is not live in this process, recover it through the recovery lane.'
                : '; the earlier briefing stands, none re-queued.'
  return head + tail + durability
}

/**
 * Mount the model-facing dispatch seam: the formal host bootstrap service on
 * the plugin's fiber, then the dispatch service, then the tool and its usage
 * guidance. Loading without the hierarchy stack or the project controller
 * fails at activation.
 * @param ctx - The plugin's context.
 * @param config - The schema-validated plugin config.
 */
export function apply(ctx: Context, config?: { bootstrap?: boolean; checksLedgerPath?: string }): void {
  // Constructing AgentDispatch mounts ctx.agentDispatch on this plugin
  // fiber, so the seam lives and dies with the plugin (HMR-safe by
  // construction). The formal host bootstrap is opt-in: deployments that
  // set `bootstrap` must mount the project controller, and the mount fails
  // loud when its authorities are missing.
  new AgentDispatch(ctx)
  if (config?.bootstrap === true) {
    new AgentProjectRun(ctx, { checksLedgerPath: config.checksLedgerPath })
  }

  ctx.systemPrompt.section({
    name: 'tool:agent-dispatch',
    order: ctx.systemPrompt.getSectionOrder('TOOL_AGENT_DISPATCH'),
    text: GUIDANCE,
  })

  ctx.tools.register(defineTool({
    name: 'agent_dispatch',
    description: DISPATCH_DESCRIPTION,
    parameters: {
      role: {
        type: 'string',
        required: true,
        description: "The child's hierarchy role: 'lead' from the controller, or 'worker' from a lead.",
      },
      taskId: {
        type: 'string',
        required: true,
        description: 'The task this child owns; one task has at most one dispatched child.',
      },
      pluginId: {
        type: 'string',
        required: true,
        description: "The plugin scope the child works under; a lead's worker scope must be in that lead's approved set.",
      },
      worktreeId: {
        type: 'string',
        required: true,
        description: 'The registered worktree id the child will own as its single writer, from worktree_create or the host.',
      },
      prompt: {
        type: 'string',
        description: 'The task briefing queued to a freshly dispatched child after publication. Never re-sent on a retry.',
      },
      retry: {
        type: 'boolean',
        description: 'Pass true to reuse the child this task already has instead of dispatching a new one; no briefing is queued on reuse.',
      },
      childId: {
        type: 'string',
        description: 'The preallocated session id for the child, when the deployment configures one (the leadPluginScopes approved sets are keyed by these ids). Omitted, the engine allocates the identity.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          childId: { type: 'string', required: true },
          role: { type: 'string', required: true },
          taskId: { type: 'string', required: true },
          worktreeId: { type: 'string', required: true },
          reused: { type: 'boolean', required: true },
          ack: {
            type: 'object',
            required: true,
            additionalProperties: false,
            properties: {
              state: { type: 'string', required: true },
              durable: { type: 'boolean', required: true },
              degraded: { type: 'boolean' },
              completed: { type: 'boolean' },
              reasonKind: { type: 'string' },
              turn: { type: 'number' },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: renderDispatchText(value),
      }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (args.role !== 'lead' && args.role !== 'worker') {
        throw new Error(`the agent dispatch tool: 'role' must be 'lead' or 'worker', got '${String(args.role)}'`)
      }
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list(), ctx.worktreeRegistry)
      const worktreeId = brandString<WorktreeId>(requireNonEmpty(args.worktreeId, 'worktreeId'))
      const row = ctx.worktreeRegistry.list(caller.workspace.id).find(entry => entry.id === worktreeId)
      if (row === undefined) {
        throw new Error(
          `the agent dispatch tool: worktree '${worktreeId}' is not registered under the calling session's workspace; `
          + 'dispatch onto a worktree this workspace holds a row for',
        )
      }
      const taskId = TaskId(requireNonEmpty(args.taskId, 'taskId'))
      const existing = args.retry === true
        ? ctx.agentDispatch.findDispatchedChild(caller.agent, taskId)
        : undefined
      if (args.retry === true && existing === undefined) {
        throw new Error(
          `the agent dispatch tool: task '${taskId}' has no dispatched child to reuse; `
          + 'dispatch fresh without retry',
        )
      }
      const child = await ctx.agentDispatch.createChildAgent(caller.agent, {
        cwd: row.path,
        role: args.role,
        taskId,
        pluginId: PluginId(requireNonEmpty(args.pluginId, 'pluginId')),
        worktree: {
          worktreeId: row.id,
          worktreePath: row.path,
          ...(row.branch !== undefined ? { branch: row.branch } : {}),
        },
      }, {
        workspaceId: caller.workspace.id,
        ...(args.childId !== undefined ? { sessionId: brandString<SessionId>(requireNonEmpty(args.childId, 'childId')) } : {}),
        ...(existing !== undefined ? { sessionId: existing.record.agentId } : {}),
        ...(existing === undefined && args.prompt !== undefined && requireNonEmpty(args.prompt, 'prompt') !== ''
          ? { prompt: args.prompt }
          : {}),
      })
      const ack = await ctx.agentDispatch.taskAck(caller.agent, taskId)
      if (ack === undefined) {
        throw new Error(`the agent dispatch tool: task '${taskId}' has no dispatched child to acknowledge`)
      }
      return {
        childId: String(child.record.agentId),
        role: args.role,
        taskId,
        worktreeId: String(row.id),
        reused: existing !== undefined,
        ack: {
          state: ack.state,
          durable: ack.durable,
          ...(ack.degraded === undefined ? {} : { degraded: true }),
          ...(ack.completed === undefined ? {} : { completed: ack.completed }),
          ...(ack.turnEnd === undefined ? {} : { reasonKind: ack.turnEnd.reason.kind, turn: ack.turnEnd.turn }),
        },
      }
    },
    presentCall: args => callCard(`agent dispatch: ${String(args.role)} for '${String(args.taskId)}'`),
    presentResult: () => ({ card: 'generic' }),
  }))
}
