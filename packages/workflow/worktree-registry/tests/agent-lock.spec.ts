import { existsSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { WorktreeGitOperationError, WorktreeId, WorktreeLockError, WorktreeLockHolder } from '../src/index.ts'
import { git, gitStyle, harness } from './helpers.ts'

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

/** Boot the shared harness and track the context and root for cleanup. */
async function boot(): Promise<Awaited<ReturnType<typeof harness>>> {
  const prepared = await harness()
  contexts.push(prepared.ctx)
  roots.push(prepared.root)
  return prepared
}

const WRITER_A = WorktreeLockHolder('session-writer-a')
const WRITER_B = WorktreeLockHolder('session-writer-b')

describe('worktree single-writer binding', () => {
  it('runs create → bind → status → reconcile → remove over real git', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')

    const worktree = await ctx.worktreeRegistry.create({
      workspaceId,
      path: join(root, 'agent-wt'),
      branch: 'agent/one',
    })
    const bound = await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)

    expect(bound.lockedBy).toBe(WRITER_A)
    expect(bound.lockedAt).toBeTypeOf('string')
    expect(bound.updatedAt).toBeTypeOf('string')
    expect(await ctx.worktreeRegistry.status(worktree.id)).toEqual({
      directoryExists: true,
      branch: 'agent/one',
      clean: true,
    })
    const listed = ctx.worktreeRegistry.list(workspaceId).find(entry => entry.id === worktree.id)
    expect(listed?.lockedBy).toBe(WRITER_A)

    // A bound row is a healthy row: registry and git agree, and the binding
    // is invisible to the reconcile classification.
    const report = await ctx.worktreeRegistry.reconcile(workspaceId)
    expect(report.dangling).toEqual([])
    expect(report.unregistered).toEqual([])

    await expect(ctx.worktreeRegistry.remove(worktree.id)).rejects.toThrow(WorktreeLockError)
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).toContain(gitStyle(worktree.path))

    await ctx.worktreeRegistry.unbind(worktree.id, WRITER_A)
    await ctx.worktreeRegistry.remove(worktree.id)
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain(gitStyle(worktree.path))
  })

  it('re-binds idempotently for the holder and refuses every other holder', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    const bound = await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)
    const again = await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)
    expect(again.lockedBy).toBe(WRITER_A)
    expect(again.lockedAt).toBe(bound.lockedAt)

    await expect(ctx.worktreeRegistry.bind(worktree.id, WRITER_B))
      .rejects.toThrow(/already bound to writer/)
    await expect(ctx.worktreeRegistry.bind(WorktreeId('no-such-wt'), WRITER_A))
      .rejects.toThrow(/holds no worktree/)
  })

  it('refuses an unbind by a non-holder and an unbind of an unbound worktree', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await expect(ctx.worktreeRegistry.unbind(worktree.id, WRITER_A)).rejects.toThrow(/not bound to any writer/)
    await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)
    await expect(ctx.worktreeRegistry.unbind(worktree.id, WRITER_B)).rejects.toThrow(/bound to writer/)
    const unbound = await ctx.worktreeRegistry.unbind(worktree.id, WRITER_A)
    expect(unbound.lockedBy).toBeUndefined()
    expect(unbound.lockedAt).toBeUndefined()
  })

  it('refuses removal with force while bound and removes after the holder unbinds', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)

    await expect(ctx.worktreeRegistry.remove(worktree.id, { force: true }))
      .rejects.toThrow(/force does not override the binding/)
    expect(ctx.worktreeRegistry.list(workspaceId)).toHaveLength(1)

    await ctx.worktreeRegistry.unbind(worktree.id, WRITER_A)
    await ctx.worktreeRegistry.remove(worktree.id, { force: true })
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
  })

  it('reports a bound row as healthy, and pruneRows drops the binding with its vanished row', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await ctx.worktreeRegistry.bind(worktree.id, WRITER_A)

    expect(ctx.worktreeRegistry.list(workspaceId).map(entry => entry.lockedBy)).toEqual([WRITER_A])

    // Deleting the directory behind the product leaves a stale row — bound or
    // not, reconcile classifies it as directory-missing and pruneRows drops
    // the row (and with it the binding), never the binding alone.
    await rm(worktree.path, { recursive: true, force: true })
    const report = await ctx.worktreeRegistry.reconcile(workspaceId, { pruneRows: true })
    expect(report.dangling).toEqual([{ id: worktree.id, path: worktree.path, reason: 'directory-missing' }])
    expect(report.removedRows).toEqual([worktree.id])
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
  })
})

describe('worktree create uniqueness', () => {
  it('fails exactly one of two concurrent creates racing the same path', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const target = join(root, 'race-wt')

    const settled = await Promise.allSettled([
      ctx.worktreeRegistry.create({ workspaceId, path: target, branch: 'race/one' }),
      ctx.worktreeRegistry.create({ workspaceId, path: target, branch: 'race/two' }),
    ])

    const outcomes = settled.map(outcome => outcome.status)
    expect(outcomes).toContain('fulfilled')
    expect(outcomes).toContain('rejected')
    const rejection = settled.find(outcome => outcome.status === 'rejected') as PromiseRejectedResult
    expect(String(rejection.reason)).toMatch(/already registered|already exists/)

    const rows = ctx.worktreeRegistry.list(workspaceId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.path).toBe(target)
  })

  it('refuses an explicitly requested branch another worktree of the same workspace already holds', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a'), branch: 'feature/one' })

    // The registry refuses before git runs, with the same classified kind the
    // git dialect would produce.
    const failure = await ctx.worktreeRegistry.create({
      workspaceId,
      path: join(root, 'wt-b'),
      branch: 'feature/one',
    }).catch((error: unknown) => error)
    expect(failure).toBeInstanceOf(WorktreeGitOperationError)
    expect((failure as WorktreeGitOperationError).kind).toBe('branch-conflict')
    expect(ctx.worktreeRegistry.list(workspaceId)).toHaveLength(1)
    // The refusal precedes git: the branch was never re-created and the
    // rejected target directory was never created either.
    await expect(git(repo, 'rev-parse', '--verify', 'refs/heads/feature/one')).resolves.toBeTypeOf('string')
    expect(existsSync(join(root, 'wt-b'))).toBe(false)
  })

  it('lets two workspaces register the same branch name in their own repositories', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const first = await createRepoWorkspace('repo-a')
    const second = await createRepoWorkspace('repo-b')

    await ctx.worktreeRegistry.create({ workspaceId: first.workspaceId, path: join(root, 'a-wt'), branch: 'shared/name' })
    await ctx.worktreeRegistry.create({ workspaceId: second.workspaceId, path: join(root, 'b-wt'), branch: 'shared/name' })

    expect(ctx.worktreeRegistry.list(first.workspaceId).map(entry => entry.branch)).toEqual(['shared/name'])
    expect(ctx.worktreeRegistry.list(second.workspaceId).map(entry => entry.branch)).toEqual(['shared/name'])
  })
})
