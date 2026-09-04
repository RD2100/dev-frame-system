import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import SessionStore from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '../src/index.ts'
import { git } from './helpers.ts'

let root: string | undefined
const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

/** Write the cordis.yml under test: the web-layer shelf (session, persistence, storage stack, workspace) plus this package. */
async function writeCompositionConfig(): Promise<string> {
  const configPath = join(root as string, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@deepseek-ai/dsh-session'",
    "- name: '@deepseek-ai/dsh-session-persistence-jsonl'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'sessions'))}`,
    '    compression: none',
    '    writeBatchMaxDelayMs: 1',
    "- name: '@deepseek-ai/dsh-storage'",
    "- name: '@deepseek-ai/dsh-storage-json'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'storage'))}`,
    "- name: '@deepseek-ai/dsh-storage-domain'",
    '  config:',
    '    backend: json',
    "- name: '@deepseek-ai/dsh-subprocess-local'",
    "- name: '@deepseek-ai/dsh-workspace'",
    "- name: '@deepseek-ai/dsh-worktree-registry'",
    '',
  ].join('\n'))
  return configPath
}

async function loadComposition(configPath: string): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  ctx.baseUrl = pathToFileURL(root as string).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  const modules = new Map<string, unknown>([
    ['@deepseek-ai/dsh-session', SessionStore],
    ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
    ['@deepseek-ai/dsh-storage', Storage],
    ['@deepseek-ai/dsh-storage-json', StorageJson],
    ['@deepseek-ai/dsh-storage-domain', StorageDomain],
    ['@deepseek-ai/dsh-subprocess-local', SubprocessLocal],
    ['@deepseek-ai/dsh-workspace', WorkspaceRegistry],
    ['@deepseek-ai/dsh-worktree-registry', GitWorktreeRegistry],
  ])
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({
    name: 'cordis:include',
    config: { path: pathToFileURL(configPath).href },
  })
  await ctx.loader.await()
  const unloaded = [...ctx.loader.entries()]
    .filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)
  expect(unloaded).toEqual([])
  return ctx
}

describe('worktree registry through a real Loader composition', () => {
  it('registers a worktree beside dsh-workspace and survives a cold restart', async () => {
    root = await mkdtemp(join(tmpdir(), 'dsh-worktree-registry-loader-'))
    const repo = join(root, 'repo')
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'worktree-registry@test.local')
    await git(repo, 'config', 'user.name', 'Worktree Registry Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')
    const configPath = await writeCompositionConfig()

    const first = await loadComposition(configPath)
    const workspace = await first.workspaceRegistry.create(repo)
    const worktree = await first.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, 'wt-a') })
    expect(first.worktreeRegistry.list(workspace.id).map(entry => entry.id)).toEqual([worktree.id])

    await first.fiber.dispose()
    contexts.splice(contexts.indexOf(first), 1)

    const second = await loadComposition(configPath)
    const restored = second.worktreeRegistry.list(workspace.id)
    expect(restored.map(entry => entry.id)).toEqual([worktree.id])
    expect(restored.map(entry => entry.path)).toEqual([worktree.path])
    expect(restored.map(entry => entry.branch)).toEqual(['wt-a'])
  })
})
