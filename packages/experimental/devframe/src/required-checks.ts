/**
 * Required-checks model for the DevFrame completion domain: the declared
 * checklist a verification must fully cover before evidence can claim
 * completion — the evidence basis for the AT1-05 "weakened required checks"
 * rejection variant.
 *
 * The human-approved configuration (one required check = a stable `checkId`
 * plus the exact command) is parsed by {@link requiredChecksConfigSchema},
 * digested by {@link requiredChecksDigest} (the canonical identity of the
 * approved set), and compared against real executed check results by
 * {@link evaluateRequiredChecks}. Like `verifySourceFingerprint`, the
 * evaluation is a pure, explicit face: it mutates nothing and never runs on
 * the binding hot path. Rejections are data — a discriminated verdict with
 * one violation per unsatisfied check — not throws; the error class covers
 * the parse boundary. The durable wiring (configuration storage, schema-level
 * coverage enforcement on `devframe/verification`, and the completion
 * admission that conjuncts this verdict with the review gate and the source
 * fingerprint verify) is registered as future work
 * (.agents/devframe/p22/required-checks-design.md).
 * @module @deepseek-ai/dsh-experimental-devframe/required-checks
 */

import { createHash } from 'node:crypto'
import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import { z } from 'zod'
import type { DevFrameCheckResult } from './events.ts'

/** Stable digest identity of one validated required-checks configuration. */
export type RequiredChecksDigest = Branded<'RequiredChecksDigest'>

/**
 * Brand a validated required-checks digest.
 * @param value - digest produced by {@link requiredChecksDigest}.
 * @returns the branded required-checks digest.
 */
export function RequiredChecksDigest(value: string): RequiredChecksDigest {
  return brandString<RequiredChecksDigest>(value)
}

/** The exact command identity one required check approves. */
export interface RequiredCheckCommand {
  /** Executable the host must invoke. */
  readonly executable: string
  /** Exact argument vector; element order is part of the command identity. */
  readonly arguments: readonly string[]
  /** Absolute working directory for the invocation. */
  readonly cwd: string
}

/** One host-approved command that must execute and pass before completion. */
export interface DevFrameRequiredCheck extends RequiredCheckCommand {
  /** Stable check identity; matched against `DevFrameCheckResult.checkId`. */
  readonly checkId: string
}

/** The human-approved checklist a verification must fully cover. */
export interface DevFrameRequiredChecksConfig {
  /** Configuration schema version. */
  readonly version: 1
  /** Required checks; ids are unique and array order carries no completion semantics. */
  readonly checks: readonly DevFrameRequiredCheck[]
}

/** Local mirror of the durable-event string primitive (events.ts keeps its own private). */
const trimmedString = z.string().min(1).refine(value => value === value.trim(), 'must be trimmed and non-empty')

const requiredCheckSchema = z.object({
  checkId: trimmedString,
  executable: trimmedString,
  // argv entries stay unconstrained: the weakening defense is exact command
  // equality against the durable evidence, not string hygiene (real CLIs
  // accept empty-string arguments).
  arguments: z.array(z.string()),
  cwd: trimmedString,
}).strict()

/**
 * Schema for one human-approved required-checks configuration. Strict, so
 * unapproved fields cannot ride along into the digest; `version` pins the
 * completion-policy generation.
 */
export const requiredChecksConfigSchema = z.object({
  version: z.literal(1),
  checks: z.array(requiredCheckSchema).min(1).refine(
    values => new Set(values.map(value => value.checkId)).size === values.length,
    'check ids must be unique',
  ),
}).strict() as z.ZodType<DevFrameRequiredChecksConfig>

/** Stable machine-routable classifications for required-checks decisions. */
export type RequiredChecksErrorCode =
  /** A required-checks configuration failed its schema at the parse boundary. */
  | 'REQUIRED_CHECKS_INVALID_CONFIG'
  /** A required check was never executed under its configured checkId. */
  | 'REQUIRED_CHECKS_MISSING'
  /** A check executed under the configured checkId with a different command. */
  | 'REQUIRED_CHECKS_COMMAND_MISMATCH'
  /** A check executed exactly as configured but its real status was not `passed`. */
  | 'REQUIRED_CHECKS_NOT_PASSED'

