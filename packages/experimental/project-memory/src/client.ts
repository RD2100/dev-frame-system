/** Client-safe Library vocabulary used by the Web Remote surface. */

import type { LibraryFile, LibraryStatus } from './library.ts'

/** Snapshot consumed by the Library page: availability plus a file listing. */
export interface MemoryLibrarySnapshot {
  /** Availability and vault metadata, including the real vault path. */
  readonly status: LibraryStatus
  /** Accessible files under the vault, sorted by relative path. */
  readonly files: readonly LibraryFile[]
}

/** List library files from the UI, with an optional depth cap. */
export interface MemoryLibraryListRequest {
  /** Maximum recursion depth (1 = root files only, 2 = one subdirectory level, …). */
  readonly maxDepth?: number
}

/** Read one library file for preview from the UI. */
export interface MemoryLibraryReadRequest {
  /** Path relative to the vault root, forward slashes. */
  readonly relativePath: string
}

/** Result of reading one library file from the UI. */
export interface MemoryLibraryReadResult {
  /** Path relative to the vault root, forward slashes. */
  readonly relativePath: string
  /** Real absolute path on disk; the copy target for references. */
  readonly absolutePath: string
  /** UTF-8 file content for preview. */
  readonly content: string
}

/** Search the library from the UI. */
export interface MemoryLibrarySearchRequest {
  /** Text to match against file paths and file contents. */
  readonly query: string
  /** Optional result cap below the default maximum of 50. */
  readonly maxResults?: number
}

export type { LibraryFile, LibrarySearchResult, LibraryStatus } from './library.ts'
