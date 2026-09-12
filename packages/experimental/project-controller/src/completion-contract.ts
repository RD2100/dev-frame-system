/**
 * Select the final-merge completion contract for one Goal from the durable
 * integration domain and the controller's evidence projection.
 *
 * The Goal completion contract requires the final merged result of every
 * bound task to be covered by whole-Goal independent verification and review
 * before the Goal can complete. This module is the honest constructor for
 * that evidence: it reads only durable records (the applied integration
 * receipts and the session projection's whole-Goal verification and review)
 * and fails loud on absence, so a host flow cannot synthesize the contract
 * from private state. Evidence quality failures — a non-passing review, a
 * worker-issued review, a stale merged fingerprint — stay with the completion
 * admission, which rejects them as data.
 * @module @deepseek-ai/dsh-experimental-project-controller/completion-contract
 */

import type { DevFrameProjectionState, GoalResultBinding } from '@deepseek-ai/dsh-experimental-devframe'
import type { FinalIntegrationContract, TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import type { MainTreeIntegrationRecord } from './spec.ts'

/** Identities and durable records one final-merge contract is selected from. */
export interface GoalCompletionIntegrationRequest {
  /** Controller Session's existing durable projection. */
  readonly state: DevFrameProjectionState
  /** The Goal whose bound tasks must have reached the final merged state. */
  readonly goalId: GoalResultBinding['goalId']
  /** The Goal binding's bound task ids; the contract must cover exactly these. */
  readonly boundTaskIds: readonly GoalTaskId[]
  /** The durable integration-domain rows for the project's tasks. */
  readonly integrations: readonly MainTreeIntegrationRecord[]
}

/**
 * Build the final-merge contract one completion admission consumes: every
 * bound task's applied integration receipt plus the newest whole-Goal
 * verification and review recorded for the Goal. The legacy Goal TaskId and
 * the integration domain's plugin TaskId share the persisted string identity.
 * @param request - the projection, Goal identity, bound tasks, and durable receipts.
 * @returns the contract for `CompleteGoalRequest.finalIntegration`.
 * @throws When the projection has a replay failure, a bound task has no
 *   applied integration receipt, no whole-Goal verification or review was
 *   recorded for the Goal, or a bound task has no delivery to name its
 *   worker for the independence anchor.
 */
export function selectGoalCompletionIntegration(request: GoalCompletionIntegrationRequest): FinalIntegrationContract {
  const { state, goalId, boundTaskIds, integrations } = request
  if (state.failure !== null) throw new Error('Goal completion selection requires an intact evidence projection')
  let targetPath: string | undefined
  const tasks = boundTaskIds.map((id) => {
    const row = integrations.find(candidate => candidate.controllerSessionId === state.controllerSessionId
      && String(candidate.taskId) === String(id))
    if (row === undefined || row.state !== 'applied' || row.appliedHead === undefined) {
      throw new Error(`Goal completion requires the applied integration receipt for task "${String(id)}"`)
    }
    if (targetPath !== undefined && targetPath !== row.targetPath) throw new Error('Goal completion receipts name different controller worktrees')
    targetPath = row.targetPath
    const delivery = state.deliveries.findLast(record => record.binding.goalId === goalId && String(record.taskId) === String(id))
    if (delivery !== undefined && (row.sourceCommit !== delivery.sourceCommit || row.sourcePath !== delivery.worktreePath)) {
      throw new Error(`Goal completion integration receipt does not cover the current delivery for task "${String(id)}"`)
    }
    return { taskId: id, appliedHead: row.appliedHead }
  })
  const verification = state.verifications
    .filter(record => record.deliveryId === undefined && record.binding.goalId === goalId)
    .at(-1)
  if (verification === undefined) {
    throw new Error('Goal completion requires whole-Goal verification of the final merged result')
  }
  const review = state.reviews
    .filter(record => record.deliveryId === undefined && record.binding.goalId === goalId)
    .at(-1)
  if (review === undefined) {
    throw new Error('Goal completion requires the whole-Goal review of the final merged result')
  }
  const workerSessionIds = boundTaskIds.map((id) => {
    const delivery = state.deliveries
      .findLast(record => record.binding.goalId === goalId && String(record.taskId) === String(id))
    if (delivery === undefined) {
      throw new Error(`Goal completion requires the delivered task output for task "${String(id)}"`)
    }
    return delivery.workerSessionId
  })
  if (targetPath === undefined) throw new Error('Goal completion requires an integration target worktree')
  return { targetPath, tasks, verification, review, workerSessionIds }
}
