/**
 * The model-facing worktree tools: create, list, status, remove, and prune
 * (reconcile) over `worktreeRegistry`. Every tool is bound to the calling
 * session's own workspace — the workspace comes from the immutable session
 * header, never from the model — so the model can only manage the second
 * checkouts of the directory it runs in. The registry owns the git mechanics
 * and the durable rows; this plugin owns the schemas, the authorization door,
 * and the model-facing renderings. Results ride the ordinary tool call/result
 * session events, so no new session event is owed.
 * @module @deepseek-ai/dsh-tool-worktree
 */

import { isAbsolute, resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolCallView } from '@deepseek-ai/dsh-tools'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { authorizedWorktree, resolveCaller } from './authorization.ts'

export const name = 'tool-worktree'

export const inject = ['tools', 'workspaceRegistry', 'worktreeRegistry', 'systemPrompt']

/**
 * Resolve a model-supplied target path against the authorized workspace:
 * absolute paths stand, relative paths resolve against the workspace
 * directory. The resolution is explicit here so the registry receives an
 * absolute path regardless of the host process cwd.
 * @param workspacePath - The authorized workspace directory.
 * @param target - The model-supplied target directory.
 * @returns the absolute target directory.
 */
function resolveTarget(workspacePath: string, target: string): string {
  return isAbsolute(target) ? target : resolve(workspacePath, target)
}

/** Reject empty model-supplied strings before they reach the registry. */
function requireNonEmpty(value: string, what: string): string {
  if (value.trim().length === 0) {
    throw new Error(`worktree tool: '${what}' must be a non-empty string`)
  }
  return value
}

const WORKTREE_ID_PROPERTIES = {
  id: { type: 'string', required: true, description: 'The worktree id, from worktree_list.' },
} as const

const CREATE_DESCRIPTION = `Create a new git worktree: a second checkout of this session's workspace repository in a separate directory, registered durably. Use it to build or test in a clean tree while the workspace holds uncommitted work, to isolate an experiment, or to run a parallel task. The target directory must not exist (git creates it) and must not be the workspace directory itself; branch is optional and names a NEW branch to check out (omitted, git derives the name from the directory). Returns the worktree id, canonical path, and observed branch — keep the id for worktree_status and worktree_remove. Refusals name the cause and the fix: an existing non-empty target (path-exists), an already-taken branch name (branch-conflict), or a target path too long for git's configuration (path-length).`

const LIST_DESCRIPTION = `List the git worktrees registered for this session's workspace: id, canonical path, branch, and creation time for each, in stable order. Registrations survive restarts. Worktrees created outside the product never appear here — use worktree_prune to see and adopt them.`

const STATUS_DESCRIPTION = `Observe one registered git worktree's live state by id: whether its directory still exists, which branch it has checked out now, and whether the tree is clean (no modified or untracked files). A missing directory is reported as directoryExists: false — an observation, not an error; recover the stale registration with worktree_prune. Get ids from worktree_list.`

const REMOVE_DESCRIPTION = `Remove one registered git worktree by id: git deletes the checkout, and only then is the registration dropped. A worktree with modified or untracked files refuses to go unless force is true, which discards them. The workspace's own checkout and the repository's history are never touched. Get ids from worktree_list; if the directory already vanished outside the product, use worktree_prune instead.`

const PRUNE_DESCRIPTION = `Reconcile the workspace's worktree registrations with what git actually reports. The report names dangling registrations (directory-missing: the directory is gone; git-unknown: git no longer tracks the path) and unregistered worktrees (git-tracked checkouts created outside the product). By default this only reports. Pass pruneDangling: true to drop the stale registrations — registry rows only, never directories or files — and adoptUnregistered: true to register the outside-created worktrees. Run this when worktree_status reports a missing directory, worktree_remove refuses on a vanished worktree, or you suspect worktrees were created or deleted outside the product.`

const GUIDANCE = `The worktree_* tools manage second checkouts (git worktrees) of the calling session's own workspace: they authorize against the session's working directory and cannot touch another workspace's registrations. Get ids with worktree_list before worktree_status or worktree_remove; create with worktree_create for clean builds, experiments, or parallel tasks. A worktree whose directory was deleted outside the product is recovered with worktree_prune (pruneDangling: true), and outside-created checkouts become manageable after worktree_prune (adoptUnregistered: true).`

/** The plain pending-state card, titled from the call's arguments. */
function callCard(title: string, rawInput?: string): ToolCallView {
  return { card: 'generic', title, ...rawInput !== undefined ? { rawInput } : {} }
}

