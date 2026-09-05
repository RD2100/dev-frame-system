/**
 * AT2C-03 三段证据链 append-only — anchored from
 * `scenarios/AT2C-03-evidence-chain-append-only.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：三段链 receipt 逐字回读，receiptId（randomUUID）与 recordedAt 由
 * ledger 打点；非零 exit code 原样入账且无验收字段；畸形 receipt 逐探针
 * fail loud `AGENT_EVIDENCE_INVALID_RECEIPT` 且零落盘；同 task 重录加行不改
 * 不删。
 *
 * @module tests/at2c-03-evidence-chain-append-only
 */

import { expect, describe, it } from 'vitest'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { SessionId } from '@deepseek-ai/dsh-session'
import { harness } from './helpers.ts'

const TASK = TaskId('t-1')
const CONTROLLER = ControllerSessionId('controller-1')
const GOAL = GoalId('goal-1')

/** One valid binding request over the draft's synthetic identity. */
function bindingRequest(goalRevision = 3) {
  return {
    taskId: TASK,
    controllerSessionId: CONTROLLER,
    goalId: GOAL,
    goalRevision,
    workspaceId: WorkspaceId('ws-default'),
    acceptanceHash: AcceptanceHash('acceptance:sha256:abc123'),
    sourceFingerprint: SourceFingerprint('source:sha256:def456'),
  }
}

/** One valid submission request. */
function submissionRequest() {
  return {
    taskId: TASK,
    submittedBy: SessionId('worker-1'),
    commit: 'a'.repeat(64),
    changedPaths: ['packages/a/src/x.ts'],
    inputDigest: SourceFingerprint('source:sha256:def456'),
  }
}

describe('AT2C-03 evidence chain append only', () => {
  it('returns each link verbatim with ledger-stamped identity fields', async () => {
    const h = await harness()
    try {
      const binding = await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest())
      expect(binding.taskId).toBe(TASK)
      expect(binding.controllerSessionId).toBe(CONTROLLER)
      expect(binding.goalId).toBe(GOAL)
      expect(binding.goalRevision).toBe(3)
      expect(binding.workspaceId).toBe('ws-default')
      expect(binding.acceptanceHash).toBe('acceptance:sha256:abc123')
      expect(binding.sourceFingerprint).toBe('source:sha256:def456')
      expect(binding.receiptId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
      expect(Number.isNaN(Date.parse(binding.recordedAt))).toBe(false)

      const submission = await h.ctx.agentEvidence.recordSubmission(submissionRequest())
      expect(submission.submittedBy).toBe('worker-1')
      expect(submission.commit).toBe('a'.repeat(64))
      expect(submission.changedPaths).toEqual(['packages/a/src/x.ts'])
      expect(submission.inputDigest).toBe('source:sha256:def456')
      expect(submission.receiptId).toBeTruthy()

      const verification = await h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm exec vitest run packages/a',
        exitCode: 0,
        artifactPaths: ['artifacts/vitest.xml'],
      })
      expect(verification.command).toBe('pnpm exec vitest run packages/a')
      expect(verification.exitCode).toBe(0)
      expect(verification.artifactPaths).toEqual(['artifacts/vitest.xml'])
    } finally {
      await h.dispose()
    }
  })

  it('records provenance only: a failed verification is kept as-is with no acceptance fields', async () => {
    const h = await harness()
    try {
      const passing = await h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm exec vitest run packages/a',
        exitCode: 0,
        artifactPaths: ['artifacts/vitest.xml'],
      })
      const failing = await h.ctx.agentEvidence.recordVerification({
        taskId: TASK,
        command: 'pnpm run lint',
        exitCode: 1,
        artifactPaths: [],
      })
      expect(failing.exitCode).toBe(1)
      expect(Object.keys(failing).sort()).toEqual(['artifactPaths', 'command', 'exitCode', 'receiptId', 'recordedAt', 'taskId'])
      // The earlier snapshot is not rewritten; both stay on the trail.
      const trail = h.ctx.agentEvidence.byTask(TASK)
      expect(trail.verifications.map(snapshot => snapshot.receiptId)).toEqual([passing.receiptId, failing.receiptId])
      expect(trail.verifications[0]?.exitCode).toBe(0)
      expect(trail.verifications[1]?.exitCode).toBe(1)
    } finally {
      await h.dispose()
    }
  })

  it('fails loud on every malformed receipt and leaves the tables untouched', async () => {
    const h = await harness()
    try {
      await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest())
      await h.ctx.agentEvidence.recordSubmission(submissionRequest())
      const baseline = h.ctx.agentEvidence.byTask(TASK)
      expect(baseline.bindings).toHaveLength(1)
      expect(baseline.submissions).toHaveLength(1)

      const invalid = { code: 'AGENT_EVIDENCE_INVALID_RECEIPT', message: 'receipt failed its schema validation' }
      // An empty taskId is the schema boundary's find: the brand factory would
      // reject it first, so the raw value goes past the brand here.
      await expect(h.ctx.agentEvidence.recordTaskGoalBinding({ ...bindingRequest(), taskId: '' as never }))
        .rejects.toMatchObject(invalid)
      await expect(h.ctx.agentEvidence.recordSubmission({ ...submissionRequest(), commit: 'A'.repeat(64) }))
        .rejects.toMatchObject(invalid)
      await expect(h.ctx.agentEvidence.recordSubmission({
        ...submissionRequest(), changedPaths: [' packages/a/src/x.ts'],
      })).rejects.toMatchObject(invalid)
      await expect(h.ctx.agentEvidence.recordVerification({
        taskId: TASK, command: ' pnpm run lint ', exitCode: 0, artifactPaths: [],
      })).rejects.toMatchObject(invalid)

      const after = h.ctx.agentEvidence.byTask(TASK)
      expect(after.bindings).toHaveLength(1)
      expect(after.submissions).toHaveLength(1)
      expect(after.verifications).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('appends a re-recorded binding without rewriting the earlier receipt', async () => {
    const h = await harness()
    try {
      const first = await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest(3))
      const second = await h.ctx.agentEvidence.recordTaskGoalBinding(bindingRequest(4))
      expect(second.receiptId).not.toBe(first.receiptId)
      const trail = h.ctx.agentEvidence.byTask(TASK)
      expect(trail.bindings).toHaveLength(2)
      expect(trail.bindings.map(binding => binding.goalRevision)).toEqual([3, 4])
      expect(trail.bindings[0]).toEqual(first)
    } finally {
      await h.dispose()
    }
  })
})
