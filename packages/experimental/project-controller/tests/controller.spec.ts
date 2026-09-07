/** Behavior tests for the project controller over the real storage composition. */

import { expect, describe, it } from 'vitest'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness, unavailableMergeRequest } from './helpers.ts'
import { MainTreeMergeMarker, ProjectControllerError } from '../src/index.ts'

const CWD = (h: { root: string }) => join(h.root, `ws-${Math.random().toString(36).slice(2, 8)}`)
const TASK = (n: string) => TaskId(`task-${n}`)
const PLUGIN = PluginId('agent-reliability')

/** Bind one live session under a role and return its id. */
async function bindSession(
  h: Awaited<ReturnType<typeof harness>>,
  role: 'controller' | 'lead' | 'worker',
): Promise<SessionId> {
  const session = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
  await h.ctx.agentBindings.bind({ agentId: session.id, role })
  return session.id
}

describe('task dispatch', () => {
  it('moves through submission and refuses integration without evidence', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const controller = await bindSession(h, 'controller')
      const worker = await bindSession(h, 'worker')

      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'Wire the gate' })
      expect(h.ctx.projectController.find(TASK('1'))?.state).toBe('planned')

      await h.ctx.projectController.assign(TASK('1'), worker)
      await h.ctx.projectController.startDevelopment(TASK('1'))
      await h.ctx.projectController.beginReview(TASK('1'))
      await h.ctx.projectController.submit(TASK('1'))
      expect(h.ctx.projectController.find(TASK('1'))?.assigneeSessionId).toBe(worker)

      await expect(h.ctx.projectController.requestMainTreeMerge(controller, TASK('1'), unavailableMergeRequest))
        .rejects.toThrow('evidence projection')
      expect(h.ctx.projectController.find(TASK('1'))?.state).toBe('submitted')
    } finally {
      await h.dispose()
    }
  })

  it('refuses an unknown task, a duplicate task, and illegal moves', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker = await bindSession(h, 'worker')
      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })

      await expect(h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'Dup' }))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_TASK_EXISTS' })
      await expect(h.ctx.projectController.assign(TASK('x'), worker))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_TASK_UNKNOWN' })
      await expect(h.ctx.projectController.startDevelopment(TASK('1')))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ILLEGAL_TRANSITION' })
      await expect(h.ctx.projectController.complete(TASK('1')))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ILLEGAL_TRANSITION' })
    } finally {
      await h.dispose()
    }
  })

  it('bounds concurrent developing tasks by the configured budget', async () => {
    const h = await harness({ maxActiveTasks: 1 })
    try {
      h.ctx.projectController.startProject()
      const worker = await bindSession(h, 'worker')
      for (const n of ['1', '2']) {
        await h.ctx.projectController.createTask({ taskId: TASK(n), pluginId: PLUGIN, title: n })
        await h.ctx.projectController.assign(TASK(n), worker)
      }
      await h.ctx.projectController.startDevelopment(TASK('1'))
      await expect(h.ctx.projectController.startDevelopment(TASK('2')))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED' })
      // Leaving development frees the single slot.
      await h.ctx.projectController.beginReview(TASK('1'))
      const developing = await h.ctx.projectController.startDevelopment(TASK('2'))
      expect(developing.state).toBe('developing')
    } finally {
      await h.dispose()
    }
  })
})

describe('blocked and failed tasks', () => {
  it('requires the full recovery triple and clears it on resume', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker = await bindSession(h, 'worker')
      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })
      await h.ctx.projectController.assign(TASK('1'), worker)

      await expect(h.ctx.projectController.block(TASK('1'), {
        blockedReason: 'registry down', nextAction: 'retry', wakeCondition: '  ',
      })).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_INVALID_DETAIL' })

      const blocked = await h.ctx.projectController.block(TASK('1'), {
        blockedReason: 'registry down',
        nextAction: 'retry the bind',
        wakeCondition: 'ctx.worktreeRegistry is reachable again',
      })
      expect(blocked.state).toBe('blocked')
      expect(blocked.blockedReason).toBe('registry down')

      const resumed = await h.ctx.projectController.resume(TASK('1'))
      expect(resumed.state).toBe('assigned')
      expect(resumed.assigneeSessionId).toBe(worker)
      expect(resumed.blockedReason).toBeUndefined()
      expect(resumed.wakeCondition).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('fails from an active state and resumes back into dispatch', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker = await bindSession(h, 'worker')
      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })
      await h.ctx.projectController.assign(TASK('1'), worker)
      await h.ctx.projectController.startDevelopment(TASK('1'))

      const failed = await h.ctx.projectController.fail(TASK('1'), {
        blockedReason: 'tests irrecoverably red',
        nextAction: 'open a follow-up task',
        wakeCondition: 'never for this task id',
      })
      expect(failed.state).toBe('failed')
      const replacement = await bindSession(h, 'worker')
      const resumed = await h.ctx.projectController.resume(TASK('1'), replacement)
      expect(resumed.state).toBe('assigned')
      expect(resumed.assigneeSessionId).toBe(replacement)
      expect(resumed.blockedReason).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })
})

