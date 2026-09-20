/**
 * Read-only service over a user-selected Obsidian Vault: list files, read
 * note content, search filenames and text, and inspect vault availability.
 * Strictly read-only, path-contained, rejecting hidden files, symlinks,
 * and .obsidian.
 * @module @deepseek-ai/dsh-experimental-project-memory/library
 */

import { lstat, readFile, readdir, realpath, stat } from 'node:fs/promises'
import { isAbsolute, join, relative, resolve } from 'node:path'
import { ProjectMemoryError } from './errors.ts'
import { truncateToByteLimit } from './notes.ts'

/** One accessible file entry inside the Obsidian library. */
export interface LibraryFile {
  /** Path relative to the vault root, normalized with forward slashes. */
  readonly relativePath: string
  /** File size in bytes. */
  readonly size: number
  /** Last modification timestamp in milliseconds since Unix epoch. */
  readonly mtimeMs: number
  /** Note kind from frontmatter (when present). */
  readonly kind?: 'fact' | 'preference'
  /** Creation timestamp from frontmatter (ISO string, when present). */
  readonly createdAt?: string
  /** Entities tagged on the note (from frontmatter, when present). */
  readonly entities?: readonly string[]
  /** Short summary extracted from the note body (first ~120 chars, when parseable). */
  readonly summary?: string
}

/** One match excerpt snippet within a searched file. */
export interface LibrarySearchMatch {
  /** Line number of the match (1-indexed). */
  readonly line: number
  /** Bounded excerpt snippet around the match. */
  readonly excerpt: string
}

/** One search result hit in the library. */
export interface LibrarySearchResult {
  /** Path relative to the vault root, normalized with forward slashes. */
  readonly relativePath: string
  /** How the query matched: 'name' (filename only), 'content' (content only), or 'both'. */
  readonly matchType: 'name' | 'content' | 'both'
  /** Bounded excerpt showing match context. */
  readonly excerpt: string
  /** Line number of the first content match (1-indexed), if content matched. */
  readonly line?: number
}

/** Status of the Obsidian library vault. */
export interface LibraryStatus {
  /** Overall availability state. */
  readonly status: 'AVAILABLE' | 'UNAVAILABLE'
  /** The configured vault root path. */
  readonly vaultRoot?: string
  /** Real absolute path to the vault root on disk, if accessible. */
  readonly realPath?: string
  /** Total count of accessible files, when available. */
  readonly fileCount?: number
  /** Total byte size of all accessible files, when available. */
  readonly totalSizeBytes?: number
  /** Explanation for why the library is unavailable, when applicable. */
  readonly reason?: string
}

/** Options for listing library files. */
export interface ListLibraryOptions {
  /** Maximum recursion depth (0 = empty, 1 = root files only, 2 = 1 subdirectory level, etc.). */
  readonly maxDepth?: number
}

/** Options for searching the library. */
export interface SearchLibraryOptions {
  /** Maximum number of results to return (default: 50). */
  readonly maxResults?: number
}

/** Windows reserved device names, rejected as path segments. */
const WINDOWS_RESERVED = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
])

/** Set of file extensions treated as searchable text files. */
const TEXT_EXTENSIONS = new Set([
  '.md', '.txt', '.markdown', '.canvas', '.json', '.csv',
])

/** File size ceiling for full content text search (2 MiB). */
const MAX_SEARCHABLE_FILE_SIZE = 2 * 1024 * 1024

/** Byte ceiling for one excerpt snippet inside a search hit. */
const EXCERPT_MAX_BYTES = 1024

/**
 * Check whether a file or directory name is forbidden by security rules:
 * hidden files (starts with dot, e.g. .obsidian, .env, .git), .env variants,
 * or Windows device names.
 */
