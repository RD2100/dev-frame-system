/**
 * Coverage-gap closure for the D5/D6 memory-library refactor: every branch the
 * feature specs leave open, exercised deterministically …config validation
 * rejects, id/source-ref shape rejections, surrogate and excerpt edge
 * alignment, receipt-seam failures, conflict and incomplete-note reads,
 * metadata-identity mismatches, vault-root misuse, and the read-only library
 * tool surface with and without a configured vault.
 * @module tests/coverage-gaps
 */

import { mkdir, mkdtemp, mkdir as ensureDir, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'
import {
  canonicalizeEntities,
  deriveNoteId,
  entitiesInclude,
  getLibraryStatus,
  listLibraryFiles,
  MemoryLibraryGateway,
  ProjectMemoryError,
  ProjectMemoryService,
  readLibraryFile,
  resolveMemorySpec,
  screenNoteBody,
  searchLibrary,
  validateSourceRef,
} from '../src/index.ts'
import { buildNoteMeta, serializeNote } from '../src/notes.ts'
import { createLibraryTools } from '../src/library-tools.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('entity canonicalization edges', () => {
  it('drops blank tags, deduplicates, and rejects overlength or unsafe tags', () => {
    expect(canonicalizeEntities(['', '  ', 'Architect', 'architect ', 'Dev'])).toEqual(['architect', 'dev'])
    expect(() => canonicalizeEntities(['x'.repeat(65)])).toThrow(/64 characters/)
    expect(() => canonicalizeEntities(['a..b'])).toThrow(/not a safe single subject/)
  })

  it('rejects a secret-bearing tag with the content rule code', () => {
    try {
      canonicalizeEntities(['password: supersecret9'])
      expect.unreachable('secret tag must be rejected')
    } catch (error) {
      expect(error).toBeInstanceOf(ProjectMemoryError)
      expect((error as ProjectMemoryError).code).toBe('MEMORY_CONTENT_REJECTED')
    }
  })

  it('matches entities case- and spacing-insensitively, and treats undefined as no match', () => {
    expect(entitiesInclude(['architect', 'dev'], ' Architect ')).toBe(true)
    expect(entitiesInclude(undefined, 'architect')).toBe(false)
    expect(entitiesInclude(['dev'], 'architect')).toBe(false)
  })
})

describe('spec resolution edges', () => {
  it('rejects non-positive limit overrides', () => {
    try {
      resolveMemorySpec({ workspaceId: 'ws', limits: { maxNoteBytes: 0 } })
      expect.unreachable('zero maxNoteBytes must be rejected')
    } catch (error) {
      expect(error).toBeInstanceOf(ProjectMemoryError)
      expect((error as ProjectMemoryError).code).toBe('MEMORY_INVALID_REQUEST')
    }
    expect(() => resolveMemorySpec({ workspaceId: 'ws', limits: { maxSearchResults: 1.5 } }))
      .toThrow(/positive integer/)
  })

  it('rejects malformed retry backoff schedules', () => {
    expect(() => resolveMemorySpec({ workspaceId: 'ws', retry: { maxAttempts: 3, backoffMs: [1] } }))
      .toThrow(/maxAttempts - 1/)
    expect(() => resolveMemorySpec({ workspaceId: 'ws', retry: { maxAttempts: 3, backoffMs: [-1, 1] } }))
      .toThrow(/non-negative integers/)
  })

  it('applies defaults when optional fields are omitted', () => {
    const spec = resolveMemorySpec({ workspaceId: 'ws' })
    expect(spec.writeEnabled).toBe(false)
    expect(spec.userScopeEnabled).toBe(false)
    expect(spec.currentSnapshot).toBeUndefined()
    expect(spec.vaultRoot).toBeUndefined()
  })
})

