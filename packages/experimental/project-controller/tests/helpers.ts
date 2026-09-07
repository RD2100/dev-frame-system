/**
 * Shared test harness: one temp storage root and the real
 * session/storage/storage-domain/JSON/binding/controller composition every
 * spec runs on, mirroring the production composition rows.
 * @module tests/helpers
 */

import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context, type Fiber } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import type { ProjectControllerConfig } from '../src/index.ts'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import ProjectController from '../src/index.ts'

/** The per-spec harness: one temp root and one booted context. */
export interface Harness {
  ctx: Context
  root: string
  dispose: (options?: { readonly keepRoot?: boolean }) => Promise<void>
}

/**
 * Boot the real storage/JSON/binding/controller composition over a directory.
 * @param config - Extra controller config; omit `maxActiveTasks` for the default.
 * @param root - Existing storage root to reuse (cold-restore specs pass the
 *   previous harness's root); omitted, a fresh temp root is created.
 * @returns the booted harness; the caller owns disposal, and `dispose()`
 *   removes the root unless `keepRoot` is set.
 */
export async function harness(
  config: ProjectControllerConfig = {}, root?: string,
): Promise<Harness & { disposeController: () => Promise<void> }> {
  const resolved = root ?? await mkdtemp(join(tmpdir(), 'dsh-project-controller-'))
  const ctx = new Context()
  let controllerFiber: Fiber
  try {
    await ctx.plugin(SessionStore)
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root: resolved })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(AgentBindingRegistry)
    controllerFiber = await ctx.plugin(ProjectController, config)
  } catch (error) {
    await ctx.fiber.dispose()
    await rm(resolved, { recursive: true, force: true })
    throw error
  }
  return {
    ctx,
    root: resolved,
    disposeController: () => controllerFiber.dispose(),
    async dispose(options) {
      await ctx.fiber.dispose()
      if (options?.keepRoot !== true) {
        await rm(resolved, { recursive: true, force: true })
      }
    },
  }
}

/** Deliberately incomplete admission used only by early-denial tests. */
export const unavailableMergeRequest = {
  git: { sourcePath: '/unavailable-source', targetPath: '/unavailable-target', sourceCommit: 'a'.repeat(40), targetHead: 'b'.repeat(40) },
  options: { executable: 'git', timeoutMs: 1000, maxOutputBytes: 1024 },
  requiredChecksStore: { async save() { throw new Error('unavailable') }, async load() { throw new Error('unavailable') } },
}
