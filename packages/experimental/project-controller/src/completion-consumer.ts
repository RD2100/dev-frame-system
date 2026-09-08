/** Whole-Goal checks and independent review of the controller's final merged tree. */
import { execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { isAbsolute } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { z as validation } from 'zod'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { Session } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-goal'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import { DevFrameSessionJournal, DevFrameSnapshotId, FileRequiredChecksConfigStore,
  RequiredChecksDigest, computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameCheckResult } from '@deepseek-ai/dsh-experimental-devframe'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {} from './controller.ts'

/** Loader plugin name. */
export const name = 'project-goal-evidence'
/** Existing host authority, evidence, tool and worktree services. */
export const inject = ['tools', 'agents', 'goals', 'sessions', 'sessionProjections', 'projectController', 'agentBindings', 'workspaceRegistry', 'worktreeRegistry']
/** Host-approved whole-Goal checks and bounded execution settings. */
export interface Config {
  /** Absolute existing checks ledger path. */
  requiredChecksPath: string
  /** Existing approved whole-Goal checkset digest. */
  requiredChecksDigest: string
  /** Deployment-selected Git executable. */
  gitExecutable: string
  /** Per-Git-process timeout. */
  gitTimeoutMs: number
  /** Per-Git-process output limit. */
  gitMaxOutputBytes: number
  /** Per-check timeout. */
  checkTimeoutMs: number
  /** Per-check output limit. */
  checkMaxOutputBytes: number
}
/** Loader validation of explicit deployment settings. */
export const Config: z<Config> = z.object({
  requiredChecksPath: z.string(), requiredChecksDigest: z.string().min(1), gitExecutable: z.string().min(1),
  gitTimeoutMs: z.number().min(1), gitMaxOutputBytes: z.number().min(1),
  checkTimeoutMs: z.number().min(1), checkMaxOutputBytes: z.number().min(1),
})
const execFileAsync = promisify(execFile)
const findingsSchema = validation.array(validation.object({
  id: validation.string().min(1), severity: validation.enum(['blocking', 'warning', 'note']), message: validation.string().min(1),
  path: validation.string().min(1).optional(), line: validation.number().int().positive().optional(),
}).strict())

/**
 * Register final-tree verification and review tools. Neither tool completes or rebinds the Goal.
 * @param ctx - Host services owning the current controller and its durable records.
 * @param config - Approved checkset and bounded subprocess settings.
 */
