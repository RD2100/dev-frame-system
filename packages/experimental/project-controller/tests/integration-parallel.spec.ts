/** Parallel sibling-branch integration over real storage, projection, and Git worktrees. */
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { prepareParallelIntegration, mountIntegrationRegistries } from './integration-harness.ts'
import { harness } from './helpers.ts'
import { executeIntegrationGit } from '../src/git-integration.ts'

describe('parallel sibling integration', { timeout: 60_000 }, () => {
  it('integrates two sibling tasks fast-forward then merge and persists the mode with the applied head', async () => {
    const f = await prepareParallelIntegration()
    let live = f.h
    try {
      const markerA = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskAId, f.requestA)
      expect((await f.h.ctx.projectController.integrate(f.taskAId, markerA)).state).toBe('integrated')
      expect(await f.git(f.requestA.git.targetPath, 'rev-parse', 'HEAD')).toBe(f.commitA)

      const markerB = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskBId, f.requestB)
      expect((await f.h.ctx.projectController.integrate(f.taskBId, markerB)).state).toBe('integrated')
      const mergeHead = await f.git(f.requestB.git.targetPath, 'rev-parse', 'HEAD')
      expect(mergeHead).not.toBe(f.commitA)
      expect(mergeHead).not.toBe(f.commitB)
      expect(await f.git(f.requestB.git.targetPath, 'rev-list', '--parents', '-n', '1', 'HEAD')).toBe(`${mergeHead} ${f.commitA} ${f.commitB}`)
      expect(await readFile(join(f.requestB.git.targetPath, 'a.txt'), 'utf8')).toBe('reviewed-a\n')
      expect(await readFile(join(f.requestB.git.targetPath, 'b.txt'), 'utf8')).toBe('reviewed-b\n')

      await f.h.dispose({ keepRoot: true })
      live = await harness({}, f.h.root)
      await mountIntegrationRegistries(live)
      live.ctx.projectController.startProject()
      const domain = live.ctx.storageDomain.get('project_tasks')!
      expect(domain.table('integrations').get(f.taskAId)).toMatchObject({ state: 'applied', mode: 'fast-forward', appliedHead: f.commitA })
      expect(domain.table('integrations').get(f.taskBId)).toMatchObject({ state: 'applied', mode: 'merge', appliedHead: mergeHead })
      expect(live.ctx.projectController.find(f.taskAId)?.state).toBe('integrated')
      expect(live.ctx.projectController.find(f.taskBId)?.state).toBe('integrated')
      expect((await live.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskBId, f.options)).kind).toBe('applied')
    } finally { await live.dispose() }
  })

  it('refuses to report applied after the target is amended to a different commit with the same two parents', async () => {
    const f = await prepareParallelIntegration()
    try {
      const markerA = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskAId, f.requestA)
      await f.h.ctx.projectController.integrate(f.taskAId, markerA)
      const markerB = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskBId, f.requestB)
      await f.h.ctx.projectController.integrate(f.taskBId, markerB)
      const recordedHead = await f.git(f.requestB.git.targetPath, 'rev-parse', 'HEAD')

      await f.git(f.requestB.git.targetPath, 'commit', '--amend', '--no-edit', '-m', 'rewritten merge')
      const amendedHead = await f.git(f.requestB.git.targetPath, 'rev-parse', 'HEAD')
      expect(amendedHead).not.toBe(recordedHead)
      await expect(f.h.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskBId, f.options))
        .rejects.toThrow('recorded applied head')
      expect(f.h.ctx.projectController.find(f.taskBId)?.state).toBe('integrated')
    } finally { await f.h.dispose() }
  })

  it('recovers a prepared merge intent whose Git already applied without its receipt', async () => {
    const f = await prepareParallelIntegration()
    let live = f.h
    try {
      const markerA = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskAId, f.requestA)
      await f.h.ctx.projectController.integrate(f.taskAId, markerA)
      // Prepare task B, then let Git apply through the raw executor without
      // recording the receipt: the durable intent stays prepared.
      const markerB = await f.h.ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskBId, f.requestB)
      expect(markerB.taskId).toBe(f.taskBId)
      const applied = await executeIntegrationGit(f.requestB.git, f.options)
      expect(applied.observation.kind).toBe('applied')
      const mergeHead = applied.observation.kind === 'applied' ? applied.observation.head : undefined
      expect(mergeHead).toBeDefined()

      await f.h.dispose({ keepRoot: true })
      live = await harness({}, f.h.root)
      await mountIntegrationRegistries(live)
      live.ctx.projectController.startProject()
      expect(live.ctx.projectController.find(f.taskBId)?.state).toBe('submitted')
      expect((await live.ctx.projectController.reconcileMainTreeIntegration(f.controller.id, f.taskBId, f.options)).kind).toBe('applied')
      expect(live.ctx.projectController.find(f.taskBId)?.state).toBe('integrated')
      const domain = live.ctx.storageDomain.get('project_tasks')!
      expect(domain.table('integrations').get(f.taskBId)).toMatchObject({ state: 'applied', mode: 'merge', appliedHead: mergeHead })
      expect(await f.git(f.requestB.git.targetPath, 'rev-parse', 'HEAD')).toBe(mergeHead)
    } finally { await live.dispose() }
  })
})
