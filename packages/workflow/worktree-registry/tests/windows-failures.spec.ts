import { existsSync } from 'node:fs'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { WorktreeGitOperationError } from '../src/index.ts'
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

/** The classified failure of one operation, typed for assertions. */
async function failureOf(operation: Promise<unknown>): Promise<WorktreeGitOperationError> {
  try {
    await operation
  } catch (error) {
    return error as WorktreeGitOperationError
  }
  throw new Error('expected the operation to reject')
}

describe('worktree registry failure classification over real git', () => {
  it('classifies an occupied target path and leaves the registry unchanged for a corrected retry', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    const occupied = join(root, 'occupied')
    await mkdir(occupied)
    await writeFile(join(occupied, 'blocker.txt'), 'not empty')

    const failure = await failureOf(ctx.worktreeRegistry.create({ workspaceId, path: occupied }))

    expect(failure).toBeInstanceOf(WorktreeGitOperationError)
    expect(failure.kind).toBe('path-exists')
    expect(failure.message).toContain('choose a different target directory')
    // No row, no worktree: the failed attempt left nothing to clean up.
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain('occupied')

    const retried = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'fresh') })
    expect(retried.branch).toBe('fresh')
  })

  it('classifies a same-name branch conflict and allows a retried create under a new name', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a'), branch: 'shared' })

    const failure = await failureOf(
      ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-b'), branch: 'shared' }),
    )

    expect(failure.kind).toBe('branch-conflict')
    expect(failure.message).toContain('choose a different branch name')
    expect(ctx.worktreeRegistry.list(workspaceId)).toHaveLength(1)

    const retried = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-b'), branch: 'shared-2' })
    expect(retried.branch).toBe('shared-2')
    expect(ctx.worktreeRegistry.list(workspaceId)).toHaveLength(2)
  })

  it('classifies a dirty-tree refusal, keeps the worktree, and retries the removal with force', async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId } = await createRepoWorkspace('repo')
    const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'wt-a') })
    await writeFile(join(worktree.path, 'scratch.txt'), 'untracked content')

    const failure = await failureOf(ctx.worktreeRegistry.remove(worktree.id))

    expect(failure).toBeInstanceOf(WorktreeGitOperationError)
    expect(failure.kind).toBe('dirty-tree')
    expect(failure.message).toContain('force: true')
    expect(existsSync(worktree.path)).toBe(true)
    expect(ctx.worktreeRegistry.list(workspaceId)).toHaveLength(1)

    await ctx.worktreeRegistry.remove(worktree.id, { force: true })
    expect(existsSync(worktree.path)).toBe(false)
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
  })

  it('classifies a long-path create failure and allows a retried create at a shorter path', { skip: process.platform !== 'win32' }, async () => {
    const { ctx, root, createRepoWorkspace } = await boot()
    const { workspaceId, repo } = await createRepoWorkspace('repo')
    // Repo-local config pins git's own MAX_PATH accounting regardless of a
    // developer's global core.longpaths setting.
    await git(repo, 'config', 'core.longpaths', 'false')
    const segment = 'abcdefghijklmnopqrstuvwxyz0123456789'
    const long = join(root, segment, segment, segment, segment, segment, segment, segment, segment)
    if (long.length <= 260) throw new Error(`test path is not long enough (${long.length})`)

    const failure = await failureOf(ctx.worktreeRegistry.create({ workspaceId, path: long }))

    expect(failure).toBeInstanceOf(WorktreeGitOperationError)
    expect(failure.kind).toBe('path-length')
    expect(failure.message).toContain('core.longpaths')
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
    expect(gitStyle(await git(repo, 'worktree', 'list', '--porcelain'))).not.toContain('abcdefghijklmnopqrstuvwxyz0123456789')

    const retried = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'short') })
    expect(retried.branch).toBe('short')
  })

  it('keeps unclassified git refusals generic', async () => {
    const { ctx, createPlainWorkspace } = await boot()
    const plainWorkspaceId = await createPlainWorkspace()

    const failure = await failureOf(ctx.worktreeRegistry.create({ workspaceId: plainWorkspaceId, path: 'x' }))

    expect(failure).not.toBeInstanceOf(WorktreeGitOperationError)
    expect(failure.message).toContain('not a git repository')
  })
})
