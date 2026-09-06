/**
 * Required-checks completion policy: schema rejections at the parse boundary,
 * digest determinism, and pure comparison verdicts against real
 * `DevFrameCheckResult` evidence — including a durable `devframe/verification`
 * payload decoded through the production schema face to prove composition
 * without modifying the frozen event module. Durable enforcement points
 * (coverage inside the event schema, journal wiring, completion admission,
 * configuration storage) have no implementation anchor in this wave and stay
 * GAP-registered (.agents/devframe/p22/required-checks-design.md).
 * @module dsh-experimental-devframe/tests/required-checks
 */

import { describe, expect, it } from 'vitest'
import {
  decodeRequiredChecksConfig,
  evaluateRequiredChecks,
  RequiredChecksError,
  requiredChecksDigest,
  type DevFrameRequiredCheck,
  type DevFrameRequiredChecksConfig,
} from '../src/required-checks.ts'
import { decodeDevFramePayload } from '../src/events.ts'
import type { DevFrameCheckResult } from '../src/events.ts'
import type { RequiredCheckViolation, RequiredChecksVerdict } from '../src/required-checks.ts'

const UNIT: DevFrameRequiredCheck = {
  checkId: 'unit-tests',
  executable: 'pnpm',
  arguments: ['exec', 'vitest', 'run', 'packages/a'],
  cwd: 'C:/ws-at105',
}
const LINT: DevFrameRequiredCheck = {
  checkId: 'lint',
  executable: 'pnpm',
  arguments: ['run', 'lint'],
  cwd: 'C:/ws-at105',
}
const TYPECHECK: DevFrameRequiredCheck = {
  checkId: 'typecheck',
  executable: 'node',
  arguments: ['node_modules/typescript/bin/tsc', '-b'],
  cwd: 'C:/ws-at105',
}
const CONFIG: DevFrameRequiredChecksConfig = {
  version: 1,
  checks: [UNIT, LINT, TYPECHECK],
}

/** Build one real executed check result matching (or deviating from) a required check. */
function executionFor(
  check: DevFrameRequiredCheck,
  status: DevFrameCheckResult['status'] = 'passed',
  command: Partial<Pick<DevFrameRequiredCheck, 'executable' | 'arguments' | 'cwd'>> = {},
): DevFrameCheckResult {
  return {
    checkId: check.checkId,
    executable: command.executable ?? check.executable,
    arguments: command.arguments ?? [...check.arguments],
    cwd: command.cwd ?? check.cwd,
    status,
    ...(status === 'passed' ? { exitCode: 0 } : status === 'failed' ? { exitCode: 1 } : {}),
    durationMs: 12,
  }
}

/** Assert a rejection and return the stable error for code-level assertions. */
function invalidConfigError(value: unknown): RequiredChecksError {
  try {
    decodeRequiredChecksConfig(value)
  } catch (error) {
    expect(error).toBeInstanceOf(RequiredChecksError)
    return error as RequiredChecksError
  }
  throw new Error('expected decodeRequiredChecksConfig to reject the configuration')
}

/** Narrow a verdict to its reject arm and return the violations. */
function violationsOf(verdict: RequiredChecksVerdict): readonly RequiredCheckViolation[] {
  expect(verdict.kind).toBe('unsatisfied')
  if (verdict.kind !== 'unsatisfied') throw new Error('expected an unsatisfied verdict')
  return verdict.violations
}

describe('required-checks configuration parse boundary', () => {
  it('parses a well-formed configuration unchanged', () => {
    expect(decodeRequiredChecksConfig(CONFIG)).toEqual(CONFIG)
  })

  it('keeps argv hygiene unconstrained: empty-string arguments stay parseable', () => {
    const config: DevFrameRequiredChecksConfig = {
      version: 1,
      checks: [{ checkId: 'ext', executable: 'tool', arguments: ['', '--flag'], cwd: 'C:/ws' }],
    }
    expect(decodeRequiredChecksConfig(config)).toEqual(config)
  })

  it('names the offending path in the rejection message', () => {
    const error = invalidConfigError({ version: 1, checks: [{ ...UNIT, checkId: ' ' }] })
    expect(error.message).toContain('checks.0.checkId')
    expect(error.code).toBe('REQUIRED_CHECKS_INVALID_CONFIG')
  })

  it.each([
    ['an empty checks array', { version: 1, checks: [] }],
    ['duplicate check ids', { version: 1, checks: [UNIT, UNIT] }],
    ['a whitespace check id', { version: 1, checks: [{ ...UNIT, checkId: '  ' }] }],
    ['an empty executable', { version: 1, checks: [{ ...UNIT, executable: '' }] }],
    ['an untrimmed cwd', { version: 1, checks: [{ ...UNIT, cwd: ' C:/ws-at105' }] }],
    ['a wrong version', { version: 2, checks: [UNIT] }],
    ['an unknown top-level key', { ...CONFIG, extra: true }],
    ['an unknown check key', { version: 1, checks: [{ ...UNIT, timeoutMs: 30 }] }],
    ['a non-string argument', { version: 1, checks: [{ ...UNIT, arguments: ['--flag', 7] }] }],
    ['a non-object root', 'required-checks'],
    ['a missing checks field', { version: 1 }],
  ])('rejects %s with REQUIRED_CHECKS_INVALID_CONFIG', (_label, value) => {
    expect(invalidConfigError(value).code).toBe('REQUIRED_CHECKS_INVALID_CONFIG')
  })
})

