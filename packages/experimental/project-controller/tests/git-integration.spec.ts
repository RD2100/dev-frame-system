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
  observeIntegrationRelation,
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

  it('refuses a gate that closes during preflight and leaves the target unchanged', async () => {
    const request = await fixture()
    const gate = new AbortController()
    // Deterministically scheduled closure: the microtask fires inside the
    // async preflight, so the refusal must come from the spawn-adjacent
    // recheck and the mutating merge must never run.
    queueMicrotask(() => gate.abort(new Error('admission closed during preflight')))
    await expect(executeIntegrationGit(request, options, gate.signal)).rejects.toThrow('admission closed during preflight')
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.targetHead)
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

  it('integrates a diverged sibling branch as a real merge commit with the exact reviewed parents', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-integration-git-'))
    roots.push(root)
    await git(root, 'init', '-b', 'main')
    await git(root, 'config', 'user.name', 'Integration Test')
    await git(root, 'config', 'user.email', 'integration@example.invalid')
    await git(root, 'config', 'commit.gpgsign', 'false')
    await git(root, 'config', 'core.autocrlf', 'false')
    await writeFile(join(root, 'base.txt'), 'base\n')
    await git(root, 'add', 'base.txt')
    await git(root, 'commit', '-m', 'base')
    const targetHead = await git(root, 'rev-parse', 'HEAD')

    const taskA = join(root, '..', `${root.split(/[\\/]/).at(-1)}-task-a`)
    roots.push(taskA)
    await git(root, 'worktree', 'add', '-b', 'task-a', taskA)
    await writeFile(join(taskA, 'a.txt'), 'reviewed-a\n')
    await git(taskA, 'add', 'a.txt')
    await git(taskA, 'commit', '-m', 'task a')
    const commitA = await git(taskA, 'rev-parse', 'HEAD')

    const taskB = join(root, '..', `${root.split(/[\\/]/).at(-1)}-task-b`)
    roots.push(taskB)
    await git(root, 'worktree', 'add', '-b', 'task-b', taskB, targetHead)
    await writeFile(join(taskB, 'b.txt'), 'reviewed-b\n')
    await git(taskB, 'add', 'b.txt')
    await git(taskB, 'commit', '-m', 'task b')
    const commitB = await git(taskB, 'rev-parse', 'HEAD')

    const first = { targetPath: root, sourcePath: taskA, sourceCommit: commitA, targetHead }
    expect(await observeIntegrationRelation(first, options)).toBe('fast-forward')
    const appliedA = await executeIntegrationGit(first, options)
    expect(appliedA.observation).toEqual({ kind: 'applied', head: commitA })

    const second = { targetPath: root, sourcePath: taskB, sourceCommit: commitB, targetHead: commitA, mode: 'merge' as const }
    expect(await observeIntegrationRelation({ ...second, mode: undefined }, options)).toBe('diverged')
    const result = await executeIntegrationGit(second, options)
    expect(result.commandError).toBeUndefined()
    expect(result.observation.kind).toBe('applied')
    const mergeHead = result.observation.kind === 'applied' ? result.observation.head : undefined
    expect(mergeHead).toBeDefined()
    expect(await git(root, 'rev-list', '--parents', '-n', '1', 'HEAD')).toBe(`${mergeHead} ${commitA} ${commitB}`)
    expect(await readFile(join(root, 'a.txt'), 'utf8')).toBe('reviewed-a\n')
    expect(await readFile(join(root, 'b.txt'), 'utf8')).toBe('reviewed-b\n')
    expect(await git(root, 'status', '--porcelain')).toBe('')
    expect(await reconcileIntegrationGit(second, options)).toEqual(result.observation)
    const postMergeHead = await git(root, 'rev-parse', 'HEAD')
    expect(await observeIntegrationRelation({ ...second, targetHead: postMergeHead, mode: undefined }, options)).toBe('already-integrated')
    expect(await git(taskB, 'status', '--porcelain')).toBe('')
    expect(await git(taskB, 'rev-parse', 'HEAD')).toBe(commitB)
  })

  it('reports an explicit conflict with the merge state left for the operator', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-integration-git-'))
    roots.push(root)
    await git(root, 'init', '-b', 'main')
    await git(root, 'config', 'user.name', 'Integration Test')
    await git(root, 'config', 'user.email', 'integration@example.invalid')
    await git(root, 'config', 'commit.gpgsign', 'false')
    await git(root, 'config', 'core.autocrlf', 'false')
    await writeFile(join(root, 'conflict.txt'), 'base\n')
    await git(root, 'add', 'conflict.txt')
    await git(root, 'commit', '-m', 'base')
    const targetHead = await git(root, 'rev-parse', 'HEAD')

    const taskA = join(root, '..', `${root.split(/[\\/]/).at(-1)}-task-a`)
    roots.push(taskA)
    await git(root, 'worktree', 'add', '-b', 'task-a', taskA)
    await writeFile(join(taskA, 'conflict.txt'), 'reviewed-a\n')
    await git(taskA, 'add', 'conflict.txt')
    await git(taskA, 'commit', '-m', 'task a')
    const commitA = await git(taskA, 'rev-parse', 'HEAD')

    const taskB = join(root, '..', `${root.split(/[\\/]/).at(-1)}-task-b`)
    roots.push(taskB)
    await git(root, 'worktree', 'add', '-b', 'task-b', taskB, targetHead)
    await writeFile(join(taskB, 'conflict.txt'), 'reviewed-b\n')
    await git(taskB, 'add', 'conflict.txt')
    await git(taskB, 'commit', '-m', 'task b')
    const commitB = await git(taskB, 'rev-parse', 'HEAD')

    expect((await executeIntegrationGit({ targetPath: root, sourcePath: taskA, sourceCommit: commitA, targetHead }, options)).observation)
      .toEqual({ kind: 'applied', head: commitA })

    const merge = { targetPath: root, sourcePath: taskB, sourceCommit: commitB, targetHead: commitA, mode: 'merge' as const }
    const result = await executeIntegrationGit(merge, options)
    expect(result.commandError).toBeDefined()
    expect(result.observation).toEqual({ kind: 'conflicted', head: commitA })
    expect(await git(root, 'rev-parse', 'HEAD')).toBe(commitA)
    expect(await git(root, 'status', '--porcelain')).not.toBe('')
    expect(await readFile(join(root, 'conflict.txt'), 'utf8')).toContain('<<<<<<<')
    expect(await reconcileIntegrationGit(merge, options)).toEqual(result.observation)
    expect(await git(taskB, 'status', '--porcelain')).toBe('')
    expect(await git(taskB, 'rev-parse', 'HEAD')).toBe(commitB)
  })

  it('stays ambiguous when the target is dirty with an unchanged HEAD and no merge state', async () => {
    const request = await fixture()
    await writeFile(join(request.targetPath, 'user-file.txt'), 'preserve\n')
    expect(await reconcileIntegrationGit({ ...request, mode: 'merge' }, options)).toEqual({
      kind: 'ambiguous', head: request.targetHead, clean: false,
    })
  })

  it('never reports an octopus merge commit as an applied reviewed merge', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-integration-git-'))
    roots.push(root)
    await git(root, 'init', '-b', 'main')
    await git(root, 'config', 'user.name', 'Integration Test')
    await git(root, 'config', 'user.email', 'integration@example.invalid')
    await git(root, 'config', 'commit.gpgsign', 'false')
    await git(root, 'config', 'core.autocrlf', 'false')
    await writeFile(join(root, 'base.txt'), 'base\n')
    await git(root, 'add', 'base.txt')
    await git(root, 'commit', '-m', 'base')
    const targetHead = await git(root, 'rev-parse', 'HEAD')
    for (const name of ['left', 'right']) {
      const path = join(root, '..', `${root.split(/[\\/]/).at(-1)}-${name}`)
      roots.push(path)
      await git(root, 'worktree', 'add', '-b', name, path, targetHead)
      await writeFile(join(path, `${name}.txt`), `${name}\n`)
      await git(path, 'add', `${name}.txt`)
      await git(path, 'commit', '-m', name)
    }
    const leftCommit = await git(root, 'rev-parse', 'left')
    const rightCommit = await git(root, 'rev-parse', 'right')
    await git(root, 'merge', '--no-edit', leftCommit, rightCommit)
    const request = { targetPath: root, sourcePath: root, sourceCommit: leftCommit, targetHead, mode: 'merge' as const }
    expect(await reconcileIntegrationGit(request, options)).toEqual({ kind: 'ambiguous', head: await git(root, 'rev-parse', 'HEAD'), clean: true })
  })

  it('refuses a driver effective through an include while the fast-forward path keeps its reviewed face', async () => {
    const request = await fixture()
    // `--local` alone does not expand includes; the merge environment sees
    // the driver through it, so the reachable-config check must refuse it.
    // The include file lives inside .git so it never dirties the worktree.
    const includePath = join(request.targetPath, '.git', 'included-config')
    await writeFile(includePath, '[merge "probe"]\n\tdriver = echo merged %A %O %B\n')
    await git(request.targetPath, 'config', 'include.path', includePath)
    await expect(inspectIntegrationGit({ ...request, mode: 'merge' }, options))
      .rejects.toThrow('no custom merge drivers or external filters')
    // The fast-forward path keeps its reviewed face and still integrates.
    expect((await executeIntegrationGit(request, options)).observation.kind).toBe('applied')
  })

  it('refuses a filter effective through worktree config', async () => {
    const request = await fixture()
    await git(request.targetPath, 'config', 'extensions.worktreeConfig', 'true')
    await git(request.targetPath, 'config', '--worktree', 'filter.probe.smudge', 'echo smudged')
    await expect(inspectIntegrationGit({ ...request, mode: 'merge' }, options))
      .rejects.toThrow('no custom merge drivers or external filters')
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.targetHead)
  })

  it('merges through built-in mechanisms only when the reviewed tree names unreachable drivers or filters', async () => {
    const request = await fixture()
    // No config anywhere reachable defines these names; global and system
    // config are stripped from the merge environment, so git can only fall
    // back to its built-in merge and plain content.
    await writeFile(join(request.sourcePath, '.gitattributes'), '*.txt merge=custom\nfeature.txt filter=ghost\n')
    await git(request.sourcePath, 'add', '.gitattributes')
    await git(request.sourcePath, 'commit', '-m', 'select unreachable mechanisms')
    const sourceCommit = await git(request.sourcePath, 'rev-parse', 'HEAD')
    await git(request.targetPath, 'commit', '--allow-empty', '-m', 'target advancement')
    const targetHead = await git(request.targetPath, 'rev-parse', 'HEAD')
    const result = await executeIntegrationGit({ ...request, sourceCommit, targetHead, mode: 'merge' }, options)
    expect(result.commandError).toBeUndefined()
    expect(result.observation.kind).toBe('applied')
    expect(await readFile(join(request.targetPath, 'feature.txt'), 'utf8')).toBe('reviewed\n')
    expect(await reconcileIntegrationGit({ ...request, sourceCommit, targetHead, mode: 'merge' }, options)).toEqual(result.observation)
  })

  it('refuses merge mode for a fast-forwardable or already-integrated source', async () => {
    const request = await fixture()
    await expect(inspectIntegrationGit({ ...request, mode: 'merge' }, options)).rejects.toThrow('use the fast-forward path')
    const integrated = await executeIntegrationGit(request, options)
    const mergedHead = integrated.observation.kind === 'applied' ? integrated.observation.head : undefined
    expect(mergedHead).toBeDefined()
    // The pre-merge target head is now an ancestor of main; park the source
    // checkout exactly there so inspection sees a consistent prepared state.
    await git(request.sourcePath, 'checkout', '--detach', request.targetHead)
    await expect(inspectIntegrationGit({ ...request, sourceCommit: request.targetHead, targetHead: mergedHead, mode: 'merge' }, options))
      .rejects.toThrow('the target already contains it')
  })

  it('rejects unrelated histories instead of merging them', async () => {
    const request = await fixture()
    await git(request.sourcePath, 'checkout', '--orphan', 'orphan')
    await git(request.sourcePath, 'add', 'feature.txt')
    await git(request.sourcePath, 'commit', '-m', 'unrelated root')
    const orphanCommit = await git(request.sourcePath, 'rev-parse', 'HEAD')
    const orphanRequest = { ...request, sourceCommit: orphanCommit }
    await expect(observeIntegrationRelation(orphanRequest, options)).rejects.toThrow('related source and target histories')
    await expect(executeIntegrationGit({ ...orphanRequest, mode: 'merge' }, options)).rejects.toThrow('related source and target histories')
    expect(await git(request.targetPath, 'rev-parse', 'HEAD')).toBe(request.targetHead)
  })

})
