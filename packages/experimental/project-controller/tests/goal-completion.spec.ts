/**
 * The final-merge completion constructor: whole-Goal verification, review,
 * and applied integration receipts are selected from durable records only,
 * and every absence fails loud with the named missing gate.
 * @module dsh-experimental-project-controller/tests/goal-completion
 */

import { describe, expect, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { TaskId as PluginTaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { DevFrameDeliveryId, DevFrameReviewId, DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { requiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe'
import { TaskId as GoalTaskId, evaluateFinalIntegrationStage } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { CONFIG, executionFor, reviewEvent } from '../../devframe/tests/completion-fixtures.ts'
import { selectGoalCompletionIntegration } from '../src/completion-contract.ts'
import type { MainTreeIntegrationRecord } from '../src/spec.ts'

const goalId = GoalId('goal-final-merge')
const workspaceId = WorkspaceId('ws-completion')
const controllerId = SessionId('controller-completion')
const workerA = SessionId('worker-a')
const workerB = SessionId('worker-b')
const createdAt = '2026-09-08T00:00:00.000Z'

function delivery(taskId: string, workerSessionId: SessionId) {
  return {
    version: 1 as const, deliveryId: DevFrameDeliveryId(`delivery-${taskId}`), taskId: GoalTaskId(taskId),
    binding: {
      controllerSessionId: controllerId, goalId, goalRevision: 2, taskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      acceptanceHash: AcceptanceHash('acceptance-completion'), workspaceId,
      sourceFingerprint: SourceFingerprint('output-source'), snapshotId: DevFrameSnapshotId('output-snapshot'),
    },
    workerSessionId, worktreeId: WorktreeId(`tree-${taskId}`), worktreePath: `C:/wt-${taskId}`,
    sourceCommit: 'a'.repeat(40), sourceFingerprint: SourceFingerprint('output-source'),
    snapshotId: DevFrameSnapshotId('output-snapshot'),
  }
}

function wholeGoalEvidence() {
  const binding = {
    controllerSessionId: controllerId, goalId, goalRevision: 2, taskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
    acceptanceHash: AcceptanceHash('acceptance-completion'), workspaceId,
    sourceFingerprint: SourceFingerprint('dsh-source-fp-v1-merged'), snapshotId: DevFrameSnapshotId('merged-snapshot'),
  }
  const verification = {
    version: 1 as const, verificationId: DevFrameVerificationId('verification-final'), binding,
    snapshotId: binding.snapshotId, status: 'passed' as const,
    requiredChecks: { config: CONFIG, digest: requiredChecksDigest(CONFIG) },
    checks: CONFIG.checks.map(check => executionFor(check)),
  }
  const review = reviewEvent('pass', {
    reviewId: DevFrameReviewId('review-final'), binding, snapshotId: binding.snapshotId,
    reviewerSessionId: SessionId('final-reviewer'),
  })
  return { verification, review }
}

function integrationRow(taskId: string, overrides: Partial<MainTreeIntegrationRecord> = {}): MainTreeIntegrationRecord {
  return {
    taskId: PluginTaskId(taskId), controllerSessionId: SessionId(String(controllerId)),
    reviewId: DevFrameReviewId('review-final'), verificationId: DevFrameVerificationId('verification-final'),
    sourcePath: `C:/wt-${taskId}`, targetPath: 'C:/controller',
    sourceCommit: 'a'.repeat(40), targetHead: 'b'.repeat(40),
    state: 'applied', appliedHead: 'b'.repeat(40),
    createdAt, updatedAt: createdAt, ...overrides,
  }
}

function fixture() {
  const { verification, review } = wholeGoalEvidence()
  const state: DevFrameProjectionState = {
    controllerSessionId: controllerId, workspaceId, failure: null,
    rolePolicy: null, bindings: [], superseded: [], acceptanceRegions: [], usage: [],
    lifecycle: null, taskWarnings: [], repairAdmissions: [],
    deliveries: [delivery('task-a', workerA), delivery('task-b', workerB)],
    verifications: [verification], reviews: [review],
  }
  return {
    state,
    request: {
      state,
      goalId,
      boundTaskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      integrations: [integrationRow('task-a'), integrationRow('task-b')] as MainTreeIntegrationRecord[],
    },
  }
}

describe('goal completion contract selection', () => {
  it('builds the final-merge contract from applied receipts and whole-Goal evidence', () => {
    const { request } = fixture()
    const contract = selectGoalCompletionIntegration(request)
    expect(contract.tasks).toEqual([
      { taskId: GoalTaskId('task-a'), appliedHead: 'b'.repeat(40) },
      { taskId: GoalTaskId('task-b'), appliedHead: 'b'.repeat(40) },
    ])
    expect(contract.verification.deliveryId).toBeUndefined()
    expect(contract.review.deliveryId).toBeUndefined()
    expect(contract.workerSessionIds).toEqual([workerA, workerB])
    // The selected contract passes the admission's final-integration stage.
    expect(evaluateFinalIntegrationStage({ contract, boundTaskIds: request.boundTaskIds }).kind).toBe('ok')
  })

  it('refuses a bound task without an applied integration receipt', () => {
    const { request } = fixture()
    expect(() => selectGoalCompletionIntegration({ ...request, integrations: [
      integrationRow('task-a'), integrationRow('task-b', { state: 'prepared', appliedHead: undefined }),
    ] })).toThrow('applied integration receipt for task "task-b"')
  })

  it('refuses to substitute a delivery-bound verification for the whole-Goal gate', () => {
    const { state, request } = fixture()
    const perTask = { ...state.verifications[0]!, deliveryId: DevFrameDeliveryId('delivery-task-a') }
    expect(() => selectGoalCompletionIntegration({
      ...request, state: { ...state, verifications: [perTask] },
    })).toThrow('whole-Goal verification')
  })

  it('refuses to substitute a per-task review for the whole-Goal review', () => {
    const { state, request } = fixture()
    const perTask = { ...state.reviews[0]!, deliveryId: DevFrameDeliveryId('delivery-task-a') }
    expect(() => selectGoalCompletionIntegration({
      ...request, state: { ...state, reviews: [perTask] },
    })).toThrow('whole-Goal review')
  })

  it('refuses a bound task with no delivery to anchor reviewer independence', () => {
    const { state, request } = fixture()
    expect(() => selectGoalCompletionIntegration({
      ...request, state: { ...state, deliveries: [state.deliveries[0]!] },
    })).toThrow('delivered task output for task "task-b"')
  })

  it('refuses a failed projection instead of selecting from untrusted state', () => {
    const { state, request } = fixture()
    expect(() => selectGoalCompletionIntegration({
      ...request, state: { ...state, failure: 'invalid review authorization' },
    })).toThrow('intact evidence projection')
  })
})
