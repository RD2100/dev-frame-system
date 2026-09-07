/** Authored transport fixture: delivery events only, without development, checks, or review claims. */
import { join } from 'node:path'
import { DevFrameSessionJournal } from '../../packages/experimental/devframe/lib/types/session-journal.js'
import { devFrameProjectionDefinition } from '../../packages/experimental/devframe/lib/types/projection.js'

export const name = 'python-sdk-task-delivery'
export const inject = ['sessions', 'sessionProjections']

/** Register the real projection and append one legal input/output pair before the model turn. */
export function apply(ctx) {
  ctx.effect(() => ctx.sessionProjections.register(devFrameProjectionDefinition))
  const initialized = new WeakSet()
  const journal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), {
    requireReviewer() { throw new Error('Transport fixture must not append review evidence') },
  })
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    if (initialized.has(agent)) return await next()
    const binding = {
      controllerSessionId: agent.session.id, workspaceId: 'transport-workspace',
      goalId: 'transport-goal', goalRevision: 1, taskIds: ['transport-task'],
      acceptanceHash: 'transport-acceptance', sourceFingerprint: 'transport-input-source',
      snapshotId: 'transport-input-snapshot',
    }
    await journal.append(agent.session, 'devframe/goal-binding', {
      ...binding, version: 1, lifecycle: 'admission_open',
      confirmation: { id: 'transport-confirmation', acceptanceHash: binding.acceptanceHash },
      budget: { maxAttempts: 1, consumedAttempts: 0 },
    })
    await journal.append(agent.session, 'devframe/task-delivery', {
      version: 1, deliveryId: 'transport-delivery', taskId: 'transport-task', binding,
      workerSessionId: 'transport-worker', worktreeId: 'transport-worktree',
      worktreePath: join(process.cwd(), 'worker'), sourceCommit: 'a'.repeat(40),
      sourceFingerprint: 'transport-output-source', snapshotId: 'transport-output-snapshot',
    })
    const state = ctx.sessionProjections.stateOf(agent.session, 'devframe')
    if (state?.deliveries.length !== 1 || state.failure !== null) {
      throw new Error('Transport fixture failed the real DevFrame projection')
    }
    initialized.add(agent)
    return await next()
  })
}
