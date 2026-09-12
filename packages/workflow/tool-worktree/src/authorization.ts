/**
 * Caller identity and workspace authorization for the worktree tools. Every
 * tool is bound to the workspace the calling session's `cwd` resolves to: a
 * call from a session outside any registered workspace rejects, and an id
 * naming another workspace's worktree is indistinguishable from an unknown
 * one. The registry itself stays unguarded; this module is the only door the
 * model gets.
 * @module @deepseek-ai/dsh-tool-worktree/authorization
 */

import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import type { Workspace, WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { Worktree, WorktreeId, WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'

/** The authorized calling context every worktree tool executes under. */
export interface WorktreeCaller {
  /** The calling agent (the tool's `exec.agent`). */
  readonly agent: Agent

  /** The workspace owning every worktree this call may touch. */
  readonly workspace: Workspace
}

/**
 * Resolve the calling agent's workspace from its session cwd. The session
 * header is immutable, so the resolution is the authorization: the tools
 * never accept a workspace id from the model.
 * @param agent - The calling agent from the tool run context; required.
 * @param workspaces - The registered workspaces in registry order.
 * @returns the caller context.
 */
export async function resolveCaller(
  agent: ToolRunContext['agent'],
  workspaces: readonly Workspace[],
): Promise<WorktreeCaller> {
  if (agent === undefined) {
    throw new Error('worktree tools require a calling agent (exec.agent was undefined)')
  }
  const cwd = agent.session.header.cwd
  if (cwd === undefined) {
    throw new Error('worktree tools require a calling session with a working directory, but the session header carries no cwd')
  }
  let canonical: string
  try {
    canonical = await realpathNormalize(cwd)
  } catch (error) {
    // A cwd that no longer exists cannot be a registered workspace; the
    // authorization error is the honest model-facing message. Any other
    // resolution failure (permissions, corruption) stays loud.
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    canonical = cwd
  }
  const workspace = workspaces.find(candidate => sameDirectory(candidate.path, canonical))
  if (workspace === undefined) {
    throw new Error(
      `worktree tools authorize the calling session's own workspace, but its directory '${canonical}' `
      + 'is not a registered workspace; the workspace must be registered before its worktrees can be managed',
    )
  }
  return { agent, workspace }
}

/**
 * Authorize one worktree id against the caller's workspace by listing the
 * workspace's registrations; an id from another workspace is reported the
 * same way an unknown one is.
 * @param registry - The worktree registry behind the tools.
 * @param workspaceId - The caller's workspace id.
 * @param id - The model-supplied worktree id.
 * @returns the registered worktree when authorized.
 */
export function authorizedWorktree(
  registry: WorktreeRegistry,
  workspaceId: WorkspaceId,
  id: WorktreeId,
): Promise<Worktree> {
  const worktree = registry.list(workspaceId).find(entry => entry.id === id)
  if (worktree === undefined) {
    throw new Error(`worktree '${id}' is not registered for this workspace; list the workspace's worktrees to get a valid id`)
  }
  return Promise.resolve(worktree)
}

/** Windows directories are case-insensitive; fold case there only. */
function sameDirectory(left: string, right: string): boolean {
  /* v8 ignore next -- native Windows coverage exercises this platform dispatch; POSIX lanes compare case-sensitively */
  return process.platform === 'win32'
    ? left.toLowerCase() === right.toLowerCase()
    : left === right
}
