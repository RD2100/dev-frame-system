/** Behavior tests for the agent evidence ledger over the real storage composition. */

import { expect, describe, it } from 'vitest'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { SessionId } from '@deepseek-ai/dsh-session'
import { harness } from './helpers.ts'

const TASK = TaskId('task-e1')
const TASK2 = TaskId('task-e2')
const CONTROLLER = ControllerSessionId('session-ctrl')
const GOAL = GoalId('goal-e1')

/** One valid binding request over the shared fixture identity. */
function bindingRequest(goalId = GOAL) {
  return {
    taskId: TASK,
    controllerSessionId: CONTROLLER,
    goalId,
    goalRevision: 3,
    workspaceId: WorkspaceId('ws-default'),
    acceptanceHash: AcceptanceHash('acceptance:sha256:abc'),
    sourceFingerprint: SourceFingerprint('source:sha256:def'),
  }
}

describe('recording receipts', () => {
  it('records binding, submission, and verification receipts and serves them per task', async () => {
    const h = await harness()
    try {
      const binding = await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest())
      expect(binding.taskId).toBe(TASK)
      expect(binding.goalId).toBe(GOAL)
      expect(binding.goalRevision).toBe(3)
      expect(binding.recordedAt).toBeTruthy()

      const submission = await h.ctx.agentEvidence.recordSubmission({
        taskId: TASK,
        submittedBy: SessionId('session-worker'),
        commit: 'a'.repeat(40),
        changedPaths: ['packages/a/src/x.ts', 'packages/a/README.md'],
        inputDigest: SourceFingerprint('source:sha256:def'),
      })
      expect(submission.commit).toBe('a'.repeat(40))
      expect(submission.changedPaths).toHaveLength(2)

      const verification = await h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm exec vitest run packages/a',
        exitCode: 1,
        artifactPaths: [],
      })
      // A failing verification is recorded as-is; the ledger does not judge it.
      expect(verification.exitCode).toBe(1)

      const trail = h.ctx.agentEvidence.byTask(TASK)
      expect(trail.bindings).toHaveLength(1)
      expect(trail.submissions).toHaveLength(1)
      expect(trail.verifications).toHaveLength(1)
      expect(h.ctx.agentEvidence.byTask(TASK2).bindings).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('keeps re-recorded bindings as an append-only trail and serves them by Goal', async () => {
    const h = await harness()
    try {
      await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest())
      await h.ctx.agentEvidence.recordTaskGoalBinding({ ...bindingRequest(), goalRevision: 4 })
      await h.ctx.agentEvidence.recordTaskGoalBinding({ ...bindingRequest(GOAL), taskId: TASK2 })

      const trail = h.ctx.agentEvidence.byTask(TASK)
      expect(trail.bindings).toHaveLength(2)
      expect(trail.bindings.map(b => b.goalRevision)).toEqual([3, 4])

      const byGoal = h.ctx.agentEvidence.bindingsByGoal(CONTROLLER, GOAL)
      expect(byGoal).toHaveLength(3)
      expect(byGoal.some(b => b.taskId === TASK2)).toBe(true)
    } finally {
      await h.dispose()
    }
  })

  it('rejects malformed receipts with a stable code', async () => {
    const h = await harness()
    try {
      await expect(h.ctx.agentEvidence.recordSubmission({
        taskId: TASK,
        submittedBy: SessionId('session-worker'),
        commit: 'not-a-sha',
        changedPaths: [],
        inputDigest: SourceFingerprint('source:sha256:def'),
      })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_INVALID_RECEIPT' })

      await expect(h.ctx.agentEvidence.recordSubmission({
        taskId: TASK,
        submittedBy: SessionId('session-worker'),
        commit: 'A'.repeat(40),
        changedPaths: [],
        inputDigest: SourceFingerprint('source:sha256:def'),
      })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_INVALID_RECEIPT' })

      await expect(h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: '  ',
        exitCode: 0,
        artifactPaths: [],
      })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_INVALID_RECEIPT' })

      await expect(h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm test',
        exitCode: 1.5,
        artifactPaths: [],
      })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_INVALID_RECEIPT' })

      await expect(h.ctx.agentEvidence.recordSubmission({
        taskId: TASK,
        submittedBy: SessionId('session-worker'),
        commit: 'b'.repeat(64),
        changedPaths: [' packages/a/src/x.ts'],
        inputDigest: SourceFingerprint('source:sha256:def'),
      })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_INVALID_RECEIPT' })
    } finally {
      await h.dispose()
    }
  })
})

describe('cold restore', () => {
  it('restores every receipt trail verbatim across a restart', async () => {
    const h1 = await harness()
    await h1.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest())
    await h1.ctx.agentEvidence.recordSubmission({
      taskId: TASK,
      submittedBy: SessionId('session-worker'),
      commit: 'c'.repeat(64),
      changedPaths: ['packages/a/src/y.ts'],
      inputDigest: SourceFingerprint('source:sha256:def'),
    })
    await h1.ctx.agentEvidence.recordVerification({
      taskId: TASK,
      command: 'node ./node_modules/typescript/bin/tsc -b packages/a',
      exitCode: 0,
      artifactPaths: ['packages/a/lib/types/index.d.ts'],
    })
    const root = h1.root
    await h1.dispose({ keepRoot: true })

    const h2 = await harness(root)
    try {
      const trail = h2.ctx.agentEvidence.byTask(TASK)
      expect(trail.bindings).toHaveLength(1)
      expect(trail.bindings[0]?.goalRevision).toBe(3)
      expect(trail.submissions[0]?.commit).toBe('c'.repeat(64))
      expect(trail.verifications[0]?.exitCode).toBe(0)
      expect(h2.ctx.agentEvidence.bindingsByGoal(CONTROLLER, GOAL)).toHaveLength(1)
      // Append-only survives the restart: new receipts join the restored trail.
      await h2.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm test',
        exitCode: 0,
        artifactPaths: [],
      })
      expect(h2.ctx.agentEvidence.byTask(TASK).verifications).toHaveLength(2)
    } finally {
      await h2.dispose()
    }
  })
})
