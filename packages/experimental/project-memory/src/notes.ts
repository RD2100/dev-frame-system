/**
 * Note file serialization, strict parsing, digests, and UTF-8 byte
 * utilities. The file format is a fixed-key front matter block plus the body;
 * a `bodyDigest` in the front matter identifies the exact stored body so an
 * interrupted write is distinguishable from a complete note.
 * @module @deepseek-ai/dsh-experimental-project-memory/notes
 */

import { createHash } from 'node:crypto'
import { z } from 'zod'
import { NOTE_SCHEMA_VERSION, type MemoryNote, type MemoryNoteMeta } from './types.ts'
import { NoteId } from './ids.ts'
import type { MemoryNamespace } from './types.ts'

/**
 * SHA-256 of the UTF-8 encoding of one string, as lowercase hex.
 * @param value - String to digest.
 * @returns the lowercase hex digest.
 */
export function sha256Hex(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex')
}

/**
 * `sha256:<hex>` digest of one UTF-8 string, as stored in notes and receipts.
 * @param value - String to digest.
 * @returns the tagged digest.
 */
export function digestTag(value: string): string {
  return `sha256:${sha256Hex(value)}`
}

/**
 * UTF-8 byte length of one string.
 * @param value - String to measure.
 * @returns the UTF-8 byte length.
 */
export function utf8ByteLength(value: string): number {
  return Buffer.byteLength(value, 'utf8')
}

/**
 * Truncate a string to at most `maxBytes` UTF-8 bytes, dropping whole code
 * points only, so the result never ends inside a multi-byte sequence or a
 * surrogate pair.
 * @param value - String to truncate.
 * @param maxBytes - Byte ceiling.
 * @returns the longest prefix that fits, with every code point intact.
 */
export function truncateToByteLimit(value: string, maxBytes: number): string {
  if (utf8ByteLength(value) <= maxBytes) return value
  let bytes = 0
  let result = ''
  for (const char of value) {
    const charBytes = utf8ByteLength(char)
    if (bytes + charBytes > maxBytes) break
    bytes += charBytes
    result += char
  }
  return result
}

/** The namespace value persisted in front matter must match this shape. */
const namespaceSchema = z
  .string()
  .regex(/^user$|^projects\/[^/\\\0]+$/)
  .transform(value => value as MemoryNamespace)

/**
 * Durable shape of one note's front matter, cast onto the shared
 * {@link MemoryNoteMeta} contract so shape drift fails to compile.
 */
const noteMetaSchema = z
  .object({
    // The file stores `schema: 1` as text; convert it back to the number
    // before checking the supported version.
    schema: z
      .string()
      .refine(value => value === String(NOTE_SCHEMA_VERSION), { message: 'unsupported schema version' })
      .transform(value => Number(value)),
    noteId: z.string().regex(/^[0-9a-f]{64}$/).transform(value => NoteId(value)),
    namespace: namespaceSchema,
    kind: z.enum(['fact', 'preference', 'lesson', 'question']),
    createdAt: z
      .string()
      .refine(value => value === new Date(value).toISOString(), {
        message: 'createdAt must be a canonical ISO-8601 instant',
      }),
    source: z.string().min(1).refine(value => !/[\u0000-\u001F\u007F]/.test(value), {
      message: 'source must be a single line without control characters',
    }),
    snapshot: z.string().min(1).optional(),
    status: z.enum(['confirmed', 'observed', 'inferred']),
    supersedes: z.string().regex(/^[0-9a-f]{64}$/).transform(value => NoteId(value)).optional(),
    // On disk the tag list is one comma-separated line; the canonical form
    // bans commas inside a tag, so the split is unambiguous.
    entities: z
      .string()
      .transform(value => value.split(',').map(tag => tag.trim()).filter(tag => tag.length > 0))
      .optional(),
    bodyDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  })
  .strict() as z.ZodType<MemoryNoteMeta>

/** Parse one `key: value` front matter line, or `undefined` when malformed. */
function parseMetaLine(line: string): readonly [string, string] | undefined {
  const separator = line.indexOf(': ')
  if (separator <= 0) return undefined
  return [line.slice(0, separator), line.slice(separator + 2)] as const
}

/** Why a file is not a self-consistent complete note. */
export type NoteParseFailure =
  | { readonly reason: 'structure'; readonly detail: string }
  | { readonly reason: 'body-digest'; readonly detail: string }

/** Success or failure of parsing one note file's contents. */
export type NoteParseResult =
  | { readonly ok: true; readonly meta: MemoryNoteMeta; readonly body: string }
  | { readonly ok: false; readonly failure: NoteParseFailure }

/**
 * Serialize one note to its durable file contents: fixed-order front matter,
 * a blank line, then the body stored verbatim (no terminator is added, so
 * the body digest survives the round trip exactly). Deterministic for
 * identical metadata and body.
 * @param meta - Host-derived note metadata; `bodyDigest` must match `body`.
 * @param body - The exact body text to store.
 * @returns the full file contents.
 */
