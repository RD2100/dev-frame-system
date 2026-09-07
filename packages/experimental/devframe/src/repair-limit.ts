/**
 * Repair-round limit for the review-repair cycle (AT1-08).
 *
 * After the initial completion review requests changes, the controller may
 * return work to the worker for at most the configured number of
 * correction/retest/review rounds (`docs/detailDesign-part1.md`: resume the
 * same worker, invalidate the earlier evidence, and repeat checks and review
 * within the repair limit). The limit is a deployment-varying validated
 * `Config` field — never a hardcoded tunable — with the acceptance-defined
 * default of two rounds. Exhaustion is a data rejection: remaining issues
 * require human input, without a replacement-member or new-run bypass.
 * @module @deepseek-ai/dsh-experimental-devframe/repair-limit
 */

/** Deployment-varying repair-limit configuration. */
export interface RepairLimitConfig {
  /**
   * Maximum correction/retest/review rounds admitted after the initial
   * review. The default is the acceptance-defined value (AT1-08: 修复上限=2).
   */
  readonly repairLimit?: number
}

/**
 * The acceptance-defined default repair limit (AT1-08): at most two
 * correction/retest/review rounds follow the initial review. It is the
 * resolved value when {@link RepairLimitConfig.repairLimit} is unset, not a
 * bypass around configuration.
 */
export const DEFAULT_REPAIR_LIMIT = 2

/** Stable, machine-routable failure classifications for the repair-limit seam. */
export type RepairLimitErrorCode =
  /** A config or accounting value is outside its serviceable range. */
  | 'REPAIR_LIMIT_INVALID_CONFIG'

/** Structured failure from repair-limit configuration or accounting validation. */
export class RepairLimitError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: RepairLimitErrorCode

  /**
   * @param message - human-readable rejection reason.
   * @param code - stable machine-routable error classification.
   */
  constructor(message: string, code: RepairLimitErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'RepairLimitError'
    this.code = code
  }
}

/**
 * Resolve the validated repair limit from its configuration.
 * @param config - deployment-supplied repair-limit configuration; omitted
 *   fields resolve to {@link DEFAULT_REPAIR_LIMIT}.
 * @returns the validated repair limit (a positive safe integer).
 * @throws {@link RepairLimitError} with `REPAIR_LIMIT_INVALID_CONFIG` when
 *   `repairLimit` is set and not a positive safe integer — misconfiguration
 *   fails loud at load, never by falling back to the default.
 */
export function resolveRepairLimit(config: RepairLimitConfig = {}): number {
  const limit = config.repairLimit ?? DEFAULT_REPAIR_LIMIT
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new RepairLimitError(
      `repairLimit must be a positive safe integer, got ${String(limit)}`,
      'REPAIR_LIMIT_INVALID_CONFIG',
    )
  }
  return limit
}

/** Input for one repair-round admission decision. */
export interface RepairRoundRequest {
  /** The validated repair limit ({@link resolveRepairLimit}). */
  readonly repairLimit: number
  /** Rounds already charged to this Goal; the initial review consumes none. */
  readonly consumedRepairRounds: number
}

/** Admission arm: one more correction/retest/review round is allowed. */
export interface RepairRoundAdmitted {
  /** Discriminant tag of the {@link RepairRoundAdmission} union. */
  readonly kind: 'admitted'
  /** The 1-based round this admission charges. */
  readonly repairRound: number
  /** Rounds still available after this one. */
  readonly remainingRepairRounds: number
}

/**
 * Exhaustion arm: the limit is fully charged. Remaining issues require human
 * input through the human-authorized resume face — no replacement-member or
 * new-run bypass is available through this seam.
 */
export interface RepairRoundExhausted {
  /** Discriminant tag of the {@link RepairRoundAdmission} union. */
  readonly kind: 'rejected'
  /** Stable machine-routable exhaustion reason. */
  readonly reason: 'repair-limit-exhausted'
  /** The configured limit that was exhausted. */
  readonly repairLimit: number
  /** The rounds already charged when this admission was attempted. */
  readonly consumedRepairRounds: number
}

/** Discriminated union returned by {@link evaluateRepairRoundAdmission}. */
export type RepairRoundAdmission = RepairRoundAdmitted | RepairRoundExhausted

/**
 * Decide whether one more correction/retest/review round may start for a
 * Goal. A round is charged when it starts (on admission), not when its review
 * lands; the initial review consumes no round, so a limit of 2 admits exactly
 * the two cycles the acceptance scenario names.
 * @param request - the validated limit and the rounds already charged.
 * @returns an admitted verdict with the charged round number, or the
 *   exhaustion rejection as data.
 * @throws {@link RepairLimitError} with `REPAIR_LIMIT_INVALID_CONFIG` when the
 *   limit is not a positive safe integer or the consumed count is not a
 *   non-negative safe integer.
 */
export function evaluateRepairRoundAdmission(request: RepairRoundRequest): RepairRoundAdmission {
  const { repairLimit, consumedRepairRounds } = request
  if (!Number.isSafeInteger(repairLimit) || repairLimit < 1) {
    throw new RepairLimitError(
      `repairLimit must be a positive safe integer, got ${String(repairLimit)}`,
      'REPAIR_LIMIT_INVALID_CONFIG',
    )
  }
  if (!Number.isSafeInteger(consumedRepairRounds) || consumedRepairRounds < 0) {
    throw new RepairLimitError(
      `consumedRepairRounds must be a non-negative safe integer, got ${String(consumedRepairRounds)}`,
      'REPAIR_LIMIT_INVALID_CONFIG',
    )
  }
  if (consumedRepairRounds >= repairLimit) {
    return {
      kind: 'rejected',
      reason: 'repair-limit-exhausted',
      repairLimit,
      consumedRepairRounds,
    }
  }
  return {
    kind: 'admitted',
    repairRound: consumedRepairRounds + 1,
    remainingRepairRounds: repairLimit - consumedRepairRounds - 1,
  }
}
