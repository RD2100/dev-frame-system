/**
 * Honest subprocess execution face for DevFrame required checks: every check
 * the approved configuration declares runs exactly once as its exact command,
 * and each real process outcome is recorded verbatim — the exit code is the
 * only verdict signal, a failing check is honest evidence, and nothing is
 * retried or repaired.
 * @module @deepseek-ai/dsh-experimental-agent-evidence/check-runner
 */

import { execFile } from 'node:child_process'
import type { ExecFileOptions } from 'node:child_process'
import { promisify } from 'node:util'
import type { DevFrameCheckResult } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'

/**
 * Execute every configured required check; one real result per configured check, in config order.
 * @param config - The approved required-checks configuration to execute exactly.
 * @returns One result per configured check, in config order.
 */
export type RequiredChecksExecution =
  (config: DevFrameRequiredChecksConfig) => Promise<readonly DevFrameCheckResult[]>

/** Options of the reference subprocess execution face. */
export interface SubprocessExecutionOptions {
  /** Per-check wall-clock kill guard in ms; defaults to 600_000. */
  readonly timeoutMs?: number
}

/** Wall-clock kill guard applied to every check when the caller provides none. */
const DEFAULT_TIMEOUT_MS = 600_000

const execFileAsync = promisify(execFile)

/**
 * Build the reference subprocess execution face over one kill guard. Each
 * check spawns its configured executable with the configured argument vector
 * and working directory, all stdio ignored (this slice captures no output, so
 * `maxBuffer` truncation semantics cannot enter the result classification),
 * and never retries: a rejected check is recorded as failed evidence.
 * @param options - The per-check wall-clock kill guard in ms.
 * @returns An execution face recording one honest result per configured check.
 */
export function createSubprocessRequiredChecksExecution(
  options?: SubprocessExecutionOptions,
): RequiredChecksExecution {
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  return async config => {
    // Sequential in config order: the result order is the config order by
    // construction, and concurrent spawns of the same workspace are avoided.
    const results: DevFrameCheckResult[] = []
    for (const check of config.checks) {
      const startedAt = Date.now()
      try {
        await execFileAsync(check.executable, [...check.arguments], {
          cwd: check.cwd,
          timeout: timeoutMs,
          // Runtime Node honors `stdio` for execFile; the @types/node face
          // omits it. 'ignore' is the ruling, not an omission: this slice
          // captures no output (outputRef is deferred), so maxBuffer
          // truncation semantics cannot enter the result classification.
          stdio: ['ignore', 'ignore', 'ignore'],
        } as ExecFileOptions)
        results.push({
          checkId: check.checkId,
          executable: check.executable,
          arguments: [...check.arguments],
          cwd: check.cwd,
          status: 'passed',
          exitCode: 0,
          durationMs: Math.max(0, Date.now() - startedAt),
        })
      } catch (error: unknown) {
        // promisified execFile rejects with `killed` set on the timeout kill
        // (this face's only kill source) and carries the numeric exit code in
        // `code`; string-code rejections (ENOENT, ...) and signal deaths have
        // no exit code.
        const rejection = error as { readonly killed?: boolean; readonly code?: string | number }
        const timedOut = rejection.killed === true
        const exitCode = !timedOut && typeof rejection.code === 'number' ? rejection.code : undefined
        results.push({
          checkId: check.checkId,
          executable: check.executable,
          arguments: [...check.arguments],
          cwd: check.cwd,
          status: timedOut ? 'timed_out' : exitCode === undefined ? 'unknown' : 'failed',
          ...(exitCode === undefined ? {} : { exitCode }),
          durationMs: Math.max(0, Date.now() - startedAt),
        })
      }
    }
    return results
  }
}

/** The default reference execution face (10-minute kill guard). */
export const subprocessRequiredChecksExecution: RequiredChecksExecution =
  createSubprocessRequiredChecksExecution()
