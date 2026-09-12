/**
 * The project memory service: the three bounded tools (`memory_search`,
 * `memory_read`, `memory_append`) over a real filesystem Vault subtree.
 *
 * Append is create-only and idempotent: note ids derive from namespace and
 * source event, retries keep the candidate body, a committed receipt is
 * checked before any create, and the receipt is durable before `created` is
 * returned. Reads verify the full file against the receipt, so externally
 * edited notes are reported (`memory_changed`) instead of silently recalled.
 * Permission errors, conflicts, and incomplete notes are never retried;
 * transient failures follow the bounded retry policy.
 *
 * @module @deepseek-ai/dsh-experimental-project-memory/memory
 */

import { open, readdir, readFile, stat, realpath } from 'node:fs/promises'
import { join } from 'node:path'
import { ProjectMemoryError } from './errors.ts'
import { deriveNoteId, NoteId, validateSourceRef } from './ids.ts'
import {
  buildNoteMeta,
  digestTag,
  parseNote,
  serializeNote,
  sameNoteContent,
  truncateToByteLimit,
  utf8ByteLength,
} from './notes.ts'
import { screenNoteBody } from './screen.ts'
import {
  ensureNamespaceDir,
  MEMORY_DIR,
  namespaceOf,
  noteRelativePath,
  resolveNoteFilePath,
} from './vault.ts'
import type {
  MemoryAppendRequest,
  MemoryAppendResult,
  MemoryFreshness,
  MemoryNamespace,
  MemoryNote,
  MemoryNoteMeta,
  MemoryReadRequest,
  MemoryReadResult,
  MemoryReceipt,
  MemoryReceiptStore,
  MemoryRetryPolicy,
  MemoryScope,
  MemorySearchHit,
  MemorySearchRequest,
  MemorySearchResult,
  MemorySpec,
} from './types.ts'

/** The receipt store seam supplied by the host at construction. */
export type ProjectMemoryReceipts = MemoryReceiptStore

/** Filesystem error codes that must never be retried (design: permission errors, conflicts). */
const NON_RETRYABLE_FS_CODES = new Set([
  'EACCES', 'EPERM', 'EROFS', 'EISDIR', 'ENOTDIR', 'EINVAL', 'EXDEV', 'EFBIG', 'ENAMETOOLONG',
])

/** Extract the `code` property of a Node filesystem error, when present. */
function fsErrorCode(error: unknown): string | undefined {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = (error as { readonly code?: unknown }).code
    if (typeof code === 'string') return code
  }
  return undefined
}

/**
 * Classify a filesystem failure for the bounded retry policy: `conflict`
 * errors propagate raw for create-only handling, `permanent` errors fail
 * immediately, everything else (including unknown codes) is transient.
 * Exported for the bounded-retry behavior tests.
 * @param error - The caught filesystem failure.
 * @returns the retry classification of the failure.
 */
export function classifyFsError(error: unknown): 'transient' | 'conflict' | 'permanent' {
  const code = fsErrorCode(error)
  if (code === 'EEXIST') return 'conflict'
  if (code !== undefined && NON_RETRYABLE_FS_CODES.has(code)) return 'permanent'
  return 'transient'
}

/** Wrap one filesystem failure as the service's explicit failure code. */
function wrapFsFailure(label: string, code: 'MEMORY_WRITE_FAILED' | 'MEMORY_UNAVAILABLE', error: unknown): ProjectMemoryError {
  if (code === 'MEMORY_WRITE_FAILED' && fsErrorCode(error) === 'ENOSYS') {
    return new ProjectMemoryError(
      `${label}: the filesystem provider cannot provide the required create-only operation; append is disabled`,
      'MEMORY_APPEND_DISABLED',
      { cause: error },
    )
  }
  return new ProjectMemoryError(`${label} failed on the vault filesystem`, code, { cause: error })
}

/** Sleep between bounded retries. */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

