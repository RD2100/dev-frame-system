/** Real controller, durable task storage, evidence projection, and isolated Git worktrees. */
import { execFile } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import type { Session } from '@deepseek-ai/dsh-session'
import { GoalId } from '@deepseek-ai/dsh-goal'
import WorktreeRegistry, { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { ConfigurationConfirmationId, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/src/source-fingerprint.ts'
import { MemoryRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { CONFIG, executionFor, reviewEvent } from '../../devframe/tests/completion-fixtures.ts'
import { harness, type Harness } from './helpers.ts'
import type { MainTreeMergeRequest } from '../src/controller.ts'

const exec = promisify(execFile)
/** Prepare one independent submitted task with persisted passing evidence; the caller disposes h. */
export async function prepareIntegration(existing?: Harness) {
  const h = existing ?? await harness()
  try {
    const git = async (cwd: string, ...args: string[]) => (await exec('git', ['-C', cwd, ...args], {
      windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
      env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
        !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
    })).stdout.trim()
    const anchor = join(h.root, 'anchor')
    const targetPath = join(h.root, 'target')
    const sourcePath = join(h.root, 'source')
    const leadPath = join(h.root, 'lead')
    await mkdir(anchor)
    await git(anchor, 'init', '-b', 'main')
    await git(anchor, 'config', 'user.name', 'Integration Test')
    await git(anchor, 'config', 'user.email', 'integration@example.invalid')
    await git(anchor, 'config', 'commit.gpgsign', 'false')
    await git(anchor, 'config', 'core.hooksPath', join(h.root, 'no-hooks'))
    await writeFile(join(anchor, 'feature.txt'), 'base\n')
    await git(anchor, 'add', 'feature.txt')
    await git(anchor, 'commit', '-m', 'base')
    await mountIntegrationRegistries(h)
    const workspace = await h.ctx.workspaceRegistry.create(anchor)
    const targetTree = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: targetPath, branch: 'target' })
    const sourceTree = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: sourcePath, branch: 'source' })
    const leadTree = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: leadPath, branch: 'lead' })
    const targetHead = await git(targetPath, 'rev-parse', 'HEAD')
    await writeFile(join(sourcePath, 'feature.txt'), 'reviewed\n')
    await git(sourcePath, 'add', 'feature.txt')
    await git(sourcePath, 'commit', '-m', 'feature')
    const sourceCommit = await git(sourcePath, 'rev-parse', 'HEAD')
    const taskId = TaskId('task-admission')
    const pluginId = PluginId('p-test')
    const controller = (await h.ctx.agentBindings.createBoundSession({ cwd: targetPath, role: 'controller', worktree: { worktreeId: targetTree.id, worktreePath: targetPath } })).session
    const lead = (await h.ctx.agentBindings.createBoundSession({ cwd: leadPath, role: 'lead', parentSessionId: controller.id, pluginId, worktree: { worktreeId: leadTree.id, worktreePath: leadPath } })).session
    const worker = (await h.ctx.agentBindings.createBoundSession({ cwd: sourcePath, role: 'worker', parentSessionId: lead.id, pluginId, taskId, worktree: { worktreeId: sourceTree.id, worktreePath: sourcePath } })).session
    await h.ctx.worktreeRegistry.bind(targetTree.id, WorktreeLockHolder(controller.id))
    await h.ctx.worktreeRegistry.bind(sourceTree.id, WorktreeLockHolder(worker.id))
    await h.ctx.plugin(SessionProjectionRegistry)
    h.ctx.effect(() => h.ctx.sessionProjections.register(devFrameProjectionDefinition))
    const { binding, review, verification, requiredChecksStore } = await appendIntegrationEvidence(
      h, controller, lead, taskId, sourcePath, WorkspaceId(String(workspace.id)),
    )
    h.ctx.projectController.startProject()
    await h.ctx.projectController.createTask({ taskId, pluginId, title: 'Integrate reviewed source' })
    await h.ctx.projectController.assign(taskId, worker.id)
    await h.ctx.projectController.startDevelopment(taskId)
    await h.ctx.projectController.beginReview(taskId)
    await h.ctx.projectController.submit(taskId)
    const request: MainTreeMergeRequest = {
      git: { sourcePath, targetPath, sourceCommit, targetHead },
      options: { executable: 'git', timeoutMs: 15_000, maxOutputBytes: 1024 * 1024 }, requiredChecksStore,
    }
    return { h, controller, lead, worker, taskId, request, git, review, verification, binding }
  } catch (error) {
    await h.dispose()
    throw error
  }
}

/** Append evidence through the real Session journal; registry identities are owned by the calling fixture. */
export async function appendIntegrationEvidence(
  h: Harness, controller: Session, lead: Session, taskId: TaskId, sourcePath: string, workspaceId?: WorkspaceId,
) {
  const original = reviewEvent('pass')
  const binding = {
    ...original.binding, ...(workspaceId === undefined ? {} : { workspaceId }), controllerSessionId: controller.id, goalId: GoalId('goal-integration'),
    taskIds: [GoalTaskId(String(taskId))], sourceFingerprint: (await computeSourceFingerprint({ worktreePath: sourcePath })).fingerprint,
  }
  const emptyPolicy = { inheritedTools: [], denyScopedTools: [] }
  controller.append('devframe/role-policy', {
    version: 1, controllerSessionId: controller.id, workspaceId: binding.workspaceId, policyVersion: original.policyVersion,
    config: { controller: emptyPolicy, worker: emptyPolicy, reviewer: emptyPolicy },
    assignments: [{ role: 'controller', sessionId: controller.id }, { role: 'lead', sessionId: lead.id }],
  })
  controller.append('devframe/goal-binding', {
    ...binding, version: 1, confirmation: { id: ConfigurationConfirmationId('confirmation-integration'), acceptanceHash: binding.acceptanceHash },
    lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
  })
  const requiredChecksStore = new MemoryRequiredChecksConfigStore()
  const digest = await requiredChecksStore.save(CONFIG)
  const verification = {
    version: 1 as const, verificationId: DevFrameVerificationId('verification-integration'), binding,
    snapshotId: binding.snapshotId, status: 'passed' as const,
    requiredChecks: { config: CONFIG, digest }, checks: CONFIG.checks.map(check => executionFor(check)),
  }
  const review = { ...original, binding, reviewerSessionId: lead.id }
  controller.append('devframe/verification', verification)
  controller.append('devframe/review', review)
  return { binding, review, verification, requiredChecksStore }
}

/** Mount the real durable worktree and workspace providers, including cold restoration. */
export async function mountIntegrationRegistries(h: Harness): Promise<void> {
  await h.ctx.plugin(JsonlPersistence, { root: join(h.root, 'sessions'), compression: 'none' })
  await h.ctx.plugin(WorkspaceRegistry)
  await h.ctx.plugin(SubprocessLocal)
  await h.ctx.plugin(WorktreeRegistry)
}
