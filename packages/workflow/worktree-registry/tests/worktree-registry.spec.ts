import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, realpath, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Storage from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { MemoryMediaPool, MemoryStorageBackend } from '../../../storage/storage-domain/tests/helpers/memory-backend.ts'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry, { WorktreeId } from '../src/index.ts'
import { git, gitStyle } from './helpers.ts'

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

interface Harness {
  ctx: Context
  root: string
  createRepoWorkspace: (name: string) => Promise<{ workspaceId: WorkspaceId; repo: string }>
  createPlainWorkspace: () => Promise<WorkspaceId>
}

/** Boot the real storage/domain/workspace/subprocess/registry composition over a temp directory. */
async function harness(): Promise<Harness> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-worktree-registry-'))
  roots.push(root)
  const pool = new MemoryMediaPool()
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(Storage)
  ctx.storage.backend.register('memory', new MemoryStorageBackend(pool))
  const facility = new DomainFacility(ctx, { backend: 'memory', routes: {} })
  ctx.storage.mount('domain', facility)
  ctx.provide('storageDomain', facility)
  ctx.provide('sessionPersistence', {
    list: async () => [],
    load: () => { throw new Error('event bodies must not be loaded') },
    inspect: () => { throw new Error('event bodies must not be inspected') },
  } as never)
  await ctx.plugin(WorkspaceRegistry)
  await ctx.plugin(SubprocessLocal)
  await ctx.plugin(GitWorktreeRegistry, {})

  const createRepoWorkspace = async (name: string) => {
    const repo = join(root, name)
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'worktree-registry@test.local')
    await git(repo, 'config', 'user.name', 'Worktree Registry Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')
    const workspace = await ctx.workspaceRegistry.create(repo)
    return { workspaceId: workspace.id, repo }
  }
  const createPlainWorkspace = async () => {
    const plain = join(root, `plain-${Math.random().toString(36).slice(2, 8)}`)
    await mkdir(plain)
    return (await ctx.workspaceRegistry.create(plain)).id
  }
  return { ctx, root, createRepoWorkspace, createPlainWorkspace }
}

describe('worktree registry create', () => {
  it('registers a worktree with the git-derived branch and the canonical path', async () => {
    const { ctx, root, createRepoWorkspace } = await harness()
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
    const { ctx, root, createRepoWorkspace } = await harness()
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
    const { ctx, root, createRepoWorkspace, createPlainWorkspace } = await harness()
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
    const { ctx, createRepoWorkspace } = await harness()
    const { workspaceId, repo } = await createRepoWorkspace('repo')

    await expect(ctx.worktreeRegistry.create({ workspaceId, path: repo }))
      .rejects.toThrow(/owner workspace directory/)
  })
})

describe('worktree registry list', () => {
  it('returns one workspace worktrees in a stable order and filters other workspaces', async () => {
    const { ctx, root, createRepoWorkspace } = await harness()
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
    const { ctx, root, createRepoWorkspace } = await harness()
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
    const { ctx, root, createRepoWorkspace } = await harness()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await ctx.worktreeRegistry.remove(worktree.id)

    expect(existsSync(worktree.path)).toBe(false)
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain(gitStyle(worktree.path))
    await expect(ctx.worktreeRegistry.status(worktree.id)).rejects.toThrow(/no worktree/)
  })

  it('refuses a dirty worktree without force and removes it with force', async () => {
    const { ctx, root, createRepoWorkspace } = await harness()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await writeFile(join(worktree.path, 'scratch.txt'), 'untracked content')

    await expect(ctx.worktreeRegistry.remove(worktree.id)).rejects.toThrow(/--force/)
    expect(existsSync(worktree.path)).toBe(true)

    await ctx.worktreeRegistry.remove(worktree.id, { force: true })
    expect(existsSync(worktree.path)).toBe(false)
  })

  it('fails loud when the directory vanished externally or the owner workspace is gone', async () => {
    const { ctx, root, createRepoWorkspace } = await harness()
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
    const { ctx, root, createRepoWorkspace } = await harness()
    const { workspaceId } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })

    await ctx.fiber.dispose()

    expect(ctx.worktreeRegistry).toBeUndefined()
  })
})
