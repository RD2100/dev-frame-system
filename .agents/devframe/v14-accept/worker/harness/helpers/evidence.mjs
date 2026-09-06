/**
 * Acceptance harness evidence and verdict assembly (v14-accept worker, design
 * §1/§0). Every pass must hang on real run artifacts: raw exit codes, raw
 * stdout/stderr, and parsed session-log JSON written under the scenario's
 * `--out` directory; `verdict.json` records each check's pass/fail with the
 * evidence-relative path and any pinned current-state failure annotation.
 *
 * Exit code rule (documented contract across all scenario scripts):
 * - `0` = PASS: every check reproduced its documented expectation.
 * - `2` = FAIL: at least one check observed a real mismatch (a verdict).
 * - `3` = BLOCKED: the scenario's real surface cannot run in this environment
 *   (e.g. the S1 keyless pin); recorded with the precise blocking reason, not
 *   counted as a product failure.
 * - `4` = HARNESS_ERROR: the harness itself faulted (usage, boot, or unexpected
 *   exception) before producing a valid observation — not a scenario verdict.
 * @module harness/lib/evidence
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'

/** The exit-code contract every scenario script implements. */
export const EXIT_CODES = Object.freeze({
  PASS: 0,
  FAIL: 2,
  BLOCKED: 3,
  HARNESS_ERROR: 4,
})

/** The verdict vocabulary written into `verdict.json`. */
export const VERDICTS = Object.freeze({
  PASS: 'PASS',
  FAIL: 'FAIL',
  BLOCKED: 'BLOCKED',
  HARNESS_ERROR: 'HARNESS_ERROR',
})

/**
 * Build one check record. Evidence paths are recorded relative to `--out` with
 * posix separators so the lead's archive stays platform-neutral.
 * @param {object} spec - check description.
 * @param {string} spec.id - stable check id (design §2 numbering).
 * @param {string} spec.expectation - the documented expectation.
 * @param {boolean} spec.pass - whether the real observation matched.
 * @param {unknown} spec.observed - the real observation (verbatim).
 * @param {string} [spec.evidence] - evidence file path relative to `--out`.
 * @returns {{id: string, expectation: string, pass: boolean, observed: unknown,
 *   evidence?: string}} the check record.
 */
export function check({ id, expectation, pass, observed, evidence }) {
  return evidence === undefined
    ? { id, expectation, pass: Boolean(pass), observed }
    : { id, expectation, pass: Boolean(pass), observed, evidence }
}

/** Convert a path to posix separators for evidence records. */
export function toPosix(path) {
  return path.split('\\').join('/')
}

/**
 * Resolve the evidence-relative path (inside `--out`) of an absolute artifact
 * path, for embedding in verdict records.
 * @param {string} outDir - the scenario's `--out` directory.
 * @param {string} artifactPath - absolute artifact path.
 * @returns {string} posix-relative evidence path.
 */
export function evidencePath(outDir, artifactPath) {
  return toPosix(resolve(artifactPath).slice(resolve(outDir).length + 1))
}

/**
 * Write one text artifact under `--out`, creating parent directories. The
 * text is written verbatim (captured stdout/stderr must stay original).
 * @param {string} outDir - the scenario's `--out` directory.
 * @param {string} relPath - artifact path relative to `--out` (e.g.
 *   `s1/stderr.txt`).
 * @param {string} text - verbatim artifact content.
 * @returns {Promise<string>} the absolute artifact path.
 */
export async function writeTextOut(outDir, relPath, text) {
  const target = join(outDir, relPath)
  await mkdir(dirname(target), { recursive: true })
  await writeFile(target, text, 'utf8')
  return target
}

/**
 * Write one JSON artifact under `--out` (2-space indent, trailing newline).
 * @param {string} outDir - the scenario's `--out` directory.
 * @param {string} relPath - artifact path relative to `--out`.
 * @param {unknown} value - JSON-serializable artifact content.
 * @returns {Promise<string>} the absolute artifact path.
 */