describe('requiredChecksDigest', () => {
  it('is deterministic for the same configuration', () => {
    expect(requiredChecksDigest(CONFIG)).toBe(requiredChecksDigest(CONFIG))
  })

  it('ignores check array order and object key insertion order', () => {
    const reordered: DevFrameRequiredChecksConfig = { version: 1, checks: [TYPECHECK, UNIT, LINT] }
    const keyShuffled: DevFrameRequiredChecksConfig = {
      version: 1,
      checks: CONFIG.checks.map(check => ({
        cwd: check.cwd,
        arguments: [...check.arguments],
        executable: check.executable,
        checkId: check.checkId,
      })),
    }
    expect(requiredChecksDigest(reordered)).toBe(requiredChecksDigest(CONFIG))
    expect(requiredChecksDigest(keyShuffled)).toBe(requiredChecksDigest(CONFIG))
  })

  it('carries the canonical v1 shape', () => {
    expect(requiredChecksDigest(CONFIG)).toMatch(/^dsh-required-checks-v1-[0-9a-f]{64}$/)
  })

  it('changes on any semantic mutation', () => {
    const mutations: readonly DevFrameRequiredChecksConfig[] = [
      { ...CONFIG, checks: [UNIT, LINT, { ...TYPECHECK, checkId: 'typecheck-2' }] },
      { ...CONFIG, checks: [UNIT, LINT, { ...TYPECHECK, executable: 'npx' }] },
      { ...CONFIG, checks: [UNIT, LINT, { ...TYPECHECK, arguments: ['node_modules/typescript/bin/tsc'] }] },
      { ...CONFIG, checks: [UNIT, LINT, { ...TYPECHECK, arguments: ['-b', 'node_modules/typescript/bin/tsc'] }] },
      { ...CONFIG, checks: [UNIT, LINT, { ...TYPECHECK, cwd: 'C:/ws-at105-2' }] },
      { ...CONFIG, checks: [UNIT, LINT] },
      { ...CONFIG, checks: [UNIT, LINT, TYPECHECK, { checkId: 'extra', executable: 'pnpm', arguments: ['-v'], cwd: 'C:/ws-at105' }] },
    ]
    const baseline = requiredChecksDigest(CONFIG)
    for (const mutated of mutations) expect(requiredChecksDigest(mutated)).not.toBe(baseline)
  })
})

