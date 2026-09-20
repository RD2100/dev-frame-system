import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtemp, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { meta, oneTurnLog } from '../../session-persistence/tests/contract.ts'
import { logPath } from '../src/format.ts'

const dirs: string[] = []

afterEach(async () => {
  for (const d of dirs.splice(0)) await rm(d, { recursive: true, force: true })
})

async function freshRoot(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-attach-'))
  dirs.push(dir)
  return dir
}

async function mounted(root: string): Promise<{ ctx: Context; dispose: () => Promise<void> }> {
  const ctx = new Context()
  await ctx.plugin(SessionStore)
  const fiber = await ctx.plugin(JsonlSessionPersistence, { root })
  return { ctx, dispose: () => fiber.dispose() }
}

/** The concrete backend face; the contract service type does not expose the seam. */
function attachable(persistence: unknown): JsonlSessionPersistence {
  return persistence as JsonlSessionPersistence
}

describe('JsonlSessionPersistence.attachSessionCwd', () => {
  it('rewrites the header, moves the log, and preserves every event', async () => {
    const root = await freshRoot()
    const { ctx, dispose } = await mounted(root)
    try {
      const m = meta('attach-me')
      await ctx.sessionPersistence.create(m)
      await ctx.sessionPersistence.append(m.id, oneTurnLog())
      const targetCwd = '/projects/shadow-trial'

      const attached = await attachable(ctx.sessionPersistence).attachSessionCwd(SessionId('attach-me'), targetCwd)
      expect(attached.cwd).toBe(targetCwd)
      expect(attached.id).toBe(m.id)

      // The list now reports the relocated header under the attached cwd.
      const row = (await ctx.sessionPersistence.list()).find(header => header.id === m.id)
      expect(row?.cwd).toBe(targetCwd)

      // The log physically moved: the new artifact exists, the old one is gone.
      await expect(stat(logPath(root, targetCwd, m.id, 'zstd'))).resolves.toBeDefined()
      await expect(stat(logPath(root, undefined, m.id, 'zstd'))).rejects.toThrow()

      // Every stored event survived the relocation byte-for-byte.
      const loaded = await ctx.sessionPersistence.load(m.id)
      expect(loaded.events.length).toBe(oneTurnLog().length)
      expect(loaded.events.map(event => event.type)).toEqual(oneTurnLog().map(event => event.type))
    } finally {
      await dispose()
    }
  })

  it('is one-way: refuses a session that already carries a cwd', async () => {
    const root = await freshRoot()
    const { ctx, dispose } = await mounted(root)
    try {
      const m = meta('attach-armed', '/projects/elsewhere')
      await ctx.sessionPersistence.create(m)
      await ctx.sessionPersistence.append(m.id, oneTurnLog())
      await expect(
        attachable(ctx.sessionPersistence).attachSessionCwd(SessionId('attach-armed'), '/projects/new'),
      ).rejects.toThrow(/already carries a cwd/)
    } finally {
      await dispose()
    }
  })

  it('refuses an unknown id, an empty cwd, and a mismatched header id', async () => {
    const root = await freshRoot()
    const { ctx, dispose } = await mounted(root)
    try {
      await expect(
        attachable(ctx.sessionPersistence).attachSessionCwd(SessionId('no-such'), '/projects/x'),
      ).rejects.toThrow(/not persisted/)

      const m = meta('attach-empty')
      await ctx.sessionPersistence.create(m)
      await ctx.sessionPersistence.append(m.id, oneTurnLog())
      await expect(
        attachable(ctx.sessionPersistence).attachSessionCwd(SessionId('attach-empty'), ''),
      ).rejects.toThrow(/empty project directory/)
    } finally {
      await dispose()
    }
  })

  it('round-trips the attached cwd through a fresh mount of the same root', async () => {
    const root = await freshRoot()
    const first = await mounted(root)
    try {
      const m = meta('attach-reload')
      await first.ctx.sessionPersistence.create(m)
      await first.ctx.sessionPersistence.append(m.id, oneTurnLog())
      await attachable(first.ctx.sessionPersistence).attachSessionCwd(SessionId('attach-reload'), '/projects/reload-me')
    } finally {
      await first.dispose()
    }
    const second = await mounted(root)
    try {
      const row = (await second.ctx.sessionPersistence.list()).find(header => header.id === 'attach-reload')
      expect(row?.cwd).toBe('/projects/reload-me')
      expect(row?.id).toBe('attach-reload')
    } finally {
      await second.dispose()
    }
  })
})
