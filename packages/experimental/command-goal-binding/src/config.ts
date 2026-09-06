/**
 * Deployment configuration for the `/goal-complete` host command composition.
 *
 * The workspace identity is required and validated loudly: a composition
 * without one cannot attribute completion evidence, so activation fails at
 * `apply` time instead of degrading the command into an unattributed path.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/config
 */

import Schema from '@deepseek-ai/schemastery'
import { isAbsolute } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'

/** Deployment configuration accepted by the `command-goal-binding` plugin. */
export interface CommandGoalBindingConfig {
  /**
   * Host-owned workspace identity every completion binding and evidence
   * record of this composition carries. Required.
   */
  readonly workspaceId: string
  /**
   * Absolute worktree root used when a `/goal-complete` line names no path.
   * Optional; when absent, the command line must carry the worktree path.
   */
  readonly workspaceRoot?: string
}

/** Validated configuration held by the composition for its whole lifetime. */
export interface ResolvedCommandGoalBindingConfig {
  /** Branded workspace identity attributed to every completion. */
  readonly workspaceId: WorkspaceId
  /** Absolute worktree fallback, present only when configured. */
  readonly workspaceRoot?: string
}

/** Schema for {@link CommandGoalBindingConfig}; `workspaceId` is required. */
export const Config: Schema<CommandGoalBindingConfig> = Schema.object({
  workspaceId: Schema.string().required(),
  workspaceRoot: Schema.string(),
}) as Schema<CommandGoalBindingConfig>

/**
 * Validate the deployment configuration and brand its workspace identity.
 * Misconfiguration fails loud at activation — this composition cannot
 * attribute completion evidence without a workspace, and a relative
 * workspace root can never satisfy the fingerprint engine's absolute-path
 * contract, so both conditions reject the plugin instead of degrading the
 * command at dispatch time.
 * @param config - configuration resolved by the plugin loader (the Schema
 *   marks `workspaceId` required; this re-check keeps direct constructions
 *   equally loud).
 * @returns the validated, branded configuration.
 */
export function resolveCommandGoalBindingConfig(
  config: CommandGoalBindingConfig,
): ResolvedCommandGoalBindingConfig {
  const rawWorkspaceId = config.workspaceId
  if (typeof rawWorkspaceId !== 'string' || rawWorkspaceId.trim().length === 0) {
    throw new TypeError('command-goal-binding config requires a non-empty workspaceId')
  }
  const rawWorkspaceRoot = config.workspaceRoot
  if (rawWorkspaceRoot !== undefined) {
    if (typeof rawWorkspaceRoot !== 'string' || rawWorkspaceRoot.trim().length === 0) {
      throw new TypeError('command-goal-binding config workspaceRoot must be a non-empty string when present')
    }
    if (!isAbsolute(rawWorkspaceRoot.trim())) {
      throw new TypeError('command-goal-binding config workspaceRoot must be an absolute path')
    }
    return {
      workspaceId: WorkspaceId(rawWorkspaceId.trim()),
      workspaceRoot: rawWorkspaceRoot.trim(),
    }
  }
  return { workspaceId: WorkspaceId(rawWorkspaceId.trim()) }
}
