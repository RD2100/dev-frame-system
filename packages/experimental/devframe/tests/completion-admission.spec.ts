/**
 * Completion admission conjunction: fingerprint match → required checks →
 * review pass, evaluated against a real git worktree and the in-memory
 * required-checks configuration store. The ordering cases pin the evidence
 * chain (the earliest failing stage rejects), and the structural-failure case
 * pins that store errors fail loud instead of turning into rejections.
 * @module dsh-experimental-devframe/tests/completion-admission
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { SessionId } from '@deepseek-ai/dsh-session'
import {
  ControllerSessionId,
  TaskId,
  evaluateCompletionAdmission,
} from '../src/controller/goal-binding.ts'
import type { CompletionAdmissionRequest } from '../src/controller/goal-binding.ts'
import { DevFrameReviewId } from '../src/events.ts'
import type { DevFrameCheckResult, DevFrameReviewEventData } from '../src/events.ts'
import {
  MemoryRequiredChecksConfigStore,
  requiredChecksDigest,
} from '../src/required-checks.ts'
import type { DevFrameRequiredCheck, DevFrameRequiredChecksConfig } from '../src/required-checks.ts'
import { computeSourceFingerprint } from '../src/source-fingerprint.ts'
import {
  AcceptanceHash,
  DevFrameSnapshotId,
  SourceFingerprint,
  WorkspaceId,
} from '../src/shared/types.ts'

const execFileAsync = promisify(execFile)

const CONFIG: DevFrameRequiredChecksConfig = {
  version: 1,
  checks: [
    { checkId: 'lint', executable: 'pnpm', arguments: ['run', 'lint'], cwd: 'C:/ws-admission' },
    {
      checkId: 'typecheck',
      executable: 'node',
      arguments: ['node_modules/typescript/bin/tsc', '-b'],
      cwd: 'C:/ws-admission',
    },
  ],
}

/** Temp roots acquired by this file, drained to quiescence by afterEach. */
const tempRoots: string[] = []

afterEach(async () => {
  const roots = [...tempRoots]
  tempRoots.length = 0
  // Bounded linear backoff absorbs Windows EBUSY/EPERM handle contention; the
  // rm resolution is the completion signal — no sleeps.
  await Promise.all(roots.map(root => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })))
})

interface WorktreeFixture {
  readonly root: string
  readonly fingerprint: SourceFingerprint
}

/**
 * Create one real committed repository with isolated git config (per-invocation
 * env, no process-global mutation) and return its fresh fingerprint, which is
 * the recorded claim every admission case verifies against.
 */
async function createCommittedWorktree(): Promise<WorktreeFixture> {
  const tempRoot = await mkdtemp(join(tmpdir(), 'dsh-devframe-admission-'))
  tempRoots.push(tempRoot)
  const root = join(tempRoot, 'repo')
  const isolatedConfig = join(tempRoot, 'isolated-git.config')
  await writeFile(isolatedConfig, '', 'utf8')
  const gitEnv = {
    ...process.env,
    GIT_CONFIG_GLOBAL: isolatedConfig,
    GIT_CONFIG_SYSTEM: isolatedConfig,
    LC_ALL: 'C',
  }
  const git = async (args: readonly string[]): Promise<void> => {
    await execFileAsync('git', ['-C', root, ...args], { encoding: 'utf8', windowsHide: true, env: gitEnv })
  }
  await mkdir(root, { recursive: true })
  await git(['init', '--quiet', '--initial-branch=main'])
  await git(['config', 'user.name', 'DevFrame Admission Test'])
  await git(['config', 'user.email', 'devframe-admission@example.test'])
  await writeFile(join(root, 'src.ts'), 'export {}\n', 'utf8')
  await git(['add', '-A'])
  await git(['commit', '--quiet', '-m', 'initial'])
  const computed = await computeSourceFingerprint({ worktreePath: root })
  return { root, fingerprint: computed.fingerprint }
}

/** Build one executed check result matching (or deviating from) a required check. */
function executionFor(
  check: DevFrameRequiredCheck,
  status: DevFrameCheckResult['status'] = 'passed',
  command: Partial<Pick<DevFrameRequiredCheck, 'arguments'>> = {},
): DevFrameCheckResult {
  return {
    checkId: check.checkId,
    executable: check.executable,
    arguments: command.arguments ?? [...check.arguments],
    cwd: check.cwd,
    status,
    ...(status === 'passed' ? { exitCode: 0 } : status === 'failed' ? { exitCode: 1 } : {}),
    durationMs: 12,
  }
}

/** One durable review event; authorization was enforced upstream at write time. */
function reviewEvent(decision: 'pass' | 'changes_required'): DevFrameReviewEventData {
  return {
    version: 1,
    reviewId: DevFrameReviewId('review-admission'),
    binding: {
      controllerSessionId: ControllerSessionId('controller-admission'),
      goalId: GoalId('goal-admission'),
      goalRevision: 2,
      taskIds: [TaskId('task-admission')],
      acceptanceHash: AcceptanceHash('acceptance-admission'),
      workspaceId: WorkspaceId('ws-admission'),
      sourceFingerprint: SourceFingerprint('source-admission'),
      snapshotId: DevFrameSnapshotId('snapshot-admission'),
    },
    snapshotId: DevFrameSnapshotId('snapshot-admission'),
    reviewerSessionId: SessionId('reviewer-admission'),
    policyVersion: 'policy-admission',
    decision,
    findings: decision === 'pass' ? [] : [{
      id: 'finding-1',
      severity: 'blocking',
      message: 'the exported contract is untested',
    }],
  }
}

/** Build one admission request over a fresh store registration, with overrides. */
async function admissionRequest(
  fixture: WorktreeFixture,
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