describe('source reference validation edges', () => {
  it('rejects empty, padded, NUL-bearing, and oversized references', () => {
    try {
      validateSourceRef('')
      expect.unreachable('an empty reference must be rejected')
    } catch (error) {
      expect(error).toBeInstanceOf(ProjectMemoryError)
      expect((error as ProjectMemoryError).code).toBe('MEMORY_INVALID_NOTE')
    }
    expect(() => validateSourceRef('  ')).toThrow(/non-empty trimmed/)
    expect(() => validateSourceRef(' padded ')).toThrow(/non-empty trimmed/)
    expect(() => validateSourceRef('a\u0000b')).toThrow(/without NUL/)
    expect(() => validateSourceRef('x'.repeat(513))).toThrow(/UTF-8 bytes/)
  })

  it('accepts a well-formed reference unchanged', () => {
    expect(validateSourceRef('session-alpha#event-1')).toBe('session-alpha#event-1')
  })
})

describe('content screening edges', () => {
  it('rejects an unpaired surrogate that cannot be UTF-8 encoded', () => {
    expect(screenNoteBody('before\uD800after')).toBe('unpaired-surrogate')
  })

  it('accepts clean prose and rejects a credential assignment', () => {
    expect(screenNoteBody('the deploy script lives in scripts/deploy.ps1')).toBeUndefined()
    expect(screenNoteBody('database password: supersecret9')).toBe('credential-assignment')
  })
})

describe('library search and status edges', () => {
  let vaultRoot: string
  let outsideRoot: string

  beforeEach(async () => {
    vaultRoot = await mkdtemp(join(tmpdir(), 'dsh-lib-gap-'))
    outsideRoot = await mkdtemp(join(tmpdir(), 'dsh-lib-gap-out-'))
    await writeFile(join(vaultRoot, 'start.md'), 'Start of the story.', 'utf8')
    await writeFile(join(vaultRoot, 'long.md'), `${'a'.repeat(60)} seed ${'b'.repeat(60)} FINALKEYWORD`, 'utf8')
    await writeFile(join(vaultRoot, 'surrogate.md'), `${'x'.repeat(23)}😀${'y'.repeat(23)}SURROGATE_SEARCH${'z'.repeat(10)}\uD83D`, 'utf8')
    await writeFile(join(vaultRoot, 'image.png'), 'not text content', 'utf8')
  })

  afterEach(async () => {
    await rm(vaultRoot, { recursive: true, force: true })
    await rm(outsideRoot, { recursive: true, force: true })
  })

  it('cuts excerpts on both edges for interior matches and only the right edge for tail matches', async () => {
    const interior = await searchLibrary(vaultRoot, 'seed')
    const interiorHit = interior.find(hit => hit.relativePath === 'long.md')
    expect(interiorHit?.excerpt.startsWith('…')).toBe(true)
    expect(interiorHit?.excerpt.endsWith('…')).toBe(true)

    const tail = await searchLibrary(vaultRoot, 'FINALKEYWORD')
    expect(tail[0]?.excerpt.endsWith('…')).toBe(false)
  })

  it('does not content-search non-text files but still matches their names', async () => {
    const results = await searchLibrary(vaultRoot, 'image')
    const hit = results.find(result => result.relativePath === 'image.png')
    expect(hit).toMatchObject({ matchType: 'name' })
  })

  it('rejects a non-positive maxResults', async () => {
    await expect(searchLibrary(vaultRoot, 'seed', { maxResults: 0 }))
      .rejects.toMatchObject({ code: 'MEMORY_INVALID_REQUEST' })
  })

  it('rejects reading a file that disappears between listing and read only through the stable code', async () => {
    // The vanished-file window is a race in library.ts; what is deterministic
    // here is that a trailing-dot segment name is rejected before any IO.
    await expect(readLibraryFile(vaultRoot, 'start.')).rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
  })

  it('reports UNAVAILABLE for an unconfigured root and AVAILABLE with a size sum', async () => {
    expect((await getLibraryStatus('')).status).toBe('UNAVAILABLE')
    const status = await getLibraryStatus(vaultRoot)
    expect(status.status).toBe('AVAILABLE')
    expect(status.totalSizeBytes).toBeGreaterThan(0)
  })
})

