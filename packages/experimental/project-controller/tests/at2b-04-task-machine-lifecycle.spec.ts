/**
 * AT2B-04 任务机九态走通 — anchored from
 * `scenarios/AT2B-04-task-machine-lifecycle.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：九态 TaskState 全序走通（七态调度脊 + blocked/failed 往返）；
 * developing 预算恰在进入处拒绝、离开时释放（maxActiveTasks: 1）；每个
 * move 返回更新后 record；非法 move fail loud、record 不变；dispatch 类
 * move 要求 admission_open。
 *
 * @module tests/at2b-04-task-machine-lifecycle
 */

import { expect, describe, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness } from './helpers.ts'

const TASK1 = TaskId('t-1')
const TASK2 = TaskId('t-2')
const PLUGIN = PluginId('plugin-a')
const TRIPLE = {
  blockedReason: 'integration gate is red',
  nextAction: 'retry the merge after the gate greens',
  wakeCondition: 'the gate reports green again',
}

/** Assert the move fails loud with the exact stable code and reason text. */
async function expectMoveRejected(move: Promise<unknown>, code: string, message: string): Promise<void> {
  await expect(move).rejects.toMatchObject({ code, message })
}

describe('AT2B-04 task machine lifecycle', () => {
  it('walks the seven-state dispatch spine under a one-slot developing budget', async () => {
    const h = await harness({ maxActiveTasks: 1 })
    try {
      // Dispatch moves require explicit admission: the fresh process starts stopped.
      await expect(h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Wire the gate' }))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' })
      expect(h.ctx.projectController.startProject()).toBe('admission_open')

      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      const worker2 = h.ctx.sessions.create(SessionId('worker-2'), { meta: { cwd: h.root } })

      const planned = await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Wire the gate' })
      expect(planned.state).toBe('planned')
      const createdAt = planned.createdAt

      const assigned = await h.ctx.projectController.assign(TASK1, worker1.id)
      expect(assigned.state).toBe('assigned')
      expect(assigned.assigneeSessionId).toBe(worker1.id)
      expect(assigned.createdAt).toBe(createdAt)
      expect(assigned.updatedAt).not.toBe(createdAt)

      const developing = await h.ctx.projectController.startDevelopment(TASK1)
      expect(developing.state).toBe('developing')

      // The second task fills up to assigned, then hits the one-slot budget.
      await h.ctx.projectController.createTask({ taskId: TASK2, pluginId: PLUGIN, title: 'Second slice' })
      await h.ctx.projectController.assign(TASK2, worker2.id)
      await expect(h.ctx.projectController.startDevelopment(TASK2)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED',
        message: 'the developing budget of 1 is exhausted',
      })
      expect(h.ctx.projectController.find(TASK2)?.state).toBe('assigned')

      // Leaving developing releases the slot; the dispatch spine completes on t-1.
      expect((await h.ctx.projectController.beginReview(TASK1)).state).toBe('reviewing')
      expect((await h.ctx.projectController.submit(TASK1)).state).toBe('submitted')
      const controller = h.ctx.sessions.create(SessionId('controller-1'), { meta: { cwd: h.root } })
      await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
      const marker = await h.ctx.projectController.requestMainTreeMerge(controller.id, TASK1)
      expect(marker.taskId).toBe(TASK1)
      expect(marker.callerSessionId).toBe(controller.id)
      expect(marker.mergeId).toBeTruthy()
      expect(marker.createdAt).toBeTruthy()
      expect((await h.ctx.projectController.integrate(TASK1, marker)).state).toBe('integrated')
      expect((await h.ctx.projectController.complete(TASK1)).state).toBe('completed')
      expect(h.ctx.projectController.find(TASK1)?.createdAt).toBe(createdAt)

      // The retry lands now that the budget freed up.
      expect((await h.ctx.projectController.startDevelopment(TASK2)).state).toBe('developing')
    } finally {
      await h.dispose()
    }
  })

  it('rejects an illegal move fail loud with the record unchanged', async () => {
    const h = await harness({ maxActiveTasks: 1 })
    try {
      h.ctx.projectController.startProject()
      await h.ctx.projectController.createTask({ taskId: TASK2, pluginId: PLUGIN, title: 'Second slice' })
      const before = h.ctx.projectController.find(TASK2)
      await expectMoveRejected(
        h.ctx.projectController.beginReview(TASK2),
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
        'task "t-2" cannot move planned → reviewing',
      )
      expect(h.ctx.projectController.find(TASK2)).toEqual(before)
    } finally {
      await h.dispose()
    }
  })

  it('round-trips the blocked and failed states back into dispatch', async () => {
    const h = await harness({ maxActiveTasks: 1 })
    try {
      h.ctx.projectController.startProject()
      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK2, pluginId: PLUGIN, title: 'Second slice' })
      await h.ctx.projectController.assign(TASK2, worker1.id)

      const blocked = await h.ctx.projectController.block(TASK2, TRIPLE)
      expect(blocked.state).toBe('blocked')
      expect(blocked.blockedReason).toBe(TRIPLE.blockedReason)
      expect(blocked.nextAction).toBe(TRIPLE.nextAction)
      expect(blocked.wakeCondition).toBe(TRIPLE.wakeCondition)
      expect((await h.ctx.projectController.resume(TASK2)).state).toBe('assigned')

      expect((await h.ctx.projectController.startDevelopment(TASK2)).state).toBe('developing')
      const failed = await h.ctx.projectController.fail(TASK2, TRIPLE)
      expect(failed.state).toBe('failed')
      expect((await h.ctx.projectController.resume(TASK2)).state).toBe('assigned')
    } finally {
      await h.dispose()
    }
  })
})