export function serializeNote(meta: MemoryNoteMeta, body: string): string {
  const lines = [
    '---',
    `schema: ${meta.schema}`,
    `noteId: ${meta.noteId}`,
    `namespace: ${meta.namespace}`,
    `kind: ${meta.kind}`,
    `createdAt: ${meta.createdAt}`,
    `source: ${meta.source}`,
    ...(meta.snapshot === undefined ? [] : [`snapshot: ${meta.snapshot}`]),
    `status: ${meta.status}`,
    ...(meta.supersedes === undefined ? [] : [`supersedes: ${meta.supersedes}`]),
    ...(meta.entities === undefined || meta.entities.length === 0
      ? []
      : [`entities: ${meta.entities.join(', ')}`]),
    `bodyDigest: ${meta.bodyDigest}`,
    '---',
    '',
    body,
  ]
  return lines.join('\n')
}

/**
 * Build the host-derived metadata for one candidate note.
 * @param args - Derived id, resolved namespace, request fields, and body.
 * @returns the metadata with `createdAt` stamped to now and `bodyDigest`
 *   computed over the body.
 */
export function buildNoteMeta(args: {
  readonly noteId: NoteId
  readonly namespace: MemoryNamespace
  readonly kind: MemoryNoteMeta['kind']
  readonly status: MemoryNoteMeta['status']
  readonly source: string
  readonly snapshot: string | undefined
  readonly supersedes: NoteId | undefined
  readonly entities: readonly string[] | undefined
  readonly body: string
}): MemoryNoteMeta {
  const meta: {
    schema: number
    noteId: NoteId
    namespace: MemoryNamespace
    kind: MemoryNoteMeta['kind']
    createdAt: string
    source: string
    snapshot?: string
    status: MemoryNoteMeta['status']
    supersedes?: NoteId
    entities?: readonly string[]
    bodyDigest: string
  } = {
    schema: NOTE_SCHEMA_VERSION,
    noteId: args.noteId,
    namespace: args.namespace,
    kind: args.kind,
    createdAt: new Date().toISOString(),
    source: args.source,
    status: args.status,
    bodyDigest: digestTag(args.body),
  }
  if (args.snapshot !== undefined) meta.snapshot = args.snapshot
  if (args.supersedes !== undefined) meta.supersedes = args.supersedes
  if (args.entities !== undefined && args.entities.length > 0) meta.entities = args.entities
  return meta
}

/**
 * Parse one note file's contents strictly. Structural failures and body
 * digest mismatches both mean the file is not a self-consistent complete
 * note; callers preserve it and report `incomplete_note` — a digest mismatch
 * proves a change or truncation, never which.
 * @param contents - Full file contents as UTF-8 text.
 * @returns the parsed note, or the parse failure.
 */
export function parseNote(contents: string): NoteParseResult {
  const lines = contents.split('\n')
  if (lines[0] !== '---') {
    return { ok: false, failure: { reason: 'structure', detail: 'missing front matter opening' } }
  }
  const meta: Record<string, string> = {}
  let index = 1
  for (; index < lines.length; index += 1) {
    const line = lines[index]
    if (line === undefined) break
    if (line === '---') {
      index += 1
      break
    }
    if (line.length === 0) {
      return { ok: false, failure: { reason: 'structure', detail: 'blank line inside front matter' } }
    }
    const pair = parseMetaLine(line)
    if (pair === undefined || meta[pair[0]] !== undefined) {
      return { ok: false, failure: { reason: 'structure', detail: `malformed front matter line: ${line.slice(0, 32)}` } }
    }
    meta[pair[0]] = pair[1]
  }
  // One blank line separates front matter from the body; tolerate its absence
  // so a body starting immediately after `---` still parses.
  if (lines[index] === '') index += 1
  const body = lines.slice(index).join('\n')
  let parsed: MemoryNoteMeta
  try {
    parsed = noteMetaSchema.parse(meta)
  } catch (error: unknown) {
    const detail = error instanceof z.ZodError
      ? error.issues.map(issue => issue.path.join('.') || 'front matter').join(', ')
      : 'invalid front matter'
    return { ok: false, failure: { reason: 'structure', detail } }
  }
  if (digestTag(body) !== parsed.bodyDigest) {
    return { ok: false, failure: { reason: 'body-digest', detail: 'body does not match its recorded digest' } }
  }
  return { ok: true, meta: parsed, body }
}

/**
 * Compare a complete existing note against a candidate append: retries and
 * lost concurrent races match on every host-derived field and the body
 * digest, while `createdAt` (stamped once at create) is deliberately not
 * compared.
 * @param existing - The parsed note occupying the derived path.
 * @param candidate - The candidate note for the same derived path.
 * @returns `true` when both record the same note content.
 */
export function sameNoteContent(existing: MemoryNote, candidate: MemoryNote): boolean {
  const sameEntities = (existing.entities === undefined && candidate.entities === undefined) ||
    (existing.entities !== undefined &&
      candidate.entities !== undefined &&
      existing.entities.length === candidate.entities.length &&
      existing.entities.every((tag, index) => tag === candidate.entities[index]))
  return (
    existing.noteId === candidate.noteId &&
    existing.namespace === candidate.namespace &&
    existing.kind === candidate.kind &&
    existing.source === candidate.source &&
    existing.status === candidate.status &&
    existing.snapshot === candidate.snapshot &&
    existing.supersedes === candidate.supersedes &&
    sameEntities &&
    existing.bodyDigest === candidate.bodyDigest
  )
}