/**
 * Structured failure from required-checks parsing, aligned with the
 * `GoalBindingError`/`SourceFingerprintError` message+code shape. Policy
 * rejections (`REQUIRED_CHECKS_MISSING`, `REQUIRED_CHECKS_COMMAND_MISMATCH`,
 * `REQUIRED_CHECKS_NOT_PASSED`) travel as verdict violations, never as
 * throws; the future completion admission routes them through this same
 * code union.
 */
export class RequiredChecksError extends Error {
  /** Stable machine-routable classification of this failure. */
  readonly code: RequiredChecksErrorCode

  /**
   * @param message - human-readable failure reason with the schema issues where available.
   * @param code - stable machine-routable error classification.
   * @param options - standard Error options carrying the underlying cause.
   */
  constructor(message: string, code: RequiredChecksErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'RequiredChecksError'
    this.code = code
  }
}

/**
 * Parse one untrusted required-checks configuration at its durable boundary.
 * @param value - untrusted configuration value from host storage.
 * @returns the validated configuration.
 * @throws {@link RequiredChecksError} with `REQUIRED_CHECKS_INVALID_CONFIG`,
 *   carrying every schema issue in the message.
 */
export function decodeRequiredChecksConfig(value: unknown): DevFrameRequiredChecksConfig {
  const parsed = requiredChecksConfigSchema.safeParse(value)
  if (!parsed.success) {
    const summary = parsed.error.issues
      .map(issue => `${issue.path.map(String).join('.') || '(root)'}: ${issue.message}`)
      .join('; ')
    throw new RequiredChecksError(
      `required-checks configuration is invalid: ${summary}`,
      'REQUIRED_CHECKS_INVALID_CONFIG',
      { cause: parsed.error },
    )
  }
  return parsed.data
}

/** Pass arm of a required-checks verdict: every required check ran exactly as approved and passed. */
export interface RequiredChecksSatisfied {
  /** Discriminant tag of the discriminated {@link RequiredChecksVerdict} union. */
  readonly kind: 'satisfied'
  /** Canonical identity of the configuration this verdict evaluated. */
  readonly digest: RequiredChecksDigest
}

/** One unsatisfied required check in a {@link RequiredChecksUnsatisfied} verdict. */
export type RequiredCheckViolation =
  | RequiredChecksMissingViolation
  | RequiredChecksCommandMismatchViolation
  | RequiredChecksNotPassedViolation

/** A required check with no executed result under its configured checkId. */
export interface RequiredChecksMissingViolation {
  /** Stable rejection reason; the machine-routable discriminant of this arm. */
  readonly reason: 'REQUIRED_CHECKS_MISSING'
  /** checkId of the required check that was never executed. */
  readonly checkId: string
}

/** The configured checkId was executed, but never with the approved command. */
export interface RequiredChecksCommandMismatchViolation {
  /** Stable rejection reason; the machine-routable discriminant of this arm. */
  readonly reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH'
  /** checkId shared by the approved check and the deviating executions. */
  readonly checkId: string
  /** The approved command; the authority side of the comparison. */
  readonly configured: RequiredCheckCommand
  /** Every executed command that claimed this checkId, in execution order. */
  readonly executed: readonly RequiredCheckCommand[]
}

/** The approved command ran for real, but its status was not `passed`. */
export interface RequiredChecksNotPassedViolation {
  /** Stable rejection reason; the machine-routable discriminant of this arm. */
  readonly reason: 'REQUIRED_CHECKS_NOT_PASSED'
  /** checkId of the required check that did not pass. */
  readonly checkId: string
  /** Real status of the command-exact execution; `skipped` counts here. */
  readonly status: DevFrameCheckResult['status']
}

/** Reject arm of a required-checks verdict: at least one required check is missing, altered, or not passed. */
export interface RequiredChecksUnsatisfied {
  /** Discriminant tag of the discriminated {@link RequiredChecksVerdict} union. */
  readonly kind: 'unsatisfied'
  /** Canonical identity of the configuration this verdict evaluated. */
  readonly digest: RequiredChecksDigest
  /** One violation per unsatisfied required check, in configuration order. */
  readonly violations: readonly RequiredCheckViolation[]
}