function isForbiddenName(name: string): boolean {
  const trimmed = name.trim()
  if (trimmed.length === 0) return true
  if (trimmed.startsWith('.')) return true
  if (trimmed === '.env' || trimmed.startsWith('.env.') || trimmed.endsWith('.env')) return true
  const stem = trimmed.split('.')[0] ?? trimmed
  if (WINDOWS_RESERVED.has(trimmed.toUpperCase()) || WINDOWS_RESERVED.has(stem.toUpperCase())) return true
  return false
}

/** Parsed frontmatter metadata from a memory note. */
interface ParsedFrontmatter {
  kind?: 'fact' | 'preference'
  createdAt?: string
  entities?: readonly string[]
  summary?: string
}

/**
 * Parse frontmatter metadata from a memory note file content.
 * Lightweight parser for card previews: extracts kind/createdAt/entities/summary
 * without enforcing body digest integrity (that is the writer's responsibility).
 */
function parseFrontmatter(content: string): ParsedFrontmatter {
  if (!content.startsWith('---\n')) return {}
  const endIdx = content.indexOf('\n---\n', 4)
  if (endIdx < 0) return {}

  const fmText = content.slice(4, endIdx)
  const body = content.slice(endIdx + 5).trim()

  const result: ParsedFrontmatter = {}

  for (const line of fmText.split('\n')) {
    const colonIdx = line.indexOf(':')
    if (colonIdx < 0) continue
    const key = line.slice(0, colonIdx).trim()
    const value = line.slice(colonIdx + 1).trim()
    if (key === 'kind' && (value === 'fact' || value === 'preference')) {
      result.kind = value
    } else if (key === 'createdAt') {
      result.createdAt = value
    } else if (key === 'entities') {
      result.entities = value.split(',').map(s => s.trim()).filter(Boolean)
    }
  }

  // Extract summary from body: first non-empty line, truncated to 120 chars
  const firstLine = body.split('\n').find(l => l.trim().length > 0)
  if (firstLine) {
    result.summary = firstLine.trim().slice(0, 120)
  }

  return result
}

/** Read a Node filesystem error code safely. */
function fsErrorCode(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('code' in error)) return undefined
  const code = (error as { readonly code?: unknown }).code
  return typeof code === 'string' ? code : undefined
}

/** Verify that a resolved path is strictly inside the vault root. */
function isInsideRoot(child: string, root: string): boolean {
  const normChild = resolve(child)
  const normRoot = resolve(root)
  const rel = relative(normRoot, normChild)
  if (rel.startsWith('..') || isAbsolute(rel)) {
    return false
  }
  const separator = normRoot.endsWith('\\') || normRoot.endsWith('/') ? '' : '\\'
  return normChild.toLowerCase().startsWith((normRoot + separator).toLowerCase()) ||
    normChild.toLowerCase().startsWith((normRoot + '/').toLowerCase())
}

/**
 * Validate and resolve the vault root, ensuring it is an accessible directory.
 */
async function requireVaultRoot(vaultRoot: string): Promise<string> {
  if (typeof vaultRoot !== 'string' || vaultRoot.trim().length === 0) {
    throw new ProjectMemoryError('memory vault is not configured', 'MEMORY_UNAVAILABLE')
  }
  let stats
  try {
    stats = await stat(vaultRoot)
  } catch (error: unknown) {
    throw new ProjectMemoryError('memory vault root is not an accessible directory', 'MEMORY_UNAVAILABLE', { cause: error })
  }
  if (!stats.isDirectory()) {
    throw new ProjectMemoryError('memory vault root is not a directory', 'MEMORY_UNAVAILABLE')
  }
  try {
    return await realpath(vaultRoot)
  } catch (error: unknown) {
    throw new ProjectMemoryError('memory vault root is not an accessible directory', 'MEMORY_UNAVAILABLE', { cause: error })
  }
}

/**
 * Validate a user-provided relative path: reject traversal, absolute paths,
 * control characters, and forbidden segments.
 */
