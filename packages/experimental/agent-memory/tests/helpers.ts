/** Shared real JSON storage composition for agent-memory tests. */
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import AgentMemoryService from '../src/index.ts'

export interface Harness {
  readonly ctx: Context
  readonly root: string
  dispose(options?: { readonly keepRoot?: boolean }): Promise<void>
}

export async function harness(
  root?: string,
  config: { readonly workspaceId?: string; readonly autoRetrieve?: boolean } = {},
): Promise<Harness> {
  const resolved = root ?? await mkdtemp(join(tmpdir(), 'dsh-agent-memory-'))
  const ctx = new Context()
  try {
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root: resolved })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)
    await ctx.plugin(AgentMemoryService, { workspaceId: config.workspaceId ?? 'ws-alpha', autoRetrieve: config.autoRetrieve ?? false })
  } catch (error) {
    await ctx.fiber.dispose()
    await rm(resolved, { recursive: true, force: true })
    throw error
  }
  return {
    ctx,
    root: resolved,
    async dispose(options) {
      await ctx.fiber.dispose()
      if (options?.keepRoot !== true) await rm(resolved, { recursive: true, force: true })
    },
  }
}
