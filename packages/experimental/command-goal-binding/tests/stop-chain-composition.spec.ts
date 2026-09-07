import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import type { CommandExecution } from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import type { JobHooks, JobOutcome } from '@deepseek-ai/dsh-jobs'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import { spawnSubprocess } from '../../../subprocess/subprocess-local/src/spawn.ts'
import { DevFrameOperationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, MemoryGoalBindingStore } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { GoalBinding, GoalBindingStore } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import { GoalBindingComposition } from '../src/composition.ts'
import { resolveCommandGoalBindingConfig } from '../src/config.ts'
import {
  START_GOAL_RUNNING_TEXT,
  STOP_ALREADY_STOPPED_TEXT,
  STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE,
  STOP_IN_PROGRESS_TEXT,
  renderResumeSuccess,
  renderStartSuccess,
  renderStopChainBookkeepingUnsettledText,
  renderStopChainNeedsAttentionText,
  renderStopChainStoppedText,
} from '../src/command.ts'
import { compositionRolePolicy, devFrameStateOf, resultTupleOf } from '../src/host-evidence.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-stop-chain')

const roots: string[] = []
const contexts: Context[] = []
const handles: SubprocessHandle[] = []

afterEach(async () => {
  for (const handle of handles.splice(0).reverse()) {
    try { handle.terminate() } catch { /* already exited */ }
  }
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
  await drainWorktreeFixtures()
})

/** The approved checklist /devframe-start executes for real on one worktree. */
function startChecks(root: string): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [{
      checkId: 'probe-pass',
      executable: 'node',
      arguments: ['-e', 'process.exit(0)'],
      cwd: root,
    }],
  }
}

interface TestComposition {
  readonly ctx: Context
  readonly agent: Agent
  readonly session: Session
  readonly composition: GoalBindingComposition
}

interface BootOptions {
  readonly checks: DevFrameRequiredChecksConfig
  readonly workspaceRoot: string
  readonly storageRoot: string
  readonly sessionId: SessionId
  readonly restore?: boolean
  readonly stopGraceMs?: number
  /** Mount the real process-local job registry (ctx.jobs). */
  readonly mountJobs?: boolean
  /** Inject a custom binding store (checkpoint-failure simulations). */
  readonly bindings?: GoalBindingStore
  readonly stopAdapters?: {
    /** The host-verified project tree; absent means an unverifiable inventory. */
    readonly tree?: () => readonly Agent[]
    readonly processes?: () => readonly { readonly ownerSession: SessionId; readonly label: string; readonly handle: SubprocessHandle }[]
    readonly releaseWriter?: () => void
  }
}

/** Build a live idle agent accepted by the exact-identity goal service. */
function stubAgent(session: Session): Agent {
  const inbox = new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} })
  return {
    id: session.id,
    options: {},
    session,
    inbox,
    ctx: new Context(),
    status: 'idle',
    send: () => {},
    followup: () => {},
    steer: () => {},
    inject(input) { inbox.append('next-step', input) },
    cancel() {},
    runMaintenance: task => task(new AbortController().signal),
    whenIdle() { return Promise.resolve() },
  }
}

/**
 * Boot one REAL composition with the stop chain enabled. The composition is
 * constructed directly (the host-construction face) because the stop
 * adapters are host-injected live faces, not Schema configuration.
 */
async function boot(options: BootOptions): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: options.storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  if (options.mountJobs === true) {
    await ctx.plugin(LocalJobRegistry)
    ctx.effect(function* () { yield ctx.jobs.attachController('stop-chain-spec') }, 'stop-chain-spec-jobs')
  }
  const resolved = resolveCommandGoalBindingConfig({
    workspaceId: WORKSPACE_ID,
    requiredChecksPath: join(options.storageRoot, 'required-checks.json'),
    checks: options.checks,
    taskIds: ['task-v14-stop-chain'],
    maxAttempts: 3,
    workspaceRoot: options.workspaceRoot,
    stopChain: true,
    ...(options.stopGraceMs === undefined ? {} : { stopGraceMs: options.stopGraceMs }),
  })
  const composition = new GoalBindingComposition(ctx, resolved, {
    ...(options.bindings === undefined ? {} : { bindings: options.bindings }),
    stop: options.stopAdapters === undefined ? {} : {
      ...(options.stopAdapters.tree === undefined ? {} : { tree: options.stopAdapters.tree }),
      ...(options.stopAdapters.processes === undefined ? {} : { processes: options.stopAdapters.processes }),
      ...(options.stopAdapters.releaseWriter === undefined ? {} : { releaseWriter: options.stopAdapters.releaseWriter }),
    },
  })
  let session: Session
  if (options.restore === true) {
    const preparation = await ctx.sessionPersistence.prepare(options.sessionId)
    session = preparation.session
    ctx.effect(function* () {
      yield ctx.sessions.enter(session)
      ctx.sessions.announce(session)
    }, 'test-restore-publish')
    preparation[Symbol.dispose]()
  } else {
    session = ctx.sessions.create(options.sessionId)
  }
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return { ctx, agent, session, composition }
}

