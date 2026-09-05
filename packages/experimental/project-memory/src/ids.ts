/** Branded note identity and the stable id derivation for project-memory. */

import { createHash } from 'node:crypto'
import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import { ProjectMemoryError } from './errors.ts'

/**
 * Identifies one memory note. The id is host-derived (never model-supplied)
 * from the note's namespace and source event reference, so a retry of the
 * same append lands on the same id and file. Ids are lowercase 64-hex
 * digests: the shape alone rejects traversal probes and path separators.
 */
export type NoteId = Branded<'MemoryNoteId'>

/** The maximum source-reference byte length accepted at the durable boundary. */
export const MAX_SOURCE_REF_BYTES = 512

/**
 * Validate a host-issued note id before applying its compile-time brand.
 * @param value - Candidate id, expected as the exact 64-hex digest shape.
 * @returns the same string, branded at compile time.
 * @throws {@link ProjectMemoryError} with code `MEMORY_INVALID_NOTE_ID`
 * when the value is not a lowercase 64-hex id (including traversal probes
 * such as `../x`, path separators, or uppercase hex).
 */
export function NoteId(value: string): NoteId {
  if (!/^[0-9a-f]{64}$/.test(value)) {
    throw new ProjectMemoryError(
      'note id must be a host-issued 64-hex id',
      'MEMORY_INVALID_NOTE_ID',
    )
  }
  return brandString<NoteId>(value)
}

/**
 * Validate a stable source event reference before it feeds id derivation or
 * durable note metadata.
 * @param value - Host-issued reference, e.g. a session/event identity.
 * @returns the same string, unchanged.
 * @throws {@link ProjectMemoryError} with code `MEMORY_INVALID_NOTE` when the
 * reference is empty, whitespace-only, padded, contains a NUL byte (the id
 * derivation separator), or exceeds 512 UTF-8 bytes.
 */
export function validateSourceRef(value: string): string {
  if (value.length === 0 || value.trim().length === 0 || value !== value.trim() || value.includes('\0')) {
    throw new ProjectMemoryError(
      'source reference must be a non-empty trimmed string without NUL',
      'MEMORY_INVALID_NOTE',
    )
  }
  if (Buffer.byteLength(value, 'utf8') > MAX_SOURCE_REF_BYTES) {
    throw new ProjectMemoryError(
      `source reference exceeds ${MAX_SOURCE_REF_BYTES} UTF-8 bytes`,
      'MEMORY_INVALID_NOTE',
    )
  }
  return value
}

/**
 * Derive the stable note id for one namespace and source event. The
 * derivation is deterministic: every retry of the same append derives the
 * same id, and different namespaces never collide on one file.
 * @param namespace - Relative namespace directory (`user` or
 *   `projects/<workspaceId>`), already validated.
 * @param sourceRef - Validated stable source event reference.
 * @returns the derived note id.
 */
export function deriveNoteId(namespace: string, sourceRef: string): NoteId {
  const digest = createHash('sha256').update(`${namespace}\0${sourceRef}`, 'utf8').digest('hex')
  return brandString<NoteId>(digest)
}