/**
 * Run one filesystem operation under the bounded retry policy. `conflict`
 * errors are rethrown raw (the caller distinguishes create races);
 * `ProjectMemoryError` passes through untouched. Exported for the
 * bounded-retry behavior tests.
 * @param policy - The configured attempt count and backoff schedule.
 * @param label - Operation label used in the wrapped failure message.
 * @param code - Explicit failure code the operation's errors map onto.
 * @param operation - The filesystem operation to run.
 * @returns the operation's first successful result.
 */
export async function withRetry<T>(
  policy: MemoryRetryPolicy,
  label: string,
  code: 'MEMORY_WRITE_FAILED' | 'MEMORY_UNAVAILABLE',
  operation: () => Promise<T>,
): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation()
    } catch (error: unknown) {
      if (error instanceof ProjectMemoryError) throw error
      const kind = classifyFsError(error)
      if (kind === 'conflict') throw error
      if (kind === 'permanent' || attempt >= policy.maxAttempts - 1) throw wrapFsFailure(label, code, error)
      await sleep(policy.backoffMs[attempt] ?? 0)
    }
  }
}

/**
 * Freshness of one note against the current project snapshot: a note with a
 * snapshot that differs from — or cannot be verified against — the current
 * project is potentially stale.
 */
function freshnessOf(snapshot: string | undefined, currentSnapshot: string | undefined): MemoryFreshness {
  if (snapshot === undefined) return 'current'
  if (currentSnapshot === undefined) return 'potentially_stale'
  return snapshot === currentSnapshot ? 'current' : 'potentially_stale'
}

/** Adjust slice bounds so neither edge splits a UTF-16 surrogate pair. */
function alignSurrogateBounds(value: string, start: number, end: number): readonly [number, number] {
  let alignedStart = start
  let alignedEnd = end
  while (
    alignedStart < alignedEnd &&
    value.charCodeAt(alignedStart) >= 0xdc00 &&
    value.charCodeAt(alignedStart) <= 0xdfff
  ) {
    alignedStart += 1
  }
  while (
    alignedEnd > alignedStart &&
    value.charCodeAt(alignedEnd - 1) >= 0xd800 &&
    value.charCodeAt(alignedEnd - 1) <= 0xdbff
  ) {
    alignedEnd -= 1
  }
  return [alignedStart, alignedEnd]
}

const ELLIPSIS_BYTES = utf8ByteLength('…')

/**
 * Build a bounded excerpt around the first match position, cutting only at
 * code-point boundaries and marking cut edges with `…`.
 */
function buildExcerpt(body: string, matchIndex: number, maxBytes: number): string {
  const [start, end] = alignSurrogateBounds(
    body,
    Math.max(0, matchIndex - 24),
    Math.min(body.length, matchIndex + 224),
  )
  const cutLeft = start > 0
  const cutRight = end < body.length
  const budget = maxBytes - (cutLeft ? ELLIPSIS_BYTES : 0) - (cutRight ? ELLIPSIS_BYTES : 0)
  const middle = truncateToByteLimit(body.slice(start, end), Math.max(1, budget))
  return `${cutLeft ? '…' : ''}${middle}${cutRight ? '…' : ''}`
}

/**
 * The project memory service. One instance is bound to one calling session's
 * workspace identity and allowed scopes; construct it with a spec resolved
 * by `resolveMemorySpec` and a host-owned receipt store.
 */
export class ProjectMemoryService {
  private readonly spec: MemorySpec
  private readonly receipts: ProjectMemoryReceipts

  /**
   * @param spec - Resolved service spec (vault root, consent, limits, retry).
   * @param receipts - Receipt store seam; the host implements it over the
   *   DSH session log so receipts survive restarts.
   */
  constructor(spec: MemorySpec, receipts: ProjectMemoryReceipts) {
    this.spec = spec
    this.receipts = receipts
  }

