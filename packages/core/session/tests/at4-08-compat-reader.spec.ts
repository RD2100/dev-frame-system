/**
 * AT4-08 compatibility binding (`docs/testAndAcceptance.md` R4.4): opening a
 * recorded session whose required decoder is missing or whose format version
 * is incompatible must fail clearly without modifying the log, the retained
 * compatible reader must still inspect and export the evidence, and a failed
 * open must roll back without leaving a writer behind.
 *
 * This spec anchors the dsh-session-owned mechanism face with the three
 * acceptance scenarios by name: the build's event vocabulary
 * (`KNOWN_SESSION_EVENT_TYPES`) plus the `ignorable` envelope marker that
 * defines the missing-decoder refusal, the `SESSION_FORMAT_VERSION` header
 * check that refuses an incompatible profile before any event is interpreted,
 * and the restore/store boundary where a failed open leaves no entry. The
 * load-time refusal of a non-ignorable unknown type and the file writer lock
 * are the persistence coordinator's face and stay pinned by its own contract
 * suite; nothing here duplicates it.
 *
 * @module dsh-session/tests/at4-08-compat-reader
 */

import { Context } from '@deepseek-ai/cordis'
import { describe, expect, it } from 'vitest'
import SessionStore, {
  KNOWN_SESSION_EVENT_TYPES,
  SESSION_FORMAT_VERSION,
  Session,
  SessionId,
  SessionLogOffset,
  SessionSeq,
} from '../src/index.ts'
import type { SessionEvent, SessionHeader } from '../src/index.ts'

/** A balanced two-event recorded log, contiguous from seq 0. */
function recordedLog(): SessionEvent[] {
  return [
    { type: 'turn/start', seq: SessionSeq(0), time: 1, data: { turn: 1 } },
    { type: 'turn/end', seq: SessionSeq(1), time: 2, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
}

/** The storage header a current harness stamps on every new session. */
function header(id: string, version: number = SESSION_FORMAT_VERSION): SessionHeader {
  return { version, id: SessionId(id), createdAt: 1, isSeeded: false }
}

/** Deep clone via the same lossless JSON the log itself must survive. */
function jsonClone(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value))
}

describe('AT4-08 compatibility binding', () => {
  it('missing required decoder: an event type outside the build vocabulary is un-interpretable, and only the ignorable marker lets a compatible reader retain it', () => {
    // The "decoder missing" state is exactly this classification: a type the
    // running build has no vocabulary entry for. The persistence read path
    // refuses a log carrying it unless the envelope marks it ignorable.
    expect(KNOWN_SESSION_EVENT_TYPES.has('future/event')).toBe(false)

    // The marker cannot be forged: only `ignorable: true` is a compatibility
    // marker; any other value fails the envelope at the restore boundary.
    const forged = [
      ...recordedLog(),
      { type: 'future/event', seq: SessionSeq(2), time: 3, data: { payload: 1 }, ignorable: false },
    ] as unknown as SessionEvent[]
    expect(() => Session.fromRestore(SessionId('at4-08-forged'), forged, header('at4-08-forged'), SessionLogOffset(0)))
      .toThrow(/invalid event envelope/)

    // With the genuine marker the compatible reader reconstructs the log and
    // retains the foreign event verbatim — evidence is kept, never dropped.
    const marked = [
      ...recordedLog(),
      { type: 'future/event', seq: SessionSeq(2), time: 3, data: { payload: 1 }, ignorable: true },
    ] as unknown as SessionEvent[]
    const session = Session.fromRestore(SessionId('at4-08-marked'), marked, header('at4-08-marked'), SessionLogOffset(0))
    const retained = session.eventAt(SessionSeq(2))
    expect(retained).toEqual(marked[2])
    expect(retained?.type).toBe('future/event')
  })

  it('incompatible profile: a log stamped with any other format version fails clearly before events are interpreted, without modifying the log', () => {
    for (const version of [SESSION_FORMAT_VERSION + 99, SESSION_FORMAT_VERSION - 1]) {
      const log = recordedLog()
      const before = jsonClone(log)
      // The header check is the first validation, so the refusal names the
      // incompatible version and no event of the log has been interpreted.
      expect(() => Session.fromRestore(SessionId('at4-08-version'), log, header('at4-08-version', version), SessionLogOffset(0)))
        .toThrow(new RegExp(`session header version must be ${SESSION_FORMAT_VERSION}, got ${version}`))
      expect(jsonClone(log)).toEqual(before)
    }
  })

  it('compatible reader: the retained log can be inspected and exported, and a failed open rolls back without leaving a writer', async () => {
    // Inspect/export: a compatible reader restores the log — including an
    // ignorable foreign event — reads it back positionally, and exports it
    // losslessly as the plain JSON the durable format is made of.
    const log: SessionEvent[] = [
      ...recordedLog(),
      { type: 'future/event', seq: SessionSeq(2), time: 3, data: { payload: 1 }, ignorable: true },
    ] as unknown as SessionEvent[]
    const session = Session.fromRestore(SessionId('at4-08-reader'), log, header('at4-08-reader'), SessionLogOffset(0))
    expect(session.eventAt(SessionSeq(0))).toEqual(log[0])
    expect(session.eventAt(SessionSeq(2))).toEqual(log[2])
    const exported = jsonClone(session.snapshotEvents())
    expect(exported.slice(0, 3)).toEqual(jsonClone(log))

    // Rollback: an incompatible open throws before the store ever sees the
    // session — no entry, no publication hooks, and the id opens cleanly
    // afterwards.
    const ctx = new Context()
    await ctx.plugin(SessionStore)
    const id = SessionId('at4-08-rollback')
    expect(() => ctx.sessions.prepare(id, {
      seedSource: 'persistence',
      seed: [...log],
      meta: header('at4-08-rollback', SESSION_FORMAT_VERSION + 1),
      inheritedEventCount: SessionLogOffset(0),
    })).toThrow(/session header version must be/)
    expect(ctx.sessions.get(id)).toBeUndefined()
    expect(ctx.sessions.list()).toEqual([])

    const session2 = ctx.sessions.prepare(id, {
      seedSource: 'persistence',
      seed: [...log],
      meta: header('at4-08-rollback'),
      inheritedEventCount: SessionLogOffset(0),
    })
    const detach = ctx.sessions.enter(session2)
    try {
      expect(ctx.sessions.get(id)).toBe(session2)
      expect(session2.header.version).toBe(SESSION_FORMAT_VERSION)
    } finally {
      detach()
    }
  })
})
