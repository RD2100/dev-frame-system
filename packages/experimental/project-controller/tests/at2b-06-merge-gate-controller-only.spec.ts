/**
 * AT2B-06 合并门非总控拒绝 — anchored from
 * `scenarios/AT2B-06-merge-gate-controller-only.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：只有 controller 绑定会话能铸造合并 marker；角色检查先于任务状态
 * 检查（非 controller 无论任务何态都在铸造前被拒）；无绑定与绑定非
 * controller 两形拒绝同码 NOT_CONTROLLER；marker 单次消费、跨任务即
 * MARKER_INVALID、已消费 marker 在任务前进后仍报 MARKER_INVALID（marker
 * 检查先于状态检查）；双任务正对照走满 integrate+complete。
 *
 * @module tests/at2b-06-merge-gate-controller-only
 */

import { expect, describe, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness } from './helpers.ts'

const TASK1 = TaskId('t-1')
const TASK2 = TaskId('t-2')
const PLUGIN = PluginId('plugin-a')

describe('AT2B-06 merge gate controller only', () => {
  it('refuses lead and unbound callers before minting anything', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const controller = h.ctx.sessions.create(undefined, { meta: { cwd: h.root } })
      await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
      const lead = h.ctx.sessions.create(SessionId('lead-1'), { meta: { cwd: h.root } })
      await h.ctx.agentBindings.bind({ agentId: lead.id, role: 'lead' })
      const unbound = h.ctx.sessions.create(SessionId('drifter-1'), { meta: { cwd: h.root } })
      await h.ctx.projectController.createTask({ taskId: TASK1, pluginId: PLUGIN, title: 'Merge probe' })
      await h.ctx.projectController.assign(TASK1, lead.id)
      await h.ctx.projectController.startDevelopment(TASK1)
      await h.ctx.projectController.beginReview(TASK1)
      await h.ctx.projectController.submit(TASK1)

      await expect(h.ctx.projectController.requestMainTreeMerge(lead.id, TASK1)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_NOT_CONTROLLER',
        message: `session "${lead.id}" carries role "lead", not "controller"`,
      })
      await expect(h.ctx.projectController.requestMainTreeMerge(unbound.id, TASK1)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_NOT_CONTROLLER',
        message: `session "${unbound.id}" has no agent binding`,
      })
      // The role check precedes the task-state check: a non-controller caller
      // is refused before the task is even consulted.
      await expect(h.ctx.projectController.requestMainTreeMerge(lead.id, TaskId('task-none')))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_NOT_CONTROLLER' })
      expect(h.ctx.projectController.find(TASK1)?.state).toBe('submitted')
    } finally {
      await h.dispose()
    }
  })

  it('consumes a controller-minted marker once and rejects cross-task and replayed markers', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const controller = h.ctx.sessions.create(SessionId('controller-1'), { meta: { cwd: h.root } })
      await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
      const worker = h.ctx.sessions.create(SessionId('worker-1'), { meta: { cwd: h.root } })
      for (const taskId of [TASK1, TASK2]) {
        await h.ctx.projectController.createTask({ taskId, pluginId: PLUGIN, title: `Merge ${String(taskId)}` })
        await h.ctx.projectController.assign(taskId, worker.id)
        await h.ctx.projectController.startDevelopment(taskId)
        await h.ctx.projectController.beginReview(taskId)
        await h.ctx.projectController.submit(taskId)
      }

      const marker1 = await h.ctx.projectController.requestMainTreeMerge(controller.id, TASK1)
      const marker2 = await h.ctx.projectController.requestMainTreeMerge(controller.id, TASK2)
      expect(marker1.mergeId).not.toBe(marker2.mergeId)

      // A marker naming another task is invalid; the task stays submitted.
      await expect(h.ctx.projectController.integrate(TASK2, marker1)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_MARKER_INVALID',
        message: `merge marker "${marker1.mergeId}" does not name a pending merge for task "t-2"`,
      })
      expect(h.ctx.projectController.find(TASK2)?.state).toBe('submitted')

      expect((await h.ctx.projectController.integrate(TASK1, marker1)).state).toBe('integrated')
      // Replaying the consumed marker reports MARKER_INVALID even though the
      // task has already moved on: the marker check precedes the state check.
      await expect(h.ctx.projectController.integrate(TASK1, marker1)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_MARKER_INVALID',
      })
      expect(h.ctx.projectController.find(TASK1)?.state).toBe('integrated')

      expect((await h.ctx.projectController.complete(TASK1)).state).toBe('completed')
      expect((await h.ctx.projectController.integrate(TASK2, marker2)).state).toBe('integrated')
      expect((await h.ctx.projectController.complete(TASK2)).state).toBe('completed')
    } finally {
      await h.dispose()
    }
  })
})