  /** The allowed namespaces: user memory only when explicitly enabled. */
  private assertScope(scope: MemoryScope): void {
    if (scope === 'user' && !this.spec.userScopeEnabled) {
      throw new ProjectMemoryError(
        'user-scope memory is not allowed for this instance',
        'MEMORY_SCOPE_FORBIDDEN',
      )
    }
  }

  /** The Vault root realpath, or an explicit `MEMORY_UNAVAILABLE` failure. */
  private async requireVaultRoot(): Promise<string> {
    const root = this.spec.vaultRoot
    if (root === undefined || root.length === 0) {
      throw new ProjectMemoryError('memory vault is not configured', 'MEMORY_UNAVAILABLE')
    }
    let stats
    try {
      stats = await stat(root)
    } catch (error: unknown) {
      throw new ProjectMemoryError('memory vault root is not an accessible directory', 'MEMORY_UNAVAILABLE', { cause: error })
    }
    if (!stats.isDirectory()) {
      throw new ProjectMemoryError('memory vault root is not a directory', 'MEMORY_UNAVAILABLE')
    }
    try {
      return await realpath(root)
    } catch (error: unknown) {
      throw new ProjectMemoryError('memory vault root is not an accessible directory', 'MEMORY_UNAVAILABLE', { cause: error })
    }
  }

  /** The namespace directory of one scope, relative to the Vault root. */
  private namespace(scope: MemoryScope): MemoryNamespace {
    return namespaceOf(scope, this.spec.workspaceId)
  }

  /** Read one receipt, failing loud when the seam is unusable. */
  private async readReceipt(noteId: NoteId): Promise<MemoryReceipt | undefined> {
    try {
      return await this.receipts.read(noteId)
    } catch (error: unknown) {
      throw new ProjectMemoryError('receipt store read failed', 'MEMORY_RECEIPT_FAILED', { cause: error })
    }
  }

  /** Commit one receipt; a failure here leaves the note file unconfirmed. */
  private async writeReceipt(receipt: MemoryReceipt): Promise<void> {
    try {
      await this.receipts.write(receipt)
    } catch (error: unknown) {
      throw new ProjectMemoryError(
        'append receipt could not be committed; the note file stays unconfirmed',
        'MEMORY_RECEIPT_FAILED',
        { cause: error },
      )
    }
  }

  /** Read a note file under the bounded retry policy. */
  private async readNoteFile(path: string): Promise<string> {
    return await withRetry(this.spec.retry, 'note read', 'MEMORY_UNAVAILABLE', () => readFile(path, 'utf8'))
  }

  /**
   * Read a note for append-path evaluation, allowing a bounded stabilization
   * window: a concurrent writer of the same derived path may still be
   * flushing when the exclusive create loses its race, and that in-flight
   * write must not be misreported as an interrupted (incomplete) note. A
   * genuinely interrupted write stays incomplete after the window and is
   * then reported for explicit repair.
   */
  private async readExistingForAppend(path: string): Promise<readonly [string, ReturnType<typeof parseNote>]> {
    const stabilizeAttempts = 5
    let contents = await this.readNoteFile(path)
    let parsed = parseNote(contents)
    for (let attempt = 0; !parsed.ok && attempt < stabilizeAttempts; attempt += 1) {
      await sleep(50)
      contents = await this.readNoteFile(path)
      parsed = parseNote(contents)
    }
    return [contents, parsed] as const
  }

  /**
   * Verify a complete note's file against its committed receipt.
   * @returns `true` (verified), `false` (receipt disagrees), or `null` (no receipt).
   */
  private verifyReceipt(contents: string, receipt: MemoryReceipt | undefined, relativePath: string): boolean | null {
    if (receipt === undefined) return null
    return receipt.digest === digestTag(contents) && receipt.relativePath === relativePath
  }

