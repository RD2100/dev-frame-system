/**
 * The default in-memory receipt store.
 *
 * The project-memory plugin wires this store directly at runtime when no
 * durable host-backed store is injected (the durable implementation belongs
 * to the DSH session log). Tests use the same factory as a lightweight
 * stand-in; pass entries to rehydrate a cold start.
 */

import { brandString } from '@deepseek-ai/dsh-brand'
import type { NoteId } from './ids.ts'
import type { MemoryReceipt, MemoryReceiptStore } from './types.ts'

/**
 * Create the default in-memory {@link MemoryReceiptStore}. The project-memory
 * plugin wires this store directly at runtime when no durable host-backed
 * store is injected (receipts must live in the DSH session log before an
 * append returns `created`). Tests reuse the same factory as a lightweight
 * stand-in for callers that assemble the seam from an already-restored list.
 * @param entries - Receipts restored from the session log, rehydrating the
 *   store for a cold service start.
 * @returns the store, backed by a plain map keyed by note id.
 */
export function createMemoryReceiptStore(entries?: readonly MemoryReceipt[]): MemoryReceiptStore {
  const receipts = new Map<NoteId, MemoryReceipt>()
  for (const receipt of entries ?? []) receipts.set(brandString<NoteId>(receipt.noteId), receipt)
  return {
    read(noteId) {
      return Promise.resolve(receipts.get(noteId))
    },
    write(receipt) {
      receipts.set(brandString<NoteId>(receipt.noteId), receipt)
      return Promise.resolve()
    },
  }
}