/** Execute one slash command through the same registry boundary as a UI adapter. */
async function execute(test: TestComposition, line: string): Promise<CommandExecution> {
  const execution = await test.ctx.commands.execute(test.agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error('expected command was not registered')
  return execution
}

/** Every logged goal-binding event payload, in log order. */
function goalBindingEvents(test: TestComposition): GoalBinding[] {
  return test.session.snapshotEvents()
    .filter(candidate => candidate.type === 'devframe/goal-binding')
    .map(candidate => (candidate as { readonly data: GoalBinding }).data)
}

/** The lifecycle sequence the goal's binding records fold through. */
function lifecycleSequence(test: TestComposition): string[] {
  return goalBindingEvents(test).map(binding => binding.lifecycle)
}

/** Whether one pid is present in the host process table (ESRCH/EPERM aware). */
function processPresent(pid: number): boolean {
  if (process.platform !== 'win32') {
    try {
      process.kill(pid, 0)
      return true
    } catch (error) {
      return (error as NodeJS.ErrnoException).code === 'EPERM'
    }
  }
  const listing = spawnSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], { encoding: 'utf8' })
  if (listing.error !== undefined) throw listing.error
  return (listing.stdout ?? '').split('\n').some(line => line.includes(`,"${pid}",`))
}

/**
 * Poll until the host process table no longer lists the pid: the table can
 * lag the confirmed exit briefly, so a bounded poll keeps the assertion
 * honest without a timing flake.
 */
async function expectProcessGone(pid: number): Promise<void> {
  const bound = Date.now() + 3000
  while (processPresent(pid)) {
    if (Date.now() > bound) throw new Error(`process ${pid} is still present after the drain confirmed its exit`)
    await delay(50)
  }
}

/**
 * One real heartbeat child that beats every 40 ms until it is killed. The
 * child self-publishes its pid (the handle does not expose one) as the
 * heartbeat file's first line. The file lives outside the fingerprinted
 * worktree so its constant appends cannot race the source fingerprint.
 */
function spawnHeartbeatChild(fileBase: string): { handle: SubprocessHandle; heartbeatPath: string } {
  const heartbeatPath = `${fileBase}-heartbeat-${Math.random().toString(36).slice(2)}.log`
  const script = [
    'const fs = require("node:fs");',
    `const path = ${JSON.stringify(heartbeatPath)};`,
    'fs.writeFileSync(path, String(process.pid) + "\\n");',
    'const timer = setInterval(() => fs.appendFileSync(path, String(Date.now()) + "\\n"), 40);',
    'process.on("exit", () => clearInterval(timer));',
  ].join('')
  const handle = spawnSubprocess({
    argv: [process.execPath, '-e', script],
    cwd: dirname(fileBase),
    graceMs: 2000,
    stdio: { stdin: 'ignore', stdout: { maxBytes: 1000 }, stderr: { maxBytes: 1000 } },
  })
  handles.push(handle)
  return { handle, heartbeatPath }
}

/** Poll until the real child is beating; resolve with its self-published pid. */
async function awaitHeartbeats(heartbeatPath: string, minimum: number): Promise<number> {
  const bound = Date.now() + 5000
  while (true) {
    if (existsSync(heartbeatPath)) {
      const lines = readFileSync(heartbeatPath, 'utf8').split('\n').filter(line => line.length > 0)
      if (lines.length >= minimum + 1) return Number(lines[0])
    }
    if (Date.now() > bound) throw new Error('the heartbeat child never started beating')
    await delay(25)
  }
}