  /**
   * Search one allowed namespace: deterministic filename order, bounded
   * candidate scan, bounded text matching, and explicit partial-coverage
   * reporting. Scope checks run before any note content is read; notes that
   * disagree with their receipt, are incomplete, or are superseded inside
   * the same namespace are excluded from automatic recall.
   * @param request - Scope, query text, and optional result cap.
   * @returns the bounded hits with coverage and truncation facts.
   */
  async search(request: MemorySearchRequest): Promise<MemorySearchResult> {
    this.assertScope(request.scope)
    const queryBytes = utf8ByteLength(request.query)
    if (queryBytes === 0) {
      throw new ProjectMemoryError('search query must be non-empty', 'MEMORY_INVALID_REQUEST')
    }
    if (queryBytes > this.spec.limits.maxQueryBytes) {
      throw new ProjectMemoryError(
        `search query exceeds ${this.spec.limits.maxQueryBytes} UTF-8 bytes`,
        'MEMORY_QUERY_TOO_LARGE',
      )
    }
    const limit = request.limit ?? this.spec.limits.maxSearchResults
    if (!Number.isInteger(limit) || limit <= 0 || limit > this.spec.limits.maxSearchResults) {
      throw new ProjectMemoryError(
        `result limit must be between 1 and ${this.spec.limits.maxSearchResults}`,
        'MEMORY_INVALID_REQUEST',
      )
    }
    const rootReal = await this.requireVaultRoot()
    const namespace = this.namespace(request.scope)
    const dir = join(rootReal, MEMORY_DIR, ...namespace.split('/'))
    let entries: string[]
    try {
      entries = await readdir(dir)
    } catch {
      // The subtree is created lazily by the first append; no notes exist yet.
      return { hits: [], truncated: false, coverageComplete: true }
    }
    const noteFiles = entries.filter(name => name.endsWith('.md')).sort((left, right) => left.localeCompare(right))
    const coverageComplete = noteFiles.length <= this.spec.limits.maxCandidateFiles
    const candidates = noteFiles.slice(0, this.spec.limits.maxCandidateFiles)

    const loweredQuery = request.query.toLowerCase()
    const superseded = new Set<NoteId>()
    const complete: { readonly meta: MemoryNoteMeta; readonly body: string }[] = []
    for (const name of candidates) {
      const contents = await this.readNoteFile(join(dir, name))
      const parsed = parseNote(contents)
      if (!parsed.ok) continue
      const receipt = await this.readReceipt(parsed.meta.noteId)
      const verified = this.verifyReceipt(contents, receipt, noteRelativePath(namespace, parsed.meta.noteId))
      if (verified === false) continue
      if (parsed.meta.supersedes !== undefined) superseded.add(parsed.meta.supersedes)
      complete.push({ meta: parsed.meta, body: parsed.body })
    }

    const hits: MemorySearchHit[] = []
    let truncated = false
    let usedBytes = 0
    for (const note of complete) {
      if (superseded.has(note.meta.noteId)) continue
      const matchIndex = note.body.toLowerCase().indexOf(loweredQuery)
      if (matchIndex < 0) continue
      const hit: MemorySearchHit = {
        noteId: note.meta.noteId,
        excerpt: buildExcerpt(note.body, matchIndex, this.spec.limits.maxExcerptBytes),
        createdAt: note.meta.createdAt,
        kind: note.meta.kind,
        status: note.meta.status,
        snapshot: note.meta.snapshot,
        freshness: freshnessOf(note.meta.snapshot, this.spec.currentSnapshot),
        source: note.meta.source,
      }
      const hitBytes = utf8ByteLength(JSON.stringify(hit))
      if (hits.length >= limit || usedBytes + hitBytes > this.spec.limits.maxReturnBytes) {
        truncated = true
        break
      }
      hits.push(hit)
      usedBytes += hitBytes
    }
    return { hits, truncated, coverageComplete }
  }

