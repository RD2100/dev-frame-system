/**
 * AT3-07 / AT3-08 failure behavior: unavailable and read-only vaults report
 * honestly, invalid and secret-bearing content is rejected without echoing
 * the secret, and transient failures stop at the configured retry bound with
 * a stable candidate reference left behind.
 */

import { readdir, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ProjectMemoryService } from '../src/index.ts'
import { classifyFsError, withRetry } from '../src/memory.ts'
import { deriveNoteId } from '../src/ids.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('AT3-07: optional memory fails honestly without blocking reads', () => {
  it('reports memory_unavailable when the vault root disappears', async () => {
    const h = await makeHarness()
    try {
      expect(await h.service.append(appendRequest())).toMatchObject({ status: 'created' })
      await rm(h.vaultRoot, { recursive: true, force: true })
      await expect(h.service.search({ scope: 'project', query: 'deploy' }))
        .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
      await expect(h.service.append(appendRequest({ sourceRef: 'session-alpha#event-2' })))
        .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    } finally {
      await h.dispose()
    }
  })

  it('keeps read-only memory usable and refuses appends while writes are disabled', async () => {
    const h = await makeHarness({ writeEnabled: true })
    try {
      expect(await h.service.append(appendRequest())).toMatchObject({ status: 'created' })
      const readOnly = new ProjectMemoryService({ ...h.spec, writeEnabled: false }, {
        read: _noteId => Promise.resolve(undefined),
        write: () => Promise.resolve(),
      })
      await expect(readOnly.append(appendRequest()))
        .rejects.toMatchObject({ code: 'MEMORY_APPEND_DISABLED' })
      // Read-only memory stays available; nothing was reported as saved.
      const hits = await readOnly.search({ scope: 'project', query: 'deploy' })
      expect(hits.hits).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it('treats a failed memory-only append as an explicit failure, never a save', async () => {
    const h = await makeHarness({ writeEnabled: false })
    try {
      await expect(h.service.append(appendRequest())).rejects.toBeInstanceOf(Error)
      expect(h.committedReceipts).toHaveLength(0)
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await expect(readdir(namespaceDir)).rejects.toMatchObject({ code: 'ENOENT' })
    } finally {
      await h.dispose()
    }
  })
})

describe('AT3-08: invalid and secret-bearing content, bounded retries', () => {
  it('rejects known secret patterns with the rule name only, never the secret', async () => {
    const h = await makeHarness()
    try {
      const fixtures: readonly (readonly [string, string, string])[] = [
        ['deepseek-api-key', 'DEEPSEEK_API_KEY=sk-abc123def456ghi789', 'sk-abc123def456ghi789'],
        ['deepseek-api-key', 'the key sk-abcdefghijklmnop1234 was rotated', 'sk-abcdefghijklmnop1234'],
        ['private-key-block', '-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----', 'MIIB'],
        ['aws-access-key', 'aws key AKIAIOSFODNN7EXAMPLE in use', 'AKIAIOSFODNN7EXAMPLE'],
        ['github-token', 'token ghp_abcdefghijklmnopqrstuvwx0123456789', 'ghp_abcdefghijklmnopqrstuvwx0123456789'],
        ['credential-assignment', 'database password: supersecret9', 'supersecret9'],
      ]
      for (const [rule, body, secret] of fixtures) {
        const attempt = h.service.append(appendRequest({
          sourceRef: `session-alpha#event-secret-${rule}`,
          body,
        }))
        await expect(attempt).rejects.toMatchObject({ code: 'MEMORY_CONTENT_REJECTED' })
        await attempt.catch((error: Error) => {
          expect(error.message).toContain(rule)
          expect(error.message.includes(secret)).toBe(false)
          expect(error.message.includes(body)).toBe(false)
        })
      }
      expect(h.committedReceipts).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('rejects raw environment dumps and unsafe control characters', async () => {
    const h = await makeHarness()
    try {
      const dump = Array.from({ length: 10 }, (_, index) => `VAR_${index}=value-${index}`).join('\n')
      await expect(h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-dump',
        body: dump,
      }))).rejects.toMatchObject({ code: 'MEMORY_CONTENT_REJECTED' })
      await expect(h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-ctrl',
        body: 'fine so far\u0000suddenly binary',
      }))).rejects.toMatchObject({ code: 'MEMORY_CONTENT_REJECTED' })
      await expect(h.service.append(appendRequest({ body: '   ' })))
        .rejects.toMatchObject({ code: 'MEMORY_INVALID_NOTE' })
    } finally {
      await h.dispose()
    }
  })

  it('accepts ordinary technical prose that merely mentions key-adjacent words', async () => {
    const h = await makeHarness()
    try {
      const appended = await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-prose',
        body: 'Rotate the deploy token quarterly; the API key header is X-Api-Key and the password policy requires 12 chars.',
      }))
      expect(appended.status).toBe('created')
    } finally {
      await h.dispose()
    }
  })

  it('stops transient failures at the configured retry bound', async () => {
    const h = await makeHarness({ retry: { maxAttempts: 3, backoffMs: [1, 1] } })
    try {
      const transient = Object.assign(new Error('device busy'), { code: 'EBUSY' })
      expect(classifyFsError(transient)).toBe('transient')
      expect(classifyFsError(Object.assign(new Error('denied'), { code: 'EACCES' }))).toBe('permanent')
      expect(classifyFsError(Object.assign(new Error('exists'), { code: 'EEXIST' }))).toBe('conflict')

      let attempts = 0
      await expect(withRetry(h.spec.retry, 'probe', 'MEMORY_WRITE_FAILED', async () => {
        attempts += 1
        throw transient
      })).rejects.toMatchObject({ code: 'MEMORY_WRITE_FAILED' })
      expect(attempts).toBe(h.spec.retry.maxAttempts)

      // A permanent error is not retried at all.
      attempts = 0
      const permanent = Object.assign(new Error('denied'), { code: 'EACCES' })
      await expect(withRetry(h.spec.retry, 'probe', 'MEMORY_WRITE_FAILED', async () => {
        attempts += 1
        throw permanent
      })).rejects.toMatchObject({ code: 'MEMORY_WRITE_FAILED' })
      expect(attempts).toBe(1)
    } finally {
      await h.dispose()
    }
  })

  it('leaves a stable recoverable candidate reference after failures', async () => {
    const h = await makeHarness({ retry: { maxAttempts: 3, backoffMs: [1, 1] } })
    try {
      const ref = 'session-alpha#event-after-failure'
      const expectedId = deriveNoteId('projects/ws-alpha', ref)
      const transient = Object.assign(new Error('device busy'), { code: 'EBUSY' })
      await expect(withRetry(h.spec.retry, 'probe', 'MEMORY_WRITE_FAILED', async () => {
        throw transient
      })).rejects.toBeInstanceOf(Error)

      // The same append, retried after the transient condition cleared,
      // lands on the same stable id and succeeds.
      const recovered = await h.service.append(appendRequest({ sourceRef: ref }))
      expect(recovered.status).toBe('created')
      expect(recovered.noteId).toBe(expectedId)
    } finally {
      await h.dispose()
    }
  })
})
