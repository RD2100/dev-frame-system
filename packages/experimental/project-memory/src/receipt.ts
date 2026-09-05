/** The in-memory receipt store used by tests and as the seam reference. */

import { brandString } from '@deepseek-ai/dsh-brand'
import type { NoteId } from './ids.ts'
import type { MemoryReceipt, MemoryReceiptStore } from './types.ts'

/**
 * Create an in-memory {@link MemoryReceiptStore}. The durable implementation
 * belongs to the host (receipts must live in the DSH session log before an
 * append returns `created`); this store exists for tests and for callers
 * that assemble the seam from an already-restored receipt list.
 * @param entries - Receipts restored from the session log, rehydrating the
 *   store for a cold service start.
 * @returns the store, backed by a plain map keyed by note id.
 */
export function createMemoryReceiptStore(entries?: readonly MemoryReceipt[]): MemoryReceiptStore {
  const receipts = new Map<NoteId, MemoryReceipt>()
  for (const receipt of entries ?? []) receipts.set(brandString<NoteId>(receipt.noteId), receipt)
  return {
    async read(noteId) {
      return receipts.get(noteId)
    },
    async write(receipt) {
      receipts.set(brandString<NoteId>(receipt.noteId), receipt)
    },
  }
}