  /**
   * Read one note by host-issued id within one allowed namespace. Unknown
   * ids, missing files, changed files, and incomplete files are each
   * reported honestly; nothing is chased across namespaces.
   * @param request - Scope and the host-issued note id.
   * @returns the honest read outcome for the note.
   */
  async read(request: MemoryReadRequest): Promise<MemoryReadResult> {
    this.assertScope(request.scope)
    const noteId = NoteId(request.noteId)
    const rootReal = await this.requireVaultRoot()
    const namespace = this.namespace(request.scope)
    const relativePath = noteRelativePath(namespace, noteId)
    const target = await resolveNoteFilePath(rootReal, namespace, noteId)
    if (!target.exists) return { status: 'memory_missing' }
    const contents = await this.readNoteFile(target.path)
    const parsed = parseNote(contents)
    const receipt = await this.readReceipt(noteId)
    const verified = this.verifyReceipt(contents, receipt, relativePath)
    if (verified === false) {
      // The full file disagrees with the committed receipt: changed, shown,
      // excluded from automatic recall. The content is included when the
      // file is still structurally readable, and a digest mismatch proves a
      // change without telling whether it is a correction or corruption.
      return parsed.ok
        ? { status: 'memory_changed', note: { ...parsed.meta, body: parsed.body } }
        : { status: 'memory_changed', reason: parsed.failure.detail }
    }
    if (!parsed.ok) {
      return {
        status: 'incomplete_note',
        reason: parsed.failure.reason === 'structure'
          ? `malformed note file: ${parsed.failure.detail}`
          : parsed.failure.detail,
      }
    }
    const note: MemoryNote = { ...parsed.meta, body: parsed.body }
    return { status: 'found', note, verified }
  }