describe('merge gate', () => {
  it('rejects unbound and non-controller callers and forged markers', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const controller = await bindSession(h, 'controller')
      const lead = await bindSession(h, 'lead')
      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })
      await h.ctx.projectController.assign(TASK('1'), lead)
      await h.ctx.projectController.startDevelopment(TASK('1'))
      await h.ctx.projectController.beginReview(TASK('1'))
      await h.ctx.projectController.submit(TASK('1'))

      await expect(h.ctx.projectController.requestMainTreeMerge(lead, TASK('1'), unavailableMergeRequest))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_NOT_CONTROLLER' })
      await expect(h.ctx.projectController.requestMainTreeMerge(SessionId('session-none'), TASK('1'), unavailableMergeRequest))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_NOT_CONTROLLER' })

      const forged: MainTreeMergeMarker = {
        mergeId: 'forged', taskId: TASK('1'), callerSessionId: controller, createdAt: 'now',
      }
      await expect(h.ctx.projectController.integrate(TASK('1'), forged))
        .rejects.toBeInstanceOf(ProjectControllerError)
    } finally {
      await h.dispose()
    }
  })
})

describe('project lifecycle', () => {
  it('closes admission on stop and holds quiescence until no task is in flight', async () => {
    const h = await harness()
    try {
      h.ctx.projectController.startProject()
      const worker = await bindSession(h, 'worker')
      await h.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })
      await h.ctx.projectController.assign(TASK('1'), worker)

      h.ctx.projectController.requestStop()
      await expect(h.ctx.projectController.createTask({ taskId: TASK('2'), pluginId: PLUGIN, title: 'Two' }))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' })
      await expect(h.ctx.projectController.startDevelopment(TASK('1')))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' })
      // confirmQuiescence is synchronous; a sync throw must be caught directly.
      try {
        h.ctx.projectController.confirmQuiescence()
        expect.unreachable('quiescence must not confirm while tasks are in flight')
      } catch (error: unknown) {
        expect(error).toMatchObject({ code: 'PROJECT_CONTROLLER_QUIESCENCE_INCOMPLETE' })
      }

      // Recording the stop reason is still possible while admission is closed.
      const blocked = await h.ctx.projectController.block(TASK('1'), {
        blockedReason: 'project stop requested',
        nextAction: 're-dispatch after restart',
        wakeCondition: 'a fresh controller opens admission',
      })
      expect(blocked.state).toBe('blocked')

      h.ctx.projectController.confirmQuiescence()
      expect(h.ctx.projectController.completeStop()).toBe('stopped')
      // No new work and no recording after the stop completed.
      await expect(h.ctx.projectController.createTask({ taskId: TASK('3'), pluginId: PLUGIN, title: 'Three' }))
        .rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' })
    } finally {
      await h.dispose()
    }
  })

  it('rejects lifecycle moves outside their legal order', async () => {
    const h = await harness()
    try {
      expect(() => h.ctx.projectController.requestStop())
        .toThrow(ProjectControllerError)
      h.ctx.projectController.startProject()
      h.ctx.projectController.markAmbiguous()
      expect(h.ctx.projectController.lifecycle).toBe('ambiguous')
      expect(() => h.ctx.projectController.startProject())
        .toThrow(ProjectControllerError)
      h.ctx.projectController.markNeedsAttention()
      expect(h.ctx.projectController.requestStop()).toBe('stop_requested')
      expect(() => h.ctx.projectController.completeStop())
        .toThrow(ProjectControllerError)
      h.ctx.projectController.confirmQuiescence()
      expect(h.ctx.projectController.completeStop()).toBe('stopped')
      expect(h.ctx.projectController.startProject()).toBe('admission_open')
    } finally {
      await h.dispose()
    }
  })
})

describe('cold restore', () => {
  it('restores the board verbatim and refuses a new controller without evidence', async () => {
    const h1 = await harness()
    h1.ctx.projectController.startProject()
    await bindSession(h1, 'controller')
    const worker = await bindSession(h1, 'worker')
    await h1.ctx.projectController.createTask({ taskId: TASK('1'), pluginId: PLUGIN, title: 'One' })
    await h1.ctx.projectController.assign(TASK('1'), worker)
    await h1.ctx.projectController.startDevelopment(TASK('1'))
    await h1.ctx.projectController.beginReview(TASK('1'))
    await h1.ctx.projectController.submit(TASK('1'))
    const root = h1.root
    await h1.dispose({ keepRoot: true })

    const h2 = await harness({ maxActiveTasks: 2 }, root)
    try {
      // In-flight work died with the process; the submitted record returns verbatim.
      expect(h2.ctx.projectController.find(TASK('1'))?.state).toBe('submitted')
      h2.ctx.projectController.startProject()
      const controller2 = await bindSession(h2, 'controller')
      await expect(h2.ctx.projectController.requestMainTreeMerge(controller2, TASK('1'), unavailableMergeRequest))
        .rejects.toThrow('evidence projection')
    } finally {
      await h2.dispose()
    }
  })
})
