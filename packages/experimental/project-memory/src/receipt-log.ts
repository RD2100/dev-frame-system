/**
 * The session-log receipt store: persists one committed append receipt per
 * note into the DSH session log as a log-only `memory/receipt` event, so a
 * cold restart rehydrates the receipt authority by replaying the log instead
 * of trusting the note files themselves. The design (`docs/detailDesign-part3.md`)
 * requires the receipt to be durable before an append returns `created`.
 * @module @deepseek-ai/dsh-experimental-project-memory/receipt-log
 */

import { z } from 'zod'
import type { Session, SessionEvent } from '@deepseek-ai/dsh-session'
import { NoteId } from './ids.ts'
import type { MemoryNamespace, MemoryReceipt, MemoryReceiptStore } from './types.ts'

/**
 * Durable payload of one `memory/receipt` event. Ids stay opaque strings at
 * the log boundary (the plain-string shape a replay decodes); decoding
 * re-applies the brands and validates the digest shapes.
 */
export interface MemoryReceiptEventData {
  /** The note the receipt confirms (64-hex digest shape). */
  readonly noteId: string
  /** Relative namespace directory recorded at commit time. */
  readonly namespace: string
  /** Expected path relative to the Vault root. */
  readonly relativePath: string
  /** `sha256:<hex>` digest of the complete note file bytes. */
  readonly digest: string
  /** ISO-8601 instant the receipt was committed. */
  readonly recordedAt: string
}

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /** Committed append receipt for one memory note; latest event per noteId is the live receipt. */
    'memory/receipt': MemoryReceiptEventData
  }
}

const hex64 = /^[0-9a-f]{64}$/
const sha256Digest = /^sha256:[0-9a-f]{64}$/
const namespaceShape = /^user$|^projects\/[a-zA-Z0-9][a-zA-Z0-9._-]*$/

/**
 * Durable-boundary schema for one receipt event. Decoding validates every
 * field shape and re-applies the `NoteId` brand, so a malformed or hostile
 * log row fails loudly instead of feeding a wrong confirmation into reads.
 */
export const memoryReceiptEventSchema = z.object({
  noteId: z.string().refine(value => hex64.test(value), {
    message: 'noteId must be a lowercase 64-hex digest',
  }).transform(value => NoteId(value)),
  namespace: z.string().refine(value => namespaceShape.test(value), {
    message: 'namespace must be "user" or "projects/<workspaceId>"',
  }).transform(value => value as MemoryNamespace),
  relativePath: z.string().min(1),
  digest: z.string().refine(value => sha256Digest.test(value), {
    message: 'digest must be "sha256:<64 hex characters>"',
  }),
  recordedAt: z.string().min(1),
}) satisfies z.ZodType<MemoryReceiptEventData>

/** Validate one event payload and re-brand it into the service vocabulary. */
function receiptFromEventData(data: MemoryReceiptEventData): MemoryReceipt {
  return memoryReceiptEventSchema.parse(data)
}

/**
 * Append one committed receipt to a session's log. `Session.append` is
 * synchronous and snapshots the payload, so when it returns the receipt is
 * part of the durable log — the ordering the design requires before an
 * append may report `created` to its caller.
 * @param session - The calling agent's session; its log is the durable source of truth.
 * @param receipt - The already-validated receipt the service committed.
 * @returns the receipt as decoded from the logged snapshot.
 */
export function appendMemoryReceipt(session: Session, receipt: MemoryReceipt): MemoryReceipt {
  const data: MemoryReceiptEventData = {
    noteId: receipt.noteId,
    namespace: receipt.namespace,
    relativePath: receipt.relativePath,
    digest: receipt.digest,
    recordedAt: receipt.recordedAt,
  }
  const event = session.append('memory/receipt', data)
  return receiptFromEventData(event.data)
}

/**
 * Fold a session log into the live receipt per note. Later events win: the
 * log is append-only and a re-committed receipt replaces the earlier one.
 * Every receipt event is decoded strictly at the durable boundary.
 * @param events - Live or replayed session events, in log order.
 * @returns the folded receipts keyed by note id.
 */
export function foldMemoryReceipts(events: readonly SessionEvent[]): Map<NoteId, MemoryReceipt> {
  const receipts = new Map<NoteId, MemoryReceipt>()
  for (const event of events) {
    if (event.type !== 'memory/receipt') continue
    const receipt = receiptFromEventData(event.data)
    receipts.set(receipt.noteId, receipt)
  }
  return receipts
}

/**
 * Build a {@link MemoryReceiptStore} over one session's log: reads fold the
 * log (so a replayed or resumed session rehydrates the receipts), and writes
 * append the durable event. The store serves exactly this session's log —
 * the host creates one per dispatching session.
 * @param session - The session whose log owns the receipts.
 * @returns the receipt-store seam implementation.
 */
export function createSessionLogReceiptStore(session: Session): MemoryReceiptStore {
  return {
    read(noteId: NoteId): Promise<MemoryReceipt | undefined> {
      return Promise.resolve(foldMemoryReceipts(session.snapshotEvents()).get(noteId))
    },
    write(receipt: MemoryReceipt): Promise<void> {
      appendMemoryReceipt(session, receipt)
      return Promise.resolve()
    },
  }
}

/**
 * Rehydrate a receipt store from one session's replayed log: every receipt
 * event that the store does not already confirm is written into it. A receipt
 * the store already holds is left untouched, so a newer in-process commit
 * never regresses to an older logged row.
 * @param store - The process-wide receipt index backing the service.
 * @param session - A live or cold-restored session whose log is folded.
 * @returns resolution after the missing receipts are written.
 */
export async function rehydrateMemoryReceipts(store: MemoryReceiptStore, session: Session): Promise<void> {
  for (const receipt of foldMemoryReceipts(session.snapshotEvents()).values()) {
    if (await store.read(receipt.noteId) === undefined) {
      await store.write(receipt)
    }
  }
}