export function apply(ctx: Context): void {
  // Capture the injected services once, in apply scope: the tools close over
  // these values instead of re-reading the scoped proxy at execute time.
    // Usage policy ships with the tool (the master convention: tool guidance
  // lives in tool plugins as prompt sections, not in the deployment persona).
  ctx.systemPrompt.section({
    name: 'tool:worktree',
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
        text: `Created worktree ${value.id} at '${value.path}' on branch '${value.branch}'.`,
      }],
    },
    isConcurrencySafe: false,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const target = resolveTarget(caller.workspace.path, requireNonEmpty(args.path, 'path'))
      const worktree = await ctx.worktreeRegistry.create({
        workspaceId: caller.workspace.id,
        path: target,
        ...args.branch !== undefined ? { branch: requireNonEmpty(args.branch, 'branch') } : {},
      })
      return { id: worktree.id, path: worktree.path, branch: worktree.branch }
    },
    presentCall: args => callCard(`worktree: create '${args.path}'`),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_list',
    description: LIST_DESCRIPTION,
    parameters: {},
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          worktrees: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', required: true },
                path: { type: 'string', required: true },
                branch: { type: 'string', required: true },
                createdAt: { type: 'string', required: true },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.worktrees.length === 0
          ? 'No worktrees are registered for this workspace.'
          : `${value.worktrees.length} worktree(s) registered for this workspace:\n`
            + value.worktrees.map(w => `- ${w.id} at '${w.path}' on branch '${w.branch}' (created ${w.createdAt})`).join('\n'),
      }],
    },
    isConcurrencySafe: true,
    async execute(_args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      return {
        worktrees: ctx.worktreeRegistry.list(caller.workspace.id).map(worktree => ({
          id: worktree.id,
          path: worktree.path,
          branch: worktree.branch,
          createdAt: worktree.createdAt,
        })),
      }
    },
    presentCall: () => callCard('worktree: list'),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_status',
    description: STATUS_DESCRIPTION,
    parameters: WORKTREE_ID_PROPERTIES,
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string', required: true },
          directoryExists: { type: 'boolean', required: true },
          branch: { type: 'string' },
          clean: { type: 'boolean' },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: value.directoryExists
          ? `Worktree ${value.id}: directory exists; branch '${value.branch}'; clean: ${value.clean ? 'yes' : 'no'}.`
          : `Worktree ${value.id}: its directory no longer exists; recover the stale registration with worktree_prune.`,
      }],
    },
    isConcurrencySafe: true,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const id = brandString<WorktreeId>(requireNonEmpty(args.id, 'id'))
      await authorizedWorktree(ctx.worktreeRegistry, caller.workspace.id, id)
      const status = await ctx.worktreeRegistry.status(id)
      return {
        id,
        directoryExists: status.directoryExists,
        ...status.branch !== undefined ? { branch: status.branch } : {},
        ...status.clean !== undefined ? { clean: status.clean } : {},
      }
    },
    presentCall: args => callCard(`worktree: status ${args.id}`),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_remove',
    description: REMOVE_DESCRIPTION,
    parameters: {
      ...WORKTREE_ID_PROPERTIES,
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
    isConcurrencySafe: false,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const id = brandString<WorktreeId>(requireNonEmpty(args.id, 'id'))
      const worktree = await authorizedWorktree(ctx.worktreeRegistry, caller.workspace.id, id)
      await ctx.worktreeRegistry.remove(id, args.force === true ? { force: true } : {})
      return { id, path: worktree.path }
    },
    presentCall: args => callCard(`worktree: remove ${args.id}${args.force === true ? ' --force' : ''}`),
    presentResult: () => ({ card: 'generic' }),
  }))

  ctx.tools.register(defineTool({
    name: 'worktree_prune',
    description: PRUNE_DESCRIPTION,
    parameters: {
      pruneDangling: {
        type: 'boolean',
        description: 'Drop the dangling registrations (registry rows only; never directories or files).',
      },
      adoptUnregistered: {
        type: 'boolean',
        description: 'Register the unregistered git-tracked worktrees under this workspace.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          dangling: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', required: true },
                path: { type: 'string', required: true },
                reason: { type: 'string', required: true },
              },
            },
          },
          unregistered: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                path: { type: 'string', required: true },
                branch: { type: 'string' },
              },
            },
          },
          removedCount: { type: 'integer', required: true },
          adoptedCount: { type: 'integer', required: true },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: renderPrune(value.dangling, value.unregistered, value.removedCount, value.adoptedCount),
      }],
    },
    isConcurrencySafe: false,
    async execute(args, exec) {
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list())
      const report = await ctx.worktreeRegistry.reconcile(caller.workspace.id, {
        ...(args.pruneDangling === true ? { pruneRows: true } : {}),
        ...(args.adoptUnregistered === true ? { adoptUnregistered: true } : {}),
      })
      return {
        dangling: report.dangling.map(stale => ({ id: stale.id, path: stale.path, reason: stale.reason })),
        unregistered: report.unregistered.map(entry => ({
          path: entry.path,
          ...entry.branch !== undefined ? { branch: entry.branch } : {},
        })),
        removedCount: report.removedRows.length,
        adoptedCount: report.adoptedPaths.length,
      }
    },
    presentCall: args => callCard(`worktree: prune${args.pruneDangling === true ? ' pruneDangling' : ''}${args.adoptUnregistered === true ? ' adoptUnregistered' : ''}`),
    presentResult: () => ({ card: 'generic' }),
  }))
}

/** Render the reconcile outcome: the observed differences and what changed. */
function renderPrune(
  dangling: readonly { id: string; path: string; reason: string }[],
  unregistered: readonly { path: string; branch?: string }[],
  removedCount: number,
  adoptedCount: number,
): string {
  const lines: string[] = []
  if (dangling.length === 0 && unregistered.length === 0) {
    return 'Registry and git agree: no dangling registrations, no unregistered worktrees.'
  }
  for (const stale of dangling) {
    lines.push(`- dangling registration ${stale.id} at '${stale.path}' (${stale.reason})`)
  }
  for (const entry of unregistered) {
    lines.push(`- unregistered worktree at '${entry.path}'${entry.branch !== undefined ? ` on branch '${entry.branch}'` : ' (detached HEAD)'}`)
  }
  lines.push(`Actions: ${removedCount} registration(s) dropped, ${adoptedCount} worktree(s) adopted.`)
  return lines.join('\n')
}
