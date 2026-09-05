/**
 * Caller identity and workspace authorization for the per-agent worktree
 * seam. Every operation is bound to the calling session's own workspace and
 * its durable session id: the workspace comes from the immutable session
 * header (never from the model), and the durable id is the single-writer
 * marker that survives agent recovery. The registry itself stays unguarded;
 * this module is the only door the model gets.
 * @module @deepseek-ai/dsh-experimental-agent-worktree/authorization
 */

import { isAbsolute, resolve } from 'node:path'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'

/** The authorized calling context every agent worktree operation runs under. */
export interface AgentWorktreeCaller {
  /** The calling agent (the tool's `exec.agent`). */
  readonly agent: Agent

  /** The calling session's durable id, branded as the single-writer marker. */
  readonly holder: WorktreeLockHolder

  /** The workspace owning every worktree this call may touch. */
  readonly workspace: Workspace
}

/**
 * Resolve the calling agent's workspace from its session cwd and mint its
 * single-writer marker. The session header is immutable, so the resolution
 * is the authorization: the tools never accept a workspace id from the model.
 * @param agent - The calling agent from the tool run context; required.
 * @param workspaces - The registered workspaces in registry order.
 * @returns the caller context.
 */
export async function resolveCaller(
  agent: ToolRunContext['agent'],
  workspaces: readonly Workspace[],
): Promise<AgentWorktreeCaller> {
  if (agent === undefined) {
    throw new Error('agent worktree tools require a calling agent (exec.agent was undefined)')
  }
  const cwd = agent.session.header.cwd
  if (cwd === undefined) {
    throw new Error(
      'agent worktree tools require a calling session with a working directory, '
      + 'but the session header carries no cwd',
    )
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
      `agent worktree tools authorize the calling session's own workspace, but its directory '${canonical}' `
      + 'is not a registered workspace; the workspace must be registered before its worktrees can be managed',
    )
  }
  return { agent, holder: WorktreeLockHolder(String(agent.session.id)), workspace }
}

/**
 * Resolve a model-supplied target path against the authorized workspace:
 * absolute paths stand, relative paths resolve against the workspace
 * directory. The resolution is explicit so the registry receives an absolute
 * path regardless of the host process cwd.
 * @param workspacePath - The authorized workspace directory.
 * @param target - The model-supplied target directory.
 * @returns the absolute target directory.
 */
export function resolveTarget(workspacePath: string, target: string): string {
  return isAbsolute(target) ? target : resolve(workspacePath, target)
}

/**
 * Reject empty model-supplied strings before they reach the registry.
 * @param value - The model-supplied string to validate.
 * @param what - The argument name the error message names.
 * @returns the validated string, unchanged.
 */
export function requireNonEmpty(value: string, what: string): string {
  if (value.trim().length === 0) {
    throw new Error(`agent worktree tools: '${what}' must be a non-empty string`)
  }
  return value
}

/** Windows directories are case-insensitive; fold case there only. */
function sameDirectory(left: string, right: string): boolean {
  /* v8 ignore next -- native Windows coverage exercises this platform dispatch; POSIX lanes compare case-sensitively */
  return process.platform === 'win32'
    ? left.toLowerCase() === right.toLowerCase()
    : left === right
}
