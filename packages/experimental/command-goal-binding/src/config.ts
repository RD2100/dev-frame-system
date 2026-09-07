/**
 * Deployment configuration for the DevFrame host command composition
 * (`/goal-complete`, `/devframe-start`, `/devframe-resume`).
 *
 * The workspace identity and the approved work parameters are required and
 * validated loudly: a composition without them cannot bind or admit work, so
 * activation fails at `apply` time instead of degrading the commands into
 * unattributed paths. `checks` is the human-approved required-checks
 * checklist; `taskIds`, `maxAttempts`, and `maxGoalRounds` are the approved
 * work parameters every start binding freezes in.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/config
 */

import Schema from '@deepseek-ai/schemastery'
import { isAbsolute } from 'node:path'
import { decodeRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe'
import { TaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { TaskId as BrandedTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { resolveRepairLimit } from '@deepseek-ai/dsh-experimental-devframe'

/** Deployment configuration accepted by the `command-goal-binding` plugin. */
export interface CommandGoalBindingConfig {
  /** Shared Goal repair-round limit; omitted resolves to the DevFrame default. */
  readonly repairLimit?: number
  /**
   * Host-owned workspace identity every completion binding and evidence
   * record of this composition carries. Required.
   */
  readonly workspaceId: string
  /** Absolute ledger path for approved checklists; its parent must already exist. */
  readonly requiredChecksPath: string
  /**
   * Absolute worktree root used when a `/goal-complete` line names no path,
   * and the only worktree `/devframe-start` binds (objective and path cannot
   * be split unambiguously on one command line). Optional.
   */
  readonly workspaceRoot?: string
  /**
   * The human-approved required-checks checklist `/devframe-start` registers
   * into the required-checks store and executes for real. Required.
   */
  readonly checks: DevFrameRequiredChecksConfig
  /**
   * Non-empty unique native task ids every start binding carries. Required.
   */
  readonly taskIds: readonly string[]
  /**
   * Maximum charged attempts frozen into every start binding. Required.
   */
  readonly maxAttempts: number
  /**
   * Optional continuation round cap frozen into every start binding.
   */
  readonly maxGoalRounds?: number
}

/** Validated configuration held by the composition for its whole lifetime. */
export interface ResolvedCommandGoalBindingConfig {
  /** Validated repair-round limit shared by review and warning consumers. */
  readonly repairLimit: number
  /** Branded workspace identity attributed to every completion. */
  readonly workspaceId: WorkspaceId
  /** Validated absolute approved-checks ledger path. */
  readonly requiredChecksPath: string
  /** Absolute worktree root, present only when configured. */
  readonly workspaceRoot?: string
  /** The approved required-checks checklist, schema-validated at activation. */
  readonly checks: DevFrameRequiredChecksConfig
  /** Branded, non-empty, unique task ids frozen into every start binding. */
  readonly taskIds: readonly BrandedTaskId[]
  /** Positive maximum charged attempts frozen into every start binding. */
  readonly maxAttempts: number
  /** Optional positive continuation round cap. */
  readonly maxGoalRounds?: number
}

/** Schema for the approved-checks nested configuration. */
const ChecksConfig = Schema.object({
  version: Schema.const(1).required(),
  checks: Schema.array(Schema.object({
    checkId: Schema.string().required(),
    executable: Schema.string().required(),
    arguments: Schema.array(Schema.string()),
    cwd: Schema.string().required(),
  })).min(1).required(),
})

/** Schema for {@link CommandGoalBindingConfig}; every start parameter is required. */
export const Config: Schema<CommandGoalBindingConfig> = Schema.object({
  repairLimit: Schema.number(),
  workspaceId: Schema.string().required(),
  requiredChecksPath: Schema.string().required(),
  workspaceRoot: Schema.string(),
  checks: ChecksConfig.required(),
  taskIds: Schema.array(Schema.string()).min(1).required(),
  maxAttempts: Schema.number().required(),
  maxGoalRounds: Schema.number(),
}) as Schema<CommandGoalBindingConfig>

/** Validate the task-id list shape and uniqueness, returning branded ids. */
function resolveTaskIds(rawTaskIds: readonly string[]): BrandedTaskId[] {
  if (!Array.isArray(rawTaskIds) || rawTaskIds.length === 0) {
    throw new TypeError('command-goal-binding config taskIds must be a non-empty array')
  }
  const taskIds: BrandedTaskId[] = []
  for (const rawTaskId of rawTaskIds) {
    if (typeof rawTaskId !== 'string' || rawTaskId.trim().length === 0 || rawTaskId !== rawTaskId.trim()) {
      throw new TypeError('command-goal-binding config taskIds entries must be non-empty trimmed strings')
    }
    taskIds.push(TaskId(rawTaskId))
  }
  if (new Set(taskIds).size !== taskIds.length) {
    throw new TypeError('command-goal-binding config taskIds must be unique')
  }
  return taskIds
}

/** Validate the approved checks beyond the schema: every cwd must be absolute. */
function resolveChecks(rawChecks: DevFrameRequiredChecksConfig): DevFrameRequiredChecksConfig {
  const checks = decodeRequiredChecksConfig(rawChecks)
  for (const check of checks.checks) {
    if (!isAbsolute(check.cwd)) {
      throw new TypeError(`command-goal-binding config checks entry "${check.checkId}" must carry an absolute cwd`)
    }
  }
  return checks
}

/**
 * Validate the deployment configuration and brand its identities.
 * Misconfiguration fails loud at activation — this composition cannot bind
 * or admit work without a workspace, an approved checklist, and approved
 * work parameters, and a relative workspace root or check cwd can never
 * satisfy the fingerprint engine's absolute-path contract, so every such
 * condition rejects the plugin instead of degrading a command at dispatch
 * time.
 * @param config - configuration resolved by the plugin loader (the Schema
 *   marks the required fields; this re-check keeps direct constructions
 *   equally loud and adds the deep shape rules).
 * @returns the validated, branded configuration.
 */
export function resolveCommandGoalBindingConfig(
  config: CommandGoalBindingConfig,
): ResolvedCommandGoalBindingConfig {
  const rawWorkspaceId = config.workspaceId
  if (typeof rawWorkspaceId !== 'string' || rawWorkspaceId.trim().length === 0) {
    throw new TypeError('command-goal-binding config requires a non-empty workspaceId')
  }
  const workspaceId = WorkspaceId(rawWorkspaceId.trim())
  const requiredChecksPath = config.requiredChecksPath
  if (typeof requiredChecksPath !== 'string' || requiredChecksPath.length === 0
    || requiredChecksPath !== requiredChecksPath.trim() || !isAbsolute(requiredChecksPath)) {
    throw new TypeError('command-goal-binding config requiredChecksPath must be a non-empty trimmed absolute path')
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
      repairLimit: resolveRepairLimit(config),
      workspaceId,
      requiredChecksPath,
      workspaceRoot: rawWorkspaceRoot.trim(),
      checks: resolveChecks(config.checks),
      taskIds: resolveTaskIds(config.taskIds),
      maxAttempts: validatedPositiveInteger(config.maxAttempts, 'maxAttempts'),
      ...config.maxGoalRounds === undefined
        ? {}
        : { maxGoalRounds: validatedPositiveInteger(config.maxGoalRounds, 'maxGoalRounds') },
    }
  }
  return {
    repairLimit: resolveRepairLimit(config),
    workspaceId,
    requiredChecksPath,
    checks: resolveChecks(config.checks),
    taskIds: resolveTaskIds(config.taskIds),
    maxAttempts: validatedPositiveInteger(config.maxAttempts, 'maxAttempts'),
    ...config.maxGoalRounds === undefined
      ? {}
      : { maxGoalRounds: validatedPositiveInteger(config.maxGoalRounds, 'maxGoalRounds') },
  }
}

/** Validate one required positive safe integer loudly. */
function validatedPositiveInteger(value: number, field: 'maxAttempts' | 'maxGoalRounds'): number {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(`command-goal-binding config ${field} must be a positive safe integer`)
  }
  return value
}
