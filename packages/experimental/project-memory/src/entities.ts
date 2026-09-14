/**
 * Entity-tag canonicalization for memory notes: the model proposes tags at
 * append time, the host normalizes and validates them. Tags anchor a note to
 * the subjects it is about — the flat-file stand-in for a knowledge graph's
 * entity nodes. Canonical form is lowercase, whitespace-collapsed, bounded,
 * and comma-free (commas are the on-disk list delimiter); tags ride the same
 * secret screening as bodies.
 * @module @deepseek-ai/dsh-experimental-project-memory/entities
 */

import { ProjectMemoryError } from './errors.ts'
import { screenNoteBody } from './screen.ts'

/** The most entity tags one note may carry. */
export const MAX_NOTE_ENTITIES = 8

/** The longest canonical form of one entity tag, in characters. */
export const MAX_ENTITY_CHARS = 64

/** Canonical tags are single-line, comma-free, and human-readable subjects. */
const ENTITY_PATTERN = /^[\p{L}\p{N}][\p{L}\p{N} _\-.:]{0,63}$/u

/**
 * Canonicalize model-proposed entity tags: trim, collapse inner whitespace,
 * lowercase, drop duplicates case-insensitively, and validate each tag's
 * shape and safety. Invalid or secret-bearing input fails loud with a
 * stable code — tags are metadata and never rewritten behind the caller's
 * back.
 * @param inputs - The raw tags proposed for one note.
 * @returns The canonical deduplicated tag list in first-proposed order.
 * @throws ProjectMemoryError with `MEMORY_INVALID_REQUEST` for shape
 *   violations and `MEMORY_CONTENT_REJECTED` when a tag trips secret
 *   screening.
 */
export function canonicalizeEntities(inputs: readonly string[]): string[] {
  const canonical: string[] = []
  const seen = new Set<string>()
  for (const input of inputs) {
    const tag = input.trim().replace(/\s+/g, ' ').toLowerCase()
    if (tag.length === 0) continue
    if (tag.length > MAX_ENTITY_CHARS) {
      throw new ProjectMemoryError(
        `entity tag exceeds ${String(MAX_ENTITY_CHARS)} characters: "${tag.slice(0, 32)}…"`,
        'MEMORY_INVALID_REQUEST',
      )
    }
    if (!ENTITY_PATTERN.test(tag) || tag.includes('..')) {
      throw new ProjectMemoryError(
        `entity tag is not a safe single subject: "${tag.slice(0, 32)}"`,
        'MEMORY_INVALID_REQUEST',
      )
    }
    const rule = screenNoteBody(tag)
    if (rule !== undefined) {
      throw new ProjectMemoryError(
        `entity tag rejected by content screening: matched rule "${rule}"`,
        'MEMORY_CONTENT_REJECTED',
      )
    }
    if (!seen.has(tag)) {
      seen.add(tag)
      canonical.push(tag)
    }
  }
  if (canonical.length > MAX_NOTE_ENTITIES) {
    throw new ProjectMemoryError(
      `a note carries at most ${String(MAX_NOTE_ENTITIES)} entity tags (got ${String(canonical.length)})`,
      'MEMORY_INVALID_REQUEST',
    )
  }
  return canonical
}

/**
 * Case-insensitive entity containment check against one note's canonical
 * tags: the requested tag is canonicalized the same way, so a filter query
 * matches regardless of the caller's casing or spacing.
 * @param entities - The note's canonical tags.
 * @param requested - The raw entity filter from a search request.
 * @returns `true` when the note carries the requested entity.
 */
export function entitiesInclude(entities: readonly string[] | undefined, requested: string): boolean {
  if (entities === undefined) return false
  const tag = requested.trim().replace(/\s+/g, ' ').toLowerCase()
  return entities.some(candidate => candidate === tag)
}