function validateRelativePath(relativePath: string): string[] {
  if (typeof relativePath !== 'string' || relativePath.trim().length === 0) {
    throw new ProjectMemoryError('path must be a non-empty string', 'MEMORY_INVALID_REQUEST')
  }
  if (/[\u0000-\u001F\u007F]/.test(relativePath)) {
    throw new ProjectMemoryError('path contains invalid characters', 'MEMORY_PATH_REJECTED')
  }
  if (isAbsolute(relativePath) || /^[a-zA-Z]:/.test(relativePath) || relativePath.startsWith('/') || relativePath.startsWith('\\')) {
    throw new ProjectMemoryError('path must be a relative path', 'MEMORY_PATH_REJECTED')
  }
  const segments = relativePath.split(/[/\\]+/).filter(Boolean)
  if (segments.length === 0) {
    throw new ProjectMemoryError('path must contain at least one segment', 'MEMORY_PATH_REJECTED')
  }
  for (const segment of segments) {
    if (segment === '.' || segment === '..' || isForbiddenName(segment)) {
      throw new ProjectMemoryError(`forbidden or traversal path segment: ${segment}`, 'MEMORY_PATH_REJECTED')
    }
    if (segment.endsWith('.')) {
      throw new ProjectMemoryError(`invalid path segment: ${segment}`, 'MEMORY_PATH_REJECTED')
    }
  }
  return segments
}

/**
 * Build a bounded excerpt snippet around a match index.
 */
/**
 * Build a bounded excerpt snippet around a match index. A cut edge is marked
 * with an ellipsis so the reader can tell the text continues.
 */
function buildExcerpt(content: string, matchIndex: number, queryLength: number): string {
  const prefixStart = Math.max(0, matchIndex - 30)
  const suffixEnd = Math.min(content.length, matchIndex + queryLength + 50)
  const snippet = content.slice(prefixStart, suffixEnd).replace(/\r?\n/g, ' ')
  const bounded = truncateToByteLimit(snippet, EXCERPT_MAX_BYTES)
  return `${prefixStart > 0 ? '…' : ''}${bounded}${suffixEnd < content.length ? '…' : ''}`
}

/**
 * List accessible files in the Obsidian library vault, excluding hidden files,
 * forbidden directories (.obsidian), and symlinks.
 * @param vaultRoot - The root directory of the Obsidian vault.
 * @param options - Listing options including optional recursion depth limit.
 * @returns Sorted list of accessible library files with relative paths and metadata.
 * @throws {@link ProjectMemoryError} with code `MEMORY_UNAVAILABLE` when the
 * vault root is not configured or inaccessible, or `MEMORY_INVALID_REQUEST`
 * when options are invalid.
 */
export async function listLibraryFiles(
  vaultRoot: string,
  options?: ListLibraryOptions,
): Promise<LibraryFile[]> {
  const rootReal = await requireVaultRoot(vaultRoot)
  const maxDepth = options?.maxDepth
  if (maxDepth !== undefined && (!Number.isInteger(maxDepth) || maxDepth < 0)) {
    throw new ProjectMemoryError('maxDepth must be a non-negative integer', 'MEMORY_INVALID_REQUEST')
  }
  if (maxDepth === 0) return []

  const results: LibraryFile[] = []

  async function walk(currentDir: string, relDir: string, depth: number): Promise<void> {
    let entries
    try {
      entries = await readdir(currentDir, { withFileTypes: true })
    } catch {
      return
    }
    entries.sort((a, b) => a.name.localeCompare(b.name))

    for (const entry of entries) {
      if (isForbiddenName(entry.name)) continue
      if (entry.isSymbolicLink()) continue

      const fullPath = join(currentDir, entry.name)
      const relPath = relDir ? `${relDir}/${entry.name}` : entry.name

      if (entry.isDirectory()) {
        if (maxDepth === undefined || depth + 1 < maxDepth) {
          await walk(fullPath, relPath, depth + 1)
        }
      } else if (entry.isFile()) {
        try {
          const stats = await lstat(fullPath)
          if (stats.isSymbolicLink() || !stats.isFile()) continue
          const normalizedRel = relPath.replace(/\\/g, '/')
          // Parse frontmatter for memory notes (bounded read for performance)
          let meta: ParsedFrontmatter = {}
          if (normalizedRel.endsWith('.md')) {
            try {
              const content = await readFile(fullPath, 'utf8')
              meta = parseFrontmatter(content)
            } catch {
              // Ignore unreadable or transient files
            }
          }
          const fileEntry: LibraryFile = {
            relativePath: normalizedRel,
            size: stats.size,
            mtimeMs: stats.mtimeMs,
            ...meta.kind !== undefined ? { kind: meta.kind } : {},
            ...meta.createdAt !== undefined ? { createdAt: meta.createdAt } : {},
            ...meta.entities !== undefined ? { entities: meta.entities } : {},
            ...meta.summary !== undefined ? { summary: meta.summary } : {},
          }
          results.push(fileEntry)
        } catch {
          // Ignore unreadable or transient files
        }
      }
    }
  }

  await walk(rootReal, '', 0)
  results.sort((a, b) => a.relativePath.localeCompare(b.relativePath))
  return results
}

