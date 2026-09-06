/**
 * Required-checks completion policy: schema rejections at the parse boundary,
 * digest determinism, and pure comparison verdicts against real
 * `DevFrameCheckResult` evidence. The durable composition cases drive a real
 * `devframe/verification` payload through the production schema face, whose
 * coverage rule now rejects a weakened payload at decode time (self-declared
 * `requiredChecks` must hash to its claimed digest and be exactly executed by
 * the recorded checks) while the comparison face rejects the same executed
 * set independently — the two rejection layers are pinned side by side. The
 * configuration store cases cover the digest → configuration registration the
 * completion admission reads.
 * @module dsh-experimental-devframe/tests/required-checks
 */

import { describe, expect, it } from 'vitest'
import {
  acceptanceCheckComponent,
  decodeRequiredChecksConfig,
  evaluateRequiredChecks,
  MemoryRequiredChecksConfigStore,
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
  /** The self-declared coverage for one approved configuration. */
  function coverageFor(config: DevFrameRequiredChecksConfig) {
    return { config, digest: requiredChecksDigest(config) }
  }

  /** One untrusted `devframe/verification` payload carrying the executed checks. */
  function verificationPayload(
    checks: readonly DevFrameCheckResult[],
    coverage: ReturnType<typeof coverageFor> = coverageFor(CONFIG),
  ): Record<string, unknown> {
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
      requiredChecks: coverage,
      checks,
    }
  }

  it('evaluates checks decoded from a real devframe/verification payload', () => {
    const payload = verificationPayload(CONFIG.checks.map(check => executionFor(check)))
    const decoded = decodeDevFramePayload('devframe/verification', payload)
    expect(decoded.requiredChecks.digest).toBe(requiredChecksDigest(CONFIG))
    expect(evaluateRequiredChecks(CONFIG, decoded.checks))
      .toEqual({ kind: 'satisfied', digest: requiredChecksDigest(CONFIG) })
  })

  it('rejects a weakened payload at the durable schema level', () => {
    const weakened = [
      executionFor(UNIT, 'passed', { arguments: ['exec', 'vitest', 'run', '--silent'] }),
      executionFor(LINT),
    ]
    let caught: unknown
    try {
      decodeDevFramePayload('devframe/verification', verificationPayload(weakened))
    } catch (error) {
      caught = error
    }
    expect((caught as Error).message).toMatch(/DevFrame devframe\/verification payload is invalid/)
    // The coverage rule names both deviations: the swapped command under the
    // required name and the required check that never ran.
    expect(String((caught as Error).cause)).toContain('is not exactly executed')
    expect(String((caught as Error).cause)).toContain('typecheck')
  })

  it('keeps honest failed evidence decodable when every declared check ran exactly', () => {
    const failed = [executionFor(UNIT, 'failed'), executionFor(LINT), executionFor(TYPECHECK)]
    const decoded = decodeDevFramePayload('devframe/verification', verificationPayload(failed))
    expect(decoded.status).toBe('failed')
    // The schema enforces exact execution, not pass status: a declared check
    // that ran exactly and failed is honest failed evidence here. Passing is
    // the completion admission's judgment, not the schema's.
    expect(decoded.checks.map(check => check.status)).toEqual(['failed', 'passed', 'passed'])
  })

  it('rejects a coverage declaration whose digest does not match its configuration', () => {
    // The declared set is the full CONFIG, but the claimed identity is the
    // digest of a different (single-check) configuration — a fabricated
    // self-description the schema refuses to decode.
    const fabricated = { config: CONFIG, digest: requiredChecksDigest({ version: 1, checks: [UNIT] }) }
    const payload = verificationPayload(CONFIG.checks.map(check => executionFor(check)), fabricated)
    expect(() => decodeDevFramePayload('devframe/verification', payload))
      .toThrow(/DevFrame devframe\/verification payload is invalid/)
  })

  it('still rejects the same weakened executed set at the comparison face', () => {
    const weakened = [
      executionFor(UNIT, 'passed', { arguments: ['exec', 'vitest', 'run', '--silent'] }),
      executionFor(LINT),
    ]
    expect(violationsOf(evaluateRequiredChecks(CONFIG, weakened))).toEqual([
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

describe('required-checks configuration storage', () => {
  it('registers a configuration under its canonical digest and decodes it back', async () => {
    const store = new MemoryRequiredChecksConfigStore()
    const digest = await store.save(CONFIG)
    expect(digest).toBe(requiredChecksDigest(CONFIG))
    await expect(store.load(digest)).resolves.toEqual(CONFIG)
  })

  it('treats a repeated registration of the same set as the same registration', async () => {
    const store = new MemoryRequiredChecksConfigStore()
    const first = await store.save(CONFIG)
    const reordered: DevFrameRequiredChecksConfig = { version: 1, checks: [...CONFIG.checks].reverse() }
    const second = await store.save(reordered)
    expect(second).toBe(first)
    await expect(store.load(first)).resolves.toEqual(CONFIG)
  })

  it('fails loud when resolving an unregistered digest', async () => {
    const store = new MemoryRequiredChecksConfigStore()
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
    })
  })
})

describe('acceptance composition component', () => {
  it('contributes the canonical digest as the check-configuration component', () => {
    expect(acceptanceCheckComponent(CONFIG)).toBe(requiredChecksDigest(CONFIG))
    expect(acceptanceCheckComponent(CONFIG)).toMatch(/^dsh-required-checks-v1-[0-9a-f]{64}$/)
  })
})
