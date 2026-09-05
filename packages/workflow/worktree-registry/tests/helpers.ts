/**
 * Shared test helpers: real git invocation for repository setup and the
 * storage/domain/workspace/subprocess/registry boot every registry spec runs
 * on. The code under test spawns git through the subprocess seam; `git` here
 * exists so setup and assertions never depend on it.
 * @module tests/helpers
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import Storage from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { MemoryMediaPool, MemoryStorageBackend } from '../../../storage/storage-domain/tests/helpers/memory-backend.ts'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '../src/index.ts'

/**
 * Run one git command, failing loud with its stderr.
 * @param cwd - Working directory for the invocation.
 * @param args - git arguments after the executable.
 * @returns the collected stdout.
 */
export function git(cwd: string, ...args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile('git', args, { cwd, windowsHide: true }, (error, stdout, stderr) => {
      if (error !== null) {
        const code = typeof (error as NodeJS.ErrnoException).code === 'string' ? ` code=${(error as NodeJS.ErrnoException).code}` : ''
        rejectPromise(new Error(`git ${args.join(' ')} failed${code}: ${error.message} stderr=${String(stderr ?? '')}`))
      } else {
        resolvePromise(String(stdout))
      }
    })
  })
}

/** git prints worktree paths with forward slashes; normalize both sides for containment checks. */
export function gitStyle(path: string): string {
  return path.replace(/\\/g, '/').toLowerCase()
}

/** The per-spec harness: one temp root, one booted context, workspace factories. */
export interface Harness {
  ctx: Context
  root: string
  createRepoWorkspace: (name: string) => Promise<{ workspaceId: WorkspaceId; repo: string }>
  createPlainWorkspace: () => Promise<WorkspaceId>
}

/**
 * Boot the real storage/domain/workspace/subprocess/registry composition over
 * a temp directory. The caller owns disposal (`ctx.fiber.dispose()`) and root
 * cleanup, typically through its own `afterEach`.
 * @param providerConfig - Extra provider config (defaults serve local git).
 * @returns the booted harness.
 */
export async function harness(
  providerConfig: Record<string, unknown> = {},
): Promise<Harness> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-worktree-registry-'))
  const pool = new MemoryMediaPool()
  const ctx = new Context()
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
  await ctx.plugin(GitWorktreeRegistry, providerConfig)

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
