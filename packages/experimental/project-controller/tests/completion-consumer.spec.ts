/** Loader-mounted final-tree producer and native completion with real Git and check subprocesses. */
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import AgentRegistry, { Inbox, type Agent } from '@deepseek-ai/dsh-agent'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import type { Session } from '@deepseek-ai/dsh-session'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import { FileRequiredChecksConfigStore, DevFrameDeliveryId, DevFrameVerificationId, DevFrameReviewId,
  deliveryResultBinding, computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe'
import { foldDevFrameState } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import * as goalCommand from '@deepseek-ai/dsh-experimental-command-goal-binding'
import type { GoalBindingComposition } from '@deepseek-ai/dsh-experimental-command-goal-binding'
import * as consumer from '../src/completion-consumer.ts'
import { prepareIntegration } from './integration-harness.ts'

/**
 * Test-controlled hook firing inside the source-observation window the
 * consumer must close: between the receipt ancestry check and the fingerprint
 * bind. Only the barrier test arms it; every other test leaves it null and
 * the mock delegates unchanged.
 */
const sourceObservationBarrier: { fire: null | (() => Promise<void>) } = { fire: null }
vi.mock('@deepseek-ai/dsh-experimental-devframe', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@deepseek-ai/dsh-experimental-devframe')>()
  return {
    ...actual,
    computeSourceFingerprint: async (...args: Parameters<typeof actual.computeSourceFingerprint>) => {
      await sourceObservationBarrier.fire?.()
      return actual.computeSourceFingerprint(...args)
    },
  }
})

const cleanups: (() => Promise<void>)[] = []
afterEach(async () => { for (const cleanup of cleanups.splice(0).reverse()) await cleanup() })

function live(session: Session): Agent {
  const inbox = new Inbox(session, { inserted() {}, discarded() {}, claimed() {} })
  return { id: session.id, ctx: new Context(), session, inbox, options: {}, status: 'idle',
    send() {}, followup() {}, steer() {}, inject(input) { inbox.append('next-step', input) }, cancel() {},
    runMaintenance: task => task(new AbortController().signal), whenIdle: async () => {} }
}

