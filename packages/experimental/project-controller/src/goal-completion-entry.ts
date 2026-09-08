/** Select the final-merge completion requirements without changing the authorized Goal binding. */

import type { DevFrameProjectionState, GoalResultBinding } from '@deepseek-ai/dsh-experimental-devframe'
import type { FinalIntegrationContract, TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import type { MainTreeIntegrationRecord } from './spec.ts'
import { selectGoalCompletionIntegration } from './completion-contract.ts'

/** Identities and durable records one completion-gate decision reads. */
export interface GoalCompletionGateInput {
  /** Controller Session's existing durable projection. */
  readonly state: DevFrameProjectionState
  /** The Goal whose completion is being attempted. */
  readonly goalId: GoalResultBinding['goalId']
  /** The Goal binding's bound task ids. */
  readonly boundTaskIds: readonly GoalTaskId[]
  /** The durable integration-domain rows for the project's tasks. */
  readonly integrations: readonly MainTreeIntegrationRecord[]
}

/**
 * Require final-merge evidence once this Goal has a delivery, a controller-owned
 * integration receipt, or whole-Goal evidence beyond its original source.
 * Projection failure also engages the requirement so corruption cannot select
 * the plain completion lane.
 * @param input - Goal projection and controller-owned durable integration receipts.
 * @returns Whether completion requires final merged-tree evidence.
 */
export function goalCompletionGateEngaged(input: GoalCompletionGateInput): boolean {
  const { state, goalId, boundTaskIds, integrations } = input
  if (state.failure !== null) return true
  if (state.deliveries.some(delivery => delivery.binding.goalId === goalId)) return true
  const namesBoundTask = (taskId: unknown) =>
    boundTaskIds.some(id => String(id) === String(taskId))
  if (integrations.some(row => row.controllerSessionId === state.controllerSessionId && namesBoundTask(row.taskId))) return true
  const startClaim = state.bindings.filter(binding => binding.goalId === goalId).at(-1)
  const movedWholeGoal = (record: { readonly deliveryId?: unknown; readonly binding: { readonly goalId: GoalResultBinding['goalId']; readonly sourceFingerprint: GoalResultBinding['sourceFingerprint'] } }) =>
    record.deliveryId === undefined
    && record.binding.goalId === goalId
    && (startClaim === undefined || record.binding.sourceFingerprint !== startClaim.sourceFingerprint)
  return state.verifications.some(movedWholeGoal) || state.reviews.some(movedWholeGoal)
}

/**
 * Select the final-merge evidence contract for one engaged completion gate.
 * @param input - the projection, Goal identity, bound tasks, and durable receipts.
 * @returns The contract for `CompleteGoalRequest.finalIntegration`, or
 *   `undefined` when the gate is not engaged and the plain completion lane
 *   applies.
 * @throws The named absence from {@link selectGoalCompletionIntegration} when
 *   the gate is engaged but the evidence is incomplete — the caller renders
 *   this as a stable completion refusal.
 */
export function selectGoalCompletionEvidence(input: GoalCompletionGateInput): FinalIntegrationContract | undefined {
  if (!goalCompletionGateEngaged(input)) return undefined
  return selectGoalCompletionIntegration(input)
}
