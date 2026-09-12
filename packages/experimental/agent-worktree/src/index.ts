/**
 * The per-agent model-facing worktree tools over `ctx.agentWorktree`:
 * worktree_create, worktree_status, and worktree_remove. Every tool is bound
 * to the calling session's own workspace and its durable session id — the
 * workspace comes from the immutable session header and the binding holder is
 * the session id, never model input — so an agent session can mint a checkout
 * only it may write to and remove. The worktree registry owns the git
 * mechanics and the durable rows; this plugin owns the schemas, the
 * authorization door, and the model-facing renderings. Results ride the
 * ordinary tool call/result session events, so no new session event is owed.
 * @module @deepseek-ai/dsh-experimental-agent-worktree
 */

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolCallView } from '@deepseek-ai/dsh-tools'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { RegistryAgentWorktree } from './provider.ts'
import { requireNonEmpty, resolveCaller, resolveTarget } from './authorization.ts'

/** Cordis plugin name. */
export const name = 'agent-worktree'

/** Services required by the plugin; the registry missing fails the load. */
export const inject = ['tools', 'workspaceRegistry', 'worktreeRegistry', 'systemPrompt']

export { AgentWorktree } from './service.ts'
export { RegistryAgentWorktree } from './provider.ts'
export type {
  AgentWorktreeCreateRequest,
  AgentWorktreeStatus,
  AgentWorktreeView,
} from './types.ts'

const CREATE_DESCRIPTION = 'Create a new git worktree bound to this session: a second checkout of this session\'s workspace repository in a separate directory that only this session may write to until it unbinds or removes it. Use it to isolate a task\'s changes from the workspace, or to give a parallel agent its own checkout. The target directory must not exist (git creates it); branch is optional and names a NEW branch to check out (omitted, git derives the name from the directory). Returns the worktree id, canonical path, and observed branch — keep the id for worktree_status and worktree_remove. Refusals name the cause and the fix: an existing non-empty target (path-exists), an already-taken branch name (branch-conflict), or a target path too long for git\'s configuration (path-length).'

const STATUS_DESCRIPTION = 'Observe one registered git worktree\'s live state by id: whether its directory still exists, which branch it has checked out now, whether the tree is clean, and who holds its single-writer binding (locked plus lockedByThisSession). A missing directory is reported as directoryExists: false — an observation, not an error; the stale registration is recovered with the registry\'s reconcile. Get ids from the session that created the worktree or from the host.'

const REMOVE_DESCRIPTION = 'Remove one registered git worktree by id: git deletes the checkout and then the registration. A worktree bound to another session refuses until that session removes it or unbinds it — this session\'s own binding is released automatically as part of the removal. Pass force: true to discard modified or untracked files. The workspace\'s own checkout and the repository\'s history are never touched.'

const GUIDANCE = 'The agent worktree tools manage second checkouts (git worktrees) of the calling session\'s own workspace. worktree_create binds the new worktree to this session as its single writer: other sessions can observe it but cannot remove it, and it survives restarts — always worktree_remove a worktree this session created before finishing, or unbind it explicitly if another session must take it over. Get ids from the creating session or the host before worktree_status or worktree_remove.'

/** The plain pending-state card, titled from the call's arguments. */
function callCard(title: string, rawInput?: string): ToolCallView {
  return { card: 'generic', title, ...rawInput !== undefined ? { rawInput } : {} }
}

/** The tool names this plugin registers, in registration order. */
export const TOOL_NAMES = ['worktree_create', 'worktree_status', 'worktree_remove'] as const

/**
 * Mount the per-agent worktree seam: the registry-backed service on the
 * plugin's fiber, then the three tools and their usage guidance. Loading
 * without the worktree registry fails at activation.
 * @param ctx - The plugin's context.
 */
export function apply(ctx: Context): void {
  // Constructing the Service mounts ctx.agentWorktree on this plugin fiber,
  // so the seam lives and dies with the plugin (HMR-safe by construction).
  new RegistryAgentWorktree(ctx)

  ctx.systemPrompt.section({
    name: 'tool:agent-worktree',
    order: ctx.systemPrompt.getSectionOrder('TOOL_WORKTREE'),
    text: GUIDANCE,
  })

  ctx.tools.register(defineTool({
    name: 'worktree_create',
    description: CREATE_DESCRIPTION,
    parameters: {
      path: {
        type: 'string',
        required: true,
        description: 'Target checkout directory for the new worktree; absolute, or relative to the workspace directory. Must not exist.',
      },
      branch: {
        type: 'string',
        description: 'New branch to create and check out. Omitted, git derives the branch name from the directory name.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string', required: true },
          path: { type: 'string', required: true },
          branch: { type: 'string', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: `Created worktree ${value.id} at '${value.path}' on branch '${value.branch}', bound to this session as its single writer.`,
      }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const target = resolveTarget(caller.workspace.path, requireNonEmpty(args.path, 'path'))
      const worktree = await ctx.agentWorktree.create(caller.holder, {
        workspaceId: caller.workspace.id,
        path: target,
        ...args.branch !== undefined ? { branch: requireNonEmpty(args.branch, 'branch') } : {},
      })
      return { id: worktree.id, path: worktree.path, branch: worktree.branch }
    },
    presentCall: args => callCard(`agent worktree: create '${args.path}'`),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_status',
    description: STATUS_DESCRIPTION,
    parameters: {
      id: {
        type: 'string',
        required: true,
        description: 'The worktree id, from the creating session or the host.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string', required: true },
          directoryExists: { type: 'boolean', required: true },
          branch: { type: 'string' },
          clean: { type: 'boolean' },
          locked: { type: 'boolean', required: true },
          lockedByThisSession: { type: 'boolean', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.directoryExists
          ? `Worktree ${value.id}: directory exists; branch '${value.branch}'; clean: ${value.clean ? 'yes' : 'no'}; `
            + (value.locked
              ? value.lockedByThisSession ? 'bound to this session.' : 'bound to another session (it refuses removal here).'
              : 'unbound.')
          : `Worktree ${value.id}: its directory no longer exists; recover the stale registration with the registry's reconcile.`,
      }],
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const id = brandString<WorktreeId>(requireNonEmpty(args.id, 'id'))
      const status = await ctx.agentWorktree.status(caller.workspace.id, id)
      return {
        id,
        directoryExists: status.directoryExists,
        ...status.branch !== undefined ? { branch: status.branch } : {},
        ...status.clean !== undefined ? { clean: status.clean } : {},
        locked: status.lockedBy !== undefined,
        lockedByThisSession: status.lockedBy === caller.holder,
      }
    },
    presentCall: args => callCard(`agent worktree: status ${args.id}`),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_remove',
    description: REMOVE_DESCRIPTION,
    parameters: {
      id: {
        type: 'string',
        required: true,
        description: 'The worktree id to remove.',
      },
      force: {
        type: 'boolean',
        description: 'Pass true to allow removing a worktree with modified or untracked files, discarding them.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string', required: true },
          path: { type: 'string', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: `Removed worktree ${value.id} at '${value.path}'.`,
      }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const id = brandString<WorktreeId>(requireNonEmpty(args.id, 'id'))
      const path = await ctx.agentWorktree.remove(
        caller.holder,
        caller.workspace.id,
        id,
        args.force === true ? { force: true } : {},
      )
      return { id, path }
    },
    presentCall: args => callCard(`agent worktree: remove ${args.id}${args.force === true ? ' --force' : ''}`),
    presentResult: () => ({ card: 'generic' }),
  }))
}
