/**
 * AT3-03 / AT3-09 append behavior: concurrency idempotency, retry with
 * matching and conflicting content, interruption during write, and the
 * external-edit / move / delete handling around committed receipts.
 */

import { readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createMemoryReceiptStore, ProjectMemoryService } from '../src/index.ts'
import { deriveNoteId } from '../src/ids.ts'
import { digestTag } from '../src/notes.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('AT3-03: concurrent and retried appends create at most one note', () => {
  it('lets concurrent appends of one source event produce one complete note', async () => {
    const h = await makeHarness()
    try {
      const results = await Promise.all(Array.from({ length: 8 }, () => h.service.append(appendRequest())))
      const created = results.filter(result => result.status === 'created')
      const existing = results.filter(result => result.status === 'already_exists')
      expect(created).toHaveLength(1)
      expect(existing).toHaveLength(7)
      expect(new Set(results.map(result => result.noteId)).size).toBe(1)
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      const files = await readdir(namespaceDir)
      expect(files.filter(name => name.endsWith('.md'))).toHaveLength(1)
      // Every committed receipt — one from the winner, plus idempotent
      // re-commits from losers that confirmed the same file — describes the
      // one complete note.
      expect(new Set(h.committedReceipts.map(receipt => receipt.noteId)).size).toBe(1)
      expect(new Set(h.committedReceipts.map(receipt => receipt.digest)).size).toBe(1)
    } finally {
      await h.dispose()
    }
  })

  it('returns already_exists for a matching retry and memory_conflict for different content', async () => {
    const h = await makeHarness()
    try {
      const first = await h.service.append(appendRequest())
      expect(first.status).toBe('created')
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      const filePath = join(namespaceDir, `${first.noteId}.md`)
      const before = await readFile(filePath, 'utf8')

      const retry = await h.service.append(appendRequest())
      expect(retry.status).toBe('already_exists')
      expect(await readFile(filePath, 'utf8')).toBe(before)

      const conflicting = await h.service.append(appendRequest({
        body: 'The deploy script actually lives elsewhere entirely',
      }))
      expect(conflicting.status).toBe('memory_conflict')
      // Neither version was modified by the conflict.
      expect(await readFile(filePath, 'utf8')).toBe(before)
      expect(h.committedReceipts).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it('reports incomplete_note and preserves a file interrupted mid-write', async () => {
    const h = await makeHarness()
    try {
      await h.service.append(appendRequest({ sourceRef: 'session-alpha#event-seed' }))
      const receiptsBefore = h.committedReceipts.length
      // Simulate a crash during the write of a second note: a partial file
      // exists at its derived path, with no receipt for it.
      const partialRef = 'session-alpha#event-partial'
      const noteId = deriveNoteId('projects/ws-alpha', partialRef)
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      const partialPath = join(namespaceDir, `${noteId}.md`)
      const partial = `---\nschema: 1\nnoteId: ${noteId}\nnamespace: projects/ws-`
      await writeFile(partialPath, partial, 'utf8')

      const result = await h.service.append(appendRequest({ sourceRef: partialRef }))
      expect(result.status).toBe('incomplete_note')
      expect(await readFile(partialPath, 'utf8')).toBe(partial)
      expect(h.committedReceipts).toHaveLength(receiptsBefore)
    } finally {
      await h.dispose()
    }
  })

  it('confirms complete unreceipted matching content by the original append retry', async () => {
    const h = await makeHarness()
    try {
      // Crash after flush and close but before the receipt was committed:
      // a complete note file exists with no receipt behind it.
      const first = await h.service.append(appendRequest())
      expect(first.status).toBe('created')
      h.committedReceipts.length = 0
      const restored = new ProjectMemoryService(h.spec, createMemoryReceiptStore())
      const retry = await restored.append(appendRequest())
      expect(retry.status).toBe('already_exists')
      expect(h.committedReceipts).toHaveLength(0)
      // The retry itself commits the missing receipt.
      expect(await restored.read({ scope: 'project', noteId: first.noteId }))
        .toMatchObject({ status: 'found', verified: true })
    } finally {
      await h.dispose()
    }
  })
})

describe('AT3-09: external edits, moves, and deletions around receipts', () => {
  it('reports memory_changed for an edited body and keeps the file', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest())
      const filePath = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${appended.noteId}.md`)
      const original = await readFile(filePath, 'utf8')
      const edited = original.replace('scripts/deploy.ps1', 'scripts/actually-deploy.ps1')
      await writeFile(filePath, edited, 'utf8')

      const retry = await h.service.append(appendRequest())
      expect(retry.status).toBe('memory_changed')
      expect(await readFile(filePath, 'utf8')).toBe(edited)

      const read = await h.service.read({ scope: 'project', noteId: appended.noteId })
      expect(read.status).toBe('memory_changed')
      // The edited note is excluded from automatic confirmed recall.
      const hits = await h.service.search({ scope: 'project', query: 'deploy' })
      expect(hits.hits).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('does not let an edited inline digest replace the session receipt', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest())
      const filePath = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${appended.noteId}.md`)
      const original = await readFile(filePath, 'utf8')
      // The user edits the body and coherently edits the front-matter digest:
      // the file is now self-consistent, but the full-file digest still
      // disagrees with the committed session receipt.
      const closing = original.indexOf('\n---\n', 4)
      const head = original.slice(0, closing + 5)
      const body = original.slice(closing + 6)
      const editedBody = body.replace('scripts/deploy.ps1', 'scripts/actually-deploy.ps1')
      const forged = head.replace(/bodyDigest: sha256:[0-9a-f]{64}/, `bodyDigest: ${digestTag(editedBody)}`) + editedBody
      await writeFile(filePath, forged, 'utf8')

      const read = await h.service.read({ scope: 'project', noteId: appended.noteId })
      expect(read.status).toBe('memory_changed')
      const retry = await h.service.append(appendRequest())
      expect(retry.status).toBe('memory_changed')
    } finally {
      await h.dispose()
    }
  })

  it('reports memory_missing at the recorded path and never recreates', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest())
      await rm(join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${appended.noteId}.md`))
      const retry = await h.service.append(appendRequest())
      expect(retry.status).toBe('memory_missing')
      expect(retry.relativePath).toBe(h.committedReceipts[0]?.relativePath)
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      expect(await readdir(namespaceDir)).toHaveLength(0)

      // A file hand-moved elsewhere in the namespace is not chased back.
      await writeFile(join(namespaceDir, 'renamed-by-user.md'), 'hand-moved content', 'utf8')
      const renamed = await h.service.read({ scope: 'project', noteId: appended.noteId })
      expect(renamed.status).toBe('memory_missing')
    } finally {
      await h.dispose()
    }
  })

  it('creates a sourced superseding note on explicit correction and preserves the old one', async () => {
    const h = await makeHarness()
    try {
      const old = await h.service.append(appendRequest())
      const filePath = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${old.noteId}.md`)
      const before = await readFile(filePath, 'utf8')
      const correction = await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-correction',
        body: 'Correction: the deploy script lives in scripts/actually-deploy.ps1',
        supersedes: old.noteId,
      }))
      expect(correction.status).toBe('created')
      // Append-only supersession: the old file byte-identical, still readable.
      expect(await readFile(filePath, 'utf8')).toBe(before)
      const oldRead = await h.service.read({ scope: 'project', noteId: old.noteId })
      expect(oldRead.status).toBe('found')
      // Recall now surfaces only the correction.
      const hits = await h.service.search({ scope: 'project', query: 'deploy' })
      expect(hits.hits).toHaveLength(1)
      expect(hits.hits[0]?.noteId).toBe(correction.noteId)
    } finally {
      await h.dispose()
    }
  })
})

