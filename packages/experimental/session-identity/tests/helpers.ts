/**
 * Shared test harness: one temp storage root and the real
 * session/storage/storage-domain/JSON/registry composition every spec runs
 * on, mirroring the production composition rows (JSON documents under the
 * configured root stand in for the deployed storages directory).
 * @module tests/helpers
 */

import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import AgentBindingRegistry from '../src/index.ts'

/** The per-spec harness: one temp root and one booted context. */
export interface Harness {
  ctx: Context
  root: string
  dispose: (options?: { readonly keepRoot?: boolean }) => Promise<void>
}

/**
 * Boot the real session/storage/JSON/registry composition over a directory.
 * @param root - Existing storage root to reuse (cold-restore specs pass the
 *   previous harness's root); omitted, a fresh temp root is created.
 * @returns the booted harness; the caller owns disposal, and `dispose()`
 *   removes the root unless `keepRoot` is set.
 */
export async function harness(root?: string): Promise<Harness> {
  const resolved = root ?? await mkdtemp(join(tmpdir(), 'dsh-session-identity-'))
  const ctx = new Context()
  try {
    await ctx.plugin(SessionStore)
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root: resolved })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(AgentBindingRegistry)
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
      if (options?.keepRoot !== true) {
        await rm(resolved, { recursive: true, force: true })
      }
    },
  }
}
