/**
 * Session-log receipt durability: the `memory/receipt` event vocabulary, the
 * per-session receipt store, strict decoding at the durable boundary, and the
 * cold-recovery rehydration path (replayed logs restore the receipt authority).
 */

import { describe, expect, it } from 'vitest'
import { Session, SessionId } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import { NoteId } from '../src/ids.ts'
import {
  appendMemoryReceipt,
  createSessionLogReceiptStore,
  foldMemoryReceipts,
  rehydrateMemoryReceipts,
} from '../src/receipt-log.ts'
import { createMemoryReceiptStore } from '../src/receipt.ts'
import type { MemoryReceipt } from '../src/types.ts'

const NOTE_ID = NoteId('a'.repeat(64))
const DIGEST = `sha256:${'b'.repeat(64)}`

/** One valid receipt for the shared note id. */
function receipt(overrides: Partial<MemoryReceipt> = {}): MemoryReceipt {
  return {
    noteId: NOTE_ID,
    namespace: 'projects/ws-alpha',
    relativePath: `devframe-memory/projects/ws-alpha/${NOTE_ID}.md`,
    digest: DIGEST,
    recordedAt: '2026-09-06T00:00:00.000Z',
    ...overrides,
  }
}

describe('session-log receipt store', () => {
  it('reads back a committed receipt from the live log', async () => {
    const session = Session.create(SessionId('pm-receipt-live'))
    const store = createSessionLogReceiptStore(session)
    await store.write(receipt())
    const read = await store.read(NOTE_ID)
    expect(read).toEqual(receipt())
    expect(read?.noteId).toBe(NOTE_ID)
  })

  it('answers undefined for a note with no committed receipt', async () => {
    const session = Session.create(SessionId('pm-receipt-empty'))
    const store = createSessionLogReceiptStore(session)
    await expect(store.read(NoteId('c'.repeat(64)))).resolves.toBeUndefined()
  })

  it('keeps the latest receipt per note: a re-committed receipt replaces the earlier one', async () => {
    const session = Session.create(SessionId('pm-receipt-latest'))
    const store = createSessionLogReceiptStore(session)
    await store.write(receipt())
    const later = receipt({ digest: `sha256:${'d'.repeat(64)}`, recordedAt: '2026-09-06T00:01:00.000Z' })
    await store.write(later)
    await expect(store.read(NOTE_ID)).resolves.toEqual(later)
  })

  it('appends the receipt as a memory/receipt event carrying the durable payload', () => {
    const session = Session.create(SessionId('pm-receipt-event'))
    appendMemoryReceipt(session, receipt())
    const event = session.snapshotEvents().findLast(item => item.type === 'memory/receipt')
    expect(event).toBeDefined()
    expect(event?.data).toEqual({
      noteId: NOTE_ID,
      namespace: 'projects/ws-alpha',
      relativePath: `devframe-memory/projects/ws-alpha/${NOTE_ID}.md`,
      digest: DIGEST,
      recordedAt: '2026-09-06T00:00:00.000Z',
    })
  })
})

describe('cold recovery', () => {
  it('rehydrates receipts from a replayed session log', async () => {
    const original = Session.create(SessionId('pm-receipt-cold'))
    const store = createSessionLogReceiptStore(original)
    await store.write(receipt())
    await store.write(receipt({ noteId: NoteId('e'.repeat(64)) }))

    // Cold recovery: a fresh process replays the persisted events into a new
    // session; the receipt authority comes back from the log, not the files.
    const recovered = Session.create(SessionId('pm-receipt-cold-2'), original.snapshotEvents())
    const recoveredStore = createSessionLogReceiptStore(recovered)
    await expect(recoveredStore.read(NOTE_ID)).resolves.toEqual(receipt())
    await expect(recoveredStore.read(NoteId('e'.repeat(64)))).resolves.toBeDefined()
  })

  it('rehydrates a receipt index through rehydrateMemoryReceipts without regressing newer rows', async () => {
    const logged = Session.create(SessionId('pm-rehydrate-source'))
    appendMemoryReceipt(logged, receipt())

    const index = createMemoryReceiptStore()
    const newer = receipt({ digest: `sha256:${'f'.repeat(64)}` })
    await index.write(newer)
    await rehydrateMemoryReceipts(index, logged)

    const rows = await Promise.all([
      index.read(NOTE_ID),
      index.read(NoteId('e'.repeat(64))),
    ])
    expect(rows[0]).toEqual(newer)
    expect(rows[1]).toBeUndefined()

    const empty = createMemoryReceiptStore()
    await rehydrateMemoryReceipts(empty, logged)
    await expect(empty.read(NOTE_ID)).resolves.toEqual(receipt())
  })

  it('rejects a malformed receipt event at the durable boundary instead of trusting it', () => {
    const malformed = {
      type: 'memory/receipt',
      seq: 0,
      time: 0,
      data: { noteId: NOTE_ID, namespace: 'projects/ws-alpha', relativePath: 'x', digest: 'sha256:nope', recordedAt: 'x' },
    } as unknown as SessionEvent
    expect(() => foldMemoryReceipts([malformed])).toThrow(/digest/u)
  })
})
