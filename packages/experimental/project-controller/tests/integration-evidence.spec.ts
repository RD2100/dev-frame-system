/** Registry and persisted-evidence mismatches cannot borrow a previous passing result. */

import { describe, expect, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { DevFrameDeliveryId, DevFrameVerificationId, deliveryResultBinding } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { requiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { DevFrameSnapshotId, SourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { CONFIG, executionFor, reviewEvent } from '../../devframe/tests/completion-fixtures.ts'
import { selectIntegrationEvidence, type IntegrationEvidenceRequest } from '../src/integration-evidence.ts'

function fixture(): IntegrationEvidenceRequest {
  const leadId = SessionId('lead-admission')
  const workerId = SessionId('worker-admission')
  const review = reviewEvent('pass', { reviewerSessionId: leadId })
  const expected = { ...review.binding, taskIds: [GoalTaskId('task-admission'), GoalTaskId('task-other')] }
  const controllerId = SessionId(String(expected.controllerSessionId))
  const taskId = TaskId('task-admission')
  const pluginId = PluginId('p-test')
  const createdAt = '2026-09-07T00:00:00.000Z'
  const delivery = {
    version: 1 as const, deliveryId: DevFrameDeliveryId('delivery-admission'), taskId: GoalTaskId(String(taskId)), binding: expected,
    workerSessionId: workerId, worktreeId: WorktreeId('worker-tree'), worktreePath: 'C:/worker',
    sourceCommit: 'a'.repeat(40), sourceFingerprint: SourceFingerprint('output-source'), snapshotId: DevFrameSnapshotId('output-snapshot'),
  }
  const output = deliveryResultBinding(delivery)
  return {
    expected,
    task: { taskId, pluginId, title: 'task', state: 'submitted', assigneeSessionId: workerId, createdAt, updatedAt: createdAt },
    controller: {
      agentId: controllerId, sessionId: controllerId, role: 'controller', createdAt,
      worktreeId: WorktreeId('controller-tree'), worktreePath: 'C:/controller',
    },
    lead: {
      agentId: leadId, sessionId: leadId, role: 'lead', parentSessionId: controllerId, pluginId, createdAt,
      worktreeId: WorktreeId('lead-tree'), worktreePath: 'C:/lead',
    },
    worker: {
      agentId: workerId, sessionId: workerId, role: 'worker', parentSessionId: leadId, pluginId, taskId, createdAt,
      worktreeId: WorktreeId('worker-tree'), worktreePath: 'C:/worker',
    },
    state: {
      controllerSessionId: controllerId, workspaceId: expected.workspaceId, failure: null,
      rolePolicy: null, bindings: [], usage: [], lifecycle: null, taskWarnings: [], repairAdmissions: [],
      deliveries: [delivery],
      reviews: [{ ...review, deliveryId: delivery.deliveryId, binding: output, snapshotId: output.snapshotId }],
      verifications: [{
        version: 1, verificationId: DevFrameVerificationId('verification'), binding: output,
        deliveryId: delivery.deliveryId, snapshotId: output.snapshotId, status: 'passed',
        requiredChecks: { config: CONFIG, digest: requiredChecksDigest(CONFIG) }, checks: CONFIG.checks.map(check => executionFor(check)),
      }],
    },
  }
}

describe('integration evidence selection', () => {
  it('rejects whole-Goal evidence without a task delivery', () => {
    const request = fixture()
    request.state.deliveries.length = 0
    expect(() => selectIntegrationEvidence(request)).toThrow('current task delivery')
  })

  it('does not borrow another task review within the same Goal', () => {
    const request = fixture()
    const other = { ...request.state.deliveries[0]!, taskId: GoalTaskId('task-other'), deliveryId: DevFrameDeliveryId('delivery-other') }
    request.state.deliveries.push(other)
    request.state.reviews[0] = { ...request.state.reviews[0]!, deliveryId: other.deliveryId }
    expect(() => selectIntegrationEvidence(request)).toThrow('persisted verification and review')
  })

  it('does not reuse passing evidence after a newer delivery of the same task', () => {
    const request = fixture()
    request.state.deliveries.push({ ...request.state.deliveries[0]!, deliveryId: DevFrameDeliveryId('delivery-new') })
    expect(() => selectIntegrationEvidence(request)).toThrow('persisted verification and review')
  })

  it('selects the exact task evidence issued by its plugin lead', () => {
    const request = fixture()
    expect(selectIntegrationEvidence(request)).toEqual({
      delivery: request.state.deliveries[0],
      review: request.state.reviews[0], verification: request.state.verifications[0],
    })
  })

  it('rejects a failed persisted projection', () => {
    const request = fixture()
    request.state.failure = 'invalid review authorization'
    expect(() => selectIntegrationEvidence(request)).toThrow('replay failure')
  })

  it('does not fall back to a passing verification after a newer failed one', () => {
    const request = fixture()
    request.state.verifications.push({ ...request.state.verifications[0]!, status: 'failed' })
    expect(() => selectIntegrationEvidence(request)).toThrow('verification failed')
  })

  it('returns the newest negative review for the existing completion evaluator to reject', () => {
    const request = fixture()
    request.state.reviews.push({ ...request.state.reviews[0]!, decision: 'changes_required' })
    expect(selectIntegrationEvidence(request).review.decision).toBe('changes_required')
  })

  it('rejects evidence for a different source even when it passed', () => {
    const request = fixture()
    const old = request.state.reviews[0]!
    request.state.reviews.push({ ...old, binding: { ...old.binding, sourceFingerprint: SourceFingerprint('other') } })
    expect(() => selectIntegrationEvidence(request)).toThrow('source snapshot')
  })

  it('rejects a Worker reviewing itself', () => {
    const request = fixture()
    request.state.reviews[0] = { ...request.state.reviews[0]!, reviewerSessionId: request.worker.sessionId }
    expect(() => selectIntegrationEvidence(request)).toThrow('plugin lead')
  })

  it('rejects a lead from another plugin', () => {
    const request = fixture()
    expect(() => selectIntegrationEvidence({ ...request, lead: { ...request.lead, pluginId: PluginId('foreign') } }))
      .toThrow('independent plugin lead')
  })

  it('rejects a Worker under another controller branch', () => {
    const request = fixture()
    expect(() => selectIntegrationEvidence({
      ...request, lead: { ...request.lead, parentSessionId: SessionId('other-controller') },
    })).toThrow('independent plugin lead')
  })

  it('rejects shared worktree ownership', () => {
    const request = fixture()
    expect(() => selectIntegrationEvidence({
      ...request, lead: { ...request.lead, worktreeId: request.worker.worktreeId! },
    })).toThrow('independent registered worktrees')
  })

  it('requires evidence for the selected task rather than another task in the project', () => {
    const request = fixture()
    request.state.reviews.length = 0
    expect(() => selectIntegrationEvidence(request)).toThrow('persisted verification and review')
  })
})
