/** Isolated real-Git setup and post-process storage verification for the positive integration snapshot. */
import { execFile } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { promisify } from 'node:util'
import { Context } from '@deepseek-ai/cordis'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import { projectTasksDomainSpec } from '@deepseek-ai/dsh-experimental-project-controller'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'

const exec = promisify(execFile)

async function git(cwd: string, ...args: string[]): Promise<string> {
  const env = Object.fromEntries(Object.entries(process.env)
    .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const result = await exec('git', ['-C', cwd, ...args], {
    env: {
      ...env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: join(dirname(cwd), 'empty-config'),
      GIT_AUTHOR_DATE: '2026-01-01T00:00:00Z', GIT_COMMITTER_DATE: '2026-01-01T00:00:00Z',
    },
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
  })
  return result.stdout.trim()
}

/**
 * Seed fixed commits in worktrees owned by one SDK run's disposable Harness home.
 * @param cwd - The run-owned root, never a user checkout.
 */
export async function prepareProjectIntegration(cwd: string): Promise<void> {
  const root = join(cwd, '.dsh', 'integration')
  const repo = join(root, 'repo')
  await mkdir(repo, { recursive: true })
  await writeFile(join(root, 'empty-config'), '')
  await writeFile(join(root, 'empty-attributes'), '')
  await mkdir(join(root, 'empty-template'))
  await git(repo, 'init', '--template=' + join(root, 'empty-template'), '--object-format=sha1', '-b', 'main')
  for (const [key, value] of [
    ['user.name', 'Snapshot Integration'], ['user.email', 'snapshot@example.invalid'],
    ['commit.gpgsign', 'false'], ['core.autocrlf', 'false'], ['core.filemode', 'false'],
    ['core.hooksPath', join(root, 'no-hooks')],
    ['core.attributesFile', join(root, 'empty-attributes')],
  ]) await git(repo, 'config', key as string, value as string)
  await writeFile(join(repo, 'feature.txt'), 'base\n')
  await git(repo, 'add', 'feature.txt')
  await git(repo, 'commit', '-m', 'base')
  for (const role of ['target', 'lead', 'worker']) {
    await git(repo, 'worktree', 'add', '-b', role, join(root, role))
  }
  const source = join(root, 'worker')
  await writeFile(join(source, 'feature.txt'), 'reviewed\n')
  await git(source, 'add', 'feature.txt')
  await git(source, 'commit', '-m', 'reviewed implementation')
}

/**
 * Read Git and reopen durable storage after the SDK process exits; no model self-report is accepted.
 * @param cwd - The same isolated SDK run root used for setup.
 */
export async function verifyProjectIntegration(cwd: string): Promise<void> {
  const root = join(cwd, '.dsh', 'integration')
  const [targetHead, sourceHead, baseHead, content] = await Promise.all([
    git(join(root, 'target'), 'rev-parse', 'HEAD'), git(join(root, 'worker'), 'rev-parse', 'HEAD'),
    git(join(root, 'repo'), 'rev-parse', 'HEAD'), readFile(join(root, 'target', 'feature.txt'), 'utf8'),
  ])
  if (targetHead !== sourceHead || targetHead === baseHead || content !== 'reviewed\n') {
    throw new Error(`Integration snapshot did not apply the reviewed commit: target=${targetHead} source=${sourceHead} base=${baseHead}`)
  }
  const ctx = new Context()
  try {
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root: join(cwd, '.dsh', 'storages') })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    const domain = await ctx.storageDomain.open(projectTasksDomainSpec)
    try {
      const task = domain.table('tasks').get(TaskId('task-integration'))
      const intent = domain.table('integrations').get(TaskId('task-integration'))
      if (task?.state !== 'integrated' || intent?.state !== 'applied' || intent.sourceCommit !== targetHead) {
        throw new Error(`Integration snapshot durable outcome disagrees with Git: task=${task?.state} intent=${intent?.state}`)
      }
      await writeFile(join(cwd, 'integration-result.json'), JSON.stringify({
        taskState: task.state, intentState: intent.state, reviewedCommitApplied: true, content,
      }, null, 2) + '\n')
    } finally {
      await domain.close()
    }
  } finally {
    await ctx.fiber.dispose()
  }
}
