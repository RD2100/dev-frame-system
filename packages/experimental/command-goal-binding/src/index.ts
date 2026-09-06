/**
 * Host command surface composition for DevFrame goal completion: the human
 * `/goal-complete` slash command dispatches through `ctx.commands` into the
 * `GoalBindingController.complete` admission conjunction over the live native
 * Goal service, and lands an admitted verdict as a durable completion
 * receipt. Function-plugin package: named exports only, no default export.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding
 */

import type { Context } from '@deepseek-ai/cordis'
import { GoalBindingComposition } from './composition.ts'
import { resolveCommandGoalBindingConfig } from './config.ts'
import type { CommandGoalBindingConfig } from './config.ts'

export { GoalBindingComposition } from './composition.ts'
export type {
  GoalBindingCompositionStores,
  StartGoalBindingRequest,
} from './composition.ts'
export { Config, resolveCommandGoalBindingConfig } from './config.ts'
export type {
  CommandGoalBindingConfig,
  ResolvedCommandGoalBindingConfig,
} from './config.ts'
export {
  COMMAND_HINT,
  COMMAND_NAME,
  GOAL_COMPLETE_DESCRIPTION,
  completionAdmissionEvidence,
  goalCompleteDescriptor,
  parseGoalCompleteInput,
  renderCompletionRejection,
  renderCompletionSuccess,
} from './command.ts'

/** Loader plugin name. */
export const name = 'command-goal-binding'

/** Services this plugin requires at activation: the command registry, the native goal service, and the projection registry. */
export const inject = ['commands', 'goals', 'sessionProjections']

/**
 * Activate the composition: validate the deployment configuration loudly and
 * construct the {@link GoalBindingComposition}, which registers the devframe
 * projection unit and the effect-wrapped `/goal-complete` command on the
 * calling fiber.
 * @param ctx - the plugin fiber's context.
 * @param config - deployment configuration; `workspaceId` is required.
 * @returns the composition service constructed for this fiber, also
 *   available in-process as the `commandGoalBinding` service.
 */
export function apply(
  ctx: Context,
  config: CommandGoalBindingConfig,
): GoalBindingComposition {
  return new GoalBindingComposition(ctx, resolveCommandGoalBindingConfig(config))
}
