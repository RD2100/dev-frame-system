/**
 * The gateway is a thin Remote delegation layer over the library service:
 * verify each method passes the UI request through to the vault and returns
 * the DTO the page consumes, and that an unconfigured deployment stays
 * fail-closed while reporting the honest UNAVAILABLE status.
 */

import { Context } from '@deepseek-ai/cordis'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { MemoryLibraryGateway } from '../src/gateway.ts'

describe('MemoryLibraryGateway Remote delegation', () => {
  let vaultRoot: string

  beforeEach(async () => {
    vaultRoot = await mkdtemp(join(tmpdir(), 'dsh-lib-gw-'))
    await writeFile(join(vaultRoot, 'welcome.md'), '# Welcome\nHello vault.', 'utf8')
    await mkdir(join(vaultRoot, 'projects'), { recursive: true })
    await writeFile(join(vaultRoot, 'projects', 'devframe.md'), '# DevFrame\nKeyword: alpha-omega.', 'utf8')
  })

  afterEach(async () => {
    await rm(vaultRoot, { recursive: true, force: true })
  })

  it('view() reports the status and the accessible file listing', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    const snapshot = await gateway.view()
    expect(snapshot.status.status).toBe('AVAILABLE')
    expect(snapshot.status.realPath).toBeDefined()
    expect(snapshot.files.map(file => file.relativePath)).toEqual([
      'projects/devframe.md',
      'welcome.md',
    ])
  })

  it('view() reports UNAVAILABLE with an empty listing without a vault', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), undefined)
    const snapshot = await gateway.view()
    expect(snapshot.status.status).toBe('UNAVAILABLE')
    expect(snapshot.files).toEqual([])
  })

  it('status() exposes the same availability object as the model tool', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    const status = await gateway.status()
    expect(status.status).toBe('AVAILABLE')
    expect(status.fileCount).toBe(2)
  })

  it('status() is UNAVAILABLE without a vault', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), undefined)
    await expect(gateway.status()).resolves.toMatchObject({ status: 'UNAVAILABLE' })
  })

  it('list() passes an optional depth cap through', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    const files = await gateway.list({ maxDepth: 1 })
    expect(files.map(file => file.relativePath)).toEqual(['welcome.md'])
  })

  it('list() fails closed without a vault', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), undefined)
    await expect(gateway.list({})).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
  })

  it('read() returns content plus the real absolute on-disk path', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    const result = await gateway.read({ relativePath: 'projects/devframe.md' })
    expect(result.content).toContain('Keyword: alpha-omega.')
    expect(result.absolutePath).toBe(join(vaultRoot, 'projects', 'devframe.md'))
  })

  it('read() rejects traversal paths with the stable code', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    await expect(gateway.read({ relativePath: '../outside.md' })).rejects
      .toMatchObject({ code: 'MEMORY_PATH_REJECTED' })
  })

  it('read() fails closed without a vault', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), undefined)
    await expect(gateway.read({ relativePath: 'welcome.md' })).rejects
      .toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
  })

  it('search() passes the query and an optional result cap through', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), vaultRoot)
    const hits = await gateway.search({ query: 'alpha-omega', maxResults: 5 })
    expect(hits.map(hit => hit.relativePath)).toEqual(['projects/devframe.md'])
    expect(hits[0]?.matchType).toBe('content')
  })

  it('search() fails closed without a vault', async () => {
    const gateway = new MemoryLibraryGateway(new Context(), undefined)
    await expect(gateway.search({ query: 'alpha' })).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
  })
})
