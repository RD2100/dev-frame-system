/** Snapshot-only preconditions; the SDK Agent itself executes project_integrate through its model turn. */
import { execFile } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-experimental-project-controller'
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import type {} from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { FileRequiredChecksConfigStore, computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { AcceptanceHash, ConfigurationConfirmationId, DevFrameSnapshotId, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { DevFrameDeliveryId, DevFrameReviewId, DevFrameVerificationId, deliveryResultBinding } from '../../../devframe/lib/types/events.js'
import { devFrameProjectionDefinition } from '../../../devframe/lib/types/projection.js'
import { DevFrameSessionJournal } from '../../../devframe/lib/types/session-journal.js'

export const name = 'project-integration-snapshot'
export const inject = ['agents', 'sessions', 'sessionProjections', 'agentBindings', 'projectController', 'workspaceRegistry', 'worktreeRegistry']

/**
 * Install host-owned evidence before the first model request.
 * @param ctx - SDK composition containing the real registry, journal, and controller services.
 * @param options - Whether the task must correct a rejected delivery before final review.
 */
export function apply(ctx: Context, options: { repairBeforeIntegration?: boolean } = {}): void {
  const initialized = new WeakSet<object>()
  ctx.effect(() => ctx.sessionProjections.register(devFrameProjectionDefinition))
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    if (initialized.has(agent)) return await next()
    if (String(agent.id) !== 'fixture-root-session') throw new Error('Integration snapshot received an unexpected root Agent')
    const root = join(process.cwd(), '.dsh', 'integration')
    const workspace = await ctx.workspaceRegistry.create(join(root, 'repo'))
    await ctx.worktreeRegistry.reconcile(workspace.id, { adoptUnregistered: true })
    const rows = ctx.worktreeRegistry.list(workspace.id)
    const rowFor = (role: string) => {
      const row = rows.find(candidate => candidate.branch === role)
      if (row === undefined) throw new Error(`Integration snapshot is missing its ${role} worktree`)
      return row
    }
    const target = rowFor('target')
    const leadTree = rowFor('lead')
    const source = rowFor('worker')
    const pluginId = PluginId('snapshot-plugin')
    const taskId = TaskId('task-integration')
    await ctx.agentBindings.bind({ agentId: agent.id, role: 'controller',
      worktree: { worktreeId: target.id, worktreePath: target.path } })
    const lead = (await ctx.agentBindings.createBoundSession({
      cwd: leadTree.path, role: 'lead', parentSessionId: agent.id, pluginId,
      worktree: { worktreeId: leadTree.id, worktreePath: leadTree.path },
    })).session
    const worker = (await ctx.agentBindings.createBoundSession({
      cwd: source.path, role: 'worker', parentSessionId: lead.id, pluginId, taskId,
      worktree: { worktreeId: source.id, worktreePath: source.path },
    })).session
    for (const [tree, session] of [[target, agent.session], [leadTree, lead], [source, worker]] as const) {
      await ctx.worktreeRegistry.bind(tree.id, WorktreeLockHolder(String(session.id)))
    }
    const journal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), {
      requireReviewer(sessionId) {
        const binding = ctx.agentBindings.find(sessionId)
        if (binding?.role !== 'lead' || binding.parentSessionId !== agent.id || binding.pluginId !== pluginId
          || binding.sessionId === worker.id || binding.worktreeId === source.id) {
          throw new Error('Snapshot review requires the independent registered plugin lead')
        }
      },
    })
    const policy = { inheritedTools: [], denyScopedTools: [] }
    const binding = {
      controllerSessionId: ControllerSessionId(String(agent.id)), workspaceId: WorkspaceId(String(workspace.id)),
      goalId: GoalId('goal-integration'), goalRevision: 1,
      taskIds: [GoalTaskId(String(taskId))], acceptanceHash: AcceptanceHash('acceptance-integration'),
      snapshotId: DevFrameSnapshotId('snapshot-integration'),
      sourceFingerprint: (await computeSourceFingerprint({ worktreePath: target.path })).fingerprint,
    }
    await journal.append(agent.session, 'devframe/role-policy', {
      version: 1, controllerSessionId: agent.id, workspaceId: binding.workspaceId, policyVersion: 'snapshot-policy',
      config: { controller: policy, worker: policy, reviewer: policy },
      assignments: [{ role: 'controller', sessionId: agent.id }, { role: 'lead', sessionId: lead.id }],
    })
    await journal.append(agent.session, 'devframe/goal-binding', {
      ...binding, version: 1,
      confirmation: { id: ConfigurationConfirmationId('confirmation-integration'), acceptanceHash: binding.acceptanceHash },
      lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
    })
    const check = { checkId: 'diff-check', executable: 'git', arguments: ['diff', '--check'], cwd: '.' }
    const config = { version: 1 as const, checks: [check] }
    const store = new FileRequiredChecksConfigStore({ path: join(process.cwd(), '.dsh', 'project-checks.json') })
    const digest = await store.save(config)
    const env = Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
    const sourceCommit = (await promisify(execFile)('git', ['rev-parse', 'HEAD'], {
      cwd: source.path, env, windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    })).stdout.trim()
    let delivery = {
      version: 1 as const, deliveryId: DevFrameDeliveryId('delivery-integration'), taskId: GoalTaskId(String(taskId)), binding,
      workerSessionId: worker.id, worktreeId: source.id, worktreePath: source.path, sourceCommit,
      sourceFingerprint: (await computeSourceFingerprint({ worktreePath: source.path })).fingerprint,
      snapshotId: DevFrameSnapshotId('output-snapshot-integration'),
    }
    ctx.projectController.startProject()
    await ctx.projectController.createTask({ taskId, pluginId, title: 'Integrate reviewed snapshot source' })
    await ctx.projectController.assign(taskId, worker.id)
    await ctx.projectController.startDevelopment(taskId)
    if (options.repairBeforeIntegration) {
      await journal.append(agent.session, 'devframe/task-delivery', delivery)
      const rejectedOutput = deliveryResultBinding(delivery)
      await promisify(execFile)('git', ['diff', '--check'], {
        cwd: source.path, env, windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
      })
      await journal.append(agent.session, 'devframe/verification', {
        version: 1, verificationId: DevFrameVerificationId('verification-before-repair'), binding: rejectedOutput,
        snapshotId: rejectedOutput.snapshotId, deliveryId: delivery.deliveryId, status: 'passed',
        requiredChecks: { config: { version: 1, checks: [check] }, digest },
        checks: [{ ...check, status: 'passed', exitCode: 0, durationMs: 0 }],
      })
      await ctx.projectController.beginReview(taskId)
      const reviewId = DevFrameReviewId('review-before-repair')
      await journal.append(agent.session, 'devframe/review', {
        version: 1, reviewId, binding: rejectedOutput, snapshotId: rejectedOutput.snapshotId,
        deliveryId: delivery.deliveryId, reviewerSessionId: lead.id, policyVersion: 'snapshot-policy',
        decision: 'changes_required', findings: [{ id: 'required-content', severity: 'blocking',
          path: 'feature.txt', message: 'The required feature content is repaired, not reviewed.' }],
      })
      const request = { identity: { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
        cause: { kind: 'review' as const, reviewId }, repairLimit: 2 }
      const admitted = await journal.admitRepair(agent.session, request)
      const restoredJournal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), {
        requireReviewer() { throw new Error('Repair admission must reuse the existing durable review') },
      })
      const repeated = await restoredJournal.admitRepair(agent.session, request)
      if (admitted.kind !== 'admitted' || admitted.repairRound !== 1
        || repeated.kind !== 'admitted' || repeated.repairRound !== 1) {
        throw new Error('Repair admission must charge the same Goal once across Journal replacement')
      }
      await ctx.projectController.returnToDevelopment(taskId)
      await writeFile(join(source.path, 'feature.txt'), 'repaired\n')
      const repairEnv = { ...env, GIT_AUTHOR_DATE: '2026-01-01T00:00:00Z', GIT_COMMITTER_DATE: '2026-01-01T00:00:00Z' }
      for (const args of [['add', 'feature.txt'], ['commit', '-m', 'repair reviewed implementation']]) {
        await promisify(execFile)('git', args, { cwd: source.path, env: repairEnv,
          windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024 })
      }
      delivery = { ...delivery, deliveryId: DevFrameDeliveryId('delivery-after-repair'),
        sourceCommit: (await promisify(execFile)('git', ['rev-parse', 'HEAD'], {
          cwd: source.path, env, windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
        })).stdout.trim(),
        sourceFingerprint: (await computeSourceFingerprint({ worktreePath: source.path })).fingerprint,
        snapshotId: DevFrameSnapshotId('output-snapshot-after-repair'),
      }
    }
    await journal.append(agent.session, 'devframe/task-delivery', delivery)
    const output = deliveryResultBinding(delivery)
    await promisify(execFile)('git', ['diff', '--check'], {
      cwd: source.path, env, windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    })
    await journal.append(agent.session, 'devframe/verification', {
      version: 1, verificationId: DevFrameVerificationId('verification-integration'), binding: output, snapshotId: output.snapshotId,
      deliveryId: delivery.deliveryId,
      status: 'passed', requiredChecks: { config, digest },
      // The subprocess outcome is real; the fixture clock reports a fixed duration.
      checks: [{ ...check, status: 'passed', exitCode: 0, durationMs: 0 }],
    })
    await journal.append(agent.session, 'devframe/review', {
      version: 1, reviewId: DevFrameReviewId('review-integration'), binding: output, snapshotId: output.snapshotId,
      deliveryId: delivery.deliveryId,
      reviewerSessionId: lead.id, policyVersion: 'snapshot-policy', decision: 'pass', findings: [],
    })
    await ctx.projectController.beginReview(taskId)
    await ctx.projectController.submit(taskId)
    await ctx.sessions.flush(lead)
    await ctx.sessions.flush(worker)
    initialized.add(agent)
    return await next()
  })
}