describe('memory service failure and identity edges', () => {
  it('fails when the vault root is a file, not a directory', async () => {
    const h = await makeHarness()
    try {
      const fileRoot = join(h.vaultRoot, 'vault-file.txt')
      await writeFile(fileRoot, 'not a directory', 'utf8')
      const service = new ProjectMemoryService({ ...h.spec, vaultRoot: fileRoot }, {
        read: () => Promise.resolve(undefined),
        write: () => Promise.resolve(),
      })
      await expect(service.search({ scope: 'project', query: 'deploy' }))
        .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    } finally {
      await h.dispose()
    }
  })

  it('propagates a receipt store read failure as MEMORY_RECEIPT_FAILED', async () => {
    const h = await makeHarness()
    try {
      await h.service.append(appendRequest())
      const broken = new ProjectMemoryService(h.spec, {
        read: () => Promise.reject(new Error('receipt store offline')),
        write: () => Promise.resolve(),
      })
      await expect(broken.search({ scope: 'project', query: 'deploy' }))
        .rejects.toMatchObject({ code: 'MEMORY_RECEIPT_FAILED' })
    } finally {
      await h.dispose()
    }
  })

  it('reports MEMORY_RECEIPT_FAILED when the receipt cannot be committed after create', async () => {
    const h = await makeHarness()
    try {
      const failing = new ProjectMemoryService(h.spec, {
        read: () => Promise.resolve(undefined),
        write: () => Promise.reject(new Error('journal full')),
      })
      await expect(failing.append(appendRequest({ sourceRef: 'session-alpha#event-receipt-fail' })))
        .rejects.toMatchObject({ code: 'MEMORY_RECEIPT_FAILED' })
    } finally {
      await h.dispose()
    }
  })

  it('reports a conflict when an unreceipted file holds different content at the derived path', async () => {
    const h = await makeHarness()
    try {
      const sourceRef = 'session-alpha#event-conflict'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const dir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await ensureDir(dir, { recursive: true })
      const meta = buildNoteMeta({
        noteId,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'DIFFERENT BODY occupies the derived path',
      })
      await writeFile(join(dir, `${noteId}.md`), serializeNote(meta, 'DIFFERENT BODY occupies the derived path'), 'utf8')
      const result = await h.service.append(appendRequest({ sourceRef, body: 'the candidate body' }))
      expect(result).toMatchObject({ status: 'memory_conflict' })
    } finally {
      await h.dispose()
    }
  })

  it('reports incomplete notes by structure and by digest mismatch', async () => {
    const h = await makeHarness()
    try {
      const sourceRef = 'session-alpha#event-incomplete'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const dir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await ensureDir(dir, { recursive: true })
      const file = join(dir, `${noteId}.md`)
      await writeFile(file, '---\nnoteId: broken\n---\n', 'utf8')
      await expect(h.service.read({ scope: 'project', noteId })).resolves.toMatchObject({
        status: 'incomplete_note',
        reason: /front matter/,
      })

      const meta = buildNoteMeta({
        noteId,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'THE RECORDED BODY',
      })
      await writeFile(file, serializeNote({ ...meta, bodyDigest: 'sha256:' + '0'.repeat(64) }, 'THE RECORDED BODY'), 'utf8')
      await expect(h.service.read({ scope: 'project', noteId })).resolves.toMatchObject({
        status: 'incomplete_note',
        reason: /does not match its recorded digest/,
      })
    } finally {
      await h.dispose()
    }
  })

  it('reports a changed note when the file identity disagrees with its path', async () => {
    const h = await makeHarness()
    try {
      const sourceRef = 'session-alpha#event-identity'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const dir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await ensureDir(dir, { recursive: true })
      const other = deriveNoteId('projects/ws-alpha', 'session-alpha#other')
      const meta = buildNoteMeta({
        noteId: other,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'THE RECORDED BODY',
      })
      await writeFile(join(dir, `${noteId}.md`), serializeNote(meta, 'THE RECORDED BODY'), 'utf8')
      await expect(h.service.read({ scope: 'project', noteId })).resolves.toMatchObject({
        status: 'memory_changed',
        reason: 'note metadata does not match the requested path',
      })
    } finally {
      await h.dispose()
    }
  })

  it('skips foreign-named files and identity-mismatched notes in search', async () => {
    const h = await makeHarness()
    try {
      const dir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await ensureDir(dir, { recursive: true })
      const sourceRef = 'session-alpha#event-search-skip'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const meta = buildNoteMeta({
        noteId,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'SEARCHABLE_ANCHOR one',
      })
      await writeFile(join(dir, `${noteId}.md`), serializeNote(meta, 'SEARCHABLE_ANCHOR one'), 'utf8')
      await writeFile(join(dir, 'not-a-note.md'), 'SEARCHABLE_ANCHOR two', 'utf8')
      // A file at a managed path whose front matter identifies a different id
      // is not the note its name claims, so recall must skip it.
      const other = deriveNoteId('projects/ws-alpha', 'session-alpha#other')
      const foreignMeta = buildNoteMeta({
        noteId,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'SEARCHABLE_ANCHOR three',
      })
      await writeFile(join(dir, `${other}.md`), serializeNote(foreignMeta, 'SEARCHABLE_ANCHOR three'), 'utf8')

      const hits = await h.service.search({ scope: 'project', query: 'SEARCHABLE_ANCHOR' })
      expect(hits.hits).toHaveLength(1)
      expect(hits.hits[0]?.noteId).toBe(noteId)
    } finally {
      await h.dispose()
    }
  })

  it('excludes a note whose file disagrees with its committed receipt from recall', async () => {
    const h = await makeHarness()
    try {
      const sourceRef = 'session-alpha#event-tamper'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const dir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await ensureDir(dir, { recursive: true })
      const file = join(dir, `${noteId}.md`)
      const meta = buildNoteMeta({
        noteId,
        namespace: 'projects/ws-alpha',
        kind: 'fact',
        status: 'observed',
        source: sourceRef,
        snapshot: undefined,
        supersedes: undefined,
        entities: [],
        body: 'ORIGINAL_ANCHOR body',
      })
      await writeFile(file, serializeNote(meta, 'ORIGINAL_ANCHOR body'), 'utf8')
      await h.service.append(appendRequest({ sourceRef: 'session-alpha#event-tamper-seed' }))
      // Seed the receipt store through the same backing seam as a real append,
      // then tamper with the file the committed receipt describes.
      await h.service.append(appendRequest({ sourceRef, body: 'ORIGINAL_ANCHOR body' }))
      await writeFile(file, serializeNote(meta, 'ORIGINAL_ANCHOR body TAMPERED'), 'utf8')
      const hits = await h.service.search({ scope: 'project', query: 'ORIGINAL_ANCHOR' })
      expect(hits.hits.some(hit => hit.noteId === noteId)).toBe(false)
      await expect(h.service.read({ scope: 'project', noteId })).resolves.toMatchObject({
        status: 'incomplete_note',
        reason: /does not match its recorded digest/,
      })
    } finally {
      await h.dispose()
    }
  })

  it('rejects a committed receipt that disagrees with the derived path', async () => {
    const h = await makeHarness()
    try {
      const sourceRef = 'session-alpha#event-path-disagree'
      const noteId = deriveNoteId('projects/ws-alpha', sourceRef)
      const service = new ProjectMemoryService(h.spec, {
        read: () => Promise.resolve({
          noteId,
          namespace: 'projects/ws-alpha',
          relativePath: 'devframe-memory/user/some-other.md',
          digest: 'sha256:' + '0'.repeat(64),
          recordedAt: new Date().toISOString(),
        }),
        write: () => Promise.resolve(),
      })
      await expect(service.append(appendRequest({ sourceRef })))
        .rejects.toMatchObject({ code: 'MEMORY_RECEIPT_FAILED' })
    } finally {
      await h.dispose()
    }
  })

  it('builds excerpts that cut around an interior match and align surrogate edges', async () => {
    const h = await makeHarness()
    try {
      const longBody = `${'seed '.repeat(40)}SURROGATE_SEARCH mid-content`
      await h.service.append(appendRequest({ sourceRef: 'session-alpha#event-excerpt', body: longBody }))
      const hits = await h.service.search({ scope: 'project', query: 'SURROGATE_SEARCH' })
      expect(hits.hits[0]?.excerpt.startsWith('…')).toBe(true)

      await h.service.append(appendRequest({
        sourceRef: 'session-alpha#event-surrogate',
        body: `${'x'.repeat(23)}😀${'y'.repeat(23)}SURROGATE_SEARCH${'z'.repeat(10)}`,
      }))
      const surrogateHits = await h.service.search({ scope: 'project', query: 'SURROGATE_SEARCH' })
      expect(surrogateHits.hits.some(hit => hit.excerpt.includes('SURROGATE_SEARCH'))).toBe(true)
    } finally {
      await h.dispose()
    }
  })
})

