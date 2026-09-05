/**
 * Agent-side receipt rehydration end to end: real Vault files, real tool
 * dispatch, real session logs. `memory_append` lands its receipt in the
 * calling agent's log, a replayed log rehydrates a fresh context through the
 * plugin's `agent/created` hook, and the rehydrated authority drives honest
 * reads, idempotent retries, and conflict reporting. No mocks anywhere.
 */

import { afterEach, describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { Session, SessionId } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import * as projectMemory from '../src/index.ts'
import { digestTag } from '../src/notes.ts'
import type { Config } from '../src/index.ts'

const ROOTS: string[] = []
const CONTEXTS: Context[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
  while (ROOTS.length > 0) {
    const root = ROOTS.pop()
    if (root !== undefined) rmSync(root, { recursive: true, force: true })
  }
})

/** Create one throwaway Vault root with the memory subtree pre-created. */
function makeVault(): string {
  const root = mkdtempSync(join(tmpdir(), 'pm-agent-rehydrate-'))
  ROOTS.push(root)
  mkdirSync(join(root, 'devframe-memory'), { recursive: true })
  return root
}

/** Boot a minimal context with the memory plugin mounted over the given Vault. */
async function boot(config: Config): Promise<Context> {
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(projectMemory, config)
  return ctx
}

/**
 * One structural stand-in for a dispatching agent: the append tool needs only
 * the live session whose log receives the receipt — the same seam the host
 * passes to tools. The Session itself is a real dsh-session instance.
 */
function agentWithSession(sessionId: string): Agent {
  return { session: Session.create(SessionId(sessionId)) } as unknown as Agent
}

/** Dispatch one tool call through the live registry pipeline. */
async function dispatch(ctx: Context, name: string, args: unknown, callNumber: number, agent?: Agent) {
  return await ctx.tools.execute({
    callId: ToolCallId(`pm-agent-rehydrate-${callNumber}`),
    name,
    arguments: args,
    signal: new AbortController().signal,
    ...(agent === undefined ? {} : { agent }),
  })
}

/** The memory/receipt events of one session log, in log order. */
function receiptEvents(session: Session): SessionEvent<'memory/receipt'>[] {
  return session.snapshotEvents()
    .filter((event): event is SessionEvent<'memory/receipt'> => event.type === 'memory/receipt')
}

