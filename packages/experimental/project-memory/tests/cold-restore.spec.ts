/**
 * Cold recovery: a restarted service over the same Vault with receipts
 * rehydrated from the session log recalls verbatim, retries idempotently,
 * and reports changed and missing files instead of recreating them.
 */

import { rm } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createMemoryReceiptStore, ProjectMemoryService } from '../src/index.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('cold recovery over the real Vault', () => {
  it('recalls restored receipts and keeps append retries idempotent after restart', async () => {
    const h = await makeHarness()
    try {
      const observation = await h.service.append(appendRequest())
      const preference = await h.service.append(appendRequest({
        scope: 'user',
        sourceRef: 'session-alpha#event-2',
        kind: 'preference',
        assertionStatus: 'confirmed',
        humanConfirmation: 'user-message-42',
        body: 'The user prefers pnpm over npm on this machine',
      }))
      expect(h.committedReceipts).toHaveLength(2)

      // Restart: the host rehydrates the receipts from the session log and
      // builds a fresh service over the same Vault root.
      const restarted = new ProjectMemoryService(h.spec, createMemoryReceiptStore(h.committedReceipts))
      const projectHits = await restarted.search({ scope: 'project', query: 'deploy' })
      expect(projectHits.hits).toHaveLength(1)
      expect(projectHits.hits[0]?.noteId).toBe(observation.noteId)
      const userHits = await restarted.search({ scope: 'user', query: 'pnpm' })
      expect(userHits.hits).toHaveLength(1)
      expect(userHits.hits[0]?.noteId).toBe(preference.noteId)

      const read = await restarted.read({ scope: 'project', noteId: observation.noteId })
      expect(read).toMatchObject({ status: 'found', verified: true })

      // Retries stay idempotent against the restored receipts.
      expect(await restarted.append(appendRequest())).toMatchObject({ status: 'already_exists' })
    } finally {
      await h.dispose()
    }
  })

  it('reports missing externally deleted notes after restart instead of recreating them', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest())
      await rm(join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${appended.noteId}.md`))

      const restarted = new ProjectMemoryService(h.spec, createMemoryReceiptStore(h.committedReceipts))
      expect(await restarted.append(appendRequest())).toMatchObject({ status: 'memory_missing' })
      expect(await restarted.read({ scope: 'project', noteId: appended.noteId })).toMatchObject({ status: 'memory_missing' })
    } finally {
      await h.dispose()
    }
  })
})
