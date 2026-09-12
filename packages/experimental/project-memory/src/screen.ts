/**
 * Content screening for candidate note bodies: secret patterns, environment
 * dumps, and unsafe control characters. Screening reduces accidental
 * leakage; it is not a guarantee. Rejections name the matched rule only —
 * suspected secrets are never echoed into errors or logs.
 * @module @deepseek-ai/dsh-experimental-project-memory/screen
 */

/** Stable ids of the screening rules; safe to surface in errors and logs. */
export type ScreeningRuleId =
  | 'private-key-block'
  | 'credential-assignment'
  | 'bearer-token'
  | 'aws-access-key'
  | 'github-token'
  | 'slack-token'
  | 'deepseek-api-key'
  | 'environment-dump'
  | 'control-characters'
  | 'unpaired-surrogate'

/**
 * One screening rule. `pattern` runs against the whole body; a match rejects
 * the note. Rule ids are the only detail a rejection reveals.
 */
interface ScreeningRule {
  readonly id: ScreeningRuleId
  readonly pattern: RegExp
}

/**
 * The fixed rule set. Patterns are deliberately conservative against
 * incidental prose but catch the common credential shapes verbatim.
 */
/**
 * The fixed rule set, ordered most-specific first so a known credential
 * shape is reported by its own rule instead of the generic assignment
 * pattern. Patterns are deliberately conservative against incidental prose
 * but catch the common credential shapes verbatim.
 */
const RULES: readonly ScreeningRule[] = [
  { id: 'private-key-block', pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  { id: 'deepseek-api-key', pattern: /(?:DEEPSEEK[_-]?API[_-]?KEY\s*[:=])|sk-[A-Za-z0-9]{16,}/ },
  { id: 'aws-access-key', pattern: /AKIA[0-9A-Z]{16}/ },
  { id: 'github-token', pattern: /gh[pousr]_[A-Za-z0-9]{20,}/ },
  { id: 'slack-token', pattern: /xox[baprs]-[A-Za-z0-9-]{10,}/ },
  // Under /i the case-folded [a-z] and [A-Z] ranges coincide, so one range
  // carries both cases and the class holds no duplicates.
  { id: 'bearer-token', pattern: /Bearer\s+[a-z0-9\-_.~+/]{20,}/i },
  {
    id: 'credential-assignment',
    pattern: new RegExp(
      '(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|client[_-]?secret)' +
        '["\']?\\s*[:=]\\s*["\']?[^\\s"\']{8,}',
      'i',
    ),
  },
]

/** Minimum number of `KEY=value` lines that reads as a raw environment dump. */
const ENV_DUMP_LINE_THRESHOLD = 8

/**
 * Screen a candidate note body before it reaches the Vault.
 * @param body - Candidate body text.
 * @returns the matched rule id, or `undefined` when the body passes.
 */
export function screenNoteBody(body: string): ScreeningRuleId | undefined {
  for (const rule of RULES) {
    if (rule.pattern.test(body)) return rule.id
  }
  let envLines = 0
  for (const line of body.split('\n')) {
    if (/^[A-Z][A-Z0-9_]*=\S/.test(line)) envLines += 1
  }
  if (envLines >= ENV_DUMP_LINE_THRESHOLD) return 'environment-dump'
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/.test(body)) return 'control-characters'
  // A lone surrogate cannot be encoded as UTF-8; storing it would corrupt
  // the body digest on the next read.
  for (const char of body) {
    if (char.length === 1 && char >= '\uD800' && char <= '\uDFFF') return 'unpaired-surrogate'
  }
  return undefined
}