/**
 * Read the UTF-8 content of a single library file inside the vault, enforcing
 * path containment and rejecting symlinks or forbidden files.
 * @param vaultRoot - The root directory of the Obsidian vault.
 * @param relativePath - Relative path to the file inside the vault.
 * @returns The UTF-8 string content of the requested file.
 * @throws {@link ProjectMemoryError} with code `MEMORY_PATH_REJECTED` for
 * traversal, forbidden files, or symlinks, or `MEMORY_UNAVAILABLE` when the
 * file or vault cannot be read.
 */
export async function readLibraryFile(
  vaultRoot: string,
  relativePath: string,
): Promise<string> {
  const rootReal = await requireVaultRoot(vaultRoot)
  const segments = validateRelativePath(relativePath)

  let current = rootReal
  for (const [i, segment] of segments.entries()) {
    current = join(current, segment)
    let stats
    try {
      stats = await lstat(current)
    } catch (error: unknown) {
      if (fsErrorCode(error) === 'ENOENT') {
        throw new ProjectMemoryError(`file not found: ${relativePath}`, 'MEMORY_UNAVAILABLE', { cause: error })
      }
      throw new ProjectMemoryError(`cannot inspect path: ${relativePath}`, 'MEMORY_UNAVAILABLE', { cause: error })
    }
    if (stats.isSymbolicLink()) {
      throw new ProjectMemoryError(`symlinks are not permitted: ${segment}`, 'MEMORY_PATH_REJECTED')
    }
    if (i < segments.length - 1) {
      if (!stats.isDirectory()) {
        throw new ProjectMemoryError(`path component is not a directory: ${segment}`, 'MEMORY_PATH_REJECTED')
      }
    } else {
      if (!stats.isFile()) {
        throw new ProjectMemoryError(`path is not a regular file: ${relativePath}`, 'MEMORY_PATH_REJECTED')
      }
    }
  }

  let real: string
  try {
    real = await realpath(current)
  } catch (error: unknown) {
    throw new ProjectMemoryError(`cannot resolve realpath: ${relativePath}`, 'MEMORY_UNAVAILABLE', { cause: error })
  }
  if (!isInsideRoot(real, rootReal)) {
    throw new ProjectMemoryError('resolved path escapes vault root', 'MEMORY_PATH_REJECTED')
  }

  try {
    return await readFile(real, 'utf8')
  } catch (error: unknown) {
    throw new ProjectMemoryError(`failed to read library file: ${relativePath}`, 'MEMORY_UNAVAILABLE', { cause: error })
  }
}

