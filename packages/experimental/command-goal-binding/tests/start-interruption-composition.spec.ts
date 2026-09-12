import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import type { CommandExecution } from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { GoalBindingStore } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { MemoryGoalBindingStore } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import { GoalBindingComposition } from '../src/composition.ts'
import { resolveCommandGoalBindingConfig } from '../src/config.ts'
import {
  RESUME_NO_BINDING_RECORD_TEXT,
  START_GOAL_RUNNING_TEXT,
  renderStartSuccess,
} from '../src/command.ts'
import { devFrameStateOf } from '../src/host-evidence.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-interruption')

const roots: string[] = []
const contexts: Context[] = []
let bootNumber = 0

afterEach(async () => {
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
  readonly interruptedSaveCount: () => number
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
 * The injection fixture: a binding store whose first `save` throws once —
 * the durable outage between the native Goal creation and the binding
 * persistence inside the start path — and delegates every call afterwards.
 */
function flakyBindingStore(): GoalBindingStore & { readonly saveCount: () => number } {
  const inner = new MemoryGoalBindingStore()
  let saves = 0
  return {
    load: async controllerSessionId => inner.load(controllerSessionId),
    save: async (binding) => {
      saves += 1
      if (saves === 1) throw new Error('injected persistence outage')
      await inner.save(binding)
    },
    read: async workspaceId => inner.read(workspaceId),
    write: async record => inner.write(record),
    saveCount: () => saves,
  }
}

/**
 * Boot one REAL composition whose binding store is the injected outage
 * fixture: the stack is identical to the plugin route, but the composition
 * is constructed directly so the store boundary is the injected one.
 */
async function boot(workspaceRoot: string, sessionId: SessionId): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  const storageRoot = mkdtempSync(join(tmpdir(), `dsh-command-goal-binding-interrupt-${++bootNumber}-`))
  roots.push(storageRoot)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  const resolved = resolveCommandGoalBindingConfig({
    workspaceId: WORKSPACE_ID,
    requiredChecksPath: join(storageRoot, 'required-checks.json'),
    checks: startChecks(workspaceRoot),
    taskIds: ['task-v14-interruption'],
    maxAttempts: 3,
    workspaceRoot,
  })
  const flaky = flakyBindingStore()
  // Direct composition construction (the Service self-registers on the
  // context): the plugin route cannot pass the injected store, and the
  // injection boundary — not the fiber plumbing — is this spec's subject.
  const composition = new GoalBindingComposition(ctx, resolved, { bindings: flaky })
  const session = ctx.sessions.create(sessionId)
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return {
    ctx,
    agent,
    session,
    composition,
    interruptedSaveCount: () => flaky.saveCount(),
  }
}

/** Execute one slash command through the same registry boundary as a UI adapter. */
async function execute(test: TestComposition, line: string): Promise<CommandExecution> {
  const execution = await test.ctx.commands.execute(test.agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error('expected command was not registered')
  return execution
}

describe('start interruption injection (native Goal created, binding persistence failed)', { timeout: 120_000 }, () => {
  it('fails closed without rollback or binding, answers honestly, and retries after the human clear', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot(fixture.root, SessionId('controller-v14-interruption'))

    // The first /devframe-start creates the native Goal and disarms it, then
    // the injected store outage fails the first binding persistence.
    await expect(execute(test, '/devframe-start fix the login bug')).rejects.toMatchObject({
      name: 'GoalBindingError',
      code: 'GOAL_BINDING_PERSISTENCE',
    })

    // Fail-closed, no rollback: the native Goal of the interrupted attempt
    // still exists, disarmed (continuation authority removed) and active.
    const interrupted = test.ctx.goals.get(test.agent)
    expect(interrupted).toBeDefined()
    expect(interrupted?.phase).toBe('active')
    expect(interrupted?.activation).toBe('disarmed')
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
    expect(test.interruptedSaveCount()).toBe(1)

    // The binding never landed: the store holds nothing and the session log
    // holds no DevFrame record (role-policy and goal-binding are both absent).
    await expect(test.composition.bindingStore.load(SessionId(test.agent.id))).resolves.toEqual([])
    await expect(test.composition.bindingStore.read(WORKSPACE_ID)).resolves.toBeUndefined()
    expect(test.session.snapshotEvents().some(event => event.type.startsWith('devframe/'))).toBe(false)
    expect(test.session.snapshotEvents().some(event =>
      event.type === 'goal/change' && (event.data as { operation?: string }).operation === 'create')).toBe(true)
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()

    // The honest error face of the un-repaired state: the interrupted Goal
    // blocks a fresh start, the resume lane reports the missing record, and
    // neither answer adds structural damage.
    const retry = await execute(test, '/devframe-start fix the login bug')
    if (retry.result.kind !== 'error') throw new Error('expected an error result')
    expect(retry.result.text).toBe(START_GOAL_RUNNING_TEXT)
    const resumed = await execute(test, '/devframe-resume')
    if (resumed.result.kind !== 'error') throw new Error('expected an error result')
    expect(resumed.result.text).toBe(RESUME_NO_BINDING_RECORD_TEXT)
    expect(test.session.snapshotEvents().some(event => event.type.startsWith('devframe/'))).toBe(false)
    expect(test.ctx.goals.get(test.agent)?.id).toBe(interrupted?.id)

    // The human recovery face: clear the orphaned ambiguous Goal behind the
    // native durable tombstone (the native replacement path for a
    // non-complete current Goal), then the start lane retries for real.
    test.ctx.goals.clear(test.agent, { id: interrupted!.id, revision: interrupted!.revision })
    expect(test.ctx.goals.get(test.agent)).toBeUndefined()

    const second = await execute(test, '/devframe-start fix the login bug')
    if (second.result.kind !== 'success') throw new Error('expected a success result')
    expect(second.result.text).toBe(renderStartSuccess(1, 'passed'))
    const restarted = test.ctx.goals.get(test.agent)
    expect(restarted?.id).not.toBe(interrupted?.id)
    expect(restarted?.phase).toBe('active')
    expect(test.composition.admissionOf(test.agent)).toBe('open')
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
    await expect(test.composition.bindingStore.load(SessionId(test.agent.id)))
      .resolves.toEqual([expect.objectContaining({ goalId: restarted?.id, lifecycle: 'admission_open' })])
    expect(test.session.snapshotEvents().filter(event => event.type === 'devframe/goal-binding')).toHaveLength(1)
  })
})
