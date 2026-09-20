/**
 * Host Remote owner for the Library page over the read-only Obsidian vault.
 * The model tools remain the in-session surface; this gateway additionally
 * exposes the browsing operations the Library page needs — snapshot, status,
 * listing, file preview, and search — to the Web UI, with absolute on-disk
 * paths for copying and conversation references.
 *
 * The gateway is deployment-true: it is mounted even when no vault is
 * configured, and then reports the honest `UNAVAILABLE` status while every
 * file-touching method fails closed with `MEMORY_UNAVAILABLE` — a
 * misconfigured deployment never reads an arbitrary directory through the UI
 * either.
 * @module @deepseek-ai/dsh-experimental-project-memory/gateway
 */

import type { Context } from '@deepseek-ai/cordis'
import { realpath } from 'node:fs/promises'
import { join } from 'node:path'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {
  MemoryLibraryListRequest,
  MemoryLibraryReadRequest,
  MemoryLibraryReadResult,
  MemoryLibrarySearchRequest,
  MemoryLibrarySnapshot,
} from './client.ts'
import { ProjectMemoryError } from './errors.ts'
import {
  getLibraryStatus,
  listLibraryFiles,
  readLibraryFile,
  searchLibrary,
  type LibraryFile,
  type LibrarySearchResult,
  type LibraryStatus,
} from './library.ts'

/** Fail loud with the stable code when the deployment configured no vault. */
function unavailableVault(): never {
  throw new ProjectMemoryError('memory vault is not configured', 'MEMORY_UNAVAILABLE')
}

/** Host service backing the generated `ctx.remote.library` namespace. */
export class MemoryLibraryGateway extends TypertRemoteService {
  /**
   * @param ctx - Host context that owns the Remote service registration.
   * @param vaultRoot - The configured Obsidian Vault root, or undefined when
   *   the deployment has no vault (the gateway then stays fail-closed).
   */
  constructor(
    ctx: Context,
    private readonly vaultRoot: string | undefined,
  ) {
    super(ctx, 'memoryLibraryGateway', { namespace: 'library' })
  }

  /**
   * Read the current library status and file listing in one call.
   * @returns availability metadata plus the accessible files; an unconfigured
   *   vault yields an `UNAVAILABLE` status and an empty listing.
   */
  @Remote('view')
  async view(): Promise<MemoryLibrarySnapshot> {
    const status = await getLibraryStatus(this.vaultRoot ?? '')
    const files = status.status === 'AVAILABLE' && status.realPath !== undefined
      ? await listLibraryFiles(status.realPath)
      : []
    return { status, files }
  }

  /**
   * Inspect vault availability without touching any file.
   * @returns the same status object the model tool reports.
   */
  @Remote('status')
  status(): Promise<LibraryStatus> {
    return getLibraryStatus(this.vaultRoot ?? '')
  }

  /**
   * List the accessible library files with an optional depth cap.
   * @param request - Listing options.
   * @returns the sorted file metadata rows.
   * @throws {@link ProjectMemoryError} with `MEMORY_UNAVAILABLE` when no vault
   *   is configured or the vault is inaccessible.
   */
  @Remote('list')
  async list(request: MemoryLibraryListRequest): Promise<readonly LibraryFile[]> {
    if (this.vaultRoot === undefined) unavailableVault()
    return listLibraryFiles(this.vaultRoot, request.maxDepth !== undefined ? { maxDepth: request.maxDepth } : undefined)
  }

  /**
   * Read one library file for preview, with its real absolute on-disk path.
   * @param request - Relative path inside the vault (forward slashes).
   * @returns the file content and the absolute copy/reference target.
   * @throws {@link ProjectMemoryError} with the same codes as
   *   {@link readLibraryFile}; the absolute path is computed only after the
   *   path has passed the full containment and symlink validation.
   */
  @Remote('read')
  async read(request: MemoryLibraryReadRequest): Promise<MemoryLibraryReadResult> {
    if (this.vaultRoot === undefined) unavailableVault()
    const content = await readLibraryFile(this.vaultRoot, request.relativePath)
    const realRoot = await realpath(this.vaultRoot)
    return { relativePath: request.relativePath, absolutePath: join(realRoot, request.relativePath), content }
  }

  /**
   * Search the library by name and text content from the UI.
   * @param request - Non-empty query and an optional result cap.
   * @returns the bounded search hits.
   * @throws {@link ProjectMemoryError} with the same codes as
   *   {@link searchLibrary}.
   */
  @Remote('search')
  async search(request: MemoryLibrarySearchRequest): Promise<readonly LibrarySearchResult[]> {
    if (this.vaultRoot === undefined) unavailableVault()
    return searchLibrary(this.vaultRoot, request.query, request.maxResults !== undefined ? { maxResults: request.maxResults } : undefined)
  }
}
