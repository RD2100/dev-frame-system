/**
 * Host command surface composition for DevFrame goal work: the human
 * `/goal-complete` slash command dispatches through `ctx.commands` into the
 * `GoalBindingController.complete` admission conjunction over the live native
 * Goal service and lands an admitted verdict as a durable completion receipt;
 * `/devframe-start` starts a bound goal from the configured worktree and
 * produces real verification evidence; `/devframe-resume` restores and
 * resumes the bound goal after a stop or restart. Function-plugin package:
 * named exports only, no default export.
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
  DEVFRAME_RESUME_COMMAND_NAME,
  DEVFRAME_RESUME_DESCRIPTION,
  DEVFRAME_START_COMMAND_NAME,
  DEVFRAME_START_DESCRIPTION,
  DEVFRAME_START_HINT,
  GOAL_COMPLETE_DESCRIPTION,
  RESUME_INPUT_UNEXPECTED_TEXT,
  RESUME_NO_BINDING_RECORD_TEXT,
  RESUME_NO_CURRENT_GOAL_TEXT,
  START_GOAL_RUNNING_TEXT,
  START_OBJECTIVE_REQUIRED_TEXT,
  START_WORKTREE_REQUIRED_TEXT,
  completionAdmissionEvidence,
  devframeResumeDescriptor,
  devframeStartDescriptor,
  goalCompleteDescriptor,
  parseDevframeResumeInput,
  parseDevframeStartInput,
  parseGoalCompleteInput,
  renderCompletionRejection,
  renderCompletionSuccess,
  renderResumeSuccess,
  renderStartSuccess,
} from './command.ts'
export {
  ProjectionEvidenceReviewerDirectory,
  acceptanceHashOf,
  compositionDevFrameJournal,
  resultTupleOf,
  sessionFlush,
} from './host-evidence.ts'

/** Loader plugin name. */
export const name = 'command-goal-binding'

/** Services this plugin requires at activation: the command registry, the native goal service, the projection registry, and the session store. */
export const inject = ['commands', 'goals', 'sessions', 'sessionProjections']

/**
 * Activate the composition: validate the deployment configuration loudly and
 * construct the {@link GoalBindingComposition}, which registers the devframe
 * projection unit and the effect-wrapped `/goal-complete`, `/devframe-start`,
 * and `/devframe-resume` commands on the calling fiber.
 * @param ctx - the plugin fiber's context.
 * @param config - deployment configuration; `workspaceId`, `checks`,
 *   `taskIds`, and `maxAttempts` are required.
 * @returns the composition service constructed for this fiber, also
 *   available in-process as the `commandGoalBinding` service.
 */
export function apply(
  ctx: Context,
  config: CommandGoalBindingConfig,
): GoalBindingComposition {
  return new GoalBindingComposition(ctx, resolveCommandGoalBindingConfig(config))
}
