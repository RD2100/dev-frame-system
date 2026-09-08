/** SDK transport fixture with journal-backed repair admission; no development, checks, or review claims. */
import { join } from 'node:path'
import { writeFile } from 'node:fs/promises'
import { DevFrameSessionJournal } from '../../packages/experimental/devframe/lib/types/session-journal.js'
import { devFrameProjectionDefinition } from '../../packages/experimental/devframe/lib/types/projection.js'

export const name = 'python-sdk-task-delivery'
export const inject = ['sessions', 'sessionProjections', 'goals']

/** Register the real projection and append one legal input/output pair before the model turn. */
export function apply(ctx, config = {}) {
  if (config.resumeBarrierUrl !== undefined) {
    installResumeProbe(ctx, config.resumeBarrierUrl)
    return
  }
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
    await journal.append(agent.session, 'devframe/task-warning', {
      version: 1, taskId: 'transport-task', warning: 'MEMORY_WRITE_FAILED', tool: 'project_memory_save', grade: 'fail',
    })
    const request = {
      identity: { controllerSessionId: agent.session.id, goalId: binding.goalId },
      cause: { kind: 'task-warning', taskId: 'transport-task' }, repairLimit: 2,
    }
    const admission = await journal.admitRepair(agent.session, request)
    const restoredJournal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), {
      requireReviewer() { throw new Error('Transport fixture must not append review evidence') },
    })
    const repeated = await restoredJournal.admitRepair(agent.session, request)
    if (admission.kind !== 'admitted' || admission.repairRound !== 1
      || repeated.kind !== 'admitted' || repeated.repairRound !== 1) {
      throw new Error('The same durable repair cause must retain its first admission across Journal replacement')
    }
    const state = ctx.sessionProjections.stateOf(agent.session, 'devframe')
    if (state?.deliveries.length !== 1 || state.repairAdmissions.length !== 1 || state.failure !== null) {
      throw new Error('Transport fixture failed the real DevFrame projection')
    }
    initialized.add(agent)
    return await next()
  })
}

/** Exercise deferred native activation through explicit SDK prompts and real persistence. */
function installResumeProbe(ctx, barrierUrl) {
  const preparedAgents = new WeakSet()
  ctx.on('agent/pre-step', async ({ agent, messages, signal }, next) => {
    const decision = await next()
    if (decision.kind !== 'enter') return decision
    const goal = ctx.goals.get(agent)
    if (goal === undefined) {
      await writeFile(join(process.cwd(), 'resume-probe.pid'), String(process.pid), { flag: 'wx', mode: 0o600 })
      const created = ctx.goals.create(agent, { objective: 'Complete the delayed resume transport probe.', maxGoalRounds: 1 })
      ctx.goals.pause(agent, created)
      await ctx.sessions.flush(agent.session)
      return decision
    }
    if (goal.phase !== 'paused' || preparedAgents.has(agent)) return decision
    if (!messages.some(message => message.content.some(block => block.type === 'text' && block.text === 'Resume the paused transport goal.'))) {
      throw new Error('The transport probe only resumes after the explicit SDK prompt')
    }
    preparedAgents.add(agent)
    const prepared = ctx.goals.prepareResume(agent, goal)
    const held = await fetch(`${barrierUrl}/held`, {
      method: 'POST', signal, body: JSON.stringify(ctx.goals.get(agent)),
    })
    if (!held.ok) throw new Error('Resume transport barrier refused')
    if (ctx.goals.get(agent)?.activation !== 'disarmed') throw new Error('Continuation armed before persistence')
    if (await ctx.sessions.flush(agent.session) === false) throw new Error('Resume transport has no persistence')
    const durable = await fetch(`${barrierUrl}/durable`, {
      method: 'POST', signal, body: JSON.stringify(prepared.goal),
    })
    if (!durable.ok) throw new Error('The resume event was not durable before activation')
    prepared.activate()
    return { kind: 'reject' }
  })
}
