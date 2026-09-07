/** Real Git worktrees exercise exact-source admission and post-failure reconciliation. */

import { execFile } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it } from 'vitest'
import {
  executeIntegrationGit,
  inspectIntegrationGit,
  reconcileIntegrationGit,
  type IntegrationGitOptions,
} from '../src/git-integration.ts'

const exec = promisify(execFile)
const roots: string[] = []
const options: IntegrationGitOptions = { executable: 'git', timeoutMs: 15_000, maxOutputBytes: 1024 * 1024 }

async function git(cwd: string, ...args: string[]): Promise<string> {
  return (await exec('git', ['-C', cwd, ...args], { windowsHide: true })).stdout.trim()
}

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'dsh-integration-git-'))
  roots.push(root)
  await git(root, 'init', '-b', 'main')
  await git(root, 'config', 'user.name', 'Integration Test')
  await git(root, 'config', 'user.email', 'integration@example.invalid')
  await git(root, 'config', 'commit.gpgsign', 'false')
  await writeFile(join(root, 'feature.txt'), 'base\n')
  await git(root, 'add', 'feature.txt')
  await git(root, 'commit', '-m', 'base')
  const targetHead = await git(root, 'rev-parse', 'HEAD')
  const sourcePath = join(root, '..', `${root.split(/[\\/]/).at(-1)}-source`)
  roots.push(sourcePath)
  await git(root, 'worktree', 'add', '-b', 'feature', sourcePath)
  await writeFile(join(sourcePath, 'feature.txt'), 'reviewed\n')
  await git(sourcePath, 'add', 'feature.txt')
  await git(sourcePath, 'commit', '-m', 'feature')
  const sourceCommit = await git(sourcePath, 'rev-parse', 'HEAD')
  return { targetPath: root, sourcePath, sourceCommit, targetHead }
}

afterEach(async () => {
  for (const root of roots.splice(0).reverse()) await rm(root, { recursive: true, force: true })
})

describe('controller Git integration', () => {
  it('fast-forwards the exact reviewed commit and recovers its applied observation without another merge', async () => {
    const request = await fixture()
    const result = await executeIntegrationGit(request, options)
    expect(result).toEqual({ observation: { kind: 'applied', head: request.sourceCommit } })
    expect(await reconcileIntegrationGit(request, options)).toEqual(result.observation)
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.sourceCommit)
    await expect(executeIntegrationGit(request, options)).rejects.toThrow('HEAD changed')
  })

  it('rejects uncommitted reviewed-source edits and preserves the target', async () => {
    const request = await fixture()
    await writeFile(join(request.sourcePath, 'feature.txt'), 'unreviewed\n')
    await expect(executeIntegrationGit(request, options)).rejects.toThrow('clean source and target')
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.targetHead)
  })

  it('rejects target drift instead of merging against a different base', async () => {
    const request = await fixture()
    await git(request.targetPath, 'commit', '--allow-empty', '-m', 'concurrent change')
    await expect(executeIntegrationGit(request, options)).rejects.toThrow('HEAD changed')
    expect((await reconcileIntegrationGit(request, options)).kind).toBe('ambiguous')
  })

  it('rejects a dirty target without changing the user file', async () => {
    const request = await fixture()
    await writeFile(join(request.targetPath, 'user-file.txt'), 'preserve\n')
    await expect(executeIntegrationGit(request, options)).rejects.toThrow('clean source and target')
    expect(await reconcileIntegrationGit(request, options)).toEqual({
      kind: 'ambiguous', head: request.targetHead, clean: false,
    })
  })

  it('rejects a non-fast-forward source before changing target state', async () => {
    const request = await fixture()
    await git(request.targetPath, 'commit', '--allow-empty', '-m', 'divergent base')
    const targetHead = await git(request.targetPath, 'rev-parse', 'HEAD')
    await expect(executeIntegrationGit({ ...request, targetHead }, options)).rejects.toThrow()
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(targetHead)
  })

  it('refuses cancellation before mutation and reports the unchanged target', async () => {
    const request = await fixture()
    const signal = AbortSignal.abort(new Error('cancel integration'))
    await expect(executeIntegrationGit(request, options, signal)).rejects.toThrow('cancel integration')
    expect(await reconcileIntegrationGit(request, options)).toEqual({ kind: 'unchanged', head: request.targetHead })
  })

  it('rejects using the controller checkout as its own independent source', async () => {
    const request = await fixture()
    await expect(inspectIntegrationGit({ ...request, sourcePath: request.targetPath }, options)).rejects.toThrow('independent')
  })

  it('preserves ignored user files that collide with reviewed tracked content', async () => {
    const request = await fixture()
    await writeFile(join(request.targetPath, '.git', 'info', 'exclude'), 'local.txt\n')
    await writeFile(join(request.targetPath, 'local.txt'), 'user content\n')
    await writeFile(join(request.sourcePath, 'local.txt'), 'reviewed content\n')
    await git(request.sourcePath, 'add', '-f', 'local.txt')
    await git(request.sourcePath, 'commit', '-m', 'track ignored path')
    const sourceCommit = await git(request.sourcePath, 'rev-parse', 'HEAD')
    const result = await executeIntegrationGit({ ...request, sourceCommit }, options)
    expect(result.commandError).toBeDefined()
    expect(result.observation).toEqual({ kind: 'unchanged', head: request.targetHead })
    expect(await readFile(join(request.targetPath, 'local.txt'), 'utf8')).toBe('user content\n')
  })
  it('checks the synchronous host admission after Git preflight and before mutation', async () => {
    const request = await fixture()
    let reached = false
    await expect(executeIntegrationGit(request, options, undefined, () => {
      reached = true
      throw new Error('admission revoked')
    })).rejects.toThrow('admission revoked')
    expect(reached).toBe(true)
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.targetHead)
  })

  it('rejects a no-op source that cannot distinguish prepared from applied', async () => {
    const request = await fixture()
    await expect(inspectIntegrationGit({ ...request, sourceCommit: request.targetHead }, options)).rejects.toThrow('unapplied source')
  })

})
