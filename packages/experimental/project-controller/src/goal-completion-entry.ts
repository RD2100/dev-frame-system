/**
 * Production entry face for the final-merge completion gate: decide whether
 * the gate is engaged for one Goal, and select the evidence contract when it
 * is.
 *
 * The command face consumes this before building `CompleteGoalRequest`. A
 * Goal whose work never entered the controller tree keeps the plain
 * completion lane; once any integration receipt or whole-Goal record exists,
 * the gate is engaged and completion must carry the complete final-merge
 * evidence — a half-integrated Goal cannot complete through the plain lane.
 * @module @deepseek-ai/dsh-experimental-project-controller/goal-completion-entry
 */

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
 * Whether the final-merge completion gate applies to this Goal: any
 * integration receipt in any state naming a bound task, or any whole-Goal
 * verification or review recorded for the Goal, means the work entered the
 * controller tree and completion must carry the final-merge evidence. The
 * integration rows persist no goal id, so a receipt engages by its bound task
 * name under this controller, while whole-Goal records are goal-scoped. A
 * projection with a replay failure is treated as engaged fail-closed, so a
 * broken evidence face cannot silently route completion to the plain lane.
 * @param input - the projection, Goal identity, bound tasks, and durable receipts.
 * @returns Whether completion must go through the final-merge evidence contract.
 */
export function goalCompletionGateEngaged(input: GoalCompletionGateInput): boolean {
  const { state, goalId, boundTaskIds, integrations } = input
  if (state.failure !== null) return true
  const namesBoundTask = (taskId: unknown) =>
    boundTaskIds.some(id => String(id) === String(taskId))
  if (integrations.some(row => namesBoundTask(row.taskId))) return true
  const wholeGoal = (record: { readonly deliveryId?: unknown; readonly binding: { readonly goalId: GoalResultBinding['goalId'] } }) =>
    record.deliveryId === undefined && record.binding.goalId === goalId
  return state.verifications.some(wholeGoal) || state.reviews.some(wholeGoal)
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
