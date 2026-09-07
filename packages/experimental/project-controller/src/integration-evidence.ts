/** Select exact-source evidence from the existing controller projection under three-layer review authority. */

import type { AgentBindingRecord, TaskRecord } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { GoalResultBinding } from '@deepseek-ai/dsh-experimental-devframe/controller'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe'
import { deliveryResultBinding } from '@deepseek-ai/dsh-experimental-devframe'
import type {
  DevFrameTaskDeliveryEventData,
  DevFrameReviewEventData,
  DevFrameVerificationEventData,
} from '@deepseek-ai/dsh-experimental-devframe'

/** Host-resolved identities, read from the task board, binding registry, and current Goal. */
export interface IntegrationEvidenceRequest {
  /** Controller Session's existing durable projection. */
  readonly state: DevFrameProjectionState
  /** Submitted task being admitted. */
  readonly task: TaskRecord
  /** Current Goal result identity, including acceptance and source snapshot. */
  readonly expected: GoalResultBinding
  /** Caller identity from the binding registry. */
  readonly controller: AgentBindingRecord
  /** Reviewing lead identity from the binding registry. */
  readonly lead: AgentBindingRecord
  /** Implementing Worker identity from the binding registry. */
  readonly worker: AgentBindingRecord
}

/** Compare the complete work identity; order within the task set does not confer authority. */
function sameBinding(left: GoalResultBinding, right: GoalResultBinding): boolean {
  return left.controllerSessionId === right.controllerSessionId
    && left.goalId === right.goalId && left.goalRevision === right.goalRevision
    && left.workspaceId === right.workspaceId && left.acceptanceHash === right.acceptanceHash
    && left.sourceFingerprint === right.sourceFingerprint && left.snapshotId === right.snapshotId
    && left.taskIds.length === right.taskIds.length
    && left.taskIds.every(id => right.taskIds.includes(id))
}

/**
 * Select the newest task evidence without falling back to an older passing review or verification.
 * The host supplies registry records and a real projection; model/tool inputs cannot supply either.
 * @param request - Current task and Goal identities plus registry-backed hierarchy and persisted evidence.
 * @returns The paired verification and review for the exact expected work tuple.
 */
export function selectIntegrationEvidence(request: IntegrationEvidenceRequest): {
  readonly delivery: DevFrameTaskDeliveryEventData
  readonly verification: DevFrameVerificationEventData
  readonly review: DevFrameReviewEventData
} {
  const { state, task, expected, controller, lead, worker } = request
  if (state.failure !== null) throw new Error('Integration evidence projection has a replay failure')
  if (task.state !== 'submitted') throw new Error('Integration requires a submitted task')
  if (controller.role !== 'controller' || controller.parentSessionId !== undefined
    || controller.sessionId !== state.controllerSessionId
    || controller.sessionId !== expected.controllerSessionId
    || state.workspaceId !== expected.workspaceId) {
    throw new Error('Integration evidence belongs to a different controller or workspace')
  }
  if (lead.role !== 'lead' || lead.parentSessionId !== controller.sessionId || lead.pluginId !== task.pluginId
    || worker.role !== 'worker' || worker.parentSessionId !== lead.sessionId || worker.pluginId !== task.pluginId
    || worker.taskId !== task.taskId || task.assigneeSessionId !== worker.sessionId
    || lead.sessionId === worker.sessionId) {
    throw new Error('Integration requires the task Worker and its independent plugin lead under this controller')
  }
  if (controller.worktreePath === undefined || lead.worktreePath === undefined || worker.worktreePath === undefined
    || controller.worktreeId === undefined || lead.worktreeId === undefined || worker.worktreeId === undefined
    || new Set([controller.worktreeId, lead.worktreeId, worker.worktreeId]).size !== 3
    || new Set([controller.worktreePath, lead.worktreePath, worker.worktreePath]).size !== 3) {
    throw new Error('Integration hierarchy requires three independent registered worktrees')
  }
  // The legacy Goal TaskId and the plugin task-board TaskId share the persisted string identity.
  const namesTask = (binding: GoalResultBinding) => binding.taskIds.some(id => String(id) === String(task.taskId))
  if (!namesTask(expected)) throw new Error('Integration task is absent from the current Goal binding')
  const delivery = state.deliveries.findLast(record => record.binding.goalId === expected.goalId
    && String(record.taskId) === String(task.taskId))
  if (delivery === undefined || !sameBinding(delivery.binding, expected)
    || delivery.workerSessionId !== worker.sessionId || delivery.worktreeId !== worker.worktreeId
    || delivery.worktreePath !== worker.worktreePath) {
    throw new Error('Integration requires the current task delivery from its registered Worker worktree')
  }
  const output = deliveryResultBinding(delivery)
  const verification = state.verifications.findLast(record => record.deliveryId === delivery.deliveryId)
  const review = state.reviews.findLast(record => record.deliveryId === delivery.deliveryId)
  if (verification === undefined || review === undefined) throw new Error('Integration requires persisted verification and review')
  if (!sameBinding(verification.binding, output) || !sameBinding(review.binding, output)
    || verification.snapshotId !== output.snapshotId || review.snapshotId !== output.snapshotId) {
    throw new Error('Integration evidence does not match the current task, acceptance, and source snapshot')
  }
  if (review.reviewerSessionId !== lead.sessionId) throw new Error('Integration review was not issued by the task plugin lead')
  if (verification.status !== 'passed') throw new Error('Integration verification failed')
  // Required-check configuration and the review decision are evaluated by evaluateCompletionAdmission.
  return { delivery, verification, review }
}
