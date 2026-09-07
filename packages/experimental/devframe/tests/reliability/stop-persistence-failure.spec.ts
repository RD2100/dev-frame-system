/** Stop results retain ownership and redact real JSONL persistence failures. */
import { Context } from '@deepseek-ai/cordis'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { stopProject, type StopObservation } from '../../src/reliability/stop.ts'

describe('stop with real session persistence', () => {
  it.each([false, true])('settles after the JSONL durability barrier (directory conflict: %s)', async (conflict) => {
    const directory = await mkdtemp(join(tmpdir(), 'dsh-stop-persistence-'))
    const privatePath = 'private-storage-marker'
    const privateContent = 'private-session-content-marker'
    const root = join(directory, privatePath)
    const ctx = new Context()
    try {
      await ctx.plugin(SessionStore)
      await ctx.plugin(JsonlSessionPersistence, { root, compression: 'none' })
      // The backend accepts an absent root. A file installed before Session
      // creation makes its first real materialization fail without a race.
      if (conflict) await writeFile(root, privateContent, { flag: 'wx', mode: 0o600 })
      const session = ctx.sessions.create(SessionId('stop-persistence-owner'))
      session.append('turn/start', { turn: 1 })
      session.append('user/message', createUserMessage({
        content: [{ type: 'text', text: privateContent }], source: { kind: 'user' },
      }), { surfaceOp: 'append' })
      session.append('turn/end', { turn: 1, reason: { kind: 'completed' } })

      const observations: StopObservation[] = []
      const order: string[] = []
      const releaseWriter = vi.fn(() => { order.push('released') })
      let persistenceError: unknown
      const result = await stopProject({
        agents: [],
        registry: { get: () => undefined },
        goals: { disarm: () => undefined, pause: () => undefined },
        jobs: { list: () => [], kill: vi.fn(), wait: vi.fn() },
        processes: () => [],
        graceMs: 30_000,
        closeAdmission: () => { order.push('closed') },
        record: (observation) => { observations.push(observation) },
        flush: async () => {
          try {
            await ctx.sessions.flush(session)
            order.push('durable')
          } catch (error: unknown) {
            persistenceError = error
            throw error
          }
        },
        releaseWriter,
      })

      const published = JSON.stringify({ result, observations })
      expect(published).not.toContain(privatePath)
      expect(published).not.toContain(privateContent)
      expect(observations.map(observation => observation.status))
        .toEqual(['stop_requested', 'quiescence_confirmed'])
      if (conflict) {
        expect(persistenceError).toBeInstanceOf(Error)
        if (!(persistenceError instanceof Error) || !('code' in persistenceError)) {
          throw new Error('expected the JSONL backend to expose a filesystem error')
        }
        expect(['EEXIST', 'ENOTDIR']).toContain(persistenceError.code)
        expect(persistenceError.message).toContain(privatePath)
        expect(result).toEqual({ status: 'needs_attention', remaining: [
          { resource: 'session:flush', reason: 'operation_failed' },
        ] })
        expect(releaseWriter).not.toHaveBeenCalled()
        expect(order).toEqual(['closed'])
        expect(await readFile(root, 'utf8')).toBe(privateContent)
      } else {
        expect(persistenceError).toBeUndefined()
        expect(result).toEqual({ status: 'stopped', remaining: [] })
        expect(releaseWriter).toHaveBeenCalledOnce()
        expect(order).toEqual(['closed', 'durable', 'released'])
        const raw = await ctx.sessionPersistence.readRaw(session.id)
        expect(raw?.content).toContain(privateContent)
        expect(raw?.content).toContain('"type":"turn/end"')
        const restored = await ctx.sessionPersistence.load(session.id)
        expect(restored.events.map(event => event.type)).toEqual(['turn/start', 'user/message', 'turn/end'])
      }
    } finally {
      try {
        await ctx.fiber.dispose()
      } finally {
        await rm(directory, { recursive: true, force: true })
      }
    }
  }, 30_000)
})
