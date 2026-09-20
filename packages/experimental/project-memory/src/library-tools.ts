/**
 * Model tool faces over the read-only Obsidian library vault. The service
 * (`library.ts`) is authoritative; these tools bind its configured vault root
 * and surface the four read operations with lossless-JSON output schemas. A
 * deployment without a vault root keeps the tools registered but fail-closed
 * with `MEMORY_UNAVAILABLE`, mirroring the memory tools — an unconfigured
 * library never reads an arbitrary directory.
 * @module @deepseek-ai/dsh-experimental-project-memory/library-tools
 */

import { defineTool, type ToolDefinition } from '@deepseek-ai/dsh-tools'
import { ProjectMemoryError } from './errors.ts'
import { getLibraryStatus, listLibraryFiles, readLibraryFile, searchLibrary } from './library.ts'

/** Deployment context the library tools are bound to at registration. */
export interface LibraryToolContext {
  /** Configured vault root, or undefined when the deployment has no vault. */
  readonly vaultRoot?: string
}

const FILE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    relativePath: { type: 'string', required: true },
    size: { type: 'number', required: true },
    mtimeMs: { type: 'number', required: true },
  },
} as const

const SEARCH_HIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    relativePath: { type: 'string', required: true },
    matchType: { type: 'string', required: true, enum: ['name', 'content', 'both'] },
    excerpt: { type: 'string', required: true },
    line: { type: 'number' },
  },
} as const

/** Fail loud with the stable code when the deployment configured no vault. */
function unavailableVault(): never {
  throw new ProjectMemoryError('memory vault is not configured', 'MEMORY_UNAVAILABLE')
}

/**
 * Register the four read-only library tools bound to one vault root.
 * @param context - The deployment's vault configuration.
 * @returns the tool definitions, in `library_status`, `library_list`,
 *   `library_read`, `library_search` order.
 */
export function createLibraryTools(context: LibraryToolContext): ToolDefinition[] {
  const vaultRoot = context.vaultRoot
  return [
    defineTool({
      name: 'library_status',
      description: 'Inspect the read-only Obsidian library vault: whether it is available, its real path, accessible file count, and total size. Call this before assuming the library can serve files; an unconfigured vault reports UNAVAILABLE with a reason instead of guessing.',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            status: { type: 'string', required: true, enum: ['AVAILABLE', 'UNAVAILABLE'] },
            vaultRoot: { type: 'string' },
            realPath: { type: 'string' },
            fileCount: { type: 'number' },
            totalSizeBytes: { type: 'number' },
            reason: { type: 'string' },
          },
        },
        render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
      },
      isConcurrencySafe: () => true,
      async execute() {
        if (vaultRoot === undefined) {
          return { status: 'UNAVAILABLE' as const, reason: 'vaultRoot is not configured' }
        }
        return getLibraryStatus(vaultRoot)
      },
    }),
    defineTool({
      name: 'library_list',
      description: 'List the accessible files of the read-only Obsidian library vault: relative paths, byte sizes, and modification times, sorted by path. Hidden files and symlinks are excluded by policy. The result is metadata and can be large; prefer library_search to locate specific content.',
      parameters: {
        max_depth: {
          type: 'integer',
          description: 'Optional recursion depth limit (0 returns nothing, 1 root files only, 2 one subdirectory level, …); unlimited when omitted.',
        },
      },
      output: {
        schema: {
          type: 'array',
          items: FILE_SCHEMA,
        },
        render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
      },
      isConcurrencySafe: () => true,
      async execute(args) {
        if (vaultRoot === undefined) unavailableVault()
        return listLibraryFiles(vaultRoot, args.max_depth === undefined ? undefined : { maxDepth: args.max_depth })
      },
    }),
    defineTool({
      name: 'library_read',
      description: 'Read the UTF-8 content of one file inside the read-only Obsidian library vault by its relative path (forward slashes). Path traversal, symlinks, and hidden files are rejected with MEMORY_PATH_REJECTED; unreadable files fail with MEMORY_UNAVAILABLE. Prefer library_search for locating content.',
      parameters: {
        relative_path: { type: 'string', required: true, description: 'Path relative to the vault root, forward slashes, e.g. projects/alpha/notes.md.' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            relativePath: { type: 'string', required: true },
            content: { type: 'string', required: true },
          },
        },
        render: (_args, value) => [{ type: 'text', text: value.content }],
      },
      isConcurrencySafe: () => true,
      async execute(args) {
        if (vaultRoot === undefined) unavailableVault()
        const content = await readLibraryFile(vaultRoot, args.relative_path)
        return { relativePath: args.relative_path, content }
      },
    }),
    defineTool({
      name: 'library_search',
      description: 'Search the read-only Obsidian library vault by name and text content. Returns bounded results (default 50, capped by max_results) with the match kind (name, content, or both), a bounded excerpt, and the first content-match line. Content search covers text files up to 2 MiB. A missing hit may mean the scan cap or content ceiling was reached — absence in a search result is not proof the knowledge does not exist.',
      parameters: {
        query: { type: 'string', required: true, description: 'Text to match against file paths and file contents.' },
        max_results: { type: 'integer', description: 'Optional result cap below the default maximum of 50.' },
      },
      output: {
        schema: {
          type: 'array',
          items: SEARCH_HIT_SCHEMA,
        },
        render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
      },
      isConcurrencySafe: () => true,
      async execute(args) {
        if (vaultRoot === undefined) unavailableVault()
        return searchLibrary(
          vaultRoot,
          args.query,
          args.max_results === undefined ? undefined : { maxResults: args.max_results },
        )
      },
    }),
  ]
}
