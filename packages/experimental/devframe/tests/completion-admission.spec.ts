/**
 * Completion admission conjunction: fingerprint match → required checks →
 * review pass, evaluated against a real git worktree and the in-memory
 * required-checks configuration store. The ordering cases pin the evidence
 * chain (the earliest failing stage rejects), and the structural-failure case
 * pins that store errors fail loud instead of turning into rejections.
 * @module dsh-experimental-devframe/tests/completion-admission
 */

import { afterEach, describe, expect, it } from 'vitest'
import { evaluateCompletionAdmission } from '../src/controller/goal-binding.ts'
import type { CompletionAdmissionRequest } from '../src/controller/goal-binding.ts'
import { MemoryRequiredChecksConfigStore, requiredChecksDigest } from '../src/required-checks.ts'
import { SourceFingerprint } from '../src/shared/types.ts'
import {
  CONFIG,
  createCommittedWorktree,
  drainWorktreeFixtures,
  executionFor,
  reviewEvent,
} from './completion-fixtures.ts'

afterEach(async () => {
  await drainWorktreeFixtures()
})

describe('evaluateCompletionAdmission', { timeout: 30_000 }, () => {
  // Every case is backed by real git process creation; the per-test budget
  // stays above the runner default to absorb lane contention on that cost.

  it('admits when the fingerprint matches, the checks cover the stored configuration, and the review passed', async () => {
    const fixture = await createCommittedWorktree()
    const verdict = await evaluateCompletionAdmission(await admissionRequest(fixture))
    expect(verdict).toEqual({
      kind: 'admitted',
      fingerprint: fixture.fingerprint,
      requiredChecksDigest: requiredChecksDigest(CONFIG),
    })
  })

  it('rejects at the source-fingerprint stage before consulting checks or review', async () => {
    const fixture = await createCommittedWorktree()
    const recordedClaim = SourceFingerprint('dsh-source-fp-v1-recorded-claim')
    const verdict = await evaluateCompletionAdmission(await admissionRequest(fixture, {
      sourceFingerprint: recordedClaim,
      checks: [],
      review: reviewEvent('changes_required'),
    }))
    expect(rejectionStage(verdict)).toBe('source-fingerprint')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'source-fingerprint') {
      throw new Error('expected a fingerprint rejection')
    }
    // Dual-value evidence: the recorded claim exactly as passed in, and the
    // fresh computation from the unchanged worktree.
    expect(verdict.mismatch.recordedFingerprint).toBe(recordedClaim)
    expect(verdict.mismatch.computed.fingerprint).toBe(fixture.fingerprint)
  })

  it('rejects at the required-checks stage before consulting the review', async () => {
    const fixture = await createCommittedWorktree()
    const weakenedLint = CONFIG.checks[0]
    if (weakenedLint === undefined) throw new Error('fixture configuration is malformed')
    const verdict = await evaluateCompletionAdmission(await admissionRequest(fixture, {
      checks: [
        executionFor(weakenedLint, 'passed', { arguments: ['run', 'lint', '--fix'] }),
        executionFor(CONFIG.checks[1]!),
      ],
      review: reviewEvent('changes_required'),
    }))
    expect(rejectionStage(verdict)).toBe('required-checks')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'required-checks') {
      throw new Error('expected a required-checks rejection')
    }
    expect(verdict.verdict.digest).toBe(requiredChecksDigest(CONFIG))
    expect(verdict.verdict.violations).toEqual([{
      reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
      checkId: weakenedLint.checkId,
      configured: { executable: weakenedLint.executable, arguments: weakenedLint.arguments, cwd: weakenedLint.cwd },
      executed: [{ executable: weakenedLint.executable, arguments: ['run', 'lint', '--fix'], cwd: weakenedLint.cwd }],
    }])
  })

  it('rejects at the review stage with the review evidence', async () => {
    const fixture = await createCommittedWorktree()
    const review = reviewEvent('changes_required')
    const verdict = await evaluateCompletionAdmission(await admissionRequest(fixture, { review }))
    expect(rejectionStage(verdict)).toBe('review')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'review') {
      throw new Error('expected a review rejection')
    }
    expect(verdict.reviewId).toBe(review.reviewId)
    expect(verdict.decision).toBe('changes_required')
    expect(verdict.findings).toEqual(review.findings)
  })

  it('propagates a failed store resolution fail-loud instead of inventing a rejection', async () => {
    const fixture = await createCommittedWorktree()
    await expect(evaluateCompletionAdmission(await admissionRequest(fixture, {
      requiredChecksStore: new MemoryRequiredChecksConfigStore(),
    }))).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
    })
  })
})

/** Build one admission request over a fresh store registration, with overrides. */
async function admissionRequest(
  fixture: Awaited<ReturnType<typeof createCommittedWorktree>>,
  overrides: Partial<CompletionAdmissionRequest> = {},
): Promise<CompletionAdmissionRequest> {
  const store = new MemoryRequiredChecksConfigStore()
  const digest = await store.save(CONFIG)
  return {
    worktreePath: fixture.root,
    sourceFingerprint: fixture.fingerprint,
    checks: CONFIG.checks.map(check => executionFor(check)),
    requiredChecksDigest: digest,
    requiredChecksStore: store,
    review: reviewEvent('pass'),
    ...overrides,
  }
}

/** Narrow a verdict to its rejection arm and assert the stage. */
function rejectionStage(verdict: Awaited<ReturnType<typeof evaluateCompletionAdmission>>): 'source-fingerprint' | 'required-checks' | 'review' {
  expect(verdict.kind).toBe('rejected')
  if (verdict.kind !== 'rejected') throw new Error('expected a rejection verdict')
  return verdict.stage
}
