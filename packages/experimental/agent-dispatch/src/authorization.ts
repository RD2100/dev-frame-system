/**
 * Caller identity and workspace authorization for the model-facing dispatch
 * tool. The operation is bound to the calling session's own workspace: the
 * workspace comes from the immutable session header (never from the model),
 * mirroring the agent-worktree seam's authorization semantics. The dispatch
 * entry itself owns every policy question; this module is only the door that
 * anchors the call to a real registered workspace.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/authorization
 */

import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace'
import type { WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'

/** The authorized calling context every model dispatch runs under. */
export interface DispatchCaller {
  /** The calling agent (the tool's `exec.agent`), the engine's exact live parent. */
  readonly agent: Agent

  /** The workspace owning every worktree this call may target. */
  readonly workspace: Workspace
}

/**
 * Resolve the calling agent's workspace from its session cwd. The session
 * header is immutable, so the resolution is the authorization: the tool
 * never accepts a workspace id from the model. A session running from inside
 * one of its workspace's dispatched worktrees (a lead working its own tree)
 * authorizes to the workspace owning that row.
 * @param agent - The calling agent from the tool run context; required.
 * @param workspaces - The registered workspaces in registry order.
 * @param worktreeRegistry - The registry whose rows extend a workspace to
 *   the worktree directories its dispatched children run from.
 * @returns the caller context.
 */
export async function resolveCaller(
  agent: ToolRunContext['agent'],
  workspaces: readonly Workspace[],
  worktreeRegistry: WorktreeRegistry,
): Promise<DispatchCaller> {
  if (agent === undefined) {
    throw new Error('the agent dispatch tool requires a calling agent (exec.agent was undefined)')
  }
  const cwd = agent.session.header.cwd
  if (cwd === undefined) {
    throw new Error(
      'the agent dispatch tool requires a calling session with a working directory, '
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
    ?? workspaces.find(candidate => worktreeRegistry.list(candidate.id)
      .some(row => sameDirectory(row.path, canonical)))
  if (workspace === undefined) {
    throw new Error(
      `the agent dispatch tool authorizes the calling session's own workspace, but its directory '${canonical}' `
      + 'is not a registered workspace',
    )
  }
  return { agent, workspace }
}

/**
 * Reject empty model-supplied strings before they reach the entry.
 * @param value - The model-supplied string to validate.
 * @param what - The argument name the error message names.
 * @returns the validated string, unchanged.
 */
export function requireNonEmpty(value: string, what: string): string {
  if (value.trim().length === 0) {
    throw new Error(`the agent dispatch tool: '${what}' must be a non-empty string`)
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