describe('entity anchoring', () => {
  it('persists canonicalized tags and auto-carries the workspace entity on project notes', async () => {
    const h = await makeHarness()
    try {
      const created = await h.service.append(appendRequest({
        entities: ['  Deploy Scripts ', 'deploy scripts', 'release'],
      }))
      expect(created.status).toBe('created')
      const contents = await readFile(
        join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha', `${created.noteId}.md`),
        'utf8',
      )
      expect(contents).toContain('entities: ws-alpha, deploy scripts, release')
    } finally {
      await h.dispose()
    }
  })

  it('filters search by an entity tag and carries tags on hits', async () => {
    const h = await makeHarness()
    try {
      await h.service.append(appendRequest({ sourceRef: 'session-alpha#e1', entities: ['release'] }))
      await h.service.append(appendRequest({
        sourceRef: 'session-alpha#e2',
        body: 'The test suite lives in tests/',
        entities: ['testing'],
      }))
      const filtered = await h.service.search({ scope: 'project', query: 'lives in', entity: '  Testing ' })
      expect(filtered.hits).toHaveLength(1)
      expect(filtered.hits[0]?.entities).toEqual(['ws-alpha', 'testing'])
      const unfiltered = await h.service.search({ scope: 'project', query: 'lives in' })
      expect(unfiltered.hits).toHaveLength(2)
    } finally {
      await h.dispose()
    }
  })

  it('rejects unsafe entity tags and honors the per-note cap', async () => {
    const h = await makeHarness()
    try {
      await expect(h.service.append(appendRequest({ entities: ['sk-abcdefghijklmnop1234'] })))
        .rejects.toThrow(/content screening/u)
      await expect(h.service.append(appendRequest({ entities: ['../escape'] })))
        .rejects.toThrow(/safe single subject/u)
      await expect(h.service.append(appendRequest({
        entities: Array.from({ length: 9 }, (_, index) => `tag ${String(index)}`),
      }))).rejects.toThrow(/at most 8 entity tags/u)
    } finally {
      await h.dispose()
    }
  })
})
