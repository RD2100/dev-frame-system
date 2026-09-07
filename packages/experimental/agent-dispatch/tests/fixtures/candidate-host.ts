/**
 * Candidate host-side scenario preparation, per the digest wiring ruling: the
 * harness pre-builds real isolated git worktrees, normalizes their paths,
 * saves each task's approved checks sequentially into the ONE
 * FileRequiredChecksConfigStore the delivery, integration, and bootstrap
 * faces share, and emits the final-layer patch yml that pins the per-task
 * digests. The candidate CLI boots with this patch as the last sibling, so
 * the deployment's requiredChecksByTask matches what the store actually
 * holds before the first model request.
 * @module tests/fixtures/candidate-host
 */

import { execFile } from 'node:child_process'
import { mkdir, realpath, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import {
  FileRequiredChecksConfigStore,
  requiredChecksDigest,
} from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameRequiredChecksConfig, RequiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe'

const exec = promisify(execFile)

/** One prepared Worker worktree and its task's approved digest. */
export interface PreparedTask {
  readonly taskId: string
  readonly worktreePath: string
  readonly digest: RequiredChecksDigest
}

export interface PreparedScenario {
  /** The repository the worktrees hang off. */
  readonly anchorPath: string
  readonly tasks: readonly PreparedTask[]
  /** The controller's own integration-target worktree (realpath canon). */
  readonly targetWorktreePath: string
  /** The lead's worktree, left unbound for the lead's own dispatch. */
  readonly leadWorktreePath: string
}

/** One git invocation, failing loud with stderr; env stripped of secrets and GIT_ overrides. */
export async function scenarioGit(cwd: string, ...args: string[]): Promise<string> {
  const result = await exec('git', args, {
    cwd,
    windowsHide: true,
    timeout: 15_000,
    maxBuffer: 1024 * 1024,
    env: Object.fromEntries(Object.entries(process.env).filter(([name]) =>
      !/KEY|SECRET|TOKEN|PASSWORD/i.test(name) && !/^GIT_/i.test(name))),
  })
  return result.stdout.trim()
}

/**
 * The machine-neutral approved checklist one Worker must pass: a whitespace
 * check and the artifact-existence probe, both executing in the Worker's own
 * worktree (the delivery consumer verifies each cwd against the assigned
 * worktree realpath).
 * @param worktreePath - The normalized Worker worktree path.
 */
export function approvedChecksFor(worktreePath: string, artifactName: string): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [
      { checkId: 'git-diff-check', executable: 'git', arguments: ['diff', '--check'], cwd: worktreePath },
      { checkId: 'artifact-probe', executable: 'node', arguments: ['-e', `require("node:fs").accessSync(${JSON.stringify(artifactName)})`], cwd: worktreePath },
    ],
  }
}

/**
 * Prepare the candidate scenario: anchor repo, two Worker worktrees with one
 * initial commit each, and the sequential approved-digest registration.
 * Saves run strictly in sequence — parallel saves to the shared ledger file
 * are forbidden by the wiring ruling.
 * @param root - The isolated scenario root.
 * @param ledgerPath - The single checks ledger every face shares.
 */