describe('evaluateRequiredChecks verdicts', () => {
  it('is satisfied when every required check ran exactly as approved, regardless of order', () => {
    const executed = [executionFor(TYPECHECK), executionFor(UNIT), executionFor(LINT)]
    expect(evaluateRequiredChecks(CONFIG, executed))
      .toEqual({ kind: 'satisfied', digest: requiredChecksDigest(CONFIG) })
  })

  it('ignores executed checks outside the configuration', () => {
    const extra: DevFrameCheckResult = {
      checkId: 'exploratory',
      executable: 'node',
      arguments: ['probe.js'],
      cwd: 'C:/ws-at105',
      status: 'failed',
      exitCode: 3,
      durationMs: 5,
    }
    const executed = [...CONFIG.checks.map(check => executionFor(check)), extra]
    expect(evaluateRequiredChecks(CONFIG, executed).kind).toBe('satisfied')
  })

  it('rejects a required check that was never executed', () => {
    const verdict = evaluateRequiredChecks(CONFIG, [executionFor(UNIT), executionFor(LINT)])
    expect(violationsOf(verdict)).toEqual([{ reason: 'REQUIRED_CHECKS_MISSING', checkId: TYPECHECK.checkId }])
  })

  it('presents both command sides when the checkId ran with a deviating command', () => {
    const alteredArguments = ['exec', 'vitest', 'run', '--silent']
    const otherArguments = ['exec', 'vitest', 'run', 'packages/b']
    const verdict = evaluateRequiredChecks(CONFIG, [
      executionFor(LINT),
      executionFor(TYPECHECK),
      executionFor(UNIT, 'passed', { arguments: alteredArguments }),
      executionFor(UNIT, 'passed', { arguments: otherArguments }),
    ])
    expect(violationsOf(verdict)).toEqual([{
      reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
      checkId: UNIT.checkId,
      configured: { executable: UNIT.executable, arguments: UNIT.arguments, cwd: UNIT.cwd },
      executed: [
        { executable: UNIT.executable, arguments: alteredArguments, cwd: UNIT.cwd },
        { executable: UNIT.executable, arguments: otherArguments, cwd: UNIT.cwd },
      ],
    }])
  })

  it.each(['altered executable', 'altered working directory'] as const)('rejects a weakening via %s', (vector) => {
    const command: Partial<Pick<DevFrameRequiredCheck, 'executable' | 'arguments' | 'cwd'>> = vector === 'altered executable'
      ? { executable: 'npx' }
      : { cwd: 'C:/ws-at105-sub' }
    const verdict = evaluateRequiredChecks(CONFIG, [
      executionFor(UNIT),
      executionFor(LINT, 'passed', command),
      executionFor(TYPECHECK),
    ])
    expect(violationsOf(verdict)).toEqual([{
      reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
      checkId: LINT.checkId,
      configured: { executable: LINT.executable, arguments: LINT.arguments, cwd: LINT.cwd },
      executed: [{
        executable: command.executable ?? LINT.executable,
        arguments: LINT.arguments,
        cwd: command.cwd ?? LINT.cwd,
      }],
    }])
  })

  it.each(['failed', 'skipped', 'timed_out', 'cancelled', 'unknown'] as const)(
    'rejects an exactly-executed check with status %s',
    (status) => {
      const config: DevFrameRequiredChecksConfig = { version: 1, checks: [UNIT] }
      const verdict = evaluateRequiredChecks(config, [executionFor(UNIT, status)])
      expect(violationsOf(verdict))
        .toEqual([{ reason: 'REQUIRED_CHECKS_NOT_PASSED', checkId: UNIT.checkId, status }])
    },
  )

  it('accumulates one violation per unsatisfied check in configuration order', () => {
    const config: DevFrameRequiredChecksConfig = { version: 1, checks: [TYPECHECK, UNIT, LINT] }
    const verdict = evaluateRequiredChecks(config, [executionFor(UNIT, 'skipped'), executionFor(LINT)])
    expect(violationsOf(verdict)).toEqual([
      { reason: 'REQUIRED_CHECKS_MISSING', checkId: TYPECHECK.checkId },
      { reason: 'REQUIRED_CHECKS_NOT_PASSED', checkId: UNIT.checkId, status: 'skipped' },
    ])
  })

  it('stays total on duplicate executed checkIds the durable schema would reject', () => {
    const config: DevFrameRequiredChecksConfig = { version: 1, checks: [UNIT] }
    const executed = [
      executionFor(UNIT, 'passed', { arguments: ['exec', 'vitest', 'run'] }),
      executionFor(UNIT),
    ]
    expect(evaluateRequiredChecks(config, executed))
      .toEqual({ kind: 'satisfied', digest: requiredChecksDigest(config) })
  })

  it('carries the evaluated configuration digest in the reject arm too', () => {
    const verdict = evaluateRequiredChecks(CONFIG, [])
    expect(verdict.kind).toBe('unsatisfied')
    if (verdict.kind !== 'unsatisfied') throw new Error('expected an unsatisfied verdict')
    expect(verdict.digest).toBe(requiredChecksDigest(CONFIG))
  })
})

describe('composition with the durable verification payload', () => {
  /** One untrusted `devframe/verification` payload carrying the executed checks. */
  function verificationPayload(checks: readonly DevFrameCheckResult[]): Record<string, unknown> {
    return {
      version: 1,
      verificationId: 'verification-p05checks',
      binding: {
        controllerSessionId: 'controller-p05checks',
        goalId: 'goal-p05checks',
        goalRevision: 2,
        taskIds: ['task-p05checks'],
        acceptanceHash: 'acceptance-p05checks',
        workspaceId: 'ws-p05checks',
        sourceFingerprint: 'source-p05checks',
        snapshotId: 'snapshot-p05checks',
      },
      snapshotId: 'snapshot-p05checks',
      status: checks.every(check => check.status === 'passed') ? 'passed' : 'failed',
      checks,
    }
  }

  it('evaluates checks decoded from a real devframe/verification payload', () => {
    const payload = verificationPayload(CONFIG.checks.map(check => executionFor(check)))
    const decoded = decodeDevFramePayload('devframe/verification', payload)
    expect(evaluateRequiredChecks(CONFIG, decoded.checks))
      .toEqual({ kind: 'satisfied', digest: requiredChecksDigest(CONFIG) })
  })

  it('rejects a weakened payload the event schema alone accepts', () => {
    const weakened = [
      executionFor(UNIT, 'passed', { arguments: ['exec', 'vitest', 'run', '--silent'] }),
      executionFor(LINT),
    ]
    const decoded = decodeDevFramePayload('devframe/verification', verificationPayload(weakened))
    // The GAP made executable: the durable schema has no coverage rule, so the
    // weakened payload decodes cleanly — the evaluation face is what rejects it.
    expect(decoded.checks).toHaveLength(2)
    const verdict = evaluateRequiredChecks(CONFIG, decoded.checks)
    expect(violationsOf(verdict)).toEqual([
      {
        reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
        checkId: UNIT.checkId,
        configured: { executable: UNIT.executable, arguments: UNIT.arguments, cwd: UNIT.cwd },
        executed: [{ executable: UNIT.executable, arguments: ['exec', 'vitest', 'run', '--silent'], cwd: UNIT.cwd }],
      },
      { reason: 'REQUIRED_CHECKS_MISSING', checkId: TYPECHECK.checkId },
    ])
  })
})
