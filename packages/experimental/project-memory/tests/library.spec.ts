/**
 * Unit tests for Obsidian library read-only service: file listing, reading,
 * searching, status inspection, path containment, traversal rejection,
 * and filtering of hidden files and .obsidian.
 */

import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  getLibraryStatus,
  listLibraryFiles,
  readLibraryFile,
  searchLibrary,
} from '../src/index.ts'

describe('Obsidian Library Read-Only Service', () => {
  let vaultRoot: string
  let outsideRoot: string

  beforeEach(async () => {
    vaultRoot = await mkdtemp(join(tmpdir(), 'dsh-lib-vault-'))
    outsideRoot = await mkdtemp(join(tmpdir(), 'dsh-lib-outside-'))

    // Create normal library files and directories
    await writeFile(join(vaultRoot, 'welcome.md'), '# Welcome\nWelcome to your Obsidian vault.', 'utf8')
    await writeFile(join(vaultRoot, 'todo.txt'), 'Task 1\nTask 2: Buy milk\nTask 3', 'utf8')

    await mkdir(join(vaultRoot, 'projects'), { recursive: true })
    await writeFile(
      join(vaultRoot, 'projects', 'devframe.md'),
      '# DevFrame Project\nDevFrame integrates Obsidian as a project library.\nKeyword: alpha-omega.',
      'utf8',
    )

    await mkdir(join(vaultRoot, 'projects', 'subproject'), { recursive: true })
    await writeFile(
      join(vaultRoot, 'projects', 'subproject', 'deep.md'),
      '# Deep Note\nDeeply nested document for depth testing.',
      'utf8',
    )

    // Create forbidden / hidden directories and files
    await writeFile(join(vaultRoot, '.env'), 'DATABASE_PASSWORD=secret123', 'utf8')
    await writeFile(join(vaultRoot, '.env.local'), 'LOCAL_KEY=456', 'utf8')
    await writeFile(join(vaultRoot, '.hidden_note.md'), 'Hidden file content', 'utf8')

    await mkdir(join(vaultRoot, '.obsidian'), { recursive: true })
    await writeFile(join(vaultRoot, '.obsidian', 'app.json'), '{"theme": "dark"}', 'utf8')

    await mkdir(join(vaultRoot, 'devframe-memory', 'user'), { recursive: true })
    await writeFile(
      join(vaultRoot, 'devframe-memory', 'user', 'note.md'),
      '---\nkind: preference\ncreatedAt: 2026-01-01T00:00:00.000Z\n---\nMemory note body line',
      'utf8',
    )

    // Create an outside file for traversal/symlink escape probes
    await writeFile(join(outsideRoot, 'outside-secret.txt'), 'SUPER_SECRET_TOKEN', 'utf8')
  })

  afterEach(async () => {
    await rm(vaultRoot, { recursive: true, force: true })
    await rm(outsideRoot, { recursive: true, force: true })
  })

  describe('listLibraryFiles', () => {
    it('normally lists accessible files recursively with normalized forward slashes', async () => {
      const files = await listLibraryFiles(vaultRoot)
      const relativePaths = files.map(f => f.relativePath)

      expect(relativePaths).toEqual([
        'devframe-memory/user/note.md',
        'projects/devframe.md',
        'projects/subproject/deep.md',
        'todo.txt',
        'welcome.md',
      ])

      for (const file of files) {
        expect(file.size).toBeGreaterThan(0)
        expect(file.mtimeMs).toBeGreaterThan(0)
        expect(file.relativePath).not.toContain('\\')
      }

      // The memory note is listed with its frontmatter kind parsed
      const memoryNote = files.find(f => f.relativePath === 'devframe-memory/user/note.md')
      expect(memoryNote?.kind).toBe('preference')
      expect(memoryNote?.createdAt).toBe('2026-01-01T00:00:00.000Z')
      expect(memoryNote?.summary).toBe('Memory note body line')
    })

    it('filters out hidden files starting with dot', async () => {
      const files = await listLibraryFiles(vaultRoot)
      const relativePaths = files.map(f => f.relativePath)

      expect(relativePaths.some(p => p.includes('.hidden_note.md'))).toBe(false)
      expect(relativePaths.some(p => p.includes('.env'))).toBe(false)
    })

    it('filters out .obsidian/ directory and all contents inside', async () => {
      const files = await listLibraryFiles(vaultRoot)
      const relativePaths = files.map(f => f.relativePath)

      expect(relativePaths.some(p => p.includes('.obsidian'))).toBe(false)
    })

    it('includes devframe-memory/ directory and its notes', async () => {
      const files = await listLibraryFiles(vaultRoot)
      const relativePaths = files.map(f => f.relativePath)

      expect(relativePaths.some(p => p.includes('devframe-memory'))).toBe(true)
    })

    it('filters out dot-suffixed env names, reserved device names, and blank segments', async () => {
      await writeFile(join(vaultRoot, 'notes.env'), 'MODE=test', 'utf8')
      await writeFile(join(vaultRoot, 'CON'), 'reserved', 'utf8')
      await writeFile(join(vaultRoot, 'con.md'), 'reserved stem', 'utf8')
      await mkdir(join(vaultRoot, '   '), { recursive: true })
      await writeFile(join(vaultRoot, '   ', 'blank.md'), 'blank', 'utf8')

      const files = await listLibraryFiles(vaultRoot)
      const relativePaths = files.map(f => f.relativePath)
      expect(relativePaths).not.toContain('notes.env')
      expect(relativePaths).not.toContain('CON')
      expect(relativePaths).not.toContain('con.md')
      expect(relativePaths.some(p => p.includes('blank.md'))).toBe(false)
    })

    it('respects maxDepth option', async () => {
      // maxDepth = 0 -> empty
      const depth0 = await listLibraryFiles(vaultRoot, { maxDepth: 0 })
      expect(depth0).toHaveLength(0)

      // maxDepth = 1 -> only files directly under vaultRoot
      const depth1 = await listLibraryFiles(vaultRoot, { maxDepth: 1 })
      expect(depth1.map(f => f.relativePath)).toEqual(['todo.txt', 'welcome.md'])

      // maxDepth = 2 -> root files plus 1 level of subdirectories
      const depth2 = await listLibraryFiles(vaultRoot, { maxDepth: 2 })
      expect(depth2.map(f => f.relativePath)).toEqual([
        'projects/devframe.md',
        'todo.txt',
        'welcome.md',
      ])
    })

    it('fails when vaultRoot is unconfigured or not a directory', async () => {
      await expect(listLibraryFiles('')).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
      await expect(listLibraryFiles(join(vaultRoot, 'non-existent'))).rejects.toMatchObject({
        code: 'MEMORY_UNAVAILABLE',
      })
    })

    it('rejects invalid maxDepth parameter', async () => {
      await expect(listLibraryFiles(vaultRoot, { maxDepth: -1 })).rejects.toMatchObject({
        code: 'MEMORY_INVALID_REQUEST',
      })
      await expect(listLibraryFiles(vaultRoot, { maxDepth: 1.5 })).rejects.toMatchObject({
        code: 'MEMORY_INVALID_REQUEST',
      })
    })
  })

  describe('readLibraryFile', () => {
    it('normally reads accessible library file content', async () => {
      const content = await readLibraryFile(vaultRoot, 'welcome.md')
      expect(content).toBe('# Welcome\nWelcome to your Obsidian vault.')

      const nested = await readLibraryFile(vaultRoot, 'projects/devframe.md')
      expect(nested).toContain('Keyword: alpha-omega.')
    })

    it('rejects ../ traversal attacks', async () => {
      for (const probe of [
        '../outside-secret.txt',
        '..\\outside-secret.txt',
        'projects/../../outside-secret.txt',
        'projects/../projects/../../outside-secret.txt',
        '..',
        '.',
      ]) {
        await expect(readLibraryFile(vaultRoot, probe)).rejects.toMatchObject({
          code: 'MEMORY_PATH_REJECTED',
        })
      }
    })

    it('rejects absolute paths and drive letters', async () => {
      await expect(readLibraryFile(vaultRoot, '/etc/passwd')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, 'C:\\Windows\\win.ini')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('rejects reading .env files', async () => {
      await expect(readLibraryFile(vaultRoot, '.env')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, '.env.local')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await writeFile(join(vaultRoot, 'notes.env'), 'MODE=test', 'utf8')
      await expect(readLibraryFile(vaultRoot, 'notes.env')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('rejects reserved device names and blank or dot-suffixed segments', async () => {
      await writeFile(join(vaultRoot, 'CON'), 'reserved', 'utf8')
      await writeFile(join(vaultRoot, 'con.md'), 'reserved stem', 'utf8')
      await writeFile(join(vaultRoot, 'trailing.'), 'dot suffix', 'utf8')
      await expect(readLibraryFile(vaultRoot, 'CON')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, 'con.md')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, 'trailing.')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, '   ')).rejects.toMatchObject({
        code: 'MEMORY_INVALID_REQUEST',
      })
      await expect(readLibraryFile(vaultRoot, 'a/   /b.md')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('rejects reading through a non-directory component or a directory as the file', async () => {
      await expect(readLibraryFile(vaultRoot, 'todo.txt/x.md')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
      await expect(readLibraryFile(vaultRoot, 'projects')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('rejects reading hidden files', async () => {
      await expect(readLibraryFile(vaultRoot, '.hidden_note.md')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('rejects reading from .obsidian/ directory', async () => {
      await expect(readLibraryFile(vaultRoot, '.obsidian/app.json')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('reads notes from devframe-memory/ directory', async () => {
      const content = await readLibraryFile(vaultRoot, 'devframe-memory/user/note.md')
      expect(content).toContain('Memory note body line')
    })

    it('rejects directory symlink / junction escapes', async () => {
      // Plant a junction inside the vault pointing outside
      const junctionPath = join(vaultRoot, 'escaped_junction')
      try {
        await symlink(outsideRoot, junctionPath, 'junction')
      } catch {
        // Fallback for non-Windows platforms
        await symlink(outsideRoot, junctionPath, 'dir')
      }

      await expect(readLibraryFile(vaultRoot, 'escaped_junction/outside-secret.txt')).rejects.toMatchObject({
        code: 'MEMORY_PATH_REJECTED',
      })
    })

    it('throws MEMORY_UNAVAILABLE when requested file does not exist', async () => {
      await expect(readLibraryFile(vaultRoot, 'does-not-exist.md')).rejects.toMatchObject({
        code: 'MEMORY_UNAVAILABLE',
      })
    })
  })

  describe('searchLibrary', () => {
    it('searches by filename', async () => {
      const results = await searchLibrary(vaultRoot, 'todo')
      expect(results.length).toBeGreaterThanOrEqual(1)
      const hit = results.find(r => r.relativePath === 'todo.txt')
      expect(hit).toBeDefined()
      expect(hit?.matchType).toBe('name')
    })

    it('searches by content and returns excerpt with line number', async () => {
      const results = await searchLibrary(vaultRoot, 'alpha-omega')
      expect(results.length).toBe(1)
      const hit = results[0]
      expect(hit).toBeDefined()
      expect(hit?.relativePath).toBe('projects/devframe.md')
      expect(hit?.matchType).toBe('content')
      expect(hit?.excerpt).toContain('alpha-omega')
      expect(hit?.line).toBe(3)
    })

    it('identifies both filename and content match as matchType "both"', async () => {
      const results = await searchLibrary(vaultRoot, 'devframe')
      const hit = results.find(r => r.relativePath === 'projects/devframe.md')
      expect(hit).toBeDefined()
      expect(hit?.matchType).toBe('both')
    })

    it('respects maxResults option', async () => {
      const results = await searchLibrary(vaultRoot, 'e', { maxResults: 2 })
      expect(results.length).toBeLessThanOrEqual(2)
    })

    it('rejects empty query', async () => {
      await expect(searchLibrary(vaultRoot, '')).rejects.toMatchObject({
        code: 'MEMORY_INVALID_REQUEST',
      })
      await expect(searchLibrary(vaultRoot, '   ')).rejects.toMatchObject({
        code: 'MEMORY_INVALID_REQUEST',
      })
    })

    it('does not return hits from hidden/forbidden directories (.obsidian, .env) but includes devframe-memory notes', async () => {
      // .obsidian has 'theme'
      const obsidianResults = await searchLibrary(vaultRoot, 'theme')
      expect(obsidianResults).toHaveLength(0)

      // .env has 'secret123'
      const envResults = await searchLibrary(vaultRoot, 'secret123')
      expect(envResults).toHaveLength(0)

      // devframe-memory notes are now searchable
      const memoryResults = await searchLibrary(vaultRoot, 'Memory note')
      expect(memoryResults).toHaveLength(1)
      expect(memoryResults[0]?.relativePath).toBe('devframe-memory/user/note.md')
      expect(memoryResults[0]?.matchType).toBe('content')
    })
  })

  describe('getLibraryStatus', () => {
    it('returns UNAVAILABLE status when vaultRoot is not configured or empty', async () => {
      const status1 = await getLibraryStatus('')
      expect(status1.status).toBe('UNAVAILABLE')
      expect(status1.reason).toContain('not configured')

      const status2 = await getLibraryStatus('   ')
      expect(status2.status).toBe('UNAVAILABLE')
    })

    it('returns UNAVAILABLE status when vaultRoot path does not exist', async () => {
      const status = await getLibraryStatus(join(vaultRoot, 'non-existent-dir'))
      expect(status.status).toBe('UNAVAILABLE')
      expect(status.reason).toBeDefined()
    })

    it('returns AVAILABLE status with accurate file count and byte size when vault is valid', async () => {
      const status = await getLibraryStatus(vaultRoot)
      expect(status.status).toBe('AVAILABLE')
      expect(status.fileCount).toBe(5) // devframe.md, deep.md, todo.txt, welcome.md, devframe-memory/user/note.md
      expect(status.totalSizeBytes).toBeGreaterThan(0)
      expect(status.realPath).toBeDefined()
    })
  })
})