export async function prepareCandidateScenario(root: string, ledgerPath: string): Promise<PreparedScenario> {
  await mkdir(join(root, 'anchor'), { recursive: true })
  const anchorPath = await realpath(join(root, 'anchor'))
  await scenarioGit(root, 'init', '-b', 'main', anchorPath)
  await scenarioGit(anchorPath, 'config', 'user.name', 'Candidate Fullchain')
  await scenarioGit(anchorPath, 'config', 'user.email', 'candidate-fullchain@test.invalid')
  await scenarioGit(anchorPath, 'config', 'commit.gpgsign', 'false')
  await scenarioGit(anchorPath, 'commit', '--allow-empty', '-m', 'candidate base')

  const store = new FileRequiredChecksConfigStore({ path: ledgerPath })
  // Four independent trees: the controller's integration target, the lead's
  // own tree, and one worker tree per task. Only the target is bound at
  // bootstrap; the lead and worker trees stay free for their own holders.
  const targetWorktreePath = join(root, 'wt-target')
  await scenarioGit(anchorPath, 'worktree', 'add', targetWorktreePath, '-b', 'feature/target')
  const leadWorktreePath = join(root, 'wt-lead')
  await scenarioGit(anchorPath, 'worktree', 'add', leadWorktreePath, '-b', 'feature/lead')
  const tasks: PreparedTask[] = []
  for (const taskId of ['task-a', 'task-b'] as const) {
    const worktreePath = join(root, `wt-${taskId}`)
    await scenarioGit(anchorPath, 'worktree', 'add', worktreePath, '-b', `feature/${taskId}`)
    // git created the directory, so the realpath canon now applies.
    const canonical = await realpath(worktreePath)
    // Each worker produces its own artifact file; the approved probe checks
    // that exact name.
    const digest = await store.save(approvedChecksFor(canonical, `artifact-${taskId}.txt`))
    tasks.push({ taskId, worktreePath: canonical, digest })
  }
  return { anchorPath, tasks, targetWorktreePath: await realpath(targetWorktreePath), leadWorktreePath: await realpath(leadWorktreePath) }
}

/**
 * Emit the final-layer patch yml pinning the prepared digests and the
 * per-task check worktree paths. The harness passes this file as the last
 * `--patch`, after the shipped overlays and the loop-closure fixture.
 * @param home - The isolated home the patch file is written into.
 * @param prepared - The prepared tasks with their digests.
 */
export async function writeDigestPatch(home: string, prepared: PreparedScenario): Promise<string> {
  const rows = prepared.tasks.map(task => [
    `    '${task.taskId}': '${String(task.digest)}'`,
  ].join('\n'))
  const checkRows = prepared.tasks.map(task => {
    const checks = approvedChecksFor(task.worktreePath, `artifact-${task.taskId}.txt`).checks
    return `        '${task.taskId}': ${JSON.stringify(checks)}`
  })
  const patch = [
    '# Final-layer digest patch, generated per run by the candidate harness.',
    '# The digests match the shared ledger contents prepared before boot.',
    '- id: project-delivery-tools',
    '  config:',
    '    requiredChecksPath: !!js "process.env.DSH_CANDIDATE_HOME + \'/checks-ledger.json\'"',
    '    requiredChecksByTask:',
    ...rows,
    '    gitExecutable: git',
    '    gitTimeoutMs: 15000',
    '    gitMaxOutputBytes: 1048576',
    '    checkTimeoutMs: 15000',
    '    checkMaxOutputBytes: 1048576',
    // The approved checksets the delivery consumer loads by digest.
    `# checksets: ${checkRows.join(' ')}`,
    '',
  ].join('\n')
  const patchPath = join(home, 'candidate-digests.patch.yml')
  await writeFile(patchPath, patch, 'utf8')
  return patchPath
}

/** The bootstrap's approveTaskChecks cross-check: recompute and compare. */
export function expectedDigests(prepared: PreparedScenario): Record<string, string> {
  return Object.fromEntries(prepared.tasks.map(task => [
    task.taskId, String(requiredChecksDigest(approvedChecksFor(task.worktreePath, `artifact-${task.taskId}.txt`))),
  ]))
}

/**
 * Write the host-owned scenario file the `project_host_start` tool consumes:
 * capabilities only (anchor, worktrees, digests, approved checks) — the
 * calling model supplies none of them.
 * @param home - The isolated home hosting the file.
 * @param prepared - The prepared scenario.
 */
export async function writeScenarioFile(home: string, prepared: PreparedScenario): Promise<string> {
  const scenario = {
    anchorPath: prepared.anchorPath,
    targetWorktreePath: prepared.targetWorktreePath,
    leadWorktreePath: prepared.leadWorktreePath,
    tasks: prepared.tasks.map(task => ({
      taskId: task.taskId,
      worktreePath: task.worktreePath,
      digest: String(task.digest),
      checks: approvedChecksFor(task.worktreePath, `artifact-${task.taskId}.txt`),
    })),
  }
  const scenarioPath = join(home, 'candidate-scenario.json')
  await writeFile(scenarioPath, JSON.stringify(scenario, null, 2), 'utf8')
  return scenarioPath
}

export { TaskId }