export async function writeJsonOut(outDir, relPath, value) {
  return await writeTextOut(outDir, relPath, `${JSON.stringify(value, null, 2)}\n`)
}

/**
 * Read a JSON artifact if it exists (cross-phase handoff inside one `--out`).
 * @template T
 * @param {string} path - absolute artifact path.
 * @returns {Promise<T|undefined>} the parsed artifact, or `undefined` when
 *   the file does not exist.
 */
export async function readJsonIfExists(path) {
  try {
    return JSON.parse(await readFile(path, 'utf8'))
  } catch (error) {
    if (error?.code === 'ENOENT') return undefined
    throw error
  }
}

/**
 * Assemble the scenario verdict per design §0: a declared blocking condition
 * wins (BLOCKED with its precise reason); otherwise PASS only when every
 * check reproduced its expectation; otherwise FAIL.
 * @param {object} spec - verdict description.
 * @param {string} spec.scenario - scenario script name (e.g. `s1-headless-run`).
 * @param {Array<ReturnType<typeof check>>} spec.checks - every check record.
 * @param {{reason: string, probes?: unknown}|undefined} [spec.blocked] - the
 *   precise blocking condition, when the real surface cannot run.
 * @param {string[]} [spec.notes] - pinned current-state failure annotations
 *   and as-delivered caveats (recorded, never verdict-changing).
 * @returns {{task: string, scenario: string, verdict: string, generatedAt: string,
 *   checks: unknown[], blocked?: unknown, notes: string[]}} the verdict object.
 */
export function assembleVerdict({ scenario, checks, blocked, notes = [] }) {
  const verdict = blocked !== undefined
    ? VERDICTS.BLOCKED
    : checks.length > 0 && checks.every(entry => entry.pass)
      ? VERDICTS.PASS
      : VERDICTS.FAIL
  return {
    task: 'v14-accept',
    scenario,
    verdict,
    generatedAt: new Date().toISOString(),
    checks,
    ...(blocked !== undefined ? { blocked } : {}),
    notes,
  }
}

/**
 * Write `verdict.json` under `--out`.
 * @param {string} outDir - the scenario's `--out` directory.
 * @param {ReturnType<typeof assembleVerdict>} verdict - assembled verdict.
 * @returns {Promise<string>} the absolute verdict path.
 */
export async function writeVerdict(outDir, verdict) {
  return await writeJsonOut(outDir, 'verdict.json', verdict)
}

/**
 * Map a verdict to its process exit code.
 * @param {{verdict: string}} verdict - assembled verdict.
 * @returns {number} 0/2/3 per the module contract.
 */
export function exitCodeForVerdict(verdict) {
  switch (verdict.verdict) {
    case VERDICTS.PASS: return EXIT_CODES.PASS
    case VERDICTS.FAIL: return EXIT_CODES.FAIL
    case VERDICTS.BLOCKED: return EXIT_CODES.BLOCKED
    default: return EXIT_CODES.HARNESS_ERROR
  }
}

/**
 * Terminal handler for an unexpected harness fault: record the error verbatim
 * plus a HARNESS_ERROR verdict, and return the harness exit code.
 * @param {string} outDir - the scenario's `--out` directory.
 * @param {string} scenario - scenario script name.
 * @param {unknown} error - the thrown value.
 * @returns {Promise<number>} {@link EXIT_CODES.HARNESS_ERROR}.
 */
export async function recordHarnessError(outDir, scenario, error) {
  const message = error instanceof Error ? (error.stack ?? error.message) : String(error)
  await writeTextOut(outDir, 'harness-error.txt', `${message}\n`)
  await writeJsonOut(outDir, 'verdict.json', {
    task: 'v14-accept',
    scenario,
    verdict: VERDICTS.HARNESS_ERROR,
    generatedAt: new Date().toISOString(),
    checks: [],
    notes: [`harness fault before a valid observation (not a scenario verdict): ${message}`],
  })
  return EXIT_CODES.HARNESS_ERROR
}
