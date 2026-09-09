/**
 * The production completion-gate entry: a Goal whose work never entered the
 * controller tree keeps the plain lane, and an engaged gate demands the
 * complete final-merge evidence, propagating the named absence otherwise.
 * @module dsh-experimental-project-controller/tests/goal-completion-entry
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
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { CONFIG, executionFor, reviewEvent } from '../../devframe/tests/completion-fixtures.ts'
import { goalCompletionGateEngaged, selectGoalCompletionEvidence } from '../src/goal-completion-entry.ts'
import type { MainTreeIntegrationRecord } from '../src/spec.ts'

const goalId = GoalId('goal-entry')
const otherGoalId = GoalId('goal-other')
const workspaceId = WorkspaceId('ws-entry')
const controllerId = SessionId('controller-entry')
const workerA = SessionId('worker-a')
const workerB = SessionId('worker-b')
const createdAt = '2026-09-08T01:00:00.000Z'

function delivery(taskId: string, workerSessionId: SessionId) {
  return {
    version: 1 as const, deliveryId: DevFrameDeliveryId(`delivery-${taskId}`), taskId: GoalTaskId(taskId),
    binding: {
      controllerSessionId: controllerId, goalId, goalRevision: 2, taskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      acceptanceHash: AcceptanceHash('acceptance-entry'), workspaceId,
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
    acceptanceHash: AcceptanceHash('acceptance-entry'), workspaceId,
    sourceFingerprint: SourceFingerprint('dsh-source-fp-v1-merged'), snapshotId: DevFrameSnapshotId('merged-snapshot'),
  }
  const verification = {
    version: 1 as const, verificationId: DevFrameVerificationId('verification-entry'), binding,
    snapshotId: binding.snapshotId, status: 'passed' as const,
    requiredChecks: { config: CONFIG, digest: requiredChecksDigest(CONFIG) },
    checks: CONFIG.checks.map(check => executionFor(check)),
  }
  const review = reviewEvent('pass', {
    reviewId: DevFrameReviewId('review-entry'), binding, snapshotId: binding.snapshotId,
    reviewerSessionId: SessionId('final-reviewer'),
  })
  return { verification, review }
}

function integrationRow(taskId: string, overrides: Partial<MainTreeIntegrationRecord> = {}): MainTreeIntegrationRecord {
  return {
    taskId: PluginTaskId(taskId), controllerSessionId: SessionId(String(controllerId)),
    reviewId: DevFrameReviewId('review-entry'), verificationId: DevFrameVerificationId('verification-entry'),
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
    input: {
      state,
      goalId,
      boundTaskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      integrations: [integrationRow('task-a'), integrationRow('task-b')] as MainTreeIntegrationRecord[],
    },
  }
}

describe('goal completion gate entry', () => {
  it('requires final evidence after delivery even when the receipt reader is absent', () => {
    const { input } = fixture()
    const missing = { ...input, integrations: [] }
    expect(goalCompletionGateEngaged(missing)).toBe(true)
    expect(() => selectGoalCompletionEvidence(missing)).toThrow('applied integration receipt')
  })

  it('does not borrow another controller receipt with the same task name', () => {
    const { input } = fixture()
    const foreign = { ...input, integrations: input.integrations.map(row => ({ ...row, controllerSessionId: SessionId('other-controller') })) }
    expect(() => selectGoalCompletionEvidence(foreign)).toThrow('applied integration receipt')
  })

  it('refuses a receipt for an older task delivery', () => {
    const { input } = fixture()
    const stale = { ...input, integrations: input.integrations.map(row => ({ ...row, sourceCommit: 'c'.repeat(40) })) }
    expect(() => selectGoalCompletionEvidence(stale)).toThrow('does not cover the current delivery')
  })
  it('delivers the complete contract when every gate obligation is met', () => {
    const { input } = fixture()
    const contract = selectGoalCompletionEvidence(input)
    expect(contract?.tasks).toEqual([
      { taskId: GoalTaskId('task-a'), appliedHead: 'b'.repeat(40) },
      { taskId: GoalTaskId('task-b'), appliedHead: 'b'.repeat(40) },
    ])
    expect(contract?.workerSessionIds).toEqual([workerA, workerB])
  })

  it('keeps the plain lane when no integration row or whole-Goal record exists', () => {
    const { input } = fixture()
    const plain = {
      ...input,
      integrations: [] as MainTreeIntegrationRecord[],
      state: { ...input.state, deliveries: [], verifications: [], reviews: [] },
    }
    expect(goalCompletionGateEngaged(plain)).toBe(false)
    expect(selectGoalCompletionEvidence(plain)).toBeUndefined()
  })

  it('ignores whole-Goal records belonging to other goals', () => {
    const { state } = fixture()
    const foreign = {
      state: {
        ...state,
        deliveries: [],
        verifications: [{ ...state.verifications[0]!, binding: { ...state.verifications[0]!.binding, goalId: otherGoalId } }],
        reviews: [{ ...state.reviews[0]!, binding: { ...state.reviews[0]!.binding, goalId: otherGoalId } }],
      },
      goalId,
      boundTaskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      integrations: [] as MainTreeIntegrationRecord[],
    }
    expect(goalCompletionGateEngaged(foreign)).toBe(false)
    expect(selectGoalCompletionEvidence(foreign)).toBeUndefined()
  })

  it('engages on a prepared receipt alone and refuses the incomplete gate by name', () => {
    const { input } = fixture()
    const prepared = {
      ...input,
      integrations: [integrationRow('task-a'), integrationRow('task-b', { state: 'prepared', appliedHead: undefined })],
    }
    expect(goalCompletionGateEngaged(prepared)).toBe(true)
    expect(() => selectGoalCompletionEvidence(prepared))
      .toThrow('applied integration receipt for task "task-b"')
  })

  it('engages on a whole-Goal verification alone and refuses the missing review by name', () => {
    const { state, input } = fixture()
    const noReview = { ...input, state: { ...state, reviews: [] } }
    expect(goalCompletionGateEngaged(noReview)).toBe(true)
    expect(() => selectGoalCompletionEvidence(noReview)).toThrow('whole-Goal review')
  })

  it('treats a failed projection as engaged so the plain lane cannot swallow it', () => {
    const { state } = fixture()
    const failed = {
      state: { ...state, failure: 'invalid review authorization' },
      goalId,
      boundTaskIds: [GoalTaskId('task-a'), GoalTaskId('task-b')],
      integrations: [] as MainTreeIntegrationRecord[],
    }
    expect(goalCompletionGateEngaged(failed)).toBe(true)
    expect(() => selectGoalCompletionEvidence(failed)).toThrow('intact evidence projection')
  })
})
