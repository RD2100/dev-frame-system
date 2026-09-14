/**
 * The project-memory vocabulary: namespaces, note metadata, tool request and
 * result shapes, limits, retry policy, and the receipt-store seam. Types and
 * the durable receipt shape only — validation and filesystem behavior live in
 * `./notes.ts`, `./vault.ts`, and `./memory.ts`.
 * @module @deepseek-ai/dsh-experimental-project-memory/types
 */

import type { Branded } from '@deepseek-ai/dsh-brand'
import type { NoteId } from './ids.ts'

/** Identifies one committed append receipt across the receipt store seam. */
export type MemoryReceiptKey = Branded<'MemoryReceiptKey'>

/**
 * The two memory namespaces a tool call may select. `scope` never accepts an
 * arbitrary path: `project` resolves to the calling workspace's own
 * directory, `user` to the explicitly allowed user memory directory.
 */
export type MemoryScope = 'project' | 'user'

/** The four note kinds of the memory design. */
export type NoteKind = 'fact' | 'preference' | 'lesson' | 'question'

/**
 * The assertion status a note carries. Confirmed user preferences require a
 * direct human source; project observations keep their snapshot scope;
 * inferred lessons stay inferred — the service never promotes a status.
 */
export type AssertionStatus = 'confirmed' | 'observed' | 'inferred'

/** The on-disk schema version of the note file format. */
export const NOTE_SCHEMA_VERSION = 1

/**
 * Freshness of a note relative to the host-supplied current project
 * snapshot. A note that references a snapshot which differs from — or cannot
 * be verified against — the current project is `potentially_stale` and must
 * be verified before acting on it.
 */
export type MemoryFreshness = 'current' | 'potentially_stale'

/**
 * The relative namespace directory inside `<vault>/devframe-memory/`:
 * `user` for user memory, `projects/<workspaceId>` for one project.
 */
export type MemoryNamespace = 'user' | `projects/${string}`

/**
 * Host-derived metadata persisted in every note's front matter. Identity and
 * source fields come from the host; a model supplies candidate prose only.
 * `bodyDigest` identifies the exact stored body and distinguishes a complete
 * note from a partial (interrupted) write.
 */
export interface MemoryNoteMeta {
  /** On-disk schema version; readers reject unsupported versions. */
  readonly schema: number
  /** The host-derived stable note id (also the file name stem). */
  readonly noteId: NoteId
  /** Relative namespace directory the note lives in. */
  readonly namespace: MemoryNamespace
  /** What the note records. */
  readonly kind: NoteKind
  /** ISO-8601 creation instant, stamped once at exclusive create. */
  readonly createdAt: string
  /** Stable source session/event reference the note was derived from. */
  readonly source: string
  /** Optional source snapshot/version the observation applies to. */
  readonly snapshot?: string
  /** Assertion status carried unchanged from the append request. */
  readonly status: AssertionStatus
  /** Optional id of the same-namespace note this note explicitly supersedes. */
  readonly supersedes?: NoteId
  /**
   * Canonical entity tags the note is anchored to — the subjects it is
   * about, host-normalized from the model's proposals. The flat-file
   * equivalent of a knowledge graph's entity anchoring: `memory_search`
   * filters on them, and a project-scope note always carries its workspace.
   */
  readonly entities?: readonly string[]
  /** `sha256:<hex>` digest of the exact stored body. */
  readonly bodyDigest: string
}

/** A fully parsed, self-consistent note: metadata plus the stored body. */
export interface MemoryNote extends MemoryNoteMeta {
  /** The stored body text, byte-bounded at append time. */
  readonly body: string
}

/**
 * One committed append receipt, durably recorded in the DSH session log
 * before an append may return `created`. Readers compare the full file
 * against the receipt; editing the note's own metadata cannot replace it.
 */
export interface MemoryReceipt {
  /** The note the receipt confirms. */
  readonly noteId: NoteId
  /** Relative namespace directory recorded at commit time. */
  readonly namespace: MemoryNamespace
  /** Expected path relative to the Vault root, e.g. `devframe-memory/user/<id>.md`. */
  readonly relativePath: string
  /** `sha256:<hex>` digest of the complete note file bytes. */
  readonly digest: string
  /** ISO-8601 instant the receipt was committed. */
  readonly recordedAt: string
}

