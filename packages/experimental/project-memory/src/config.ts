/** Explicit spec resolution for the project-memory service boundary. */

import { ProjectMemoryError } from './errors.ts'
import { validateWorkspaceSegment } from './vault.ts'
import type { MemoryLimits, MemoryRetryPolicy, MemorySpec } from './types.ts'

/** The documented initial limits of `docs/detailDesign-part3.md` (tools section). */
export const DEFAULT_MEMORY_LIMITS: MemoryLimits = {
  maxNoteBytes: 8 * 1024,
  maxReturnBytes: 16 * 1024,
  maxSearchResults: 10,
  maxCandidateFiles: 200,
  maxQueryBytes: 2 * 1024,
  maxExcerptBytes: 256,
}

/** The documented initial retry policy of `docs/detailDesign-part4.md` (limits section). */
export const DEFAULT_MEMORY_RETRY: MemoryRetryPolicy = {
  maxAttempts: 3,
  backoffMs: [1_000, 3_000],
}

/** Caller-facing request for spec resolution; every field may be defaulted. */
export interface MemorySpecRequest {
  /** The user-selected Vault root; omitted when memory is not configured. */
  readonly vaultRoot?: string
  /** Whether the user enabled appends; defaults to `false` (read-only). */
  readonly writeEnabled?: boolean
  /** Whether user-scope memory is explicitly allowed; defaults to `false`. */
  readonly userScopeEnabled?: boolean
  /** Host-derived native workspace identity of the calling session. */
  readonly workspaceId: string
  /** Host-derived current project snapshot, when known. */
  readonly currentSnapshot?: string
  /** Limit overrides; each missing field keeps the documented default. */
  readonly limits?: Partial<MemoryLimits>
  /** Retry overrides; each missing field keeps the documented default. */
  readonly retry?: Partial<MemoryRetryPolicy>
}

/** Validate one finite positive integer. */
function requirePositiveInt(value: number, field: string): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new ProjectMemoryError(`${field} must be a positive integer`, 'MEMORY_INVALID_REQUEST')
  }
  return value
}

/**
 * Resolve the service spec explicitly at the package boundary: every default
 * is applied here, and `ProjectMemoryService` performs no hidden fallbacks.
 * @param request - Caller-facing configuration request.
 * @returns the resolved spec.
 * @throws {@link ProjectMemoryError} with code `MEMORY_INVALID_WORKSPACE_ID`
 * when the workspace id is not a safe path segment, or
 * `MEMORY_INVALID_REQUEST` when a limit or retry override is malformed.
 */
export function resolveMemorySpec(request: MemorySpecRequest): MemorySpec {
  const workspaceId = validateWorkspaceSegment(request.workspaceId)
  const limits: MemoryLimits = {
    maxNoteBytes: requirePositiveInt(
      request.limits?.maxNoteBytes ?? DEFAULT_MEMORY_LIMITS.maxNoteBytes,
      'limits.maxNoteBytes',
    ),
    maxReturnBytes: requirePositiveInt(
      request.limits?.maxReturnBytes ?? DEFAULT_MEMORY_LIMITS.maxReturnBytes,
      'limits.maxReturnBytes',
    ),
    maxSearchResults: requirePositiveInt(
      request.limits?.maxSearchResults ?? DEFAULT_MEMORY_LIMITS.maxSearchResults,
      'limits.maxSearchResults',
    ),
    maxCandidateFiles: requirePositiveInt(
      request.limits?.maxCandidateFiles ?? DEFAULT_MEMORY_LIMITS.maxCandidateFiles,
      'limits.maxCandidateFiles',
    ),
    maxQueryBytes: requirePositiveInt(
      request.limits?.maxQueryBytes ?? DEFAULT_MEMORY_LIMITS.maxQueryBytes,
      'limits.maxQueryBytes',
    ),
    maxExcerptBytes: requirePositiveInt(
      request.limits?.maxExcerptBytes ?? DEFAULT_MEMORY_LIMITS.maxExcerptBytes,
      'limits.maxExcerptBytes',
    ),
  }
  const maxAttempts = requirePositiveInt(
    request.retry?.maxAttempts ?? DEFAULT_MEMORY_RETRY.maxAttempts,
    'retry.maxAttempts',
  )
  const rawBackoff = request.retry?.backoffMs ?? DEFAULT_MEMORY_RETRY.backoffMs
  if (rawBackoff.length !== maxAttempts - 1 || rawBackoff.some(ms => !Number.isInteger(ms) || ms < 0)) {
    throw new ProjectMemoryError(
      'retry.backoffMs must hold exactly maxAttempts - 1 non-negative integers',
      'MEMORY_INVALID_REQUEST',
    )
  }
  return {
    vaultRoot: request.vaultRoot,
    writeEnabled: request.writeEnabled ?? false,
    userScopeEnabled: request.userScopeEnabled ?? false,
    workspaceId,
    currentSnapshot: request.currentSnapshot,
    limits,
    retry: { maxAttempts, backoffMs: [...rawBackoff] },
  }
}
