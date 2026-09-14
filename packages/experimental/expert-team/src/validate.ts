/**
 * Shared strict-value validators for the pack file parsers (`expert-md.ts`
 * and `team-yml.ts`): every check throws an {@link ExpertTeamError} carrying
 * the caller's stable code, so both parsers fail loud with pack-file detail.
 * @module @deepseek-ai/dsh-experimental-expert-team/validate
 */

import { ExpertTeamError } from './errors.ts'
import type { ExpertTeamErrorCode } from './types.ts'

/** Kebab-case id: segments of [a-z0-9] joined by single dashes. */
const KEBAB_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/**
 * Windows reserved device names, matched case-insensitively against the base
 * name before the first dot: a base name with any extension is still
 * reserved on Windows.
 */
const WINDOWS_RESERVED_DEVICE_NAMES = new Set([
  'aux',
  'con',
  'prn',
  'nul',
  ...['com', 'lpt'].flatMap(prefix => [1, 2, 3, 4, 5, 6, 7, 8, 9].map(digit => `${prefix}${digit}`)),
])

/** Maximum UTF-8 byte length of one kebab-case id. */
export const MAX_ID_BYTES = 64

/**
 * Detect control characters anywhere in one string: the C0 controls
 * (including newline and carriage return), the C1 controls, and DEL.
 * Single-line checks test for newline and carriage return explicitly first,
 * so their message stays specific.
 * @param value - String to scan.
 * @returns true when a control character is present.
 */
export function hasControlChar(value: string): boolean {
  return /\p{Cc}/u.test(value)
}

/**
 * Narrow one parsed YAML value to a plain object record.
 * @param value - Raw parsed value.
 * @returns true when the value is a non-null, non-array object.
 */
export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The one-dash line that opens and closes expert md front matter. */
export const FRONT_MATTER_DELIMITER = '---'

/**
 * Reject a parsed record with any key outside the allowed set, or any
 * required key missing. Key sets are exact: the pack file formats are fixed
 * vocabularies, so unknown keys are authoring mistakes that must fail loud.
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the record in error messages.
 * @param record - The parsed record.
 * @param required - Keys that must be present.
 * @param optional - Keys that may be present; anything else is rejected.
 */
export function requireExactKeys(
  code: ExpertTeamErrorCode,
  scope: string,
  record: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[],
): void {
  for (const key of Object.keys(record)) {
    if (!required.includes(key) && !optional.includes(key)) {
      throw new ExpertTeamError(`${scope} has unknown key: ${key}`, code)
    }
  }
  for (const key of required) {
    if (!(key in record)) {
      throw new ExpertTeamError(`${scope} is missing key: ${key}`, code)
    }
  }
}

/**
 * Validate one single-line scalar field: a non-empty, control-free string
 * within the caller's byte bound.
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the field in error messages.
 * @param value - Raw parsed value.
 * @param maxBytes - UTF-8 byte ceiling.
 * @returns the validated string.
 */
export function requireScalar(
  code: ExpertTeamErrorCode,
  scope: string,
  value: unknown,
  maxBytes: number,
): string {
  if (typeof value !== 'string') {
    throw new ExpertTeamError(`${scope} must be a string`, code)
  }
  if (value.trim().length === 0) {
    throw new ExpertTeamError(`${scope} must not be blank`, code)
  }
  if (value.includes('\n') || value.includes('\r')) {
    throw new ExpertTeamError(`${scope} must be a single line`, code)
  }
  if (hasControlChar(value)) {
    throw new ExpertTeamError(`${scope} must not contain control characters`, code)
  }
  if (Buffer.byteLength(value, 'utf8') > maxBytes) {
    throw new ExpertTeamError(`${scope} exceeds ${maxBytes} UTF-8 bytes`, code)
  }
  return value
}

/**
 * Validate one kebab-case id field on top of the single-line scalar rules.
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the field in error messages.
 * @param value - Raw parsed value.
 * @returns the validated id.
 */
export function requireKebabId(code: ExpertTeamErrorCode, scope: string, value: unknown): string {
  const id = requireScalar(code, scope, value, MAX_ID_BYTES)
  if (!KEBAB_PATTERN.test(id)) {
    throw new ExpertTeamError(`${scope} must be kebab-case ([a-z0-9] segments joined by dashes)`, code)
  }
  return id
}

/**
 * Validate one list of single-line strings: an array of non-empty, unique
 * items within the caller's bounds.
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the field in error messages.
 * @param value - Raw parsed value.
 * @param maxItems - Maximum entry count.
 * @param maxItemBytes - UTF-8 byte ceiling per item.
 * @returns the validated items.
 */
export function requireStringList(
  code: ExpertTeamErrorCode,
  scope: string,
  value: unknown,
  maxItems: number,
  maxItemBytes: number,
): readonly string[] {
  if (!Array.isArray(value)) {
    throw new ExpertTeamError(`${scope} must be an array`, code)
  }
  if (value.length > maxItems) {
    throw new ExpertTeamError(`${scope} exceeds ${maxItems} entries`, code)
  }
  const seen = new Set<string>()
  return value.map((item, index) => {
    const text = requireScalar(code, `${scope}[${index}]`, item, maxItemBytes)
    if (seen.has(text)) {
      throw new ExpertTeamError(`${scope} has duplicate entry: ${text}`, code)
    }
    seen.add(text)
    return text
  })
}

/**
 * Validate one artifact file name: a single safe path segment (no
 * separators, no dot segments) within the caller's byte bound. Windows name
 * hazards are rejected too: a colon (NTFS alternate data streams), a
 * reserved device base name with or without extension, and trailing dots or
 * spaces that Windows name normalization would silently drop.
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the field in error messages.
 * @param value - Raw parsed value.
 * @param maxBytes - UTF-8 byte ceiling.
 * @returns the validated file name.
 */
export function requirePathSegment(
  code: ExpertTeamErrorCode,
  scope: string,
  value: unknown,
  maxBytes: number,
): string {
  const name = requireScalar(code, scope, value, maxBytes)
  if (name === '.' || name === '..' || name.includes('/') || name.includes('\\')) {
    throw new ExpertTeamError(`${scope} must be a single path segment without separators`, code)
  }
  if (name.includes(':')) {
    throw new ExpertTeamError(`${scope} must not contain a colon (NTFS alternate data stream separator)`, code)
  }
  const deviceBase = (name.split('.', 1)[0] ?? '').toLowerCase()
  if (WINDOWS_RESERVED_DEVICE_NAMES.has(deviceBase)) {
    throw new ExpertTeamError(`${scope} must not use a Windows reserved device name: ${deviceBase}`, code)
  }
  if (name.endsWith('.') || name.endsWith(' ')) {
    throw new ExpertTeamError(`${scope} must not end with a dot or a space (Windows name normalization)`, code)
  }
  return name
}

/**
 * Validate one pack-relative path: forward slashes only, never absolute,
 * never escaping the pack (containment itself is enforced against the real
 * pack directory by the caller).
 * @param code - Stable error code to throw with.
 * @param scope - Human label of the field in error messages.
 * @param value - Raw parsed value.
 * @returns the validated relative path.
 */
export function requireRelativePath(
  code: ExpertTeamErrorCode,
  scope: string,
  value: unknown,
): string {
  const path = requireScalar(code, scope, value, 512)
  if (path.startsWith('/') || path.includes('\\') || /^[a-zA-Z]:/.test(path)) {
    throw new ExpertTeamError(`${scope} must be a pack-relative path using forward slashes`, code)
  }
  return path
}