/**
 * Minimal persistence seam for append receipts. The host implements this
 * over the DSH session log (the design requires receipts to be durable
 * before `created`); tests use the in-memory store from `./receipt.ts`.
 * `read` answers `undefined` for a missing receipt instead of failing.
 */
export interface MemoryReceiptStore {
  /**
   * Read one note's committed receipt.
   * @param noteId - Note selecting the receipt.
   * @returns the stored receipt, or `undefined` when none was committed.
   */
  read(noteId: NoteId): Promise<MemoryReceipt | undefined>
  /**
   * Persist one receipt, replacing any earlier receipt for the same note.
   * @param receipt - Already validated receipt to store.
   * @returns resolution after the receipt is durable.
   */
  write(receipt: MemoryReceipt): Promise<void>
}

/** Bounded limits for notes, queries, and recall output (UTF-8 byte counting). */
export interface MemoryLimits {
  /** Maximum UTF-8 byte length of one note body (design default: 8 KiB). */
  readonly maxNoteBytes: number
  /** Maximum total returned content bytes per search call (design default: 16 KiB). */
  readonly maxReturnBytes: number
  /** Maximum search results per call (design default: 10). */
  readonly maxSearchResults: number
  /** Maximum candidate files scanned per search (design default: 200). */
  readonly maxCandidateFiles: number
  /** Maximum UTF-8 byte length of one search query (default: 2 KiB). */
  readonly maxQueryBytes: number
  /** Maximum UTF-8 byte length of one search excerpt (default: 256). */
  readonly maxExcerptBytes: number
}

/**
 * Bounded retry policy for transient read/append failures (design: three
 * attempts total, 1 s then 3 s apart). Permission errors, conflicts, and
 * incomplete notes are never retried.
 */
export interface MemoryRetryPolicy {
  /** Total attempts including the first; at least 1. */
  readonly maxAttempts: number
  /** Sleep before retry `i`, in milliseconds; exactly `maxAttempts - 1` entries. */
  readonly backoffMs: readonly number[]
}

/** Fully resolved service configuration; build once with `resolveMemorySpec`. */
export interface MemorySpec {
  /**
   * The user-selected Vault root, or `undefined` when memory is not
   * configured. Every operation on an unconfigured service reports
   * `MEMORY_UNAVAILABLE`; the service never creates the Vault root itself.
   */
  readonly vaultRoot: string | undefined
  /** Whether the user enabled appends; `false` keeps memory read-only. */
  readonly writeEnabled: boolean
  /** Whether user-scope memory is explicitly allowed for this instance. */
  readonly userScopeEnabled: boolean
  /** Host-derived native workspace identity of the calling session. */
  readonly workspaceId: string
  /** Host-derived current project snapshot, when known, for staleness marking. */
  readonly currentSnapshot: string | undefined
  /** Bounded limits, resolved to the documented defaults when omitted. */
  readonly limits: MemoryLimits
  /** Bounded retry policy, resolved to the documented defaults when omitted. */
  readonly retry: MemoryRetryPolicy
}

/** Request for `memory_search`. */
export interface MemorySearchRequest {
  /** Namespace to search; scope checks run before any note content is read. */
  readonly scope: MemoryScope
  /** Bounded text query matched against note bodies. */
  readonly query: string
  /** Optional entity tag filter: only notes anchored to this subject. */
  readonly entity?: string
  /** Optional result cap below the configured maximum. */
  readonly limit?: number
}

/** One search hit: identity, bounded excerpt, date, provenance, freshness. */
export interface MemorySearchHit {
  /** The matched note's host-issued id, usable with `memory_read`. */
  readonly noteId: NoteId
  /** Bounded excerpt around the first match; `…` marks a cut edge. */
  readonly excerpt: string
  /** ISO-8601 creation instant of the note. */
  readonly createdAt: string
  /** What the note records. */
  readonly kind: NoteKind
  /** Assertion status of the note. */
  readonly status: AssertionStatus
  /** Source snapshot the observation applies to, when recorded. */
  readonly snapshot: string | undefined
  /** Freshness relative to the current project snapshot. */
  readonly freshness: MemoryFreshness
  /** Stable source session/event reference (provenance). */
  readonly source: string
  /** Canonical entity tags the note is anchored to, when any. */
  readonly entities: readonly string[] | undefined
}

