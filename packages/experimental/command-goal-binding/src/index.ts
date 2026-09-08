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
import { FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { GoalBindingComposition } from './composition.ts'
import { resolveCommandGoalBindingConfig } from './config.ts'
import type { CommandGoalBindingConfig } from './config.ts'
import { resolveHostStopAdapters } from './host-stop.ts'

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
  STOP_ALREADY_PENDING_TEXT,
  STOP_ALREADY_STOPPED_TEXT,
  STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE,
  STOP_IN_PROGRESS_TEXT,
  STOP_INPUT_UNEXPECTED_TEXT,
  STOP_NO_BINDING_RECORD_TEXT,
  STOP_NO_CURRENT_GOAL_TEXT,
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
  renderStopChainBookkeepingUnsettledText,
  renderStopChainNeedsAttentionText,
  renderStopChainStoppedText,
  renderStopSuccess,
} from './command.ts'
export {
  ProjectionEvidenceReviewerDirectory,
  acceptanceHashOf,
  compositionDevFrameJournal,
  resultTupleOf,
  sessionFlush,
} from './host-evidence.ts'
export {
  resolveHostStopAdapters,
  createHostStopTree,
  createHostWriterRelease,
} from './host-stop.ts'

/** Loader plugin name. */
export const name = 'command-goal-binding'

/** Required native command, Goal, projection, and Session services. */
export const inject = ['commands', 'goals', 'sessions', 'sessionProjections']

/**
 * Activate the composition: validate the deployment configuration loudly and
 * construct the {@link GoalBindingComposition}, which registers the devframe
 * projection unit and the effect-wrapped `/goal-complete`, `/devframe-start`,
 * and `/devframe-resume` commands on the calling fiber. The stop store mounts
 * the real host stop adapters from `./host-stop.ts` — the dispatch-lineage
 * project tree whenever the fiber carries the agent registry, and the
 * owner-checked writer release whenever the configuration names a worktree
 * root and the fiber carries the workspace and worktree registries. No
 * process face mounts: until a real capture feed owns descendant processes,
 * the chain fails closed on the absent inventory instead of reading
 * emptiness as quiescence.
 * @param ctx - the plugin fiber's context.
 * @param config - deployment configuration; `workspaceId`, `requiredChecksPath`, `checks`,
 *   `taskIds`, and `maxAttempts` are required.
 * @returns the composition service constructed for this fiber, also
 *   available in-process as the `commandGoalBinding` service.
 */
export function apply(
  ctx: Context,
  config: CommandGoalBindingConfig,
): GoalBindingComposition {
  const resolved = resolveCommandGoalBindingConfig(config)
  return new GoalBindingComposition(ctx, resolved, {
    requiredChecks: new FileRequiredChecksConfigStore({ path: resolved.requiredChecksPath }),
    goalCompletionIntegrations: controllerSessionId =>
      ctx.get('projectController')?.integrationReceipts(controllerSessionId) ?? [],
    goalCompletionGuard: (agent, targetPath, workspaceId) => {
      const controller = ctx.get('projectController')
      if (controller === undefined) throw new Error('Goal completion controller ownership is unavailable')
      controller.assertCompletionOwner(agent, targetPath, workspaceId)
    },
    stop: resolveHostStopAdapters(ctx, resolved),
  })
}
