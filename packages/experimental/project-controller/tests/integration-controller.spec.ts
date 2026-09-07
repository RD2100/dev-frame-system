/** Execution-time evidence and recovery over real storage, projection, and Git worktrees. */
import { describe, expect, it, vi } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import { DevFrameDeliveryId, DevFrameReviewId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { DevFrameSnapshotId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/src/source-fingerprint.ts'
import { prepareIntegration, mountIntegrationRegistries } from './integration-harness.ts'
import { harness } from './helpers.ts'
import { executeIntegrationGit } from '../src/git-integration.ts'

// Each case creates three real linked worktrees and may cold-open four durable domains.
describe('controller integration admission and recovery', { timeout: 30_000 }, () => {
  it('requires new delivery evidence after the Worker rebases onto a newer target', async () => {
    const f = await prepareIntegration()
    try {
      await f.git(f.request.git.targetPath, 'commit', '--allow-empty', '-m', 'target advancement')
      const targetHead = await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')
      await f.git(f.request.git.sourcePath, 'rebase', 'target')
      const sourceCommit = await f.git(f.request.git.sourcePath, 'rev-parse', 'HEAD')
      expect(sourceCommit).not.toBe(f.delivery.sourceCommit)
      const request = { ...f.request, git: { ...f.request.git, sourceCommit, targetHead } }
      await expect(f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, request))
        .rejects.toThrow('source commit does not match')
      f.controller.append('devframe/task-delivery', {
        ...f.delivery, deliveryId: DevFrameDeliveryId('delivery-rebased'), sourceCommit,
        snapshotId: DevFrameSnapshotId('snapshot-rebased'),
        sourceFingerprint: (await computeSourceFingerprint({ worktreePath: request.git.sourcePath })).fingerprint,
      })
      await expect(f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, request))
        .rejects.toThrow('persisted verification and review')
      expect(await f.git(request.git.targetPath, 'rev-parse', 'HEAD')).toBe(targetHead)
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
    } finally { await f.h.dispose() }
  })

  it('fast-forwards a reviewed task once and rejects marker replay and cross-task use', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      await expect(f.h.ctx.projectController.integrate(f.taskId, { ...marker })).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect((await f.h.ctx.projectController.integrate(f.taskId, marker)).state).toBe('integrated')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.sourceCommit)
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect((await f.h.ctx.projectController.complete(f.taskId)).state).toBe('completed')
    } finally { await f.h.dispose() }
  })

  it('rejects a newer negative review after a marker was prepared', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      f.controller.append('devframe/review', { ...f.review, reviewId: DevFrameReviewId('negative'), decision: 'changes_required' })
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('review')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
    } finally { await f.h.dispose() }
  })

  it('rejects evidence arriving while asynchronous source admission is pending', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const load = f.request.requiredChecksStore.load.bind(f.request.requiredChecksStore)
      const spy = vi.spyOn(f.request.requiredChecksStore, 'load').mockImplementation(async (digest) => {
        f.controller.append('devframe/review', { ...f.review, reviewId: DevFrameReviewId('concurrent-negative'), decision: 'changes_required' })
        return await load(digest)
      })
      try { await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('evidence changed') }
      finally { spy.mockRestore() }
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('requires an explicit retry and invalidates the old prepared marker', async () => {
    const f = await prepareIntegration()
    try {
      const old = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      await expect(f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)).rejects.toThrow('durable intent')
      const fresh = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, { ...f.request, retryUnchanged: true })
      await expect(f.h.ctx.projectController.integrate(f.taskId, old)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect((await f.h.ctx.projectController.integrate(f.taskId, fresh)).state).toBe('integrated')
    } finally { await f.h.dispose() }
  })

  it('restores a prepared intent after Git applied and records it without another merge or evidence replay', async () => {
    const f = await prepareIntegration()
    let live = f.h
    try {
      await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      expect((await executeIntegrationGit(f.request.git, f.request.options)).observation.kind).toBe('applied')
      await f.h.dispose({ keepRoot: true })
      live = await harness({}, f.h.root)
      await mountIntegrationRegistries(live)
      live.ctx.projectController.startProject()
      expect(live.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
      expect((await live.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskId, f.request.options)).kind).toBe('applied')
      expect(live.ctx.projectController.find(f.taskId)?.state).toBe('integrated')
      const domain = live.ctx.storageDomain.get('project_tasks')!
      expect(domain.table('integrations').get(f.taskId)).toMatchObject({ state: 'applied' })
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.sourceCommit)
    } finally { await live.dispose() }
  })
  it('rejects a required-memory failure recorded after preparation', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      f.controller.append('devframe/task-warning', { version: 1, taskId: f.taskId, warning: 'MEMORY_APPEND_DISABLED', tool: 'memory_append', grade: 'fail' })
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('task-warning')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('recovers after applied receipt persisted but task-board persistence failed', async () => {
    const f = await prepareIntegration()
    let live = f.h
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const domain = f.h.ctx.storageDomain.get('project_tasks')!
      const table = domain.table('tasks')
      const spy = vi.spyOn(table, 'put').mockRejectedValueOnce(new Error('interrupted board write'))
      try { await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_PERSISTENCE' }) }
      finally { spy.mockRestore() }
      expect(domain.table('integrations').get(f.taskId)).toMatchObject({ state: 'applied' })
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
      await f.h.dispose({ keepRoot: true })
      live = await harness({}, f.h.root)
      await mountIntegrationRegistries(live)
      live.ctx.projectController.startProject()
      expect((await live.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskId, f.request.options)).kind).toBe('applied')
      expect(live.ctx.projectController.find(f.taskId)?.state).toBe('integrated')
    } finally { await live.dispose() }
  })

  it('keeps an ambiguous target unchanged and never retries its prepared intent', async () => {
    const f = await prepareIntegration()
    try {
      await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      await f.git(f.request.git.targetPath, 'commit', '--allow-empty', '-m', 'other writer')
      const head = await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')
      expect((await f.h.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskId, f.request.options)).kind).toBe('ambiguous')
      await expect(f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, { ...f.request, retryUnchanged: true })).rejects.toThrow('durable intent')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(head)
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
    } finally { await f.h.dispose() }
  })

  it('refuses a source writer lock released after preparation', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const binding = f.h.ctx.agentBindings.find(f.worker.id)!
      await f.h.ctx.worktreeRegistry.unbind(binding.worktreeId!, WorktreeLockHolder(f.worker.id))
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('writer locks')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('refuses cancellation after preparation without consuming the target commit', async () => {
    const f = await prepareIntegration()
    try {
      const abort = new AbortController()
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, { ...f.request, signal: abort.signal })
      abort.abort(new Error('tool cancelled'))
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('tool cancelled')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('reconciles a failed applied-receipt write from the retained prepared intent', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const table = f.h.ctx.storageDomain.get('project_tasks')!.table('integrations')
      const spy = vi.spyOn(table, 'put').mockRejectedValueOnce(new Error('interrupted receipt write'))
      try { await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('interrupted receipt write') }
      finally { spy.mockRestore() }
      expect(table.get(f.taskId)).toMatchObject({ state: 'prepared' })
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.sourceCommit)
      expect((await f.h.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskId, f.request.options)).kind).toBe('applied')
      expect(f.h.ctx.projectController.find(f.taskId)?.state).toBe('integrated')
    } finally { await f.h.dispose() }
  })

  it('leaves a cold prepared intent unchanged without silently retrying Git', async () => {
    const f = await prepareIntegration()
    let live = f.h
    try {
      const old = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      await f.h.dispose({ keepRoot: true })
      live = await harness({}, f.h.root)
      await mountIntegrationRegistries(live)
      live.ctx.projectController.startProject()
      expect((await live.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskId, f.request.options)).kind).toBe('unchanged')
      await expect(live.ctx.projectController.integrate(f.taskId, old)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_MARKER_INVALID' })
      expect(live.ctx.projectController.find(f.taskId)?.state).toBe('submitted')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await live.dispose() }
  })

  it('closes admission while source verification is awaiting its configured checks', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const load = f.request.requiredChecksStore.load.bind(f.request.requiredChecksStore)
      const spy = vi.spyOn(f.request.requiredChecksStore, 'load').mockImplementation(async (digest) => {
        f.h.ctx.projectController.requestStop()
        return await load(digest)
      })
      try { await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' }) }
      finally { spy.mockRestore() }
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('waits for an admitted operation to settle before closing its domain on disposal', async () => {
    const f = await prepareIntegration()
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    let entered!: () => void
    const atChecks = new Promise<void>((resolve) => { entered = resolve })
    let operation: Promise<unknown> | undefined
    let disposal: Promise<unknown> | undefined
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const load = f.request.requiredChecksStore.load.bind(f.request.requiredChecksStore)
      const spy = vi.spyOn(f.request.requiredChecksStore, 'load').mockImplementation(async (digest) => {
        entered()
        await gate
        return await load(digest)
      })
      try {
        operation = f.h.ctx.projectController.integrate(f.taskId, marker)
        const rejected = expect(operation).rejects.toMatchObject({ code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED' })
        await atChecks
        let disposed = false
        disposal = f.h.ctx.projectController.ctx.fiber.dispose().then(() => { disposed = true })
        await Promise.resolve()
        expect(disposed).toBe(false)
        release()
        await rejected
        await disposal
        expect(disposed).toBe(true)
        expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
      } finally { spy.mockRestore() }
    } finally {
      release()
      await Promise.allSettled([operation, disposal])
      await f.h.dispose()
    }
  })

  it.each(['stopped', 'superseded'] as const)('refuses historical task evidence when its Goal is %s', async (change) => {
    const f = await prepareIntegration()
    try {
      const state = f.h.ctx.sessionProjections.stateOf(f.controller, 'devframe')
      const original = state.bindings[0]!
      if (change === 'stopped') {
        for (const lifecycle of ['stop_requested', 'quiescence_confirmed', 'stopped'] as const) {
          f.controller.append('devframe/goal-binding', { ...original, lifecycle })
        }
      } else {
        f.controller.append('devframe/goal-binding', {
          ...original, goalId: GoalId('replacement-goal'), taskIds: [GoalTaskId('different-task')],
        })
      }
      expect(f.h.ctx.sessionProjections.stateOf(f.controller, 'devframe').failure).toBeNull()
      await expect(f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request))
        .rejects.toThrow('current Goal')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

  it('refuses a prepared marker after a different Goal becomes current', async () => {
    const f = await prepareIntegration()
    try {
      const marker = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
      const original = f.h.ctx.sessionProjections.stateOf(f.controller, 'devframe').bindings[0]!
      f.controller.append('devframe/goal-binding', {
        ...original, goalId: GoalId('replacement-goal'), taskIds: [GoalTaskId('different-task')],
      })
      await expect(f.h.ctx.projectController.integrate(f.taskId, marker)).rejects.toThrow('current Goal')
      expect(await f.git(f.request.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.request.git.targetHead)
    } finally { await f.h.dispose() }
  })

})
