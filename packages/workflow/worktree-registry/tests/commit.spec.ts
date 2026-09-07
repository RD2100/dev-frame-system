import { chmod, mkdir, readFile, rm, rmdir, symlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { brandString } from '@deepseek-ai/dsh-brand'
import { WorktreeLockHolder } from '../src/index.ts'
import type { WorktreeCommitId } from '../src/index.ts'
import { git, harness } from './helpers.ts'

const owned: Awaited<ReturnType<typeof harness>>[] = []
const writer = WorktreeLockHolder('commit-worker')

afterEach(async () => {
  for (const fixture of owned.splice(0)) {
    await fixture.ctx.fiber.dispose()
    await rm(fixture.root, { recursive: true, force: true })
  }
})

async function prepare() {
  const fixture = await harness()
  owned.push(fixture)
  const { repo, workspaceId } = await fixture.createRepoWorkspace('repo')
  const tree = await fixture.ctx.worktreeRegistry.create({ workspaceId, path: join(fixture.root, 'worker') })
  await fixture.ctx.worktreeRegistry.bind(tree.id, writer)
  const expectedHead = brandString<WorktreeCommitId>((await git(tree.path, 'rev-parse', 'HEAD')).trim())
  await writeFile(join(tree.path, 'artifact.txt'), 'artifact\n')
  return { ...fixture, repo, tree, request: {
    id: tree.id, holder: writer, expectedHead, paths: ['artifact.txt'], message: 'record artifact',
  } }
}

describe('host-authorized worktree commits', () => {
  it('commits selected files in the held linked checkout and preserves unrelated changes', async () => {
    const { ctx, tree, repo, request } = await prepare()
    const anchorHead = (await git(repo, 'rev-parse', 'HEAD')).trim()
    await writeFile(join(tree.path, 'unrelated.txt'), 'keep me\n')
    const result = await ctx.worktreeRegistry.commit(request)
    expect(result.head).not.toBe(request.expectedHead)
    expect(result.clean).toBe(false)
    expect((await git(tree.path, 'show', `${result.head}:artifact.txt`)).trim()).toBe('artifact')
    expect((await git(tree.path, 'rev-parse', 'HEAD^')).trim()).toBe(request.expectedHead)
    expect((await git(repo, 'rev-parse', 'HEAD')).trim()).toBe(anchorHead)
    expect(await readFile(join(tree.path, 'unrelated.txt'), 'utf8')).toBe('keep me\n')
    expect(ctx.worktreeRegistry.list(tree.workspaceId).find(row => row.id === tree.id)?.lockedBy).toBe(writer)
    await expect(ctx.worktreeRegistry.commit(request)).rejects.toThrow('expected HEAD')
  })

  it('rejects other writers, stale identities and escaping paths before staging', async () => {
    const { ctx, tree, request } = await prepare()
    await expect(ctx.worktreeRegistry.commit({ ...request, holder: WorktreeLockHolder('other') })).rejects.toThrow('writer lock')
    await expect(ctx.worktreeRegistry.commit({ ...request, expectedHead: brandString<WorktreeCommitId>('0'.repeat(40)) }))
      .rejects.toThrow('expected HEAD')
    for (const path of ['../outside.txt', '.git', 'sub/../artifact.txt', 'C:/outside.txt', '.']) {
      await expect(ctx.worktreeRegistry.commit({ ...request, paths: [path] })).rejects.toThrow('paths must stay')
    }
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
    expect((await git(tree.path, 'rev-parse', 'HEAD')).trim()).toBe(request.expectedHead)
  })

  it('rejects existing staged changes and does not reset them', async () => {
    const { ctx, tree, request } = await prepare()
    await git(tree.path, 'add', 'artifact.txt')
    await expect(ctx.worktreeRegistry.commit(request)).rejects.toThrow('existing staged changes')
    expect((await git(tree.path, 'diff', '--cached', '--name-only')).trim()).toBe('artifact.txt')
  })

  it('rejects a linked directory that reaches outside the checkout', async () => {
    const { ctx, tree, root, request } = await prepare()
    const outside = join(root, 'outside')
    await mkdir(outside)
    await writeFile(join(outside, 'private.txt'), 'outside fixture content\n')
    await symlink(outside, join(tree.path, 'escape'), process.platform === 'win32' ? 'junction' : 'dir')
    for (const path of ['escape/private.txt', 'escape']) {
      await expect(ctx.worktreeRegistry.commit({ ...request, paths: [path] })).rejects.toThrow('symbolic links or junctions')
    }
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
    expect((await git(tree.path, 'rev-parse', 'HEAD')).trim()).toBe(request.expectedHead)
    expect(await readFile(join(outside, 'private.txt'), 'utf8')).toBe('outside fixture content\n')
  })

  it('accepts explicit tracked deletions but rejects a deleted directory pathspec', async () => {
    const { ctx, tree, request } = await prepare()
    const directory = join(tree.path, 'output')
    await mkdir(directory)
    await writeFile(join(directory, 'one.txt'), 'one\n')
    await writeFile(join(directory, 'two.txt'), 'two\n')
    await git(tree.path, 'add', 'output')
    await git(tree.path, 'commit', '-m', 'prepare tracked output')
    const expectedHead = brandString<WorktreeCommitId>((await git(tree.path, 'rev-parse', 'HEAD')).trim())
    await rm(join(directory, 'one.txt'))
    await rm(join(directory, 'two.txt'))
    await rmdir(directory)
    await expect(ctx.worktreeRegistry.commit({ ...request, expectedHead, paths: ['output'] }))
      .rejects.toThrow('exact tracked file')
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
    const result = await ctx.worktreeRegistry.commit({ ...request, expectedHead, paths: ['output/one.txt'] })
    expect((await git(tree.path, 'diff-tree', '--no-commit-id', '--name-only', '-r', result.head)).trim())
      .toBe('output/one.txt')
    expect(result.clean).toBe(false)
  })

  it('rejects filter-controlled files without invoking the filter', async () => {
    const { ctx, tree, repo, request } = await prepare()
    await writeFile(join(tree.path, '.gitattributes'), 'artifact.txt filter=fixture\n')
    await git(repo, 'config', 'filter.fixture.clean', 'command-that-must-not-run')
    await expect(ctx.worktreeRegistry.commit(request)).rejects.toThrow('filter attribute')
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
  })

  it('does not begin a cancelled operation', async () => {
    const { ctx, tree, request } = await prepare()
    await expect(ctx.worktreeRegistry.commit(request, AbortSignal.abort(new Error('cancelled')))).rejects.toThrow('cancelled')
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
  })

  it('rejects an unselected tracked filter before committing or refreshing status', async () => {
    const { ctx, tree, repo, request } = await prepare()
    await writeFile(join(tree.path, 'filtered.txt'), 'before\n')
    await git(tree.path, 'add', 'filtered.txt')
    await git(tree.path, 'commit', '-m', 'prepare filtered file')
    const expectedHead = brandString<WorktreeCommitId>((await git(tree.path, 'rev-parse', 'HEAD')).trim())
    await writeFile(join(tree.path, '.gitattributes'), 'filtered.txt filter=fixture\n')
    await writeFile(join(tree.path, 'filtered.txt'), 'after!\n')
    await git(repo, 'config', 'filter.fixture.clean', 'echo fixture-filter-executed >&2; exit 37')
    await git(repo, 'config', 'filter.fixture.required', 'true')
    await expect(git(tree.path, 'status', '--porcelain')).rejects.toThrow('fixture-filter-executed')
    await expect(ctx.worktreeRegistry.commit({ ...request, expectedHead })).rejects.toThrow('filter attribute')
    expect((await git(tree.path, 'rev-parse', 'HEAD')).trim()).toBe(expectedHead)
    expect(await git(tree.path, 'diff', '--cached', '--name-only')).toBe('')
  })

  it('rejects a checkout pointer redirected to another registered worktree', async () => {
    const { ctx, tree, root, request } = await prepare()
    const other = await ctx.worktreeRegistry.create({ workspaceId: tree.workspaceId, path: join(root, 'other-worker') })
    const pointer = await readFile(join(other.path, '.git'), 'utf8')
    // Git marks this file hidden on Windows; reopening it avoids CREATE_ALWAYS's hidden-file refusal.
    await writeFile(join(tree.path, '.git'), pointer, { flag: 'r+' })
    await expect(ctx.worktreeRegistry.commit(request)).rejects.toThrow('does not belong')
    expect((await git(other.path, 'rev-parse', 'HEAD')).trim()).toBe(request.expectedHead)
    expect(await git(other.path, 'diff', '--cached', '--name-only')).toBe('')
  })

  it('does not execute repository hooks in the host operation', async () => {
    const { ctx, tree, repo, request } = await prepare()
    const hooks = join(tree.path, 'hooks')
    await mkdir(hooks)
    const hook = join(hooks, 'pre-commit')
    await writeFile(hook, '#!/bin/sh\necho fixture-hook-executed >&2\nexit 37\n')
    await chmod(hook, 0o755)
    await git(repo, 'config', 'core.hooksPath', hooks)
    await expect(git(tree.path, 'commit', '--allow-empty', '-m', 'hook control')).rejects.toThrow('fixture-hook-executed')
    const result = await ctx.worktreeRegistry.commit(request)
    expect((await git(tree.path, 'rev-parse', 'HEAD')).trim()).toBe(result.head)
    expect(result.clean).toBe(false)
  })
})
