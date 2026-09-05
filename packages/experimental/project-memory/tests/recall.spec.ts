/**
 * AT3-01 / AT3-02 recall behavior: fresh-session recall with provenance and
 * project isolation, and byte/result/candidate limits over Chinese and mixed
 * UTF-8 notes.
 */

import { readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ProjectMemoryService } from '../src/index.ts'
import { deriveNoteId } from '../src/ids.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('AT3-01: fresh-session recall with provenance and isolation', () => {
  it('recalls the allowed project fact and confirmed user preference with provenance', async () => {
    const h = await makeHarness()
    try {
      const observation = await h.service.append(appendRequest())
      expect(observation.status).toBe('created')
      const preference = await h.service.append(appendRequest({
        scope: 'user',
        sourceRef: 'session-alpha#event-2',
        kind: 'preference',
        assertionStatus: 'confirmed',
        humanConfirmation: 'user-message-42',
        body: 'The user prefers pnpm over npm on this machine',
      }))
      expect(preference.status).toBe('created')

      // A fresh service instance, carrying no conversation context, recalls
      // the stored notes with identity, provenance, and freshness labels.
      const fresh = new ProjectMemoryService(h.spec, {
        read: () => Promise.resolve(undefined),
        write: () => Promise.resolve(undefined),
      })
      const projectHits = await fresh.search({ scope: 'project', query: 'deploy script' })
      expect(projectHits.hits).toHaveLength(1)
      const fact = projectHits.hits[0]
      expect(fact?.noteId).toBe(observation.noteId)
      expect(fact?.kind).toBe('fact')
      expect(fact?.status).toBe('observed')
      expect(fact?.source).toBe('session-alpha#event-1')
      expect(fact?.freshness).toBe('current')
      expect(fact?.excerpt).toContain('deploy')

      const userHits = await fresh.search({ scope: 'user', query: 'pnpm' })
      expect(userHits.hits).toHaveLength(1)
      expect(userHits.hits[0]?.status).toBe('confirmed')
      expect(userHits.hits[0]?.kind).toBe('preference')
    } finally {
      await h.dispose()
    }
  })

  it('never recalls another project private note', async () => {
    const h = await makeHarness()
    try {
      const private_ = await h.service.append(appendRequest({ body: 'Alpha staging URL is staging.alpha.example' }))
      expect(private_.status).toBe('created')

      // A different workspace identity over the same Vault sees nothing in
      // its own namespace, and cannot read the other project's note id.
      const beta = new ProjectMemoryService({ ...h.spec, workspaceId: 'ws-beta' }, {
        read: () => Promise.resolve(undefined),
        write: () => Promise.resolve(undefined),
      })
      const hits = await beta.search({ scope: 'project', query: 'staging' })
      expect(hits.hits).toHaveLength(0)
      expect(hits.coverageComplete).toBe(true)
      const read = await beta.read({ scope: 'project', noteId: private_.noteId })
      expect(read.status).toBe('memory_missing')
    } finally {
      await h.dispose()
    }
  })
})