async function setup(checkScript = "import { readFileSync } from 'node:fs'; import { strict as assert } from 'node:assert'; assert.equal(readFileSync('feature.txt','utf8').trim(),'reviewed')") {
  const f = await prepareIntegration()
  cleanups.push(() => f.h.dispose())
  const { ctx } = f.h
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(GoalService)
  const root = live(f.controller)
  const lead = live(f.lead)
  const worker = live(f.worker)
  for (const agent of [root, lead, worker]) ctx.effect(() => ctx.agents.register(agent))
  const leadBinding = ctx.agentBindings.find(f.lead.id)!
  await ctx.worktreeRegistry.bind(leadBinding.worktreeId!, WorktreeLockHolder(f.lead.id))
  const path = f.request.git.targetPath
  const requiredChecksPath = join(f.h.root, 'final-checks.json')
  const checks = { version: 1 as const, checks: [{ checkId: 'whole-goal', executable: process.execPath,
    arguments: ['--input-type=module', '-e', checkScript], cwd: path }] }
  const requiredChecksDigest = await new FileRequiredChecksConfigStore({ path: requiredChecksPath }).save(checks)
  const modules = new Map<string, unknown>([['goal-command', goalCommand], ['whole-goal', consumer]])
  const configPath = join(f.h.root, 'completion.cordis.yml')
  await writeFile(configPath, JSON.stringify([
    { name: 'goal-command', config: { workspaceId: f.binding.workspaceId, workspaceRoot: path,
      requiredChecksPath, checks, taskIds: f.binding.taskIds, maxAttempts: 10 } },
    { name: 'whole-goal', config: { requiredChecksPath, requiredChecksDigest, gitExecutable: 'git',
      gitTimeoutMs: 15_000, gitMaxOutputBytes: 1024 * 1024, checkTimeoutMs: 15_000, checkMaxOutputBytes: 1024 * 1024 } },
  ]))
  ctx.baseUrl = pathToFileURL(f.h.root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.internal = { version: 'v2', async import(specifier: string) {
    if (!modules.has(specifier)) throw new Error(`Unexpected completion Loader import ${specifier}`)
    return modules.get(specifier)
  } } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
  await ctx.loader.await()
  expect(
    [...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled).map(entry => entry.options.name),
  ).toEqual([])
  // The composition seam is deliberately unmerged from the Context service
  // map, so the in-process test resolves it by name and asserts the class.
  const composition = ctx.get('commandGoalBinding') as GoalBindingComposition
  const binding = await composition.startBinding(root, { objective: 'integrate reviewed feature',
    taskIds: f.binding.taskIds, acceptanceHash: f.binding.acceptanceHash, sourceFingerprint: f.binding.sourceFingerprint,
    snapshotId: f.binding.snapshotId, budget: { maxAttempts: 10 }, confirmationId: 'completion-test' })
  f.controller.append('devframe/goal-binding', binding)
  const delivery = { ...f.delivery, binding: {
    controllerSessionId: binding.controllerSessionId, goalId: binding.goalId, goalRevision: binding.goalRevision,
    taskIds: binding.taskIds, acceptanceHash: binding.acceptanceHash, sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId, workspaceId: binding.workspaceId,
  }, deliveryId: DevFrameDeliveryId('native-delivery') }
  f.controller.append('devframe/task-delivery', delivery)
  const output = deliveryResultBinding(delivery)
  f.controller.append('devframe/verification', { ...f.verification, verificationId: DevFrameVerificationId('native-verification'),
    binding: output, deliveryId: delivery.deliveryId })
  f.controller.append('devframe/review', { ...f.review, reviewId: DevFrameReviewId('native-review'), binding: output, deliveryId: delivery.deliveryId })
  const marker = await ctx.projectController.requestMainTreeMerge(f.controller.id, f.taskId, f.request)
  await ctx.projectController.integrate(f.taskId, marker)
  expect(ctx.sessionProjections.stateOf(f.controller, 'devframe')?.failure).toBeNull()
  const execute = (agent: Agent, name: string, args: object = {}) => ctx.tools.execute({ agent, name,
    arguments: args, signal: new AbortController().signal, callId: ToolCallId('whole-goal-call') })
  const state = () => ctx.sessionProjections.stateOf(f.controller, 'devframe')!
  return { ...f, ctx, root, lead, worker, path, binding, composition, execute, state }
}

describe('whole-Goal completion producer', { timeout: 90_000 }, () => {
  it('refuses a preserved reviewed checkout when the actual integration target changed', async () => {
    const f = await setup()
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    expect((await f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })).isError).toBe(false)
    const preserved = join(f.h.root, 'preserved')
    await f.git(f.path, 'worktree', 'add', '--detach', preserved, 'HEAD')
    expect((await computeSourceFingerprint({ worktreePath: preserved })).fingerprint).toBe(verification.binding.sourceFingerprint)
    await writeFile(join(f.path, 'feature.txt'), 'unreviewed controller change\n')
    const completion = await f.composition.completeCurrent({ agent: f.root, worktreePath: preserved })
    expect(completion.kind).toBe('error')
    expect(completion.text).toContain('controller worktree named by its integration receipts')
    expect(f.ctx.goals.get(f.root)?.phase).toBe('active')
  })

  it('refuses completion when writer ownership changes during fingerprint admission', async () => {
    const f = await setup()
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    await f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })
    const entered = Promise.withResolvers<undefined>()
    const release = Promise.withResolvers<undefined>()
    const load = f.composition.requiredChecksStore.load.bind(f.composition.requiredChecksStore)
    const spy = vi.spyOn(f.composition.requiredChecksStore, 'load').mockImplementation(async (digest) => {
      const config = await load(digest)
      entered.resolve(undefined)
      await release.promise
      return config
    })
    const completion = f.composition.completeCurrent({ agent: f.root })
    const rejected = expect(completion).rejects.toThrow('writer lock')
    try {
      await entered.promise
      const owner = f.ctx.agentBindings.find(f.root.session.id)!
      await f.ctx.worktreeRegistry.unbind(owner.worktreeId!, WorktreeLockHolder(f.root.session.id))
      release.resolve(undefined)
      await rejected
      expect(f.ctx.goals.get(f.root)?.phase).toBe('active')
    } finally { release.resolve(undefined); spy.mockRestore() }
  })

  it('refuses the visible passing review when its pending durability checkpoint fails', async () => {
    const f = await setup()
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    const entered = Promise.withResolvers<undefined>()
    const release = Promise.withResolvers<boolean>()
    const flush = f.ctx.sessions.flush.bind(f.ctx.sessions)
    const spy = vi.spyOn(f.ctx.sessions, 'flush').mockImplementation(async (session) => {
      if (session === f.controller && f.state().reviews.at(-1)?.deliveryId === undefined) {
        entered.resolve(undefined)
        return release.promise
      }
      return flush(session)
    })
    const review = f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })
    try {
      await entered.promise
      expect(f.state().reviews.at(-1)?.decision).toBe('pass')
      const completion = f.composition.completeCurrent({ agent: f.root })
      const rejected = expect(completion).rejects.toThrow(/persist|blocked/)
      release.resolve(false)
      expect((await review).isError).toBe(true)
      await rejected
      expect(f.ctx.goals.get(f.root)?.phase).toBe('active')
    } finally { release.resolve(false); spy.mockRestore() }
  })

  it('refuses source mutation while admitted check configuration is resolving', async () => {
    const f = await setup()
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    await f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })
    const entered = Promise.withResolvers<undefined>()
    const release = Promise.withResolvers<undefined>()
    const load = f.composition.requiredChecksStore.load.bind(f.composition.requiredChecksStore)
    const spy = vi.spyOn(f.composition.requiredChecksStore, 'load').mockImplementation(async (digest) => {
      const config = await load(digest)
      entered.resolve(undefined)
      await release.promise
      return config
    })
    const completion = f.composition.completeCurrent({ agent: f.root })
    try {
      await entered.promise
      await writeFile(join(f.path, 'feature.txt'), 'changed during admission\n')
      release.resolve(undefined)
      const result = await completion
      expect(result.kind, result.text).toBe('error')
      expect(f.ctx.goals.get(f.root)?.phase).toBe('active')
    } finally { release.resolve(undefined); spy.mockRestore() }
  })
  it('records actual final-tree checks and independent review then completes the same native Goal', async () => {
    const f = await setup()
    const verified = await f.execute(f.root, 'project_goal_verify')
    expect(verified.isError, JSON.stringify(verified)).toBe(false)
    const verification = f.state().verifications.at(-1)!
    expect(verification.status).toBe('passed')
    expect(verification.deliveryId).toBeUndefined()
    expect(verification.binding.sourceFingerprint).not.toBe(f.binding.sourceFingerprint)
    const reviewed = await f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })
    expect(reviewed.isError, JSON.stringify(reviewed)).toBe(false)
    expect(f.state().reviews.at(-1)?.reviewerSessionId).toBe(f.lead.session.id)
    const completion = await f.composition.completeCurrent({ agent: f.root })
    expect(completion.kind, completion.text).toBe('success')
    expect(f.ctx.goals.get(f.root)).toMatchObject({ id: f.binding.goalId, phase: 'complete' })
    expect(
      (await f.composition.bindingStore.load(ControllerSessionId(f.root.id))).at(-1)?.sourceFingerprint,
    ).toBe(f.binding.sourceFingerprint)
    const replay = foldDevFrameState(f.controller.snapshotEvents(), f.controller.header)
    expect(replay.failure).toBeNull()
    expect(replay.verifications.at(-1)).toEqual(verification)
    expect((await f.execute(f.root, 'project_goal_verify')).isError).toBe(true)
  })

  it('keeps failed final-tree checks as failed evidence and refuses a passing review', async () => {
    const f = await setup('process.exit(7)')
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    expect(verification.status).toBe('failed')
    expect(verification.checks[0]).toMatchObject({ exitCode: 7, status: 'failed' })
    const reviewed = await f.execute(f.lead, 'project_goal_review', { verificationId: verification.verificationId, decision: 'pass', findings: [] })
    expect(reviewed.isError).toBe(true)
    expect((await f.composition.completeCurrent({ agent: f.root })).kind).toBe('error')
    expect(f.ctx.goals.get(f.root)?.phase).not.toBe('complete')
  })

  it('refuses worker/controller review and changed final source', async () => {
    const f = await setup()
    await f.execute(f.root, 'project_goal_verify')
    const verification = f.state().verifications.at(-1)!
    const args = { verificationId: verification.verificationId, decision: 'pass', findings: [] }
    for (const caller of [f.root, f.worker]) expect((await f.execute(caller, 'project_goal_review', args)).isError).toBe(true)
    await writeFile(join(f.path, 'feature.txt'), 'changed\n')
    expect((await f.execute(f.lead, 'project_goal_review', args)).isError).toBe(true)
    expect(f.state().reviews.some(item => item.deliveryId === undefined && item.binding.goalId === f.binding.goalId)).toBe(false)
  })

  it('records no verification when its check mutates the final source', async () => {
    const f = await setup("import { writeFileSync } from 'node:fs'; writeFileSync('feature.txt','changed')")
    expect((await f.execute(f.root, 'project_goal_verify')).isError).toBe(true)
    expect(f.state().verifications.some(item => item.deliveryId === undefined && item.binding.goalId === f.binding.goalId)).toBe(false)
  })

  it('refuses verification when HEAD moves between the ancestry check and the fingerprint', async () => {
    const f = await setup()
    let fired = false
    sourceObservationBarrier.fire = async () => {
      fired = true
      // A forward empty commit keeps every receipt an ancestor of the moved
      // head, so only the pinned-head ordering can reject this observation.
      await f.git(f.path, 'commit', '--allow-empty', '-m', 'barrier-moved-head')
    }
    try {
      const verified = await f.execute(f.root, 'project_goal_verify')
      expect(fired, 'the barrier must fire inside the observation window').toBe(true)
      expect(verified.isError, JSON.stringify(verified)).toBe(true)
      expect(f.state().verifications.some(item => item.deliveryId === undefined && item.binding.goalId === f.binding.goalId)).toBe(false)
    } finally { sourceObservationBarrier.fire = null }
  })
})
