import { existsSync } from 'node:fs'
import { realpath, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { WorktreeId } from '../src/index.ts'
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

describe('worktree registry create', () => {
  it('registers a worktree with the git-derived branch and the canonical path', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')

    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    expect(worktree.branch).toBe('wt-a')
    expect(worktree.path).toBe(await realpath(join(root, 'wt-a')))
    expect(worktree.workspaceId).toBe(workspaceId)
    expect(worktree.createdAt).toBe(worktree.updatedAt)
    const registered = gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))
    expect(registered).toContain(gitStyle(worktree.path))
  })

  it('registers a worktree with an explicit new branch', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')

    const worktree = await ctx.worktreeRegistry.create({
      workspaceId,
      path: join(root, 'feature-wt'),
      branch: 'feature/x',
    })

    expect(worktree.branch).toBe('feature/x')
    await expect(git(repo, 'rev-parse', '--verify', 'refs/heads/feature/x')).resolves.not.toBe('')
  })

  it('fails loud for an unknown workspace, a non-git workspace, and a registered path', async () => {
    const { ctx, root, createRepoWorkspace, createPlainWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const plainWorkspaceId = await createPlainWorkspace()

    await expect(ctx.worktreeRegistry.create({ workspaceId: WorkspaceId('no-such-workspace'), path: join(root, 'wt-x') }))
      .rejects.toThrow(/unknown workspace/)
    await expect(ctx.worktreeRegistry.create({ workspaceId: plainWorkspaceId, path: join(root, 'wt-x') }))
      .rejects.toThrow(/not a git repository/)

    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    const canonical = await realpath(join(root, 'wt-a'))
    await expect(ctx.worktreeRegistry.create({ workspaceId, path: canonical }))
      .rejects.toThrow(/already registered/)
    expect(worktree.path).toBe(canonical)
  })

  it('refuses a target that is the owner workspace directory', async () => {
    const { ctx, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')

    await expect(ctx.worktreeRegistry.create({ workspaceId, path: repo }))
      .rejects.toThrow(/owner workspace directory/)
  })
})

describe('worktree registry list', () => {
  it('returns one workspace worktrees in a stable order and filters other workspaces', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const first = await createRepoWorkspace('repo-a')
    const second = await createRepoWorkspace('repo-b')

    const wtA1 = await ctx.worktreeRegistry.create({ workspaceId: first.workspaceId, path: join(root, 'a-one') })
    const wtA2 = await ctx.worktreeRegistry.create({ workspaceId: first.workspaceId, path: join(root, 'a-two') })
    const wtB1 = await ctx.worktreeRegistry.create({ workspaceId: second.workspaceId, path: join(root, 'b-one') })

    // Order is the durable (createdAt, id) sort: stable across calls and restarts,
    // but two creates inside one millisecond do not promise call-sequence order.
    const listed = ctx.worktreeRegistry.list(first.workspaceId)
    expect(new Set(listed.map(worktree => worktree.id))).toEqual(new Set([wtA1.id, wtA2.id]))
    expect(ctx.worktreeRegistry.list(first.workspaceId).map(worktree => worktree.id))
      .toEqual(listed.map(worktree => worktree.id))
    expect(ctx.worktreeRegistry.list(second.workspaceId).map(worktree => worktree.id))
      .toEqual([wtB1.id])
    expect(() => ctx.worktreeRegistry.list(WorkspaceId('no-such-workspace'))).toThrow(/unknown workspace/)
    const pathsByid = new Map(ctx.worktreeRegistry.list(first.workspaceId).map(worktree => [worktree.id, worktree.path]))
    expect(pathsByid.get(wtA1.id)).toBe(await realpath(join(root, 'a-one')))
    expect(pathsByid.get(wtA2.id)).toBe(await realpath(join(root, 'a-two')))
  })
})

describe('worktree registry status', () => {
  it('observes the live branch and cleanliness, and reports a vanished directory', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await expect(ctx.worktreeRegistry.status(worktree.id)).resolves.toEqual({
      directoryExists: true,
      branch: 'wt-a',
      clean: true,
    })

    await writeFile(join(worktree.path, 'scratch.txt'), 'untracked content')
    await expect(ctx.worktreeRegistry.status(worktree.id)).resolves.toEqual({
      directoryExists: true,
      branch: 'wt-a',
      clean: false,
    })

    await rm(worktree.path, { recursive: true, force: true })
    await expect(ctx.worktreeRegistry.status(worktree.id)).resolves.toEqual({ directoryExists: false })
    await expect(ctx.worktreeRegistry.status(WorktreeId('no-such-worktree'))).rejects.toThrow(/no worktree/)
  })
})

describe('worktree registry remove', () => {
  it('removes the worktree through git and deletes the registration', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await ctx.worktreeRegistry.remove(worktree.id)

    expect(existsSync(worktree.path)).toBe(false)
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain(gitStyle(worktree.path))
    await expect(ctx.worktreeRegistry.status(worktree.id)).rejects.toThrow(/no worktree/)
  })

  it('refuses a dirty worktree without force and removes it with force', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await writeFile(join(worktree.path, 'scratch.txt'), 'untracked content')

    await expect(ctx.worktreeRegistry.remove(worktree.id)).rejects.toThrow(/--force/)
    expect(existsSync(worktree.path)).toBe(true)

    await ctx.worktreeRegistry.remove(worktree.id, { force: true })
    expect(existsSync(worktree.path)).toBe(false)
  })

  it('fails loud when the directory vanished externally or the owner workspace is gone', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await rm(worktree.path, { recursive: true, force: true })
    await expect(ctx.worktreeRegistry.remove(worktree.id)).rejects.toThrow(/no longer exists/)

    await ctx.workspaceRegistry.delete(workspaceId)
    await expect(ctx.worktreeRegistry.remove(worktree.id)).rejects.toThrow(/unknown workspace/)
  })
})

describe('worktree registry disposal', () => {
  it('unmounts the service from the context when the fiber is disposed', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await ctx.fiber.dispose()

    expect(ctx.worktreeRegistry).toBeUndefined()
  })
})