describe('AT3-02: UTF-8 notes and byte/result/candidate limits', () => {
  it('stores and recalls Chinese and mixed UTF-8 bodies with intact characters', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-cjk',
        body: '部署脚本位于 scripts/deploy.ps1，注意 UTF-8 字节边界 😃',
      }))
      expect(appended.status).toBe('created')
      const hits = await h.service.search({ scope: 'project', query: '部署脚本' })
      expect(hits.hits).toHaveLength(1)
      const excerpt = hits.hits[0]?.excerpt ?? ''
      expect(excerpt).toContain('部署脚本')
      // Re-encoding the excerpt must round-trip: no split surrogate or
      // multi-byte sequence, so no replacement characters appear.
      expect(new TextDecoder('utf-8').decode(new TextEncoder().encode(excerpt))).toBe(excerpt)
      expect(excerpt.includes('\uFFFD')).toBe(false)
    } finally {
      await h.dispose()
    }
  })

  it('counts UTF-8 bytes, not characters, for the note limit', async () => {
    const h = await makeHarness()
    try {
      // 2730 CJK chars = 8190 UTF-8 bytes: fits. One more char overflows.
      const fits = await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-fit',
        body: 'あ'.repeat(2730),
      }))
      expect(fits.status).toBe('created')
      await expect(h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-overflow',
        body: 'あ'.repeat(2731),
      }))).rejects.toMatchObject({ code: 'MEMORY_NOTE_TOO_LARGE' })
      // 8000 ASCII chars = 8000 bytes also fits while being more characters
      // than the rejected CJK body.
      const ascii = await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-ascii',
        body: 'a'.repeat(8000),
      }))
      expect(ascii.status).toBe('created')
    } finally {
      await h.dispose()
    }
  })

  it('keeps result counts and total return bytes within the configured bounds', async () => {
    const h = await makeHarness({ limits: { maxReturnBytes: 2500, maxExcerptBytes: 96 } })
    try {
      for (let index = 0; index < 12; index += 1) {
        const appended = await h.service.append(appendRequest({
          sourceRef: `session-alpha#event-${index}`,
          body: `Runbook entry ${index}: kicker word with padding text to widen the serialized hit.`,
        }))
        expect(appended.status).toBe('created')
      }
      const capped = await h.service.search({ scope: 'project', query: 'kicker', limit: 5 })
      expect(capped.hits).toHaveLength(5)
      expect(capped.truncated).toBe(true)
      expect(capped.coverageComplete).toBe(true)

      const byteCapped = await h.service.search({ scope: 'project', query: 'kicker' })
      expect(byteCapped.hits.length).toBeLessThan(12)
      expect(byteCapped.truncated).toBe(true)
      let totalBytes = 0
      for (const hit of byteCapped.hits) totalBytes += Buffer.byteLength(JSON.stringify(hit), 'utf8')
      expect(totalBytes).toBeLessThanOrEqual(2500)
    } finally {
      await h.dispose()
    }
  })

  it('reports partial coverage explicitly when the candidate cap is reached', async () => {
    const h = await makeHarness({ limits: { maxCandidateFiles: 3 } })
    try {
      const refs = ['session-alpha#event-0', 'session-alpha#event-1', 'session-alpha#event-2', 'session-alpha#event-3']
      for (const [index, ref] of refs.entries()) {
        const appended = await h.service.append(appendRequest({
          sourceRef: ref,
          body: `probe-${index} with common deploy pipeline context.`,
        }))
        expect(appended.status).toBe('created')
      }
      // Note file order is the derived-id hash order, so map the scan window
      // deterministically: probe-<fourth> lands beyond the candidate cap.
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      const files = (await readdir(namespaceDir)).filter(name => name.endsWith('.md')).sort((a, b) => a.localeCompare(b))
      const fourthId = files[3]?.replace(/\.md$/, '')
      const fourthIndex = fourthId === undefined
        ? -1
        : refs.findIndex(ref => deriveNoteId('projects/ws-alpha', ref) === fourthId)
      expect(fourthIndex).toBeGreaterThanOrEqual(0)

      const beyondCap = await h.service.search({ scope: 'project', query: `probe-${fourthIndex}` })
      // The match sits beyond the candidate cap: no hits, but the service
      // must not claim that no matching knowledge exists anywhere.
      expect(beyondCap.hits).toHaveLength(0)
      expect(beyondCap.coverageComplete).toBe(false)
      expect(beyondCap.truncated).toBe(false)

      const firstIndex = (fourthIndex + 1) % 4
      const withinCap = await h.service.search({ scope: 'project', query: `probe-${firstIndex}` })
      // The in-window note is recallable, but the scan itself stayed partial.
      expect(withinCap.hits).toHaveLength(1)
      expect(withinCap.coverageComplete).toBe(false)
    } finally {
      await h.dispose()
    }
  })

  it('rejects oversized and empty queries with explicit codes', async () => {
    const h = await makeHarness({ limits: { maxQueryBytes: 32 } })
    try {
      await expect(h.service.search({ scope: 'project', query: 'あ'.repeat(11) }))
        .rejects.toMatchObject({ code: 'MEMORY_QUERY_TOO_LARGE' })
      await expect(h.service.search({ scope: 'project', query: '' }))
        .rejects.toMatchObject({ code: 'MEMORY_INVALID_REQUEST' })
      await expect(h.service.search({ scope: 'project', query: 'deploy', limit: 11 }))
        .rejects.toMatchObject({ code: 'MEMORY_INVALID_REQUEST' })
    } finally {
      await h.dispose()
    }
  })

  it('truncates excerpts only at valid character boundaries', async () => {
    const h = await makeHarness({ limits: { maxExcerptBytes: 40 } })
    try {
      await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-wide',
        body: `prefix padding ${'あ'.repeat(30)} emoji-😃-suffix trigger deploy`,
      }))
      const hits = await h.service.search({ scope: 'project', query: 'deploy' })
      expect(hits.hits).toHaveLength(1)
      const excerpt = hits.hits[0]?.excerpt ?? ''
      expect(Buffer.byteLength(excerpt, 'utf8')).toBeLessThanOrEqual(40)
      expect(new TextDecoder('utf-8').decode(new TextEncoder().encode(excerpt))).toBe(excerpt)
    } finally {
      await h.dispose()
    }
  })
})