/** Result of `memory_search`. */
export interface MemorySearchResult {
  /** Hits in deterministic filename order, within result and byte budgets. */
  readonly hits: readonly MemorySearchHit[]
  /** Hits were dropped by the result cap or the total-byte budget. */
  readonly truncated: boolean
  /**
   * `false` when the candidate-file cap was reached before scanning the whole
   * namespace — coverage is partial and a missing hit must not be read as
   * "no matching knowledge exists anywhere".
   */
  readonly coverageComplete: boolean
}

/** Request for `memory_read`. */
export interface MemoryReadRequest {
  /** Namespace the id is expected in; no cross-namespace chasing. */
  readonly scope: MemoryScope
  /** Host-issued note id, e.g. from a search hit. */
  readonly noteId: string
}

/** Result of `memory_read`. */
export type MemoryReadResult =
  | { readonly status: 'found'; readonly note: MemoryNote; readonly verified: boolean | null }
  /**
   * The file disagrees with its committed receipt: shown, labeled, excluded
   * from automatic recall. `note` carries the recovered content when the
   * file is still structurally readable; `reason` explains the unreadable
   * case.
   */
  | { readonly status: 'memory_changed'; readonly note?: MemoryNote; readonly reason?: string }
  /** The recorded path holds an unparsable or self-inconsistent file, preserved for explicit repair. */
  | { readonly status: 'incomplete_note'; readonly reason: string }
  /** No file exists at the note's recorded path; nothing is chased across namespaces. */
  | { readonly status: 'memory_missing' }

/** Request for `memory_append`. */
export interface MemoryAppendRequest {
  /** Namespace to append into; append consent and role checks are host-owned. */
  readonly scope: MemoryScope
  /** Stable source event reference; retries reuse it unchanged. */
  readonly sourceRef: string
  /** What the note records. */
  readonly kind: NoteKind
  /** Bounded candidate body; retained unchanged across retries. */
  readonly body: string
  /** Assertion status, fixed by the host; the service never promotes it. */
  readonly assertionStatus: AssertionStatus
  /** Optional source snapshot/version the observation applies to. */
  readonly snapshot?: string
  /** Optional id of the same-namespace note this append supersedes (append-only). */
  readonly supersedes?: NoteId
  /**
   * Model-proposed entity tags the note should be anchored to. The host
   * canonicalizes them (normalize, validate, dedupe, secret-screen) and a
   * project-scope note always carries its workspace tag additionally.
   */
  readonly entities?: readonly string[]
  /**
   * Reference to the explicit human confirmation event; required when
   * appending a `confirmed` user preference — neither Shadow nor a
   * controller can promote its own inference into a confirmed preference.
   */
  readonly humanConfirmation?: string
}

/** Result of `memory_append`. */
export type MemoryAppendResult =
  | { readonly status: 'created'; readonly noteId: NoteId; readonly relativePath: string }
  /** The note already exists with matching content (retry, or concurrent append lost the race). */
  | { readonly status: 'already_exists'; readonly noteId: NoteId; readonly relativePath: string }
  /** A complete but different note occupies the derived path; neither version was modified. */
  | { readonly status: 'memory_conflict'; readonly noteId: NoteId; readonly relativePath: string }
  /** The file disagrees with its committed receipt; preserved, reported, not recreated. */
  | { readonly status: 'memory_changed'; readonly noteId: NoteId; readonly relativePath: string }
  /** The committed receipt's file is gone; reported at the recorded path, not recreated. */
  | { readonly status: 'memory_missing'; readonly noteId: NoteId; readonly relativePath: string }
  /** A partial (interrupted) write occupies the derived path; preserved for explicit repair. */
  | { readonly status: 'incomplete_note'; readonly noteId: NoteId; readonly relativePath: string }