/** The absolute path of one project-scope note file inside the Vault. */
function notePath(vaultRoot: string, noteId: string): string {
  return join(vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${noteId}.md`)
}

/**
 * Wait until the fresh context's service verifies the note against its
 * rehydrated receipt. The plugin's `agent/created` hook rehydrates
 * asynchronously, so the wait polls the observable outcome instead of
 * sleeping a fixed interval.
 */
async function untilVerified(ctx: Context, noteId: string): Promise<void> {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    const result = await ctx.projectMemory.read({ scope: 'project', noteId })
    if (result.status === 'found' && result.verified === true) return
    await new Promise(resolve => setTimeout(resolve, 5))
  }
  throw new Error(`the receipt for ${noteId} was never rehydrated into the fresh context`)
}

describe('agent session receipts during live dispatch', () => {
  it('logs one receipt per created note in append order and keeps it live across a conflicting re-append', async () => {
    const vaultRoot = makeVault()
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const agent = agentWithSession('pm-agent-rehydrate-live')

    const first = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-a',
      kind: 'fact',
      body: 'Note A: the first receipt, written under source reference event-a.',
    }, 1, agent)
    const second = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-b',
      kind: 'lesson',
      body: 'Note B: a second note derived from a different source reference.',
    }, 2, agent)
    expect(first.isError).toBe(false)
    expect(second.isError).toBe(false)
    if (first.isError || second.isError) return
    const createdA = first.value as { status: string; noteId: string; relativePath: string }
    const createdB = second.value as { status: string; noteId: string; relativePath: string }
    expect(createdA.status).toBe('created')
    expect(createdB.status).toBe('created')

    // Same source reference with a changed body: the service reports the
    // conflict path and never overwrites or re-commits the note.
    const conflict = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-a',
      kind: 'fact',
      body: 'Note A rewritten under the same source reference.',
    }, 3, agent)
    expect(conflict.isError).toBe(false)
    if (conflict.isError) return
    expect(conflict.value).toMatchObject({ status: 'memory_conflict', noteId: createdA.noteId })

    // Receipt events appear in append order, one per created note; the
    // conflicting re-append committed nothing.
    const events = receiptEvents(agent.session)
    expect(events.map(event => event.data.noteId)).toEqual([createdA.noteId, createdB.noteId])
    for (let index = 1; index < events.length; index += 1) {
      expect(events[index]!.seq).toBeGreaterThan(events[index - 1]!.seq)
    }

    // Latest-per-noteId fold over the live log: exactly one live receipt per note.
    const folded = projectMemory.foldMemoryReceipts(agent.session.snapshotEvents())
    expect([...folded.keys()]).toEqual([
      projectMemory.NoteId(createdA.noteId),
      projectMemory.NoteId(createdB.noteId),
    ])

    // The live receipt for A matches the note file actually on disk.
    const liveA = folded.get(projectMemory.NoteId(createdA.noteId))
    expect(liveA).toBeDefined()
    if (liveA === undefined) return
    expect(liveA.digest).toBe(digestTag(readFileSync(notePath(vaultRoot, createdA.noteId), 'utf8')))
    expect(liveA.relativePath).toBe(createdA.relativePath)
    expect(liveA.relativePath).toBe(`devframe-memory/projects/ws-alpha/${createdA.noteId}.md`)
    expect(liveA.recordedAt.length).toBeGreaterThan(0)
  })
})

describe('cold recovery through the plugin agent/created hook', () => {
  it('rehydrates a fresh context from the replayed log and drives honest service outcomes', async () => {
    const vaultRoot = makeVault()
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const agent = agentWithSession('pm-agent-rehydrate-cold')
    const requestA = {
      scope: 'project',
      source_ref: 'session-alpha#event-c',
      kind: 'fact',
      body: 'Cold recovery: note C is appended before the restart.',
    }
    const requestB = {
      scope: 'project',
      source_ref: 'session-alpha#event-d',
      kind: 'question',
      body: 'Cold recovery: note D asks whether the receipt survived.',
    }
    const first = await dispatch(ctx, 'memory_append', requestA, 4, agent)
    const second = await dispatch(ctx, 'memory_append', requestB, 5, agent)
    expect(first.isError).toBe(false)
    expect(second.isError).toBe(false)
    if (first.isError || second.isError) return
    const createdA = first.value as { status: string; noteId: string }
    const createdB = second.value as { status: string; noteId: string }
    expect(createdA.status).toBe('created')
    expect(createdB.status).toBe('created')

    // Cold recovery: replay the frozen log into a fresh session, mount a
    // second plugin instance over the same Vault (a fresh in-memory index),
    // and drive the plugin's real `agent/created` hook with the recovered agent.
    const recovered = Session.create(SessionId('pm-agent-rehydrate-cold-2'), agent.session.snapshotEvents())
    const restarted = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const recoveredAgent = { session: recovered } as unknown as Agent
    restarted.emit('agent/created', { agent: recoveredAgent })
    await untilVerified(restarted, createdA.noteId)
    await untilVerified(restarted, createdB.noteId)

    // Receipt ↔ note correspondence after rehydration: the replayed receipt
    // matches the file still on disk at its recorded relative path.
    const receiptA = receiptEvents(recovered).find(event => event.data.noteId === createdA.noteId)
    expect(receiptA).toBeDefined()
    if (receiptA === undefined) return
    expect(receiptA.data.digest).toBe(digestTag(readFileSync(notePath(vaultRoot, createdA.noteId), 'utf8')))
    expect(receiptA.data.relativePath).toBe(`devframe-memory/projects/ws-alpha/${createdA.noteId}.md`)
    expect(receiptA.data.recordedAt.length).toBeGreaterThan(0)

    // The replayed log preserves the append order of the receipt events.
    expect(receiptEvents(recovered).map(event => event.data.noteId))
      .toEqual(receiptEvents(agent.session).map(event => event.data.noteId))

    // Service-level outcome through the restarted context's own service.
    const read = await restarted.projectMemory.read({ scope: 'project', noteId: createdA.noteId })
    expect(read.status).toBe('found')
    if (read.status !== 'found') return
    expect(read.verified).toBe(true)

    // Retries through the tool surface against the rehydrated authority: the
    // same body reports already_exists, a changed body reports the conflict
    // path, and neither writes a duplicate receipt into the recovered log.
    const retry = await dispatch(restarted, 'memory_append', requestA, 6, recoveredAgent)
    const conflict = await dispatch(restarted, 'memory_append', {
      ...requestA,
      body: 'Cold recovery: note C rewritten under the same reference.',
    }, 7, recoveredAgent)
    expect(retry.isError).toBe(false)
    expect(conflict.isError).toBe(false)
    if (retry.isError || conflict.isError) return
    expect(retry.value).toMatchObject({ status: 'already_exists', noteId: createdA.noteId })
    expect(conflict.value).toMatchObject({ status: 'memory_conflict', noteId: createdA.noteId })
    expect(receiptEvents(recovered)).toHaveLength(2)
  })
})

describe('service outcomes over a rehydrated receipt index', () => {
  it('serves verified reads and idempotent retries from receipts folded out of the agent log', async () => {
    const vaultRoot = makeVault()
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const agent = agentWithSession('pm-agent-rehydrate-service')
    const appended = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-e',
      kind: 'fact',
      body: 'Service rehydration: the receipt authority comes from the log.',
    }, 8, agent)
    expect(appended.isError).toBe(false)
    if (appended.isError) return
    const created = appended.value as { status: string; noteId: string }
    expect(created.status).toBe('created')

    // Rehydrate an index straight from the agent's session log, then build a
    // fresh service over the SAME Vault root — the cold-start assembly.
    const index = projectMemory.createMemoryReceiptStore()
    await projectMemory.rehydrateMemoryReceipts(index, agent.session)
    const service = new projectMemory.ProjectMemoryService(
      projectMemory.resolveMemorySpec({ vaultRoot, writeEnabled: true, workspaceId: 'ws-alpha' }),
      index,
    )

    const read = await service.read({ scope: 'project', noteId: created.noteId })
    expect(read.status).toBe('found')
    if (read.status !== 'found') return
    expect(read.verified).toBe(true)

    const retry = await service.append({
      scope: 'project',
      sourceRef: 'session-alpha#event-e',
      kind: 'fact',
      body: 'Service rehydration: the receipt authority comes from the log.',
      assertionStatus: 'observed',
    })
    expect(retry).toMatchObject({ status: 'already_exists', noteId: created.noteId })

    const conflict = await service.append({
      scope: 'project',
      sourceRef: 'session-alpha#event-e',
      kind: 'fact',
      body: 'Service rehydration: a different body under the same reference.',
      assertionStatus: 'observed',
    })
    expect(conflict).toMatchObject({ status: 'memory_conflict', noteId: created.noteId })
  })
})

describe('latest-per-noteId rebuild across a real re-commit', () => {
  it('folds the replayed log to the re-committed receipt and leaves the other note untouched', async () => {
    const vaultRoot = makeVault()
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const agent = agentWithSession('pm-agent-rehydrate-recommit')
    const requestF = {
      scope: 'project',
      source_ref: 'session-alpha#event-f',
      kind: 'fact',
      body: 'Re-commit: note F exists before the loss.',
    }
    const first = await dispatch(ctx, 'memory_append', requestF, 9, agent)
    const second = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-g',
      kind: 'lesson',
      body: 'Re-commit: note G is the bystander.',
    }, 10, agent)
    expect(first.isError).toBe(false)
    expect(second.isError).toBe(false)
    if (first.isError || second.isError) return
    const createdF = first.value as { status: string; noteId: string }
    const createdG = second.value as { status: string; noteId: string }
    const originalF = receiptEvents(agent.session).find(event => event.data.noteId === createdF.noteId)
    const originalG = receiptEvents(agent.session).find(event => event.data.noteId === createdG.noteId)
    expect(originalF).toBeDefined()
    expect(originalG).toBeDefined()
    if (originalF === undefined || originalG === undefined) return

    // Real loss: the note file disappears and the process-wide index is gone
    // with the old context. The fresh context starts with an empty index and
    // no `agent/created` is emitted, so nothing rehydrates it — the service
    // re-evaluates the derived path and re-commits through exclusive create.
    rmSync(notePath(vaultRoot, createdF.noteId))
    const fresh = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const recommitted = await dispatch(fresh, 'memory_append', {
      ...requestF,
      body: 'Re-commit: note F is recreated with a new body after the loss.',
    }, 11, agent)
    expect(recommitted.isError).toBe(false)
    if (recommitted.isError) return
    expect(recommitted.value).toMatchObject({ status: 'created', noteId: createdF.noteId })

    // The same agent log now holds two receipts for F: append order [F, G, F].
    const events = receiptEvents(agent.session)
    expect(events.map(event => event.data.noteId))
      .toEqual([createdF.noteId, createdG.noteId, createdF.noteId])

    // Latest-per-noteId rebuild after replay: the fold of the replayed log
    // keeps the re-committed receipt for F and the original receipt for G.
    const replayed = Session.create(SessionId('pm-agent-rehydrate-recommit-2'), agent.session.snapshotEvents())
    const folded = projectMemory.foldMemoryReceipts(replayed.snapshotEvents())
    const latestF = folded.get(projectMemory.NoteId(createdF.noteId))
    expect(latestF).toBeDefined()
    if (latestF === undefined) return
    expect(latestF.digest).not.toBe(originalF.data.digest)
    expect(latestF.digest).toBe(digestTag(readFileSync(notePath(vaultRoot, createdF.noteId), 'utf8')))
    expect(folded.get(projectMemory.NoteId(createdG.noteId))?.digest).toBe(originalG.data.digest)
  })
})

describe('durable boundary decode', () => {
  it('fails loud when a replayed receipt row carries a malformed digest', async () => {
    const vaultRoot = makeVault()
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot, writeEnabled: true })
    const agent = agentWithSession('pm-agent-rehydrate-guard')
    const appended = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-h',
      kind: 'fact',
      body: 'Decode guard: the only logged receipt is tampered for this case.',
    }, 12, agent)
    expect(appended.isError).toBe(false)
    if (appended.isError) return
    const logged = receiptEvents(agent.session).at(-1)
    expect(logged).toBeDefined()
    if (logged === undefined) return

    // The one cast case: a hostile log row keeps the real event's envelope
    // but swaps in a digest that violates the durable-boundary schema.
    const tampered = { ...logged, data: { ...logged.data, digest: 'sha256:nope' } } as unknown as SessionEvent
    expect(() => projectMemory.foldMemoryReceipts([tampered])).toThrow(/digest/u)

    // Rehydration through the same seam rejects the tampered replay too.
    const tamperedLog = Session.create(SessionId('pm-agent-rehydrate-guard-2'), [tampered])
    await expect(projectMemory.rehydrateMemoryReceipts(projectMemory.createMemoryReceiptStore(), tamperedLog))
      .rejects.toThrow(/digest/u)
  })
})
