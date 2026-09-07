/** Explicit Worker delivery and independent lead review over host-owned task evidence. */
import { execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { isAbsolute } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { z as validation } from 'zod'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { Session } from '@deepseek-ai/dsh-session'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import type { RequiredChecksExecution } from '@deepseek-ai/dsh-experimental-agent-evidence'
import { FileRequiredChecksConfigStore, computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe'
import { TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { RequiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe'
import { resolveRepairLimit } from '@deepseek-ai/dsh-experimental-devframe'
import { DevFrameDeliveryId, DevFrameSnapshotId, deliveryResultBinding } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameCheckResult, DevFrameTaskDeliveryEventData } from '@deepseek-ai/dsh-experimental-devframe'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from './controller.ts'
import { normalizeCommitPaths, registerProjectCommitTool } from './commit-consumer.ts'

/** Loader namespace name; the existing controller service owns task persistence. */
export const name = 'project-delivery-tools'
/** Services required to derive caller and evidence authority. */
export const inject = ['tools', 'agents', 'sessions', 'sessionProjections', 'projectController', 'agentBindings', 'workspaceRegistry', 'worktreeRegistry']
/** Explicit deployment settings; tools cannot choose identities, commands, or approval digests. */
export interface Config {
  /** Shared Goal repair-round limit; omitted uses the DevFrame default. */
  repairLimit?: number
  /** Existing approved-checks ledger. */
  requiredChecksPath: string
  /** Approved checkset digest keyed by task id. */
  requiredChecksByTask: Record<string, string>
  /** Host-selected Git executable. */
  gitExecutable: string
  /** Per-Git-process timeout. */
  gitTimeoutMs: number
  /** Per-Git-process output cap. */
  gitMaxOutputBytes: number
  /** Per-check-process timeout. */
  checkTimeoutMs: number
  /** Per-check-process output cap. */
  checkMaxOutputBytes: number
  /** Host-registered commit paths per task bounding what project_commit may commit. */
  commitPathsByTask?: Record<string, string[]>
}
/** Loader validation for deployment settings. */
export const Config: z<Config> = z.object({
  repairLimit: z.number(),
  requiredChecksPath: z.string(), requiredChecksByTask: z.dict(z.string()),
  gitExecutable: z.string().min(1), gitTimeoutMs: z.number().min(1), gitMaxOutputBytes: z.number().min(1),
  checkTimeoutMs: z.number().min(1), checkMaxOutputBytes: z.number().min(1),
  commitPathsByTask: z.dict(z.array(z.string())),
})
const execFileAsync = promisify(execFile)
const findingsSchema = validation.array(validation.object({
  id: validation.string().min(1), severity: validation.enum(['blocking', 'warning', 'note']), message: validation.string().min(1),
  path: validation.string().min(1).optional(), line: validation.number().int().positive().optional(),
}).strict())

/**
 * Register explicit delivery and review tools without creating another controller or approving checks.
 * @param ctx - Existing host services and durable role authority.
 * @param config - Approved task checksets and bounded process settings.
 */
export function apply(ctx: Context, config: Config): void {
  const repairLimit = resolveRepairLimit(config)
  if (!isAbsolute(config.requiredChecksPath) || [
    config.gitTimeoutMs, config.gitMaxOutputBytes, config.checkTimeoutMs, config.checkMaxOutputBytes,
  ]
    .some(value => !Number.isSafeInteger(value) || value < 1)) throw new Error('Project delivery requires an absolute ledger and positive integer limits')
  const store = new FileRequiredChecksConfigStore({ path: config.requiredChecksPath })
  const failedSessions = new Set<string>()
  let stopped = false
  const tails = new Map<string, Promise<unknown>>()
  const flush = async (session: Session) => {
    try {
      if (!await ctx.sessions.flush(session)) throw new Error('Project evidence persistence is unavailable')
    } catch (error) {
      failedSessions.add(String(session.id))
      throw error
    }
  }
  const reviewerDirectory = {
    roleOf(id: Session['id']): 'lead' | undefined {
      const lead = ctx.agentBindings.find(id)
      const root = lead?.parentSessionId === undefined ? undefined : ctx.agentBindings.find(lead.parentSessionId)
      const agent = lead === undefined ? undefined : ctx.agents.get(lead.agentId)
      const session = root === undefined ? undefined : ctx.sessions.get(root.sessionId)
      const policy = session === undefined ? undefined : ctx.sessionProjections.stateOf(session, 'devframe')?.rolePolicy
      if (stopped || lead?.role !== 'lead' || root?.role !== 'controller' || root.parentSessionId !== undefined
        || agent?.session.id !== id || !policy?.assignments.some(item => item.sessionId === id && item.role === 'lead')) return undefined
      return 'lead'
    },
  }
  const journal = new DevFrameSessionJournal(flush, {
    requireReviewer(id) {
      if (reviewerDirectory.roleOf(id) === undefined) throw new Error('Review requires a live registered lead in the current role policy')
    },
  })
  ctx.effect(() => async () => {
    stopped = true
    await Promise.allSettled(tails.values())
  })
  const env = () => Object.fromEntries(Object.entries(process.env)
    .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const serial = async <T>(key: string, run: () => Promise<T>): Promise<T> => {
    const previous = tails.get(key) ?? Promise.resolve()
    const pending = previous.then(run, run)
    tails.set(key, pending)
    try { return await pending } finally { if (tails.get(key) === pending) tails.delete(key) }
  }
  const resolve = (agent: Agent | undefined, taskId: ReturnType<typeof TaskId>, role: 'worker' | 'lead', signal: AbortSignal) => {
    signal.throwIfAborted()
    if (stopped || agent === undefined || ctx.agents.get(agent.id) !== agent) throw new Error('Project evidence requires the actual live caller')
    const task = ctx.projectController.find(taskId)
    const worker = task?.assigneeSessionId === undefined ? undefined : ctx.agentBindings.find(task.assigneeSessionId)
    const lead = worker?.parentSessionId === undefined ? undefined : ctx.agentBindings.find(worker.parentSessionId)
    const root = lead?.parentSessionId === undefined ? undefined : ctx.agentBindings.find(lead.parentSessionId)
    if (task === undefined || worker?.role !== 'worker' || lead?.role !== 'lead' || root?.role !== 'controller'
      || root.parentSessionId !== undefined || worker.taskId !== taskId
      || worker.pluginId !== task.pluginId || lead.pluginId !== task.pluginId
      || agent.session.id !== (role === 'worker' ? worker.sessionId : lead.sessionId)) {
      throw new Error('Project evidence requires the assigned Worker or its independent parent lead')
    }
    const actors = [root, lead, worker]
    for (const binding of actors) {
      const live = ctx.agents.get(binding.agentId)
      if (live === undefined || live.session.id !== binding.sessionId || live.session.header.cwd !== binding.worktreePath) {
        throw new Error('Project evidence requires live registered hierarchy Agents on their own worktrees')
      }
    }
    const session = ctx.sessions.get(root.sessionId)
    if (session === undefined || failedSessions.has(String(root.sessionId))) throw new Error('Project evidence controller persistence is unavailable')
    const state = ctx.sessionProjections.stateOf(session, 'devframe')
    const goal = state?.bindings.at(-1)
    if (state === undefined || state.failure !== null || goal?.lifecycle !== 'admission_open'
      || String(goal.controllerSessionId) !== String(root.sessionId) || !goal.taskIds.some(id => String(id) === String(taskId))
      || (state.lifecycle !== null && state.lifecycle.binding.goalId === goal.goalId && state.lifecycle.state !== 'admission_open')) {
      throw new Error('Project evidence requires its task in the current open Goal')
    }
    const rows = ctx.workspaceRegistry.list().flatMap(workspace => ctx.worktreeRegistry.list(workspace.id))
    const trees = actors.map(binding => rows.find(row => row.id === binding.worktreeId))
    if (actors.some((actor, i) => {
      const tree = trees[i]
      return tree === undefined || tree.path !== actor.worktreePath
        || String(tree.workspaceId) !== String(goal.workspaceId) || String(tree.lockedBy) !== String(actor.sessionId)
    })
      || new Set(trees.map(tree => tree?.id)).size !== 3 || new Set(trees.map(tree => tree?.path)).size !== 3) {
      throw new Error('Project evidence requires three independent registered worktrees and writer locks')
    }
    if (worker.worktreePath === undefined || worker.worktreeId === undefined) throw new Error('Worker worktree is absent')
    const signature = JSON.stringify({ goal, root, lead, worker, trees, policy: state.rolePolicy })
    return { task, worker, lead, root, session, state, goal, signature, sourcePath: worker.worktreePath, sourceId: worker.worktreeId }
  }
  const snapshot = async (path: string, signal: AbortSignal) => {
    const git = async (...args: string[]) => (await execFileAsync(config.gitExecutable, ['-C', path, ...args], {
      env: env(), signal, windowsHide: true, timeout: config.gitTimeoutMs, maxBuffer: config.gitMaxOutputBytes, encoding: 'utf8',
    })).stdout.trim()
    if (await git('status', '--porcelain=v1', '--untracked-files=all') !== '') {
      throw new Error('Delivery requires a clean committed Worker worktree')
    }
    const head = await git('rev-parse', '--verify', 'HEAD')
    const source = await computeSourceFingerprint({
      worktreePath: path, gitCommand: config.gitExecutable, maxOutputBytes: config.gitMaxOutputBytes,
      signal, timeoutMs: config.gitTimeoutMs,
    })
    signal.throwIfAborted()
    if (source.headCommit !== head || await git('rev-parse', '--verify', 'HEAD') !== head
      || await git('status', '--porcelain=v1', '--untracked-files=all') !== '') throw new Error('Worker source changed during observation')
    return { head, fingerprint: source.fingerprint }
  }
  const parseTask = (value: string) => {
    if (value.trim() !== value) throw new Error('Task id must be trimmed')
    return TaskId(value)
  }
  const output = {
    schema: { type: 'object' as const, additionalProperties: false, properties: {
      taskId: { type: 'string' as const, required: true as const }, state: { type: 'string' as const, required: true as const },
      outcome: { type: 'string' as const, required: true as const },
    } },
    render: (_args: unknown, value: { taskId: string; state: string; outcome: string }) => [{ type: 'text' as const,
      text: `Task ${value.taskId}: ${value.state}; ${value.outcome}.` }],
  }
  ctx.tools.register(defineTool({
    name: 'project_deliver',
    description: 'Explicitly deliver your assigned task from a clean committed Worker worktree. The host records the actual output and runs the existing approved checks. Repeated successful delivery reuses its evidence; interrupted or failed checks run again only with retryChecks true. This does not approve review or integrate work.',
    parameters: { taskId: { type: 'string', required: true, description: 'Your assigned task.' },
      retryChecks: { type: 'boolean', description: 'Explicitly rerun the approved checks after a failed or interrupted attempt.' } },
    output, isConcurrencySafe: () => false,
    async execute(args, exec) {
      const taskId = parseTask(args.taskId)
      return await serial(String(taskId), async () => {
        const initial = resolve(exec.agent, taskId, 'worker', exec.signal)
        if (!['developing', 'reviewing'].includes(initial.task.state)) throw new Error('Delivery requires a developing or reviewing task')
        const guard = () => {
          if (resolve(exec.agent, taskId, 'worker', exec.signal).signature !== initial.signature) throw new Error('Delivery authority changed')
        }
        const observed = await snapshot(initial.sourcePath, exec.signal)
        guard()
        const rawDigest = config.requiredChecksByTask[String(taskId)]
        if (rawDigest === undefined) throw new Error('Task has no host-approved checkset')
        const digest = RequiredChecksDigest(rawDigest)
        const approved = await store.load(digest)
        for (const check of approved.checks) {
          if (!isAbsolute(check.cwd) || await realpathNormalize(check.cwd) !== await realpathNormalize(initial.sourcePath)) {
            throw new Error('Approved checks must execute in the assigned Worker worktree')
          }
        }
        guard()
        const latest = initial.state.deliveries.findLast(item =>
          String(item.taskId) === String(taskId) && item.binding.goalId === initial.goal.goalId)
        const sameSource = latest !== undefined && latest.sourceCommit === observed.head
          && latest.sourceFingerprint === observed.fingerprint && latest.binding.goalRevision === initial.goal.goalRevision
          && latest.workerSessionId === initial.worker.sessionId && latest.worktreeId === initial.sourceId
          && latest.worktreePath === initial.sourcePath
        let delivery: DevFrameTaskDeliveryEventData
        if (sameSource) delivery = latest
        else {
          delivery = {
            version: 1, deliveryId: DevFrameDeliveryId(randomUUID()), taskId: GoalTaskId(String(taskId)),
            binding: {
              controllerSessionId: initial.goal.controllerSessionId, workspaceId: initial.goal.workspaceId,
              goalId: initial.goal.goalId, goalRevision: initial.goal.goalRevision, taskIds: [...initial.goal.taskIds],
              acceptanceHash: initial.goal.acceptanceHash, sourceFingerprint: initial.goal.sourceFingerprint,
              snapshotId: initial.goal.snapshotId,
            }, workerSessionId: initial.worker.sessionId,
            worktreeId: initial.sourceId, worktreePath: initial.sourcePath, sourceCommit: observed.head,
            sourceFingerprint: observed.fingerprint, snapshotId: DevFrameSnapshotId(randomUUID()),
          }
          await journal.append(initial.session, 'devframe/task-delivery', delivery, {
            beforeAppend: guard,
            prepare: async () => {
              const current = await snapshot(initial.sourcePath, exec.signal)
              if (current.head !== observed.head || current.fingerprint !== observed.fingerprint) throw new Error('Source changed before delivery recording')
            },
          })
        }
        guard()
        const latestDeliveryGuard = () => {
          guard()
          const latestNow = resolve(exec.agent, taskId, 'worker', exec.signal).state.deliveries.findLast(item =>
            String(item.taskId) === String(taskId) && item.binding.goalId === initial.goal.goalId)
          if (latestNow?.deliveryId !== delivery.deliveryId) throw new Error('Delivery was superseded')
        }
        const priorReview = resolve(exec.agent, taskId, 'worker', exec.signal).state.reviews.findLast(item => item.deliveryId === delivery.deliveryId)
        if (priorReview?.decision === 'changes_required') throw new Error('Negative review requires a changed source and a new delivery')
        let verification = resolve(exec.agent, taskId, 'worker', exec.signal).state.verifications.findLast(item => item.deliveryId === delivery.deliveryId)
        if (verification !== undefined && verification.requiredChecks.digest !== digest) throw new Error('Approved checkset differs from recorded verification')
        if (sameSource && (verification === undefined || verification.status !== 'passed') && args.retryChecks !== true) {
          throw new Error('Checks are failed or uncertain; explicit retryChecks is required to execute them again')
        }
        if (verification === undefined || verification.status !== 'passed') {
          const execution: RequiredChecksExecution = async (checks) => {
            const results: DevFrameCheckResult[] = []
            for (const check of checks.checks) {
              latestDeliveryGuard()
              if (JSON.stringify(checks) !== JSON.stringify(approved)) throw new Error('Approved checkset changed during delivery')
              const started = Date.now()
              try {
                await execFileAsync(check.executable, [...check.arguments], { cwd: check.cwd, env: env(), signal: exec.signal,
                  windowsHide: true, timeout: config.checkTimeoutMs, maxBuffer: config.checkMaxOutputBytes })
                results.push({ ...check, status: 'passed', exitCode: 0, durationMs: Date.now() - started })
              } catch (error) {
                const failure = error as { code?: string | number; killed?: boolean }
                const status = exec.signal.aborted ? 'cancelled' : failure.killed ? 'timed_out' : typeof failure.code === 'number' ? 'failed' : 'unknown'
                results.push({ ...check, status, ...(typeof failure.code === 'number' ? { exitCode: failure.code } : {}), durationMs: Date.now() - started })
              }
            }
            const checkedSource = await snapshot(initial.sourcePath, exec.signal)
            latestDeliveryGuard()
            if (checkedSource.head !== observed.head || checkedSource.fingerprint !== observed.fingerprint) {
              throw new Error('Source changed during checks; no verification was recorded')
            }
            return results
          }
          verification = await new AgentEvidenceJournal({ flush, execution, journal, reviewerDirectory }).recordVerification({
            session: initial.session, binding: deliveryResultBinding(delivery), deliveryId: delivery.deliveryId,
            requiredChecksDigest: digest, requiredChecksStore: store,
            appendOptions: {
              beforeAppend: latestDeliveryGuard,
              prepare: async () => {
                const current = await snapshot(initial.sourcePath, exec.signal)
                if (current.head !== observed.head || current.fingerprint !== observed.fingerprint) throw new Error('Source changed before verification recording')
              },
            },
          })
        }
        const after = await snapshot(initial.sourcePath, exec.signal)
        guard()
        if (after.head !== observed.head || after.fingerprint !== observed.fingerprint) throw new Error('Source changed during checks; a new delivery is required')
        if (verification.status !== 'passed') return { taskId: String(taskId), state: initial.task.state, outcome: 'checks failed' }
        const current = ctx.projectController.find(taskId)
        if (current?.state === 'developing') await ctx.projectController.beginReview(taskId, { beforePersist: latestDeliveryGuard })
        else if (current?.state !== 'reviewing') throw new Error('Task state changed before review admission')
        return { taskId: String(taskId), state: 'reviewing', outcome: 'checks passed' }
      })
    },
    presentCall: args => ({ card: 'generic', title: `Deliver task ${args.taskId}` }), presentResult: () => ({ card: 'generic' }),
  }))
  ctx.tools.register(defineTool({
    name: 'project_review',
    description: 'Record your explicit independent lead review of the latest task delivery. Pass submits that exact verified output; changes_required returns it for correction. Repeated identical decisions reuse the recorded review and repair only the task state; a conflicting decision requires a new delivery.',
    parameters: { taskId: { type: 'string', required: true, description: 'Task assigned to your Worker.' },
      decision: { type: 'string', required: true, description: 'pass or changes_required.' },
      findings: { type: 'json', required: true, description: 'Array of findings with id, severity (blocking, warning, note), message, optional path and line.' } },
    output, isConcurrencySafe: () => false,
    async execute(args, exec) {
      const taskId = parseTask(args.taskId)
      if (args.decision !== 'pass' && args.decision !== 'changes_required') throw new Error('Review decision must be pass or changes_required')
      const decision = args.decision
      const findings = findingsSchema.parse(args.findings).map(finding => ({
        id: finding.id, severity: finding.severity, message: finding.message,
        ...(finding.path === undefined ? {} : { path: finding.path }),
        ...(finding.line === undefined ? {} : { line: finding.line }),
      }))
      return await serial(String(taskId), async () => {
        const initial = resolve(exec.agent, taskId, 'lead', exec.signal)
        const guard = () => {
          if (resolve(exec.agent, taskId, 'lead', exec.signal).signature !== initial.signature) throw new Error('Review authority changed')
        }
        const delivery = initial.state.deliveries.findLast(item =>
          String(item.taskId) === String(taskId) && item.binding.goalId === initial.goal.goalId)
        if (delivery === undefined || delivery.workerSessionId !== initial.worker.sessionId || delivery.worktreeId !== initial.sourceId
          || delivery.worktreePath !== initial.sourcePath || delivery.binding.goalRevision !== initial.goal.goalRevision) {
          throw new Error('Review requires the current assigned Worker delivery')
        }
        const observed = await snapshot(initial.sourcePath, exec.signal)
        guard()
        if (observed.head !== delivery.sourceCommit || observed.fingerprint !== delivery.sourceFingerprint) throw new Error('Source changed after delivery')
        const policy = initial.state.rolePolicy
        if (policy === null || !policy.assignments.some(item => item.sessionId === initial.lead.sessionId && item.role === 'lead')) {
          throw new Error('Review requires the current recorded lead role policy')
        }
        const verification = initial.state.verifications.findLast(item => item.deliveryId === delivery.deliveryId)
        if (verification === undefined || (decision === 'pass' && verification.status !== 'passed')) {
          throw new Error('Review requires matching verification')
        }
        const reviewGuard = () => {
          guard()
          const state = resolve(exec.agent, taskId, 'lead', exec.signal).state
          const latest = state.deliveries.findLast(item =>
            String(item.taskId) === String(taskId) && item.binding.goalId === initial.goal.goalId)
          const checked = state.verifications.findLast(item => item.deliveryId === delivery.deliveryId)
          if (latest?.deliveryId !== delivery.deliveryId || checked?.verificationId !== verification.verificationId) {
            throw new Error('Delivery or verification changed during review')
          }
        }
        const prior = initial.state.reviews.findLast(item => item.deliveryId === delivery.deliveryId)
        let review = prior
        if (prior !== undefined) {
          if (prior.reviewerSessionId !== initial.lead.sessionId || prior.decision !== decision
            || JSON.stringify(prior.findings) !== JSON.stringify(findings)) {
            throw new Error('A different decision requires a new task delivery')
          }
        } else {
          if (initial.task.state !== 'reviewing') throw new Error('A new review requires a reviewing task')
          reviewGuard()
          review = await new AgentEvidenceJournal({ flush, journal, reviewerDirectory }).recordReview({
            session: initial.session, binding: deliveryResultBinding(delivery), deliveryId: delivery.deliveryId,
            reviewerSessionId: initial.lead.sessionId, policyVersion: policy.policyVersion, decision, findings,
            appendOptions: {
              beforeAppend: reviewGuard,
              prepare: async () => {
                const current = await snapshot(initial.sourcePath, exec.signal)
                if (current.head !== observed.head || current.fingerprint !== observed.fingerprint) throw new Error('Source changed before review recording')
              },
            },
          })
        }
        const after = await snapshot(initial.sourcePath, exec.signal)
        reviewGuard()
        if (after.head !== observed.head || after.fingerprint !== observed.fingerprint) throw new Error('Source changed during review recording')
        const current = ctx.projectController.find(taskId)
        if (decision === 'pass') {
          if (current?.state === 'reviewing') await ctx.projectController.submit(taskId, { beforePersist: reviewGuard })
          else if (current?.state !== 'submitted') throw new Error('Task is not ready for review recovery')
        } else {
          if (review === undefined) throw new Error('Correction requires a recorded review')
          const repair = await journal.admitRepair(initial.session, {
            identity: { controllerSessionId: initial.goal.controllerSessionId, goalId: initial.goal.goalId },
            cause: { kind: 'review', reviewId: review.reviewId },
            repairLimit,
          }, { beforeAppend: reviewGuard })
          if (repair.kind !== 'admitted') throw new Error(`The repair limit (${repair.repairLimit}) is exhausted; correction requires human input`)
          if (current?.state === 'reviewing') await ctx.projectController.returnToDevelopment(taskId, { beforePersist: reviewGuard })
          else if (current?.state !== 'developing') throw new Error('Task is not ready for correction recovery')
        }
        return { taskId: String(taskId), state: decision === 'pass' ? 'submitted' : 'developing', outcome: decision }
      })
    },
    presentCall: args => ({ card: 'generic', title: `Review task ${args.taskId}` }), presentResult: () => ({ card: 'generic' }),
  }))
  const commitPaths = new Map<string, readonly string[]>()
  for (const [taskId, paths] of Object.entries(config.commitPathsByTask ?? {})) {
    try {
      commitPaths.set(taskId, normalizeCommitPaths(paths))
    } catch (error) {
      throw new Error(`Invalid host commit path scope for task ${taskId}: ${(error as Error).message}`)
    }
  }
  registerProjectCommitTool({
    tools: ctx.tools,
    registry: ctx.worktreeRegistry,
    resolveWorker: (agent, taskId, signal) => resolve(agent, taskId, 'worker', signal),
    serial,
    gitEnvironment: env,
    commitPathsByTask: commitPaths,
    jobs: () => ctx.get('jobs'),
    resolveOwnerHead: (sourceId) => {
      const row = ctx.workspaceRegistry.list()
        .flatMap(workspace => ctx.worktreeRegistry.list(workspace.id).map(tree => ({ workspace, tree })))
        .find(entry => String(entry.tree.id) === String(sourceId))
      if (row === undefined) throw new Error('Project commit requires the registered Worker worktree row')
      return { ownerPath: row.workspace.path, branch: row.tree.branch }
    },
    config: { gitExecutable: config.gitExecutable, gitTimeoutMs: config.gitTimeoutMs, gitMaxOutputBytes: config.gitMaxOutputBytes },
  })
}
