/**
 * Note file format unit behavior: the serialize/parse round trip preserves
 * the body exactly, and broken files are classified as incomplete rather
 * than silently accepted.
 */

import { describe, expect, it } from 'vitest'
import { NoteId } from '../src/ids.ts'
import { digestTag, parseNote, serializeNote, truncateToByteLimit } from '../src/notes.ts'
import type { MemoryNoteMeta } from '../src/types.ts'

const META: MemoryNoteMeta = {
  schema: 1,
  noteId: NoteId('a'.repeat(64)),
  namespace: 'projects/ws-alpha',
  kind: 'fact',
  createdAt: '2026-02-07T12:00:00.000Z',
  source: 'session-alpha#event-1',
  status: 'observed',
  bodyDigest: '',
}

describe('note file round trip', () => {
  it('preserves the exact body across serialize and parse', () => {
    for (const body of [
      'plain body',
      'line one\nline two',
      'body ending with a newline\n',
      '部署脚本位于 scripts/deploy.ps1，😃 emoji',
      '',
    ]) {
      const contents = serializeNote({ ...META, bodyDigest: digestTag(body) }, body)
      const parsed = parseNote(contents)
      expect(parsed.ok).toBe(true)
      if (!parsed.ok) continue
      expect(parsed.body).toBe(body)
      expect(parsed.meta.noteId).toBe(META.noteId)
      expect(parsed.meta.namespace).toBe(META.namespace)
      expect(parsed.meta.schema).toBe(1)
    }
  })

  it('classifies unsupported versions and digest mismatches as incomplete', () => {
    const body = 'the body'
    const contents = serializeNote({ ...META, bodyDigest: digestTag(body) }, body)
    expect(parseNote(contents.replace('schema: 1', 'schema: 2')).ok).toBe(false)
    expect(parseNote(contents.replace('kind: fact', 'kind: rumour')).ok).toBe(false)
    expect(parseNote(contents.replace(/bodyDigest: sha256:[0-9a-f]{64}/, 'bodyDigest: sha256:' + 'b'.repeat(64))).ok)
      .toBe(false)
    expect(parseNote('not a note at all').ok).toBe(false)
  })

  it('truncates on whole code points only', () => {
    expect(truncateToByteLimit('abc', 2)).toBe('ab')
    expect(truncateToByteLimit('abc', 1)).toBe('a')
    expect(truncateToByteLimit('あああ', 7)).toBe('ああ') // 6 bytes; the third would overflow
    expect(truncateToByteLimit('😃x', 3)).toBe('') // the emoji alone is 4 bytes
    expect(truncateToByteLimit('😃x', 4)).toBe('😃')
    expect(truncateToByteLimit('a😃', 5)).toBe('a😃') // 1 + 4 fits exactly
    expect(truncateToByteLimit('a😃', 4)).toBe('a') // never split the surrogate pair
  })
})
