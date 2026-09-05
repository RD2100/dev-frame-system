/**
 * AT3-04 path-safety probes: traversal and malformed ids, unauthorized
 * namespaces, symlink/reparse escapes through the real adapter, and the
 * create-only degradation when exclusive create cannot proceed.
 */

import { mkdir, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ProjectMemoryService, resolveMemorySpec } from '../src/index.ts'
import { createMemoryReceiptStore } from '../src/receipt.ts'
import { appendRequest, makeHarness } from './helpers.ts'

describe('AT3-04: traversal, unauthorized namespaces, and escape probes', () => {
  it('rejects malformed and traversal-shaped note ids before touching the filesystem', async () => {
    const h = await makeHarness()
    try {
      for (const probe of ['../evil', '..\\evil', 'a/b', 'A'.repeat(64), `${'a'.repeat(63)}g`, '.', '']) {
        await expect(h.service.read({ scope: 'project', noteId: probe }))
          .rejects.toMatchObject({ code: 'MEMORY_INVALID_NOTE_ID' })
      }
    } finally {
      await h.dispose()
    }
  })

  it('rejects unsafe workspace identities at spec resolution', () => {
    for (const probe of ['../evil', 'a\\b', 'CON', 'ws:alpha', '.', '..', ' ws', 'ws ', `${'x'.repeat(129)}`]) {
      expect(() => resolveMemorySpec({ vaultRoot: 'unused', workspaceId: probe }))
        .toThrowError(expect.objectContaining({ code: 'MEMORY_INVALID_WORKSPACE_ID' }))
    }
    expect(resolveMemorySpec({ vaultRoot: 'unused', workspaceId: 'ws.alpha-01' }).workspaceId).toBe('ws.alpha-01')
  })

  it('rejects namespace links outside the allowed namespaces', async () => {
    const h = await makeHarness({ userScopeEnabled: false })
    try {
      await expect(h.service.search({ scope: 'user', query: 'anything' }))
        .rejects.toMatchObject({ code: 'MEMORY_SCOPE_FORBIDDEN' })
      await expect(h.service.read({ scope: 'user', noteId: 'a'.repeat(64) }))
        .rejects.toMatchObject({ code: 'MEMORY_SCOPE_FORBIDDEN' })
      await expect(h.service.append(appendRequest({ scope: 'user' })))
        .rejects.toMatchObject({ code: 'MEMORY_SCOPE_FORBIDDEN' })
    } finally {
      await h.dispose()
    }
  })

  it('rejects a reparse component that escapes the Vault root without writing outside', async () => {
    const h = await makeHarness()
    try {
      // A directory junction (no privilege required on Windows; a symlink on
      // POSIX) at the projects component pointing outside the Vault.
      const memoryDir = join(h.vaultRoot, 'devframe-memory')
      await mkdir(memoryDir, { recursive: true })
      await symlink(h.outsideRoot, join(memoryDir, 'projects'), 'junction')

      await expect(h.service.append(appendRequest()))
        .rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
      // The outside directory received nothing.
      expect(await readdir(h.outsideRoot)).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('rejects a reparse point planted at the note file position', async () => {
    const h = await makeHarness()
    try {
      const seedRef = 'session-alpha#event-seed'
      const seed = await h.service.append(appendRequest({ sourceRef: seedRef }))
      const namespaceDir = join(h.vaultRoot, 'devframe-memory', 'projects', 'ws-alpha')
      await rm(join(namespaceDir, `${seed.noteId}.md`))
      // The committed note id now points at a directory junction planted
      // where the note file would be; resolution must refuse to follow it.
      const escapedTarget = join(h.outsideRoot, 'planted.md')
      await writeFile(escapedTarget, 'outside content', 'utf8')
      await symlink(h.outsideRoot, join(namespaceDir, `${seed.noteId}.md`), 'junction')

      await expect(h.service.read({ scope: 'project', noteId: seed.noteId }))
        .rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
      await expect(h.service.append(appendRequest({ sourceRef: seedRef })))
        .rejects.toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
      expect(await readFile(escapedTarget, 'utf8')).toBe('outside content')
    } finally {
      await h.dispose()
    }
  })

  it('fails the append explicitly and writes nothing when exclusive create cannot proceed', async () => {
    const h = await makeHarness()
    try {
      // Occupying the managed subtree with a regular file blocks directory
      // creation; the service must report an explicit failure instead of
      // falling back to an unrestricted write.
      await writeFile(join(h.vaultRoot, 'devframe-memory'), 'occupied', 'utf8')

      await expect(h.service.append(appendRequest()))
        .rejects.toMatchObject({ code: 'MEMORY_WRITE_FAILED' })
      expect(await readFile(join(h.vaultRoot, 'devframe-memory'), 'utf8')).toBe('occupied')
      expect(h.committedReceipts).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('keeps a service over an unconfigured vault read-only and explicit', async () => {
    const spec = resolveMemorySpec({ workspaceId: 'ws-alpha', writeEnabled: true })
    const service = new ProjectMemoryService(spec, createMemoryReceiptStore())
    await expect(service.search({ scope: 'project', query: 'anything' }))
      .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    await expect(service.append(appendRequest()))
      .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    await expect(service.read({ scope: 'project', noteId: 'a'.repeat(64) }))
      .rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
  })
})
