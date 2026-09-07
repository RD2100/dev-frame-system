/** Controller-only preparation and single-use marker identity over a real integration fixture. */

import { expect, describe, it } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness, unavailableMergeRequest } from './helpers.ts'
import { prepareIntegration } from './integration-harness.ts'

const TASK1 = TaskId('t-1')
const TASK2 = TaskId('t-2')
const PLUGIN = PluginId('plugin-a')

describe('AT2B-06 merge gate controller only', { timeout: 30_000 }, () => {
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

      await expect(h.ctx.projectController.requestMainTreeMerge(lead.id, TASK1, unavailableMergeRequest)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_NOT_CONTROLLER',
        message: `session "${lead.id}" carries role "lead", not "controller"`,
      })
      await expect(h.ctx.projectController.requestMainTreeMerge(unbound.id, TASK1, unavailableMergeRequest)).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_NOT_CONTROLLER',
        message: `session "${unbound.id}" has no agent binding`,
      })
      // The role check precedes the task-state check: a non-controller caller
      // is refused before the task is even consulted.
      await expect(h.ctx.projectController.requestMainTreeMerge(lead.id, TaskId('task-none'), unavailableMergeRequest))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_NOT_CONTROLLER' })
      expect(h.ctx.projectController.find(TASK1)?.state).toBe('submitted')
    } finally {
      await h.dispose()
    }
  })

  it('consumes the admitted marker once and rejects cross-task use', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      await expect(f.h.ctx.projectController.integrate(TASK2, marker)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect((await f.h.ctx.projectController.integrate(f.taskId, marker)).state).toBe('integrated')
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect((await f.h.ctx.projectController.complete(f.taskId)).state).toBe('completed')
    } finally { await f.h.dispose() }
  })
})