/**
 * Search the library files by matching filename and text content.
 * @param vaultRoot - The root directory of the Obsidian vault.
 * @param query - Non-empty search query string.
 * @param options - Search options including maximum results limit.
 * @returns Array of search results with match type, snippet excerpt, and line number.
 * @throws {@link ProjectMemoryError} with code `MEMORY_INVALID_REQUEST` when
 * the query is empty or limits are invalid, or `MEMORY_UNAVAILABLE` when the
 * vault is inaccessible.
 */
export async function searchLibrary(
  vaultRoot: string,
  query: string,
  options?: SearchLibraryOptions,
): Promise<LibrarySearchResult[]> {
  if (typeof query !== 'string' || query.trim().length === 0) {
    throw new ProjectMemoryError('search query must be non-empty', 'MEMORY_INVALID_REQUEST')
  }
  const maxResults = options?.maxResults ?? 50
  if (!Number.isInteger(maxResults) || maxResults <= 0) {
    throw new ProjectMemoryError('maxResults must be a positive integer', 'MEMORY_INVALID_REQUEST')
  }

  const files = await listLibraryFiles(vaultRoot)
  const lowerQuery = query.toLowerCase()
  const results: LibrarySearchResult[] = []

  for (const file of files) {
    const matchesName = file.relativePath.toLowerCase().includes(lowerQuery)
    let contentMatch: { line: number; excerpt: string } | undefined

    const ext = file.relativePath.slice(file.relativePath.lastIndexOf('.')).toLowerCase()
    if (TEXT_EXTENSIONS.has(ext) && file.size <= MAX_SEARCHABLE_FILE_SIZE) {
      try {
        const content = await readLibraryFile(vaultRoot, file.relativePath)
        const matchIdx = content.toLowerCase().indexOf(lowerQuery)
        if (matchIdx >= 0) {
          const line = content.slice(0, matchIdx).split('\n').length
          const excerpt = buildExcerpt(content, matchIdx, query.length)
          contentMatch = { line, excerpt }
        }
      } catch {
        // Skip unreadable files
      }
    }

    if (matchesName && contentMatch) {
      results.push({
        relativePath: file.relativePath,
        matchType: 'both',
        excerpt: contentMatch.excerpt,
        line: contentMatch.line,
      })
    } else if (contentMatch) {
      results.push({
        relativePath: file.relativePath,
        matchType: 'content',
        excerpt: contentMatch.excerpt,
        line: contentMatch.line,
      })
    } else if (matchesName) {
      results.push({
        relativePath: file.relativePath,
        matchType: 'name',
        excerpt: file.relativePath,
      })
    }

    if (results.length >= maxResults) break
  }

  return results
}

/**
 * Inspect the status of the Obsidian library vault without throwing.
 * @param vaultRoot - The configured root path to test.
 * @returns Status object indicating AVAILABLE or UNAVAILABLE with details.
 */
export async function getLibraryStatus(vaultRoot: string): Promise<LibraryStatus> {
  if (typeof vaultRoot !== 'string' || vaultRoot.trim().length === 0) {
    return { status: 'UNAVAILABLE', reason: 'vaultRoot is not configured' }
  }
  let rootReal: string
  try {
    rootReal = await requireVaultRoot(vaultRoot)
  } catch (error: unknown) {
    return {
      status: 'UNAVAILABLE',
      vaultRoot,
      reason: error instanceof Error ? error.message : 'vaultRoot is not an accessible directory',
    }
  }

  try {
    const files = await listLibraryFiles(rootReal)
    let totalSizeBytes = 0
    for (const f of files) {
      totalSizeBytes += f.size
    }
    return {
      status: 'AVAILABLE',
      vaultRoot,
      realPath: rootReal,
      fileCount: files.length,
      totalSizeBytes,
    }
  } catch (error: unknown) {
    return {
      status: 'UNAVAILABLE',
      vaultRoot,
      realPath: rootReal,
      reason: error instanceof Error ? error.message : 'failed to inspect library files',
    }
  }
}
