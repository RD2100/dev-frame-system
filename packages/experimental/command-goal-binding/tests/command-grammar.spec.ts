import { describe, expect, it } from 'vitest'
import { SourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { CompletionChecksRejection, CompletionFingerprintRejection, CompletionReviewRejection } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import {
  COMMAND_NAME,
  completionAdmissionEvidence,
  goalCompleteDescriptor,
  parseGoalCompleteInput,
  renderCompletionRejection,
  renderCompletionSuccess,
} from '../src/command.ts'
import type { RequiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'

/** One required-checks rejection over a single unsatisfied check. */
function checksRejection(): CompletionChecksRejection {
  return {
    kind: 'rejected',
    stage: 'required-checks',
    verdict: {
      kind: 'unsatisfied',
      digest: 'dsh-required-checks-v1-0'.repeat(4) as RequiredChecksDigest,
      violations: [{ reason: 'REQUIRED_CHECKS_NOT_PASSED', checkId: 'lint', status: 'failed' }],
    },
  }
}

/** One source-fingerprint rejection carrying both dual-value sides. */
function fingerprintRejection(): CompletionFingerprintRejection {
  return {
    kind: 'rejected',
    stage: 'source-fingerprint',
    mismatch: {
      kind: 'mismatch',
      recordedFingerprint: SourceFingerprint('dsh-source-fp-v2-aa-recorded'),
      computed: {
        fingerprint: SourceFingerprint('dsh-source-fp-v2-bb-computed'),
        headCommit: '0'.repeat(40),
        stateHash: '1'.repeat(64),
        entryCount: 1,
        algorithm: 'v2',
      },
    },
  }
}

/** One review rejection with a blocking finding. */
function reviewRejection(): CompletionReviewRejection {
  return {
    kind: 'rejected',
    stage: 'review',
    reviewId: 'review-x' as CompletionReviewRejection['reviewId'],
    decision: 'changes_required',
    findings: [{ id: 'finding-1', severity: 'blocking', message: 'contract untested' }],
  }
}

describe('/goal-complete input grammar', () => {
  it('treats an empty line as the bare form and the remainder as one path', () => {
    expect(parseGoalCompleteInput('')).toBeUndefined()
    expect(parseGoalCompleteInput('   ')).toBeUndefined()
    expect(parseGoalCompleteInput('C:/repo with spaces')).toBe('C:/repo with spaces')
    expect(parseGoalCompleteInput('  D:/repo\t')).toBe('D:/repo')
  })

  it('exposes the descriptor without images', () => {
    expect(goalCompleteDescriptor()).toEqual({
      name: COMMAND_NAME,
      description: 'complete the current goal through the verified completion admission',
      input: { hint: '[<worktreePath>]' },
    })
  })
})

describe('/goal-complete verdict rendering', () => {
  it('renders each rejection stage without goal identities', () => {
    const fingerprintText = renderCompletionRejection(fingerprintRejection())
    expect(fingerprintText).toContain('source-fingerprint')
    expect(fingerprintText).not.toContain('dsh-source-fp-v2')

    const checksText = renderCompletionRejection(checksRejection())
    expect(checksText).toContain('required-checks')
    expect(checksText).toContain('lint: REQUIRED_CHECKS_NOT_PASSED')

    const reviewText = renderCompletionRejection(reviewRejection())
    expect(reviewText).toContain('review')
    expect(reviewText).toContain('changes_required')
    expect(reviewText).not.toContain('review-x')

    expect(renderCompletionSuccess()).not.toMatch(/goal-\d/i)
  })

  it('builds one bounded completion-admission evidence entry', () => {
    const evidence = completionAdmissionEvidence('goal-1', {
      kind: 'admitted',
      fingerprint: SourceFingerprint('dsh-source-fp-v1-aa'),
      requiredChecksDigest: 'dsh-required-checks-v1-0' as never,
    })
    expect(evidence.kind).toBe('completion-admission')
    expect(evidence.summary).toContain('recorded equals fresh')
    expect(evidence.summary).toContain('goal-1')
    expect(evidence.at).toBeGreaterThan(0)
  })
})