/**
 * One real owned job whose producer honors the kill after `settleMs`. The
 * returned flag reports whether the job ever received the kill request, so
 * tests can prove the tree drained a descendant's job — or left an
 * unrelated project's job alone.
 */
function startSlowCancelJob(
  test: TestComposition,
  owner: Agent,
  settleMs: number,
): { cancelled: () => boolean } {
  let cancelRequested = false
  let settleJob: (outcome: JobOutcome) => void = () => {}
  const done = new Promise<JobOutcome>((resolve) => { settleJob = resolve })
  test.ctx.jobs.start({
    kind: 'bash',
    label: `slow-cancel-${Math.random().toString(36).slice(2)}`,
    owner,
    run: (): JobHooks => ({
      cancel: () => {
        cancelRequested = true
        void delay(settleMs).then(() => settleJob({ status: 'killed', detail: 'project stop' }))
      },
      done,
    }),
  })
  return { cancelled: () => cancelRequested }
}

describe('stop chain composition (AT4-06: the real chain behind /devframe-stop)', { timeout: 120_000 }, () => {
  it('drains a real child process in order and releases the writer after the confirmed chain', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-ordered-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-ordered')
    const releaseOrder: string[] = []
    let publishedPid: number | undefined
    // The verified tree is captured after the boot hands back the root
    // agent; the face evaluates when the chain runs.
    const treeAgents: Agent[] = []
    const { handle, heartbeatPath } = spawnHeartbeatChild(join(storageRoot, 'state'))
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => treeAgents,
        processes: () => [{ ownerSession: sessionId, label: 'stop-chain-heartbeat', handle }],
        releaseWriter: () => { releaseOrder.push('releaseWriter') },
      },
    })
    treeAgents.push(first.agent)
    const started = await execute(first, '/devframe-start fix the billing bug')
    if (started.result.kind !== 'success') throw new Error('expected a success result')
    expect(started.result.text).toBe(renderStartSuccess(1, 'passed'))
    // Readiness: the real child has actually been beating before anything stops it.
    publishedPid = await awaitHeartbeats(heartbeatPath, 2)

    const stopped = await execute(first, '/devframe-stop')
    if (stopped.result.kind !== 'success') {
      throw new Error(`expected a success result: ${stopped.result.text} | projection failure: ${devFrameStateOf(first.ctx, first.session).failure}`)
    }
    expect(stopped.result.text).toBe(renderStopChainStoppedText())

    // The release ran exactly once, after the drain confirmed the child's
    // exit; the host table then stops listing the pid (bounded poll).
    expect(releaseOrder).toEqual(['releaseWriter'])
    await expectProcessGone(publishedPid)
    // The durable vocabulary: stop_requested (command), stop_requested (the
    // chain's own re-observation, an idempotent repeat), quiescence
    // confirmation, then the stopped terminal record.
    expect(lifecycleSequence(first)).toEqual([
      'admission_open',
      'stop_requested',
      'stop_requested',
      'quiescence_confirmed',
      'stopped',
    ])
    const stored = await first.composition.bindingStore.load(ControllerSessionId(first.agent.id))
    expect(stored.at(-1)?.lifecycle).toBe('stopped')
    // The cached controller was evicted with the terminal bookkeeping (the
    // abandon lane's reconciliation), so the fence is no longer observable
    // as open.
    expect(first.composition.admissionOf(first.agent)).not.toBe('open')
    expect(devFrameStateOf(first.ctx, first.session).failure).toBeNull()
  })

  it('drains a real descendant agent tree: child job, child process, every session flushed', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-descendant-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-descendant')
    const childSessionId = SessionId('worker-v14-stop-chain-descendant')
    let writerReleased = false
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        // The host-verified tree: the root and the real descendant worker.
        // The unrelated project agent below is deliberately absent.
        tree: () => [first.agent, childAgent],
        processes: () => [{ ownerSession: childSessionId, label: 'descendant-heartbeat', handle: childHandle }],
        releaseWriter: () => { writerReleased = true },
      },
    })
    // The real descendant worker agent on its own session, and a real
    // unrelated project agent the tree must never touch.
    const childSession = first.ctx.sessions.create(childSessionId)
    const childAgent = stubAgent(childSession)
    first.ctx.agents.register(childAgent)
    childSession.append('devframe/role-policy', compositionRolePolicy(WORKSPACE_ID, sessionId))
    const unrelatedSession = first.ctx.sessions.create(SessionId('unrelated-v14-stop-chain'))
    const unrelatedAgent = stubAgent(unrelatedSession)
    first.ctx.agents.register(unrelatedAgent)
    // A real child-owned job and a real child-owned process: both must drain.
    const childJob = startSlowCancelJob(first, childAgent, 150)
    const { handle: childHandle, heartbeatPath } = spawnHeartbeatChild(join(storageRoot, 'state'))
    // A real unrelated job the tree-scoped stop must leave alone.
    const unrelatedJob = startSlowCancelJob(first, unrelatedAgent, 150)
    const started = await execute(first, '/devframe-start fix the billing bug')
    if (started.result.kind !== 'success') throw new Error('expected a success result')
    const childPid = await awaitHeartbeats(heartbeatPath, 2)

    const stopped = await execute(first, '/devframe-stop')
    if (stopped.result.kind !== 'success') {
      throw new Error(`expected a success result: ${stopped.result.text} | projection failure: ${devFrameStateOf(first.ctx, first.session).failure}`)
    }
    expect(stopped.result.text).toBe(renderStopChainStoppedText())
    expect(writerReleased).toBe(true)
    // The descendant chain drained: its job was killed and its process died.
    expect(childJob.cancelled()).toBe(true)
    await expectProcessGone(childPid)
    // Every participating session was flushed, including the descendant's:
    // its durable log must carry the pre-stop record after the chain (the
    // JSONL backend only writes on flush, so presence proves the flush).
    const childDurable = await first.ctx.sessionPersistence.load(childSessionId)
    expect(childDurable.events.some(event => event.type === 'devframe/role-policy')).toBe(true)
    // The unrelated project was untouched: its job never received the kill.
    expect(unrelatedJob.cancelled()).toBe(false)
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
  })

  it('reports needs_attention with the writer retained and reruns after the resource settles', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-attention-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-attention')
    let writerReleased = false
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      stopGraceMs: 200,
      mountJobs: true,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => { writerReleased = true },
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    // A real owned job whose work outlives the chain's grace: the kill is
    // requested but the producer settles long after the wait timed out.
    const rootJob = startSlowCancelJob(first, first.agent, 1000)

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text.startsWith('The stop chain could not confirm quiescence (')).toBe(true)
      expect(stopped.result.text).toContain('job:')
      // The wait resolution at the grace boundary is timing-dependent — the
      // wait's own timeout and the chain deadline race — so the named reason
      // may be either; both retain the writer and name the job resource.
      expect(stopped.result.text).toMatch(/job:[^:]+: (timeout|unconfirmed|operation_failed)/)
      expect(stopped.result.text).toContain('The writer remains held')
      expect(stopped.result.text).not.toContain(STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE)
    }
    expect(writerReleased).toBe(false)
    expect(goalBindingEvents(first).at(-1)?.lifecycle).toBe('needs_attention')
    expect(rootJob.cancelled()).toBe(true)

    // The job settles after the timeout; the rerun drains cleanly and the
    // goal reaches the stopped terminal state.
    await delay(1400)
    const rerun = await execute(first, '/devframe-stop')
    expect(rerun.result.kind).toBe('success')
    if (rerun.result.kind === 'success') expect(rerun.result.text).toBe(renderStopChainStoppedText())
    expect(writerReleased).toBe(true)
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
    expect(devFrameStateOf(first.ctx, first.session).failure).toBeNull()
  })

  it('keeps the attempt budget counting across a real stop and a cold restart', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-budget-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-budget')
    const treeAgents: Agent[] = []
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => treeAgents,
        releaseWriter: () => {},
      },
    })
    treeAgents.push(first.agent)
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const bindingA = goalBindingEvents(first)[0]
    if (bindingA === undefined) throw new Error('started binding is missing')
    first.session.append('devframe/usage', {
      version: 1,
      operationId: DevFrameOperationId('operation-v14-stop-chain-1'),
      binding: resultTupleOf(bindingA),
      role: 'worker',
      attempt: 1,
      phase: 'reserved',
      consumedAttempts: 1,
      maxAttempts: bindingA.budget.maxAttempts,
    })
    expect((await execute(first, '/devframe-stop')).result.kind).toBe('success')
    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    const secondTreeAgents: Agent[] = []
    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
      mountJobs: true,
      stopAdapters: {
        tree: () => secondTreeAgents,
        releaseWriter: () => {},
      },
    })
    secondTreeAgents.push(second.agent)
    const resumed = await execute(second, '/devframe-resume')
    if (resumed.result.kind !== 'success') throw new Error('expected a success result')
    expect(resumed.result.text).toBe(renderResumeSuccess())
    const resumedBinding = goalBindingEvents(second).at(-1)
    if (resumedBinding === undefined) throw new Error('resumed binding is missing')
    second.session.append('devframe/usage', {
      version: 1,
      operationId: DevFrameOperationId('operation-v14-stop-chain-2'),
      binding: resultTupleOf(resumedBinding),
      role: 'worker',
      attempt: 2,
      phase: 'reserved',
      consumedAttempts: 2,
      maxAttempts: resumedBinding.budget.maxAttempts,
    })
    const state = devFrameStateOf(second.ctx, second.session)
    expect(state.failure).toBeNull()
    expect(state.usage.map(record => record.consumedAttempts)).toEqual([1, 2])
  })

  it('refuses a repeat stop after the stopped terminal state without new records', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-repeat-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-repeat')
    const treeAgents: Agent[] = []
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => treeAgents,
        releaseWriter: () => {},
      },
    })
    treeAgents.push(first.agent)
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    expect((await execute(first, '/devframe-stop')).result.kind).toBe('success')
    const recordsBefore = goalBindingEvents(first).length
    const repeat = await execute(first, '/devframe-stop')
    expect(repeat.result.kind).toBe('error')
    if (repeat.result.kind === 'error') expect(repeat.result.text).toBe(STOP_ALREADY_STOPPED_TEXT)
    expect(goalBindingEvents(first).length).toBe(recordsBefore)
  })

  it('refuses a second chain and a new start while the drain is in flight', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-inflight-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-inflight')
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => {},
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    // A real owned job that honors its kill after a bounded settle: the
    // chain's drain window stays open long enough for the probes.
    startSlowCancelJob(first, first.agent, 400)

    const chainPromise = execute(first, '/devframe-stop')
    // The chain's in-flight guard is set in its synchronous prologue; after
    // this settle the probes can only observe the refusal.
    await delay(50)
    const probe = await execute(first, '/devframe-stop')
    expect(probe.result.kind).toBe('error')
    if (probe.result.kind === 'error') expect(probe.result.text).toBe(STOP_IN_PROGRESS_TEXT)
    const started = await execute(first, '/devframe-start another objective')
    expect(started.result.kind).toBe('error')
    if (started.result.kind === 'error') expect(started.result.text).toBe(START_GOAL_RUNNING_TEXT)

    const chainResult = await chainPromise
    expect(chainResult.result.kind).toBe('success')
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
  }, 60_000)

  it('fails safe to needs_attention when the writer release is not wired', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-unwired-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-unwired')
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: { tree: () => [first.agent] },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toBe(renderStopChainNeedsAttentionText([{
        resource: 'writer:release',
        reason: 'operation_failed',
      }]))
    }
    // The goal stays in the stop flow — never advanced to stopped.
    expect(lifecycleSequence(first)).toEqual([
      'admission_open',
      'stop_requested',
      'stop_requested',
      'quiescence_confirmed',
      'needs_attention',
    ])
    expect(first.ctx.goals.get(first.agent)?.phase).not.toBe('complete')
  })

  it('fails closed on an unverifiable project tree inventory instead of releasing the writer', async () => {
    const fixture = await createCommittedWorktree()
    // Absent tree face: the inventory cannot be verified, so an empty list
    // must never stand in for a verified full tree.
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-unverified-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-unverified')
    let writerReleased = false
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: { releaseWriter: () => { writerReleased = true } },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toContain(STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE)
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(writerReleased).toBe(false)
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')
    expect(first.ctx.goals.get(first.agent)?.phase).not.toBe('complete')

    // An explicitly empty tree fails closed the same way.
    const emptyRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-empty-tree-'))
    roots.push(emptyRoot)
    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot: emptyRoot,
      sessionId: SessionId('controller-v14-stop-chain-empty-tree'),
      mountJobs: true,
      stopAdapters: {
        tree: () => [],
        releaseWriter: () => { writerReleased = true },
      },
    })
    expect((await execute(second, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const emptyTreeStop = await execute(second, '/devframe-stop')
    expect(emptyTreeStop.result.kind).toBe('error')
    if (emptyTreeStop.result.kind === 'error') {
      expect(emptyTreeStop.result.text).toContain(STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE)
    }
    expect(writerReleased).toBe(false)
    expect(lifecycleSequence(second).at(-1)).toBe('needs_attention')
  })

  it('refuses the release when the jobs registry is missing despite a verified tree and a wired hook', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-no-jobs-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-no-jobs')
    let writerReleased = false
    // No jobs registry mounted: a missing registry is a fail-closed
    // misconfiguration, never a verified zero-jobs state — the chain must
    // refuse the release instead of reporting a clean stop.
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => { writerReleased = true },
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text.startsWith('The stop chain could not confirm quiescence (')).toBe(true)
      expect(stopped.result.text).toContain('jobs:')
      expect(stopped.result.text).toContain('operation_failed')
      expect(stopped.result.text).toContain('The writer remains held')
      expect(stopped.result.text).not.toContain(STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE)
    }
    expect(writerReleased).toBe(false)
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')
    expect(first.ctx.goals.get(first.agent)?.phase).not.toBe('complete')
  })

  it('never lands stopped on a release failure and converges on the rerun', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-release-throw-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-release-throw')
    let writerReleased = false
    let releaseCalls = 0
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      stopGraceMs: 400,
      mountJobs: true,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => {
          releaseCalls += 1
          if (releaseCalls === 1) throw new Error('the writer file is locked by another process')
          writerReleased = true
        },
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')

    // First stop: the release callback throws after the drain confirmed —
    // the stopped terminal must NOT land (a release failure is not a stop);
    // the flow folds needs_attention and stays re-stoppable.
    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toContain('writer:release')
      expect(stopped.result.text).toContain('operation_failed')
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(writerReleased).toBe(false)
    expect(lifecycleSequence(first)).toEqual([
      'admission_open',
      'stop_requested',
      'stop_requested',
      'quiescence_confirmed',
      'needs_attention',
    ])

    // Second stop: the release succeeds now — the full chain re-drains
    // idempotently and converges to the stopped terminal.
    const rerun = await execute(first, '/devframe-stop')
    expect(rerun.result.kind).toBe('success')
    if (rerun.result.kind === 'success') expect(rerun.result.text).toBe(renderStopChainStoppedText())
    expect(writerReleased).toBe(true)
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
  })

  it('re-enters the release for a log left quiescence-confirmed and converges', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-cold-confirmed-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-cold-confirmed')
    let writerReleased = false
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => { writerReleased = true },
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    // Simulate the crash state exactly: the drain confirmed quiescence
    // durably, then the process died before the release and the terminal
    // bookkeeping. The repeat stop must NOT be refused.
    const started = goalBindingEvents(first)[0]
    if (started === undefined) throw new Error('started binding is missing')
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'stop_requested' })
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'quiescence_confirmed' })
    expect(lifecycleSequence(first).at(-1)).toBe('quiescence_confirmed')

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('success')
    if (stopped.result.kind === 'success') expect(stopped.result.text).toBe(renderStopChainStoppedText())
    expect(writerReleased).toBe(true)
    expect(lifecycleSequence(first)).toEqual([
      'admission_open',
      'stop_requested',
      'quiescence_confirmed',
      'stopped',
    ])
    const stored = await first.composition.bindingStore.load(ControllerSessionId(first.agent.id))
    expect(stored.at(-1)?.lifecycle).toBe('stopped')
  })

  it('returns bounded with honest writer state when the binding save never settles', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-never-settle-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-never-settle')
    let writerReleased = false
    // The checkpoint store hangs on the first stopped-binding save, then
    // behaves: the composition must return bounded by the stop grace, with
    // the writer state honest, and the repeat stop reconciles against the
    // durable log instead of hanging.
    const memory = new MemoryGoalBindingStore()
    let hungFirstStoppedSave = false
    const hangingStore: GoalBindingStore = {
      load: id => memory.load(id),
      read: workspaceId => memory.read(workspaceId),
      save: async (binding) => {
        if (binding.lifecycle === 'stopped' && !hungFirstStoppedSave) {
          hungFirstStoppedSave = true
          await new Promise<void>(() => { /* never settles */ })
        }
        await memory.save(binding)
      },
      write: record => memory.write(record),
    }
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      stopGraceMs: 300,
      mountJobs: true,
      bindings: hangingStore,
      stopAdapters: {
        tree: () => [first.agent],
        releaseWriter: () => { writerReleased = true },
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toBe(renderStopChainBookkeepingUnsettledText(true))
    }
    expect(writerReleased).toBe(true)
    // The record append beat the hung save: the durable log already holds
    // the stopped terminal (the log is the binding authority).
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')

    // The repeat stop is bounded and named: the log says stopped, so the
    // gate refuses with the stable already-stopped text instead of hanging.
    const rerun = await execute(first, '/devframe-stop')
    expect(rerun.result.kind).toBe('error')
    if (rerun.result.kind === 'error') expect(rerun.result.text).toBe(STOP_ALREADY_STOPPED_TEXT)
  })

  it('finishes a stop flow left at stop_requested across a cold restart', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-stop-requested-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-stop-requested')
    const treeAgents: Agent[] = []
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => treeAgents,
        releaseWriter: () => {},
      },
    })
    treeAgents.push(first.agent)
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    // Simulate the crash exactly: the stop request landed durably, then the
    // process died while the chain waited in its drain. No release, no
    // quiescence record, no drain evidence.
    const started = goalBindingEvents(first)[0]
    if (started === undefined) throw new Error('started binding is missing')
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'stop_requested' })
    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    // Cold restart: the host re-registers the agent, replays the log to
    // stop_requested, and the operator repeats the stop. The recovery
    // re-enters the drain over the verified inventory and finishes.
    const secondTreeAgents: Agent[] = []
    let writerReleased = false
    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
      mountJobs: true,
      stopAdapters: {
        tree: () => secondTreeAgents,
        releaseWriter: () => { writerReleased = true },
      },
    })
    secondTreeAgents.push(second.agent)
    expect(lifecycleSequence(second).at(-1)).toBe('stop_requested')

    const stopped = await execute(second, '/devframe-stop')
    if (stopped.result.kind !== 'success') {
      throw new Error(`expected a success result: ${stopped.result.text} | projection failure: ${devFrameStateOf(second.ctx, second.session).failure}`)
    }
    expect(stopped.result.text).toBe(renderStopChainStoppedText())
    expect(writerReleased).toBe(true)
    // The recovery's own re-observation folds as an idempotent repeat.
    expect(lifecycleSequence(second)).toEqual([
      'admission_open',
      'stop_requested',
      'stop_requested',
      'quiescence_confirmed',
      'stopped',
    ])
    const stored = await second.composition.bindingStore.load(ControllerSessionId(second.agent.id))
    expect(stored.at(-1)?.lifecycle).toBe('stopped')
  })

  it('refuses a stop_requested recovery when a tree member lost its live identity', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-stop-chain-stale-tree-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-stop-chain-stale-tree')
    const childSessionId = SessionId('worker-v14-stop-chain-stale-tree')
    let writerReleased = false
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        // The stale host inventory still lists the pre-crash descendant, but
        // that agent was never re-registered after the restart: the owner
        // identity fact is missing and the recovery must fail closed.
        tree: () => [first.agent, phantomChild],
        releaseWriter: () => { writerReleased = true },
      },
    })
    // A descendant-shaped agent that is NOT registered on the live registry.
    const phantomChild = stubAgent(first.ctx.sessions.create(childSessionId))
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const started = goalBindingEvents(first)[0]
    if (started === undefined) throw new Error('started binding is missing')
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'stop_requested' })

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text.startsWith('The stop chain could not confirm quiescence (')).toBe(true)
      expect(stopped.result.text).toContain(`agent:${childSessionId}`)
      expect(stopped.result.text).toContain('identity_unknown')
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(writerReleased).toBe(false)
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')
    expect(first.ctx.goals.get(first.agent)?.phase).not.toBe('complete')
  })
})
