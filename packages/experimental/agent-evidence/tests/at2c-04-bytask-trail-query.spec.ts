/**
 * AT2C-04 byTask 轨迹查询 — anchored from
 * `scenarios/AT2C-04-bytask-trail-query.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：byTask 三轨各自按 recorded 序返回且跨任务隔离；bindingsByGoal
 * controller+goal 双键过滤；未知任务返回三空轨（数据非错误）；查询全程
 * 只读、零落盘变化。
 *
 * 与草案的已记差异：草案"三表终态行数（bindings 3 / submissions 2 /
 * verifications 3）"与其自身逐任务计数（bindings 2+1+1）不一致；本文件按
 * 逐任务计数锚定，bindings 总行数为 4。
 *
 * @module tests/at2c-04-bytask-trail-query
 */

import { expect, describe, it } from 'vitest'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
// dsh-goal exports the GoalId factory as a value and the GoalId brand as a
// type from its types face — dual imports mirror the devframe controller precedent.
import { GoalId as makeGoalId } from '@deepseek-ai/dsh-goal'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { SessionId } from '@deepseek-ai/dsh-session'
import { harness } from './helpers.ts'

const T1 = TaskId('t-1')
const T2 = TaskId('t-2')
const T3 = TaskId('t-3')
const CONTROLLER1 = ControllerSessionId('controller-1')
const GOAL1 = makeGoalId('goal-1')
const GOAL2 = makeGoalId('goal-2')

/** Record one binding receipt for a task/goal/revision triple. */
function recordBinding(h: Awaited<ReturnType<typeof harness>>, taskId: TaskId, goalId: GoalId, goalRevision: number) {
  return h.ctx.agentEvidence.recordTaskGoalBinding({
    taskId,
    controllerSessionId: CONTROLLER1,
    goalId,
    goalRevision,
    workspaceId: WorkspaceId('ws-default'),
    acceptanceHash: AcceptanceHash('acceptance:sha256:abc123'),
    sourceFingerprint: SourceFingerprint('source:sha256:def456'),
  })
}

/** Record one submission receipt for a task. */
function recordSubmission(h: Awaited<ReturnType<typeof harness>>, taskId: TaskId) {
  return h.ctx.agentEvidence.recordSubmission({
    taskId,
    submittedBy: SessionId('worker-1'),
    commit: 'a'.repeat(64),
    changedPaths: ['packages/a/src/x.ts'],
    inputDigest: SourceFingerprint('source:sha256:def456'),
  })
}

/** Record one verification snapshot for a task. */
function recordVerification(h: Awaited<ReturnType<typeof harness>>, taskId: TaskId, exitCode: number) {
  return h.ctx.agentEvidence.recordVerification({
    taskId,
    command: `pnpm exec vitest run --exit-${exitCode}`,
    exitCode,
    artifactPaths: [],
  })
}

/** The draft's deliberately interleaved seed: three tasks share controller-1. */
async function seed(h: Awaited<ReturnType<typeof harness>>): Promise<void> {
  await recordBinding(h, T1, GOAL1, 3)
  await recordSubmission(h, T1)
  await recordSubmission(h, T2)
  await recordBinding(h, T1, GOAL1, 4)
  await recordVerification(h, T1, 0)
  await recordVerification(h, T1, 1)
  await recordBinding(h, T2, GOAL1, 3)
  await recordVerification(h, T2, 0)
  await recordBinding(h, T3, GOAL2, 1)
}

describe('AT2C-04 byTask trail query', () => {
  it('returns each trail in recorded order and isolated across tasks', async () => {
    const h = await harness()
    try {
      await seed(h)

      const t1 = h.ctx.agentEvidence.byTask(T1)
      expect(t1.bindings.map(binding => binding.goalRevision)).toEqual([3, 4])
      expect(t1.submissions).toHaveLength(1)
      expect(t1.verifications.map(snapshot => snapshot.exitCode)).toEqual([0, 1])
      expect(t1.bindings.every(binding => binding.taskId === T1)).toBe(true)

      const t2 = h.ctx.agentEvidence.byTask(T2)
      expect(t2.bindings).toHaveLength(1)
      expect(t2.submissions).toHaveLength(1)
      expect(t2.verifications.map(snapshot => snapshot.exitCode)).toEqual([0])

      const t3 = h.ctx.agentEvidence.byTask(T3)
      expect(t3.bindings).toHaveLength(1)
      expect(t3.submissions).toEqual([])
      expect(t3.verifications).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('filters the binding trail by controller and goal, both keys required', async () => {
    const h = await harness()
    try {
      await seed(h)

      const goal1 = h.ctx.agentEvidence.bindingsByGoal(CONTROLLER1, GOAL1)
      expect(goal1.map(binding => [binding.taskId, binding.goalRevision]))
        .toEqual([[T1, 3], [T1, 4], [T2, 3]])

      const goal2 = h.ctx.agentEvidence.bindingsByGoal(CONTROLLER1, GOAL2)
      expect(goal2.map(binding => binding.taskId)).toEqual([T3])

      // A different controller key matches nothing.
      expect(h.ctx.agentEvidence.bindingsByGoal(ControllerSessionId('controller-2'), GOAL1)).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('answers an unknown task with three empty trails and never writes', async () => {
    const h = await harness()
    try {
      await seed(h)
      expect(h.ctx.agentEvidence.byTask(TaskId('task-none'))).toEqual({
        bindings: [], submissions: [], verifications: [],
      })

      // The whole query sequence is read-only: the tables still hold the seed.
      expect(h.ctx.agentEvidence.byTask(T1).bindings).toHaveLength(2)
      expect(h.ctx.agentEvidence.byTask(T2).submissions).toHaveLength(1)
      expect(h.ctx.agentEvidence.bindingsByGoal(CONTROLLER1, GOAL1)).toHaveLength(3)
      const all = [...h.ctx.agentEvidence.byTask(T1).bindings, ...h.ctx.agentEvidence.byTask(T2).bindings, ...h.ctx.agentEvidence.byTask(T3).bindings]
      expect(all).toHaveLength(4)
      expect([
        ...h.ctx.agentEvidence.byTask(T1).submissions, ...h.ctx.agentEvidence.byTask(T2).submissions,
      ]).toHaveLength(2)
      expect([
        ...h.ctx.agentEvidence.byTask(T1).verifications, ...h.ctx.agentEvidence.byTask(T2).verifications,
      ]).toHaveLength(3)
    } finally {
      await h.dispose()
    }
  })
})
