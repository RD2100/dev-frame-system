/**
 * Shared completion-admission fixtures: one real committed git worktree whose
 * fresh fingerprint is the recorded claim every admission case verifies
 * against, the approved required-checks configuration with its executed-check
 * builder, and the durable review event builder. Spec files own their
 * `afterEach` and call {@link drainWorktreeFixtures} so every temp root this
 * module acquired is drained to quiescence.
 * @module dsh-experimental-devframe/tests/completion-fixtures
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { SessionId } from '@deepseek-ai/dsh-session'
import { DevFrameReviewId } from '../src/events.ts'
import type { DevFrameCheckResult, DevFrameReviewEventData } from '../src/events.ts'
import type { DevFrameRequiredCheck, DevFrameRequiredChecksConfig } from '../src/required-checks.ts'
import { computeSourceFingerprint } from '../src/source-fingerprint.ts'
import type { GoalResultBinding } from '../src/controller/goal-binding.ts'
import {
  AcceptanceHash,
  DevFrameSnapshotId,
  SourceFingerprint,
  WorkspaceId,
} from '../src/shared/types.ts'
import { ControllerSessionId, TaskId } from '../src/controller/goal-binding.ts'

const execFileAsync = promisify(execFile)

/** The approved checklist the admission fixtures register and execute. */
export const CONFIG: DevFrameRequiredChecksConfig = {
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

/** Temp roots acquired by this module, drained by {@link drainWorktreeFixtures}. */
const tempRoots: string[] = []

/**
 * Drain every temp root acquired since the last drain. Bounded linear backoff
 * absorbs Windows EBUSY/EPERM handle contention; the rm resolution is the
 * completion signal — no sleeps.
 */
export async function drainWorktreeFixtures(): Promise<void> {
  const roots = [...tempRoots]
  tempRoots.length = 0
  await Promise.all(roots.map(root => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })))
}

export interface WorktreeFixture {
  readonly root: string
  readonly fingerprint: SourceFingerprint
}

/**
 * Create one real committed repository with isolated git config (per-invocation
 * env, no process-global mutation) and return its fresh fingerprint, which is
 * the recorded claim every admission case verifies against.
 */
export async function createCommittedWorktree(): Promise<WorktreeFixture> {
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
export function executionFor(
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

/**
 * One durable review event; authorization was enforced upstream at write time.
 * The default binding names the standalone evaluation fixtures; controller
 * cases override `binding` (and `snapshotId`) with the real work tuple.
 */
export function reviewEvent(
  decision: 'pass' | 'changes_required',
  overrides: Partial<DevFrameReviewEventData> = {},
): DevFrameReviewEventData {
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
    ...overrides,
  }
}

/** The GoalResultBinding projection one controller binding shares with its evidence. */
export function resultReference(binding: GoalResultBinding): GoalResultBinding {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: binding.taskIds,
    acceptanceHash: binding.acceptanceHash,
    workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
  }
}