  /**
   * Append one note: validate, screen, derive the stable id, check the
   * committed receipt, then create the file exclusively and commit the
   * receipt before returning `created`. The candidate body is never
   * regenerated; conflicting or externally changed files are never modified.
   * @param request - Scope, stable source reference, kind, candidate body,
   *   assertion status, optional snapshot, and optional superseded note.
   * @returns the append outcome with the note id and expected path.
   */
  async append(request: MemoryAppendRequest): Promise<MemoryAppendResult> {
    if (!this.spec.writeEnabled) {
      throw new ProjectMemoryError('append is not enabled; memory is read-only', 'MEMORY_APPEND_DISABLED')
    }
    this.assertScope(request.scope)
    if (
      request.scope === 'user' &&
      request.kind === 'preference' &&
      request.assertionStatus === 'confirmed' &&
      (request.humanConfirmation === undefined || request.humanConfirmation.trim().length === 0)
    ) {
      throw new ProjectMemoryError(
        'a confirmed user preference requires a human confirmation reference',
        'MEMORY_INVALID_REQUEST',
      )
    }
    const body = request.body
    if (body.length === 0 || body.trim().length === 0) {
      throw new ProjectMemoryError('note body must be a non-empty string', 'MEMORY_INVALID_NOTE')
    }
    const bodyBytes = utf8ByteLength(body)
    if (bodyBytes > this.spec.limits.maxNoteBytes) {
      throw new ProjectMemoryError(
        `note body exceeds ${this.spec.limits.maxNoteBytes} UTF-8 bytes (got ${bodyBytes})`,
        'MEMORY_NOTE_TOO_LARGE',
      )
    }
    const rule = screenNoteBody(body)
    if (rule !== undefined) {
      throw new ProjectMemoryError(
        `note body rejected by content screening: matched rule "${rule}"`,
        'MEMORY_CONTENT_REJECTED',
      )
    }
    const sourceRef = validateSourceRef(request.sourceRef)
    const namespace = this.namespace(request.scope)
    const noteId = deriveNoteId(namespace, sourceRef)
    if (request.supersedes === noteId) {
      throw new ProjectMemoryError('a note cannot supersede itself', 'MEMORY_INVALID_NOTE')
    }
    const relativePath = noteRelativePath(namespace, noteId)
    const rootReal = await this.requireVaultRoot()
    const meta = buildNoteMeta({
      noteId,
      namespace,
      kind: request.kind,
      status: request.assertionStatus,
      source: sourceRef,
      snapshot: request.snapshot,
      supersedes: request.supersedes,
      body,
    })

    const receipt = await this.readReceipt(noteId)
    if (receipt !== undefined) {
      if (receipt.relativePath !== relativePath) {
        throw new ProjectMemoryError(
          'committed receipt disagrees with the derived note path',
          'MEMORY_RECEIPT_FAILED',
        )
      }
      const target = await resolveNoteFilePath(rootReal, namespace, noteId)
      if (!target.exists) return { status: 'memory_missing', noteId, relativePath }
      const contents = await this.readNoteFile(target.path)
      if (digestTag(contents) !== receipt.digest) return { status: 'memory_changed', noteId, relativePath }
      // Receipt and file agree: the note exists as committed. The candidate
      // still decides whether this retry matches it or conflicts with it.
      const parsed = parseNote(contents)
      if (!parsed.ok || sameNoteContent({ ...parsed.meta, body: parsed.body }, { ...meta, body })) {
        return { status: 'already_exists', noteId, relativePath }
      }
      return { status: 'memory_conflict', noteId, relativePath }
    }

    // Evaluate the derived path, then create exclusively; one re-evaluation
    // covers the lost-race window between check and create.
    for (let evaluation = 0; evaluation < 2; evaluation += 1) {
      const target = await resolveNoteFilePath(rootReal, namespace, noteId)
      if (target.exists) {
        const [contents, parsed] = await this.readExistingForAppend(target.path)
        if (!parsed.ok) return { status: 'incomplete_note', noteId, relativePath }
        if (sameNoteContent({ ...parsed.meta, body: parsed.body }, { ...meta, body })) {
          // Complete matching content is confirmed by the original append retry.
          await this.writeReceipt({
            noteId,
            namespace,
            relativePath,
            digest: digestTag(contents),
            recordedAt: new Date().toISOString(),
          })
          return { status: 'already_exists', noteId, relativePath }
        }
        return { status: 'memory_conflict', noteId, relativePath }
      }
      const created = await this.createNoteFile(rootReal, namespace, meta, body)
      if (created === 'exists') continue
      await this.writeReceipt({
        noteId,
        namespace,
        relativePath,
        digest: digestTag(serializeNote(meta, body)),
        recordedAt: new Date().toISOString(),
      })
      return { status: 'created', noteId, relativePath }
    }
    throw new ProjectMemoryError('note path kept changing during exclusive create', 'MEMORY_WRITE_FAILED')
  }

  /**
   * Exclusively create and flush one note file. The namespace directory is
   * created on demand; an `EEXIST` from the create-only open reports
   * `'exists'` so the caller re-evaluates the path instead of overwriting.
   */
  private async createNoteFile(
    rootReal: string,
    namespace: MemoryNamespace,
    meta: MemoryNoteMeta,
    body: string,
  ): Promise<'created' | 'exists'> {
    let dir: string
    try {
      dir = await withRetry(
        this.spec.retry,
        'namespace directory create',
        'MEMORY_WRITE_FAILED',
        () => ensureNamespaceDir(rootReal, namespace),
      )
    } catch (error: unknown) {
      if (error instanceof ProjectMemoryError) throw error
      throw wrapFsFailure('namespace directory create', 'MEMORY_WRITE_FAILED', error)
    }
    const filePath = join(dir, `${meta.noteId}.md`)
    const contents = serializeNote(meta, body)
    try {
      await withRetry(this.spec.retry, 'note create', 'MEMORY_WRITE_FAILED', async () => {
        const handle = await open(filePath, 'wx')
        try {
          await handle.writeFile(contents, 'utf8')
          await handle.sync()
        } finally {
          await handle.close()
        }
      })
    } catch (error: unknown) {
      if (fsErrorCode(error) === 'EEXIST') return 'exists'
      throw error
    }
    return 'created'
  }
}
