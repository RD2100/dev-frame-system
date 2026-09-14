/**
 * The opaque run identity minted by the orchestrator. A run id is also a
 * single path segment — it names the run directory under the configured
 * artifacts root — so its mint format is a format invariant, not a tunable.
 * @module @deepseek-ai/dsh-experimental-expert-team/ids
 */

import { brandString } from '@deepseek-ai/dsh-brand'
import type { Branded } from '@deepseek-ai/dsh-brand'
import { randomBytes } from 'node:crypto'

/** An opaque run identity, unique per mint and safe as one path segment. */
export type RunId = Branded<'dsh.RunId'>

/**
 * Mint one fresh run id: `run-<compact UTC instant>-<8 hex>`. The instant
 * keeps run directories roughly sortable in listings; the random suffix makes
 * concurrent mints and same-instant collisions across processes negligible.
 * @param now - Epoch milliseconds; defaults to the current time (injectable
 *   for tests).
 * @returns the minted id.
 */
export function mintRunId(now: number = Date.now()): RunId {
  const instant = new Date(now).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, '')
  return brandString<RunId>(`run-${instant}-${randomBytes(4).toString('hex')}`)
}

/**
 * Parse a model- or caller-supplied run id back to the branded form. The
 * check is a shape check (non-empty, no separators), not an existence check —
 * an unknown but well-formed id still fails the lookup with
 * `EXPERT_TEAM_RUN_UNKNOWN`.
 * @param value - Raw id string.
 * @returns the branded id.
 * @throws {@link Error} when the value is empty or not a single path segment.
 */
export function parseRunId(value: string): RunId {
  if (value.length === 0 || value.includes('/') || value.includes('\\')) {
    throw new Error(`run id must be a non-empty single path segment, got: ${JSON.stringify(value)}`)
  }
  return brandString<RunId>(value)
}
