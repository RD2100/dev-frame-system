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
import { DevFrameDeliveryId, DevFrameReviewId, DevFrameVerificationId, deliveryResultBinding } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { ConfigurationConfirmationId, DevFrameSnapshotId, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/src/source-fingerprint.ts'
import { MemoryRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { CONFIG, executionFor, reviewEvent } from '../../devframe/tests/completion-fixtures.ts'
import { harness, type Harness } from './helpers.ts'
import type { MainTreeMergeRequest } from '../src/controller.ts'

const exec = promisify(execFile)

/** One secrets-scrubbed bounded Git invocation shared by both integration preparations. */
const git = async (cwd: string, ...args: string[]) => (await exec('git', ['-C', cwd, ...args], {
  windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
})).stdout.trim()

/** Prepare one independent submitted task with persisted passing evidence; the caller disposes h. */
export async function prepareIntegration(existing?: Harness) {
  const h = existing ?? await harness()
  try {
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
    const { binding, delivery, review, verification, requiredChecksStore } = await appendIntegrationEvidence(
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
    return { h, controller, lead, worker, taskId, request, git, review, verification, binding, delivery }
  } catch (error) {
    await h.dispose()
    throw error
  }
}

/** Append evidence through the real Session journal; registry identities are owned by the calling fixture. */
export async function appendIntegrationEvidence(
  h: Harness, controller: Session, lead: Session, taskId: TaskId, sourcePath: string, workspaceId?: WorkspaceId,
  options?: { readonly goalId?: string; readonly rolePolicy?: boolean },
) {
  const original = reviewEvent('pass')
  const binding = {
    ...original.binding, ...(workspaceId === undefined ? {} : { workspaceId }), controllerSessionId: controller.id,
    goalId: GoalId(options?.goalId ?? 'goal-integration'),
    taskIds: [GoalTaskId(String(taskId))],
    sourceFingerprint: (await computeSourceFingerprint({ worktreePath: controller.header.cwd! })).fingerprint,
  }
  const emptyPolicy = { inheritedTools: [], denyScopedTools: [] }
  if (options?.rolePolicy !== false) {
    controller.append('devframe/role-policy', {
      version: 1, controllerSessionId: controller.id, workspaceId: binding.workspaceId, policyVersion: original.policyVersion,
      config: { controller: emptyPolicy, worker: emptyPolicy, reviewer: emptyPolicy },
      assignments: [{ role: 'controller', sessionId: controller.id }, { role: 'lead', sessionId: lead.id }],
    })
  }
  controller.append('devframe/goal-binding', {
    ...binding, version: 1, confirmation: { id: ConfigurationConfirmationId('confirmation-integration'), acceptanceHash: binding.acceptanceHash },
    lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
  })
  const worker = h.ctx.agentBindings.list().find(record => record.role === 'worker' && record.taskId === taskId)
  if (worker?.worktreeId === undefined || worker.worktreePath !== sourcePath) throw new Error('Integration fixture requires its registered task Worker')
  const sourceCommit = (await exec('git', ['-C', sourcePath, 'rev-parse', 'HEAD'], {
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
  })).stdout.trim()
  const delivery = {
    version: 1 as const, deliveryId: DevFrameDeliveryId(`delivery-${String(taskId)}`), taskId: GoalTaskId(String(taskId)), binding,
    workerSessionId: worker.sessionId, worktreeId: worker.worktreeId, worktreePath: sourcePath, sourceCommit,
    sourceFingerprint: (await computeSourceFingerprint({ worktreePath: sourcePath })).fingerprint,
    snapshotId: DevFrameSnapshotId(`output-snapshot-${String(taskId)}`),
  }
  controller.append('devframe/task-delivery', delivery)
  const output = deliveryResultBinding(delivery)
  const requiredChecksStore = new MemoryRequiredChecksConfigStore()
  const digest = await requiredChecksStore.save(CONFIG)
  const verification = {
    version: 1 as const, verificationId: DevFrameVerificationId(`verification-${String(taskId)}`), binding: output,
    deliveryId: delivery.deliveryId, snapshotId: output.snapshotId, status: 'passed' as const,
    requiredChecks: { config: CONFIG, digest }, checks: CONFIG.checks.map(check => executionFor(check)),
  }
  const review = {
    ...original, reviewId: DevFrameReviewId(`review-${String(taskId)}`), binding: output, deliveryId: delivery.deliveryId,
    snapshotId: output.snapshotId, reviewerSessionId: lead.id,
  }
  controller.append('devframe/verification', verification)
  controller.append('devframe/review', review)
  return { binding, delivery, review, verification, requiredChecksStore }
}

/**
 * Append one Goal binding admitting every listed task plus each task's own
 * delivery, verification, and review, all before any integration runs — the
 * real parallel shape where independent deliveries exist at the same base
 * and the controller integrates them afterwards.
 */
export async function appendParallelIntegrationEvidence(
  h: Harness, controller: Session, lead: Session,
  tasks: readonly { readonly taskId: TaskId; readonly sourcePath: string }[],
  workspaceId: WorkspaceId,
) {
  const original = reviewEvent('pass')
  const emptyPolicy = { inheritedTools: [], denyScopedTools: [] }
  controller.append('devframe/role-policy', {
    version: 1, controllerSessionId: controller.id, workspaceId, policyVersion: original.policyVersion,
    config: { controller: emptyPolicy, worker: emptyPolicy, reviewer: emptyPolicy },
    assignments: [{ role: 'controller', sessionId: controller.id }, { role: 'lead', sessionId: lead.id }],
  })
  const binding = {
    ...original.binding, workspaceId, controllerSessionId: controller.id, goalId: GoalId('goal-integration'),
    taskIds: tasks.map(task => GoalTaskId(String(task.taskId))),
    sourceFingerprint: (await computeSourceFingerprint({ worktreePath: controller.header.cwd! })).fingerprint,
  }
  controller.append('devframe/goal-binding', {
    ...binding, version: 1, confirmation: { id: ConfigurationConfirmationId('confirmation-integration'), acceptanceHash: binding.acceptanceHash },
    lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
  })
  const requiredChecksStore = new MemoryRequiredChecksConfigStore()
  const digest = await requiredChecksStore.save(CONFIG)
  for (const task of tasks) {
    const worker = h.ctx.agentBindings.list().find(record => record.role === 'worker' && record.taskId === task.taskId)
    if (worker?.worktreeId === undefined || worker.worktreePath !== task.sourcePath) {
      throw new Error('Integration fixture requires its registered task Worker')
    }
    const sourceCommit = (await exec('git', ['-C', task.sourcePath, 'rev-parse', 'HEAD'], {
      windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
      env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
        !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
    })).stdout.trim()
    const delivery = {
      version: 1 as const, deliveryId: DevFrameDeliveryId(`delivery-${String(task.taskId)}`), taskId: GoalTaskId(String(task.taskId)), binding,
      workerSessionId: worker.sessionId, worktreeId: worker.worktreeId, worktreePath: task.sourcePath, sourceCommit,
      sourceFingerprint: (await computeSourceFingerprint({ worktreePath: task.sourcePath })).fingerprint,
      snapshotId: DevFrameSnapshotId(`output-snapshot-${String(task.taskId)}`),
    }
    controller.append('devframe/task-delivery', delivery)
    const output = deliveryResultBinding(delivery)
    const verification = {
      version: 1 as const, verificationId: DevFrameVerificationId(`verification-${String(task.taskId)}`), binding: output,
      deliveryId: delivery.deliveryId, snapshotId: output.snapshotId, status: 'passed' as const,
      requiredChecks: { config: CONFIG, digest }, checks: CONFIG.checks.map(check => executionFor(check)),
    }
    const review = {
      ...original, reviewId: DevFrameReviewId(`review-${String(task.taskId)}`), binding: output, deliveryId: delivery.deliveryId,
      snapshotId: output.snapshotId, reviewerSessionId: lead.id,
    }
    controller.append('devframe/verification', verification)
    controller.append('devframe/review', review)
  }
  return { binding, requiredChecksStore }
}

/** Mount the real durable worktree and workspace providers, including cold restoration. */
export async function mountIntegrationRegistries(h: Harness): Promise<void> {
  await h.ctx.plugin(JsonlPersistence, { root: join(h.root, 'sessions'), compression: 'none' })
  await h.ctx.plugin(WorkspaceRegistry)
  await h.ctx.plugin(SubprocessLocal)
  await h.ctx.plugin(WorktreeRegistry)
}

/**
 * Prepare two independent sibling Worker tasks branched from the same base
 * with persisted passing evidence, exercising the parallel integration
 * shape: task A stays fast-forward, task B diverges and needs the merge
 * mode. Task A is not integrated here; the caller drives both merges so a
 * cold restore can replay each phase.
 */
export async function prepareParallelIntegration() {
  const h = await harness()
  try {
    const anchor = join(h.root, 'anchor')
    const targetPath = join(h.root, 'target')
    const sourceA = join(h.root, 'source-a')
    const sourceB = join(h.root, 'source-b')
    const leadPath = join(h.root, 'lead')
    await mkdir(anchor)
    await git(anchor, 'init', '-b', 'main')
    await git(anchor, 'config', 'user.name', 'Integration Test')
    await git(anchor, 'config', 'user.email', 'integration@example.invalid')
    await git(anchor, 'config', 'commit.gpgsign', 'false')
    await git(anchor, 'config', 'core.hooksPath', join(h.root, 'no-hooks'))
    await git(anchor, 'config', 'core.autocrlf', 'false')
    await writeFile(join(anchor, 'feature.txt'), 'base\n')
    await git(anchor, 'add', 'feature.txt')
    await git(anchor, 'commit', '-m', 'base')
    await mountIntegrationRegistries(h)
    const workspace = await h.ctx.workspaceRegistry.create(anchor)
    const workspaceId = WorkspaceId(String(workspace.id))
    const targetTree = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: targetPath, branch: 'target' })
    const sourceTreeA = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: sourceA, branch: 'source-a' })
    const sourceTreeB = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: sourceB, branch: 'source-b' })
    const leadTree = await h.ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: leadPath, branch: 'lead' })
    const targetHead = await git(targetPath, 'rev-parse', 'HEAD')
    await writeFile(join(sourceA, 'a.txt'), 'reviewed-a\n')
    await git(sourceA, 'add', 'a.txt')
    await git(sourceA, 'commit', '-m', 'task a')
    const commitA = await git(sourceA, 'rev-parse', 'HEAD')
    await writeFile(join(sourceB, 'b.txt'), 'reviewed-b\n')
    await git(sourceB, 'add', 'b.txt')
    await git(sourceB, 'commit', '-m', 'task b')
    const commitB = await git(sourceB, 'rev-parse', 'HEAD')
    const taskAId = TaskId('task-parallel-a')
    const taskBId = TaskId('task-parallel-b')
    const pluginId = PluginId('p-test')
    const controller = (await h.ctx.agentBindings.createBoundSession({ cwd: targetPath, role: 'controller', worktree: { worktreeId: targetTree.id, worktreePath: targetPath } })).session
    const lead = (await h.ctx.agentBindings.createBoundSession({ cwd: leadPath, role: 'lead', parentSessionId: controller.id, pluginId, worktree: { worktreeId: leadTree.id, worktreePath: leadPath } })).session
    const workerA = (await h.ctx.agentBindings.createBoundSession({ cwd: sourceA, role: 'worker', parentSessionId: lead.id, pluginId, taskId: taskAId, worktree: { worktreeId: sourceTreeA.id, worktreePath: sourceA } })).session
    const workerB = (await h.ctx.agentBindings.createBoundSession({ cwd: sourceB, role: 'worker', parentSessionId: lead.id, pluginId, taskId: taskBId, worktree: { worktreeId: sourceTreeB.id, worktreePath: sourceB } })).session
    await h.ctx.worktreeRegistry.bind(targetTree.id, WorktreeLockHolder(controller.id))
    await h.ctx.worktreeRegistry.bind(sourceTreeA.id, WorktreeLockHolder(workerA.id))
    await h.ctx.worktreeRegistry.bind(sourceTreeB.id, WorktreeLockHolder(workerB.id))
    await h.ctx.plugin(SessionProjectionRegistry)
    h.ctx.effect(() => h.ctx.sessionProjections.register(devFrameProjectionDefinition))
    h.ctx.projectController.startProject()
    for (const [taskId, worker] of [[taskAId, workerA], [taskBId, workerB]] as const) {
      await h.ctx.projectController.createTask({ taskId, pluginId, title: 'Integrate reviewed source' })
      await h.ctx.projectController.assign(taskId, worker.id)
      await h.ctx.projectController.startDevelopment(taskId)
      await h.ctx.projectController.beginReview(taskId)
      await h.ctx.projectController.submit(taskId)
    }
    const evidence = await appendParallelIntegrationEvidence(h, controller, lead,
      [{ taskId: taskAId, sourcePath: sourceA }, { taskId: taskBId, sourcePath: sourceB }], workspaceId)
    const options = { executable: 'git', timeoutMs: 15_000, maxOutputBytes: 1024 * 1024 }
    const requestA: MainTreeMergeRequest = {
      git: { sourcePath: sourceA, targetPath, sourceCommit: commitA, targetHead, mode: 'fast-forward' },
      options, requiredChecksStore: evidence.requiredChecksStore,
    }
    const requestB: MainTreeMergeRequest = {
      git: { sourcePath: sourceB, targetPath, sourceCommit: commitB, targetHead: commitA, mode: 'merge' },
      options, requiredChecksStore: evidence.requiredChecksStore,
    }
    return { h, controller, lead, taskAId, taskBId, git, commitA, commitB, targetHead, requestA, requestB, options, workspaceId, evidence }
  } catch (error) {
    await h.dispose()
    throw error
  }
}
