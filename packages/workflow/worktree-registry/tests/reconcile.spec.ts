import { existsSync } from 'node:fs'
import { realpath, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { git, gitStyle, harness } from './helpers.ts'

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

/** Boot the shared harness and track the context and root for cleanup. */
async function boot(providerConfig: Record<string, unknown> = {}): Promise<Awaited<ReturnType<typeof harness>>> {
  const prepared = await harness(providerConfig)
  contexts.push(prepared.ctx)
  roots.push(prepared.root)
  return prepared
}

describe('worktree registry reconcile', () => {
  it('reports agreement when registry rows and git worktrees match', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    const report = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(report).toEqual({ dangling: [], unregistered: [], removedRows: [], adoptedPaths: [] })
  })

  it('rejects an unknown workspace', async () => {
    const { ctx, createRepoWorkspace } = await boot()
    await createRepoWorkspace('repo')

    await expect(ctx.worktreeRegistry.reconcile(WorkspaceId('no-such-workspace')))
      .rejects.toThrow(/unknown workspace/)
  })

  it('detects a row whose directory vanished outside the product', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await rm(worktree.path, { recursive: true, force: true })

    const report = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(report.dangling).toEqual([
      { id: worktree.id, path: worktree.path, reason: 'directory-missing' },
    ])
    expect(report.unregistered).toEqual([])
    // git still lists the dead admin entry; only the registry half is stale so far.
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).toContain('wt-a')
  })

  it('detects a row git no longer tracks while its directory remains', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    // Deleting git's admin entry forgets the worktree without touching its files.
    await rm(join(repo, '.git', 'worktrees', 'wt-a'), { recursive: true, force: true })

    const report = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(report.dangling).toEqual([{ id: worktree.id, path: worktree.path, reason: 'git-unknown' }])
    expect(existsSync(worktree.path)).toBe(true)
  })

  it('drops dangling rows with pruneRows, prunes dead git entries, and never deletes files', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const vanished = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-gone') })
    const untracked = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-orphan') })
    await rm(vanished.path, { recursive: true, force: true })
    await rm(join(repo, '.git', 'worktrees', 'wt-orphan'), { recursive: true, force: true })
    const orphanDirectory = untracked.path

    const report = await ctx.worktreeRegistry.reconcile(workspaceId, { pruneRows: true })

    expect(report.removedRows).toEqual(expect.arrayContaining([vanished.id, untracked.id]))
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    // The git-prunable entry left git's list; the orphan's files were never touched.
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain('wt-gone')
    expect(existsSync(orphanDirectory)).toBe(true)
  })

  it('reports worktrees created outside the product and adopts them with observed facts', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    await git(repo, 'worktree', 'add', '-b', 'external/x', join(root, 'external'))

    const observed = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(observed.unregistered).toEqual([
      { path: await realpath(join(root, 'external')), branch: 'external/x' },
    ])
    expect(observed.dangling).toEqual([])

    const adopted = await ctx.worktreeRegistry.reconcile(workspaceId, { adoptUnregistered: true })

    expect(adopted.adoptedPaths).toEqual([await realpath(join(root, 'external'))])
    const [row] = ctx.worktreeRegistry.list(workspaceId)
    expect(row?.branch).toBe('external/x')
    expect(row?.path).toBe(await realpath(join(root, 'external')))
    // The adopted row is a first-class registration: a second pass reports agreement.
    await expect(ctx.worktreeRegistry.reconcile(workspaceId))
      .resolves.toEqual({ dangling: [], unregistered: [], removedRows: [], adoptedPaths: [] })
  })

  it('reports a detached-HEAD worktree without a branch and adopts it as HEAD', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    await git(repo, 'worktree', 'add', '--detach', join(root, 'detached'))

    const observed = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(observed.unregistered).toEqual([{ path: await realpath(join(root, 'detached')) }])

    await ctx.worktreeRegistry.reconcile(workspaceId, { adoptUnregistered: true })

    expect(ctx.worktreeRegistry.list(workspaceId).map(worktree => worktree.branch)).toEqual(['HEAD'])
  })

  it('never reports another workspace registration as unregistered', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    // A second workspace over a linked worktree, registered through adopt.
    const linked = join(root, 'linked-ws')
    await git(repo, 'worktree', 'add', '-b', 'linked-ws', linked)
    await ctx.worktreeRegistry.reconcile(workspaceId, { adoptUnregistered: true })
    await ctx.workspaceRegistry.create(linked)

    const report = await ctx.worktreeRegistry.reconcile(workspaceId)

    expect(report.unregistered).toEqual([])
    expect(ctx.worktreeRegistry.list(workspaceId).map(worktree => worktree.branch)).toEqual(['linked-ws'])
  })

  it('reports linked strays but never the repository main worktree from a linked workspace', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { repo } = await createRepoWorkspace('repo')
    const linked = join(root, 'linked-view')
    const stray = join(root, 'stray')
    await git(repo, 'worktree', 'add', '-b', 'linked-view', linked)
    await git(repo, 'worktree', 'add', '-b', 'stray', stray)
    const linkedWorkspace = await ctx.workspaceRegistry.create(linked)

    // From the linked workspace's view the main checkout is a git-tracked
    // worktree, but a repository's root checkout is never a stray; a truly
    // unregistered linked worktree still is.
    const report = await ctx.worktreeRegistry.reconcile(linkedWorkspace.id)

    expect(report.unregistered).toEqual([{ path: await realpath(stray), branch: 'stray' }])
  })

  it('fails loud instead of half-reporting when porcelain output is truncated', async () => {
    const { ctx, root, createRepoWorkspace } = await boot({ maxOutputBytes: 128 })
    const { workspaceId } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await expect(ctx.worktreeRegistry.reconcile(workspaceId)).rejects.toThrow(/maxOutputBytes/)
  })
})