/** Discriminated union returned by {@link evaluateRequiredChecks}. */
export type RequiredChecksVerdict = RequiredChecksSatisfied | RequiredChecksUnsatisfied

const DIGEST_PREFIX = 'dsh-required-checks-v1'

/**
 * Canonical identity of one validated configuration: sha256 over a JSON
 * canonicalization whose fields serialize in a fixed order and whose check
 * records are sorted (checkId uniqueness is schema-enforced, so the order is
 * total), prefixed with the algorithm generation. Two configurations holding
 * the same required set produce the same digest — object key insertion order
 * and check array order never vote — while any semantic change (a check
 * added, removed, renamed, or command-altered) changes it.
 * @param config - validated required-checks configuration.
 * @returns the branded digest `dsh-required-checks-v1-<sha256 hex>`.
 */
export function requiredChecksDigest(config: DevFrameRequiredChecksConfig): RequiredChecksDigest {
  const records = config.checks
    .map(check => JSON.stringify({
      checkId: check.checkId,
      executable: check.executable,
      arguments: [...check.arguments],
      cwd: check.cwd,
    }))
    .sort()
  const canonical = JSON.stringify({ version: config.version, checks: records })
  const digest = createHash('sha256').update(canonical, 'utf8').digest('hex')
  return RequiredChecksDigest(`${DIGEST_PREFIX}-${digest}`)
}

/** Exact command equality: no normalization, mirroring the branded-string equality of `verifySourceFingerprint`. */
function sameCommand(left: RequiredCheckCommand, right: RequiredCheckCommand): boolean {
  return left.executable === right.executable
    && left.cwd === right.cwd
    && left.arguments.length === right.arguments.length
    && left.arguments.every((argument, index) => argument === right.arguments[index])
}

/**
 * Completion-policy comparison for the AT1-05 "weakened required checks"
 * variant: decide whether the real executed check results fully cover the
 * approved configuration. A required check is satisfied only by an executed
 * result with the same `checkId` AND the exact same command (executable,
 * argument vector in order, cwd — no normalization, so a swapped script or
 * trimmed flag cannot pass under a required name) AND the real status
 * `passed`. Executed checks outside the configuration are ignored: the
 * config declares what is required, not what is permitted. The verdict
 * carries the configuration digest in both arms so it is self-describing
 * evidence.
 * @param config - validated required-checks configuration (the approved authority side).
 * @param executed - real check results, typically `checks` from a decoded `devframe/verification` payload.
 * @returns a {@link RequiredChecksSatisfied} verdict, or a
 *   {@link RequiredChecksUnsatisfied} verdict with one violation per
 *   unsatisfied required check in configuration order.
 */
export function evaluateRequiredChecks(
  config: DevFrameRequiredChecksConfig,
  executed: readonly DevFrameCheckResult[],
): RequiredChecksVerdict {
  const digest = requiredChecksDigest(config)
  const violations: RequiredCheckViolation[] = []
  for (const required of config.checks) {
    const candidates = executed.filter(result => result.checkId === required.checkId)
    if (candidates.length === 0) {
      violations.push({ reason: 'REQUIRED_CHECKS_MISSING', checkId: required.checkId })
      continue
    }
    const matching = candidates.find(result => sameCommand(result, required))
    if (matching === undefined) {
      violations.push({
        reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
        checkId: required.checkId,
        configured: { executable: required.executable, arguments: [...required.arguments], cwd: required.cwd },
        executed: candidates.map(result => ({
          executable: result.executable,
          arguments: [...result.arguments],
          cwd: result.cwd,
        })),
      })
      continue
    }
    if (matching.status !== 'passed') {
      violations.push({ reason: 'REQUIRED_CHECKS_NOT_PASSED', checkId: required.checkId, status: matching.status })
    }
  }
  if (violations.length === 0) return { kind: 'satisfied', digest }
  return { kind: 'unsatisfied', digest, violations }
}
