/**
 * The model-facing dispatch entry: the `agent_dispatch` tool over
 * `ctx.agentDispatch`. It is the formal consumer the daily journey was
 * missing — the calling session (controller or lead, per the hierarchy
 * discipline) dispatches a child onto one registered worktree it names by
 * id, with the workspace and caller resolved from the immutable session
 * header and the policy left entirely to the dispatch entry and the engine.
 * A task that already has a child is retried by passing `retry`, which
 * reuses the already-returned identity and never re-delivers a briefing;
 * the entry's `DISPATCH_IDENTITY_EXISTS` refusal names that rule. Results
 * ride the ordinary tool call/result session events, so no new session
 * event is owed.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/consumer
 */

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolCallView } from '@deepseek-ai/dsh-tools'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AgentDispatch } from './service.ts'
import { requireNonEmpty, resolveCaller } from './authorization.ts'

/** Cordis plugin name. */
export const name = 'agent-dispatch'

/** Services required by the plugin; the hierarchy stack missing fails the load. */
export const inject = ['tools', 'systemPrompt', 'workspaceRegistry', 'worktreeRegistry', 'agentHierarchy', 'agentBindings', 'agents']

const DISPATCH_DESCRIPTION = `Dispatch a child agent for one task onto one registered git worktree: the controller dispatches a lead, and a lead dispatches workers inside its approved plugin scopes. Name the task id, the plugin scope, and the worktree id (get worktree ids from worktree_create or the host), and pass a briefing prompt for a fresh dispatch — the briefing is queued only after the child is published. If this task already has a dispatched child, the tool refuses and names it: pass retry: true to reuse that child instead, which never re-delivers the briefing. The engine owns the child's lifecycle and the hierarchy owns every denial; refusals name the cause and the fix.`

const GUIDANCE = `The agent dispatch tool is the daily delegation entry over the agent hierarchy. The controller dispatches a lead per task onto its own registered worktree; the lead dispatches workers inside the plugin scopes approved for it in the deployment's leadPluginScopes. Every dispatch binds the worktree's single-writer lock to the new child for its whole life. A retried task reuses the existing child (retry: true) — never re-brief a running child.`

/** The tool names this plugin registers, in registration order. */
export const TOOL_NAMES = ['agent_dispatch'] as const

/** The plain pending-state card, titled from the call's arguments. */
function callCard(title: string, rawInput?: string): ToolCallView {
  return { card: 'generic', title, ...rawInput !== undefined ? { rawInput } : {} }
}

/**
 * Mount the model-facing dispatch seam: the dispatch service on the plugin's
 * fiber, then the tool and its usage guidance. Loading without the
 * hierarchy stack (engine, role bindings, registries) fails at activation.
 * @param ctx - The plugin's context.
 */
export function apply(ctx: Context): void {
  // Constructing the Service mounts ctx.agentDispatch on this plugin fiber,
  // so the seam lives and dies with the plugin (HMR-safe by construction).
  new AgentDispatch(ctx)

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
        description: "The task this child owns; one task has at most one dispatched child.",
      },
      pluginId: {
        type: 'string',
        required: true,
        description: "The plugin scope the child works under; a lead's worker scope must be in that lead's approved set.",
      },
      worktreeId: {
        type: 'string',
        required: true,
        description: "The registered worktree id the child will own as its single writer, from worktree_create or the host.",
      },
      prompt: {
        type: 'string',
        description: "The task briefing queued to a freshly dispatched child after publication. Never re-sent on a retry.",
      },
      retry: {
        type: 'boolean',
        description: 'Pass true to reuse the child this task already has instead of dispatching a new one; no briefing is queued on reuse.',
      },
      childId: {
        type: 'string',
        description: "The preallocated session id for the child, when the deployment configures one (the leadPluginScopes approved sets are keyed by these ids). Omitted, the engine allocates the identity.",
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
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.reused
          ? `Reusing ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}; the earlier briefing stands, none re-queued.`
          : `Dispatched ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}, bound as the worktree's single writer.`,
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
      return {
        childId: String(child.record.agentId),
        role: args.role,
        taskId,
        worktreeId: String(row.id),
        reused: existing !== undefined,
      }
    },
    presentCall: args => callCard(`agent dispatch: ${String(args.role)} for '${String(args.taskId)}'`),
    presentResult: () => ({ card: 'generic' }),
  }))
}