export function apply(ctx: Context, config: Config): void {
  if (!isAbsolute(config.requiredChecksPath) || [config.gitTimeoutMs, config.gitMaxOutputBytes,
    config.checkTimeoutMs, config.checkMaxOutputBytes].some(value => !Number.isSafeInteger(value) || value < 1)) {
    throw new Error('Whole-Goal evidence requires an absolute ledger path and positive integer limits')
  }
  const store = new FileRequiredChecksConfigStore({ path: config.requiredChecksPath })
  const digest = RequiredChecksDigest(config.requiredChecksDigest)
  const failedSessions = new Set<Session['id']>()
  const tails = new Map<Session['id'], Promise<unknown>>()
  let stopped = false
  ctx.effect(() => async () => { stopped = true; await Promise.allSettled(tails.values()) })
  const flush = async (session: Session) => {
    try {
      if (!await ctx.sessions.flush(session)) throw new Error('Whole-Goal persistence is unavailable')
    } catch (error) { failedSessions.add(session.id); throw error }
  }
  const env = () => Object.fromEntries(Object.entries(process.env)
    .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const resolve = (agent: Agent | undefined, role: 'controller' | 'lead', signal: AbortSignal) => {
    signal.throwIfAborted()
    if (stopped || agent === undefined || ctx.agents.get(agent.id) !== agent) throw new Error('Whole-Goal evidence requires the actual live caller')
    const caller = ctx.agentBindings.find(agent.session.id)
    const root = role === 'controller' ? caller : caller?.parentSessionId === undefined ? undefined : ctx.agentBindings.find(caller.parentSessionId)
    if (caller?.role !== role || caller.agentId !== agent.id || root?.role !== 'controller' || root.parentSessionId !== undefined) {
      throw new Error('Whole-Goal evidence requires the root controller or an independent direct lead')
    }
    const rootAgent = ctx.agents.get(root.agentId)
    const session = ctx.sessions.get(root.sessionId)
    if (session === undefined || rootAgent?.session !== session || failedSessions.has(session.id)) throw new Error('Whole-Goal controller is unavailable')
    const state = ctx.sessionProjections.stateOf(session, 'devframe')
    const goal = state?.bindings.at(-1)
    const nativeGoal = ctx.goals.get(rootAgent)
    if (state === undefined || state.failure !== null || goal?.lifecycle !== 'admission_open' || goal.taskIds.length === 0
      || nativeGoal?.id !== goal.goalId || nativeGoal.phase !== 'active' || nativeGoal.revision < goal.goalRevision
      || (state.lifecycle !== null && state.lifecycle.binding.goalId === goal.goalId && state.lifecycle.state !== 'admission_open')) {
      throw new Error('Whole-Goal evidence requires an intact current open Goal')
    }
    const rows = ctx.workspaceRegistry.list().flatMap(workspace => ctx.worktreeRegistry.list(workspace.id))
    const tree = rows.find(row => row.id === root.worktreeId)
    if (tree === undefined || tree.path !== root.worktreePath || rootAgent.session.header.cwd !== tree.path
      || String(tree.workspaceId) !== String(goal.workspaceId) || String(tree.lockedBy) !== String(root.sessionId)) {
      throw new Error('Whole-Goal evidence requires the controller worktree writer lock')
    }
    const integrations = ctx.projectController.integrationReceipts(session.id)
    const receipts = goal.taskIds.map(id => {
      const task = ctx.projectController.find(TaskId(String(id)))
      const delivery = state.deliveries.findLast(item => item.taskId === id && item.binding.goalId === goal.goalId)
      const row = integrations.find(item => String(item.taskId) === String(id))
      const verification = state.verifications.find(item => item.verificationId === row?.verificationId)
      const review = state.reviews.find(item => item.reviewId === row?.reviewId)
      if (task?.state !== 'integrated' || delivery === undefined || row?.state !== 'applied' || row.appliedHead === undefined
        || row.sourceCommit !== delivery.sourceCommit || row.sourcePath !== delivery.worktreePath || row.targetPath !== tree.path
        || verification?.deliveryId !== delivery.deliveryId || verification.status !== 'passed'
        || review?.deliveryId !== delivery.deliveryId || review.decision !== 'pass') {
        throw new Error(`Whole-Goal evidence requires the current applied delivery for task "${id}"`)
      }
      if (role === 'lead' && delivery.workerSessionId === caller.sessionId) throw new Error('Whole-Goal reviewer implemented a bound task')
      return row
    })
    if (role === 'lead') {
      const leadTree = rows.find(row => row.id === caller.worktreeId)
      if (caller.sessionId === root.sessionId || leadTree === undefined || leadTree.id === tree.id
        || leadTree.path === tree.path || leadTree.path !== agent.session.header.cwd
        || String(leadTree.lockedBy) !== String(caller.sessionId)
        || !state.rolePolicy?.assignments.some(item => item.sessionId === caller.sessionId && item.role === 'lead')) {
        throw new Error('Whole-Goal review requires independent live lead authority and worktree')
      }
    }
    return { session, state, goal, tree, caller, receipts,
      signature: JSON.stringify({ goal, nativeGoal, root, caller, tree, receipts, policy: state.rolePolicy }) }
  }
  const observe = async (path: string, receipts: ReturnType<typeof resolve>['receipts'], signal: AbortSignal) => {
    const git = async (...args: string[]) => (await execFileAsync(config.gitExecutable, ['-C', path, ...args], {
      env: env(), signal, windowsHide: true, timeout: config.gitTimeoutMs, maxBuffer: config.gitMaxOutputBytes, encoding: 'utf8',
    })).stdout.trim()
    // Pin HEAD first: the receipt ancestry is validated for exactly the head
    // the fingerprint will bind, so a HEAD move anywhere inside this
    // observation is rejected instead of self-consistently passing against a
    // head whose ancestry was never checked.
    const head = await git('rev-parse', '--verify', 'HEAD')
    if (await git('status', '--porcelain=v1', '--untracked-files=all') !== '') throw new Error('Whole-Goal evidence requires a clean committed controller tree')
    for (const row of receipts) await git('merge-base', '--is-ancestor', row.appliedHead!, head)
    const source = await computeSourceFingerprint({ worktreePath: path, gitCommand: config.gitExecutable,
      maxOutputBytes: config.gitMaxOutputBytes, timeoutMs: config.gitTimeoutMs, signal })
    if (source.headCommit !== head || await git('rev-parse', 'HEAD') !== head
      || await git('status', '--porcelain=v1', '--untracked-files=all') !== '') {
      throw new Error('Controller source changed during observation')
    }
    return source
  }
  const serial = async <T>(id: Session['id'], run: () => Promise<T>) => {
    const prior = tails.get(id) ?? Promise.resolve()
    const pending = prior.then(run, run)
    tails.set(id, pending)
    try { return await pending } finally { if (tails.get(id) === pending) tails.delete(id) }
  }
  const reviewerDirectory = { roleOf: (id: Session['id']): 'lead' | undefined => {
    const binding = ctx.agentBindings.find(id)
    if (binding === undefined) return undefined
    try { resolve(ctx.agents.get(binding.agentId), 'lead', new AbortController().signal); return 'lead' } catch { return undefined }
  } }
  const journal = new DevFrameSessionJournal(flush, { requireReviewer(id) {
    if (reviewerDirectory.roleOf(id) !== 'lead') throw new Error('Whole-Goal reviewer authority is unavailable')
  } })
  const output = {
    schema: { type: 'object' as const, additionalProperties: false, properties: {
      verificationId: { type: 'string' as const, required: true as const }, outcome: { type: 'string' as const, required: true as const },
      sourcePath: { type: 'string' as const, required: true as const }, sourceCommit: { type: 'string' as const, required: true as const },
    } },
    render: (_args: unknown, value: { verificationId: string; outcome: string; sourcePath: string; sourceCommit: string }) => [
      { type: 'text' as const, text: `Whole-Goal ${value.outcome}; verification ${value.verificationId}; review source ${value.sourcePath} at ${value.sourceCommit}.` },
    ],
  }
  ctx.tools.register(defineTool({
    name: 'project_goal_verify', description: 'Run the host-approved whole-Goal checks on the clean final merged controller tree after every task is integrated. Returns the exact verification identity and source to give an independent lead for review. Does not complete the Goal.',
    parameters: {}, output, isConcurrencySafe: () => false,
    async execute(_args, exec) {
      const owner = resolve(exec.agent, 'controller', exec.signal)
      return serial(owner.session.id, async () => {
        const initial = resolve(exec.agent, 'controller', exec.signal)
        const source = await observe(initial.tree.path, initial.receipts, exec.signal)
        const guard = () => {
          if (resolve(exec.agent, 'controller', exec.signal).signature !== initial.signature) throw new Error('Whole-Goal verification authority changed')
        }
        const unchanged = async () => {
          const current = await observe(initial.tree.path, initial.receipts, exec.signal)
          guard()
          if (current.fingerprint !== source.fingerprint) throw new Error('Controller source changed during whole-Goal verification')
        }
        const approved = await store.load(digest)
        for (const check of approved.checks) {
          if (!isAbsolute(check.cwd) || await realpathNormalize(check.cwd) !== await realpathNormalize(initial.tree.path)) {
            throw new Error('Whole-Goal checks must run in the controller worktree')
          }
        }
        const evidence = new AgentEvidenceJournal({ flush, journal, reviewerDirectory, execution: async checks => {
          if (JSON.stringify(checks) !== JSON.stringify(approved)) throw new Error('Approved whole-Goal checks changed')
          const results: DevFrameCheckResult[] = []
          for (const check of checks.checks) {
            guard()
            const started = Date.now()
            try {
              await execFileAsync(check.executable, [...check.arguments], { cwd: check.cwd, env: env(), signal: exec.signal,
                windowsHide: true, timeout: config.checkTimeoutMs, maxBuffer: config.checkMaxOutputBytes })
              results.push({ ...check, status: 'passed', exitCode: 0, durationMs: Date.now() - started })
            } catch (error) {
              const failure = error as { code?: string | number; killed?: boolean }
              results.push({ ...check, status: exec.signal.aborted ? 'cancelled' : failure.killed ? 'timed_out' : typeof failure.code === 'number' ? 'failed' : 'unknown',
                ...(typeof failure.code === 'number' ? { exitCode: failure.code } : {}), durationMs: Date.now() - started })
            }
          }
          await unchanged()
          return results
        } })
        const verification = await evidence.recordVerification({ session: initial.session,
          binding: { controllerSessionId: initial.goal.controllerSessionId, goalId: initial.goal.goalId,
            goalRevision: initial.goal.goalRevision, taskIds: initial.goal.taskIds, workspaceId: initial.goal.workspaceId,
            acceptanceHash: initial.goal.acceptanceHash, sourceFingerprint: source.fingerprint, snapshotId: DevFrameSnapshotId(randomUUID()) },
          requiredChecksDigest: digest, requiredChecksStore: store, appendOptions: { beforeAppend: guard, prepare: unchanged } })
        await unchanged()
        return { verificationId: String(verification.verificationId), outcome: verification.status, sourcePath: initial.tree.path, sourceCommit: source.headCommit }
      })
    },
    presentCall: () => ({ card: 'generic', title: 'Verify whole Goal' }), presentResult: () => ({ card: 'generic' }),
  }))
  ctx.tools.register(defineTool({
    name: 'project_goal_review', description: 'Record your independent review of the exact final merged source identified by project_goal_verify. Inspect that controller source and the whole Goal before deciding. Only a live independent direct lead may submit; source or evidence changes require a new review. Does not complete the Goal.',
    parameters: { verificationId: { type: 'string', required: true, description: 'Exact verification identity from project_goal_verify whose source you inspected.' },
      decision: { type: 'string', required: true, description: 'pass or changes_required.' },
      findings: { type: 'json', required: true, description: 'Array of findings with id, severity (blocking, warning, note), message, optional path and line.' } },
    output, isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (args.decision !== 'pass' && args.decision !== 'changes_required') throw new Error('Whole-Goal decision must be pass or changes_required')
      const decision = args.decision
      const findings = findingsSchema.parse(args.findings).map(finding => ({
        id: finding.id, severity: finding.severity, message: finding.message,
        ...(finding.path === undefined ? {} : { path: finding.path }),
        ...(finding.line === undefined ? {} : { line: finding.line }),
      }))
      const owner = resolve(exec.agent, 'lead', exec.signal)
      return serial(owner.session.id, async () => {
        const initial = resolve(exec.agent, 'lead', exec.signal)
        const verification = initial.state.verifications.findLast(item => item.deliveryId === undefined && item.binding.goalId === initial.goal.goalId)
        if (verification === undefined || verification.verificationId !== args.verificationId || verification.requiredChecks.digest !== digest
          || verification.binding.goalRevision !== initial.goal.goalRevision || verification.binding.acceptanceHash !== initial.goal.acceptanceHash
          || (decision === 'pass' && verification.status !== 'passed')) throw new Error('Whole-Goal review requires the current matching verification')
        const guard = () => {
          const current = resolve(exec.agent, 'lead', exec.signal)
          if (current.signature !== initial.signature || current.state.verifications.findLast(item =>
            item.deliveryId === undefined && item.binding.goalId === initial.goal.goalId)?.verificationId !== verification.verificationId) {
            throw new Error('Whole-Goal review authority or verification changed')
          }
        }
        const unchanged = async () => {
          const source = await observe(initial.tree.path, initial.receipts, exec.signal)
          guard()
          if (source.fingerprint !== verification.binding.sourceFingerprint) throw new Error('Controller source changed after whole-Goal verification')
          return source
        }
        const source = await unchanged()
        await new AgentEvidenceJournal({ flush, journal, reviewerDirectory }).recordReview({
          session: initial.session, binding: verification.binding, reviewerSessionId: initial.caller.sessionId,
          policyVersion: initial.state.rolePolicy!.policyVersion, decision, findings,
          appendOptions: { beforeAppend: guard, prepare: async () => { await unchanged() } },
        })
        await unchanged()
        return { verificationId: String(verification.verificationId), outcome: decision, sourcePath: initial.tree.path, sourceCommit: source.headCommit }
      })
    },
    presentCall: () => ({ card: 'generic', title: 'Review whole Goal' }), presentResult: () => ({ card: 'generic' }),
  }))
}
