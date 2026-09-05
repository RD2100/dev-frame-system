/**
 * AT2B-05 blocked 三元组与恢复 — anchored from
 * `scenarios/AT2B-05-blocked-triple-recovery.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：blocked/failed 恢复三元组逐字段强制非空 trim（缺字段/空串/纯空白
 * 各自报 INVALID_DETAIL 且文本逐字段点名、record 不改写）；合法 block 落盘
 * 三字段逐字；resume 清三元组经 assigned 回调度，缺省保留、显式替换
 * assignee；failed → completed 为非法转移。
 *
 * @module tests/at2b-05-blocked-triple-recovery
 */

import { expect, describe, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness } from './helpers.ts'
import type { TaskBlockDetail } from '../src/index.ts'

const TASK1 = TaskId('t-1')
const TASK2 = TaskId('t-2')
const PLUGIN = PluginId('plugin-a')
const TRIPLE: TaskBlockDetail = {
  blockedReason: 'registry down',
  nextAction: 'retry the bind',
  wakeCondition: 'ctx.worktreeRegistry is reachable again',
}
const TRIPLE2: TaskBlockDetail = {
  blockedReason: 'tests irrecoverably red',
  nextAction: 'open a follow-up task',
  wakeCondition: 'a fresh controller opens admission',
}

/** One triple with exactly one field deleted, so each probe breaks a single field. */
function tripleWithout(key: keyof TaskBlockDetail): TaskBlockDetail {
  const { [key]: _omitted, ...rest } = TRIPLE
  return rest as TaskBlockDetail
}

describe('AT2B-05 blocked triple recovery', () => {
  it('rejects a blocked move one broken field at a time, leaving the record assigned', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Recovery probe' })
      await h.ctx.projectController.assign(TASK1, worker1.id)

      await expect(h.ctx.projectController.block(TASK1, tripleWithout('nextAction'))).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_INVALID_DETAIL',
        message: 'nextAction must be a non-empty trimmed string',
      })
      await expect(h.ctx.projectController.block(TASK1, { ...TRIPLE, wakeCondition: '  ' })).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_INVALID_DETAIL',
        message: 'wakeCondition must be a non-empty trimmed string',
      })
      await expect(h.ctx.projectController.block(TASK1, tripleWithout('blockedReason'))).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_INVALID_DETAIL',
        message: 'blockedReason must be a non-empty trimmed string',
      })
      await expect(h.ctx.projectController.block(TASK1, { ...TRIPLE, blockedReason: '' })).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_INVALID_DETAIL',
        message: 'blockedReason must be a non-empty trimmed string',
      })
      expect(h.ctx.projectController.find(TASK1)?.state).toBe('assigned')
    } finally {
      await h.dispose()
    }
  })

  it('persists the triple verbatim on block and clears it on resume, keeping the assignee', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Recovery probe' })
      await h.ctx.projectController.assign(TASK1, worker1.id)

      const blocked = await h.ctx.projectController.block(TASK1, TRIPLE)
      expect(blocked.state).toBe('blocked')
      expect(blocked.blockedReason).toBe('registry down')
      expect(blocked.nextAction).toBe('retry the bind')
      expect(blocked.wakeCondition).toBe('ctx.worktreeRegistry is reachable again')

      const resumed = await h.ctx.projectController.resume(TASK1)
      expect(resumed.state).toBe('assigned')
      expect(resumed.assigneeSessionId).toBe(worker1.id)
      expect(resumed.blockedReason).toBeUndefined()
      expect(resumed.nextAction).toBeUndefined()
      expect(resumed.wakeCondition).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('fails from developing with the triple and resumes into a replacement assignee', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      const worker2 = h.ctx.sessions.create(SessionId('worker-2'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Recovery probe' })
      await h.ctx.projectController.assign(TASK1, worker1.id)
      expect((await h.ctx.projectController.startDevelopment(TASK1)).state).toBe('developing')

      const failed = await h.ctx.projectController.fail(TASK1, TRIPLE2)
      expect(failed.state).toBe('failed')
      expect(failed.blockedReason).toBe(TRIPLE2.blockedReason)
      expect(failed.nextAction).toBe(TRIPLE2.nextAction)
      expect(failed.wakeCondition).toBe(TRIPLE2.wakeCondition)

      const resumed = await h.ctx.projectController.resume(TASK1, worker2.id)
      expect(resumed.state).toBe('assigned')
      expect(resumed.assigneeSessionId).toBe(worker2.id)
      expect(resumed.blockedReason).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('refuses completed from failed and blocks straight from planned', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker1 = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Recovery probe' })
      await h.ctx.projectController.assign(TASK1, worker1.id)
      expect((await h.ctx.projectController.startDevelopment(TASK1)).state).toBe('developing')
      await h.ctx.projectController.fail(TASK1, TRIPLE2)

      await expect(h.ctx.projectController.complete(TASK1)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
        message: 'task "t-1" cannot move failed → completed',
      })
      expect(h.ctx.projectController.find(TASK1)?.state).toBe('failed')
      expect((await h.ctx.projectController.resume(TASK1)).state).toBe('assigned')

      // block enters from every active state, planned included.
      await h.ctx.projectController.createTask({ taskId: TASK2, pluginId: PLUGIN, title: 'Planned block probe' })
      const blockedFromPlanned = await h.ctx.projectController.block(TASK2, TRIPLE)
      expect(blockedFromPlanned.state).toBe('blocked')
    } finally {
      await h.dispose()
    }
  })
})