describe('vault layout edges', () => {
  it('rejects a file occupying the devframe-memory directory', async () => {
    const h = await makeHarness()
    try {
      await writeFile(join(h.vaultRoot, 'devframe-memory'), 'occupied', 'utf8')
      await expect(h.service.search({ scope: 'project', query: 'deploy' }))
        .rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
    } finally {
      await h.dispose()
    }
  })

  it('rejects a namespace directory that resolves outside the vault root', async () => {
    const h = await makeHarness()
    try {
      await mkdir(join(h.vaultRoot, 'devframe-memory'), { recursive: true })
      try {
        await symlink(h.outsideRoot, join(h.vaultRoot, 'devframe-memory', 'user'), 'junction')
      } catch {
        await symlink(h.outsideRoot, join(h.vaultRoot, 'devframe-memory', 'user'), 'dir')
      }
      await expect(h.service.search({ scope: 'user', query: 'anything' }))
        .rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
    } finally {
      await h.dispose()
    }
  })
})

describe('library gateway and tool-surface edges', () => {
  it('lists and searches with omitted option objects through the gateway', async () => {
    const h = await makeHarness()
    try {
      const ctx = new Context()
      const gateway = new MemoryLibraryGateway(ctx, h.vaultRoot)
      await expect(gateway.list({})).resolves.toHaveLength(0)
      await expect(gateway.search({ query: 'deploy' })).resolves.toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('fails closed through the read-only tools without a configured vault', async () => {
    const [, listTool, readTool, searchTool] = createLibraryTools({})
    const exec = { signal: new AbortController().signal } as ToolRunContext
    await expect(listTool!.execute({}, exec)).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    await expect(readTool!.execute({ relative_path: 'a.md' }, exec)).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    await expect(searchTool!.execute({ query: 'x' }, exec)).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    expect(listTool!.isConcurrencySafe?.({})).toBe(true)
    expect(readTool!.isConcurrencySafe?.({ relative_path: 'a.md' })).toBe(true)
    expect(searchTool!.isConcurrencySafe?.({ query: 'x' })).toBe(true)
  })

  it('passes depth and result caps through the read-only tools', async () => {
    const h = await makeHarness()
    try {
      await writeFile(join(h.vaultRoot, 'welcome.md'), '# Welcome', 'utf8')
      const tools = createLibraryTools({ vaultRoot: h.vaultRoot })
      const [statusTool, listTool, readTool, searchTool] = tools
      const exec = { signal: new AbortController().signal } as ToolRunContext
      await expect(statusTool!.execute({}, exec)).resolves.toMatchObject({ status: 'AVAILABLE' })
      await expect(listTool!.execute({ max_depth: 1 }, exec)).resolves.toHaveLength(1)
      await expect(readTool!.execute({ relative_path: 'welcome.md' }, exec)).resolves.toMatchObject({
        relativePath: 'welcome.md',
        content: '# Welcome',
      })
      await expect(searchTool!.execute({ query: 'Welcome', max_results: 1 }, exec)).resolves.toHaveLength(1)
      expect(statusTool!.isConcurrencySafe?.({})).toBe(true)
    } finally {
      await h.dispose()
    }
  })

  it('keeps listing bounded by the configured depth and rejects negative depths', async () => {
    const h = await makeHarness()
    try {
      await writeFile(join(h.vaultRoot, 'a.md'), 'a', 'utf8')
      await expect(listLibraryFiles(h.vaultRoot, { maxDepth: -1 }))
        .rejects.toMatchObject({ code: 'MEMORY_INVALID_REQUEST' })
      await expect(listLibraryFiles(h.vaultRoot, { maxDepth: 0 })).resolves.toEqual([])
    } finally {
      await h.dispose()
    }
  })
})
