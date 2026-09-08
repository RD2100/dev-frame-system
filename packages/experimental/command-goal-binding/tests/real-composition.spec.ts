import { execFile } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import type { CommandExecution } from '@deepseek-ai/dsh-commands'
import GoalService, { GoalId } from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { requiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { DevFrameDeliveryId, DevFrameReviewId, DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type {
  DevFrameCheckResult,
  DevFrameReviewEventData,
  DevFrameRolePolicyEventData,
  DevFrameTaskDeliveryEventData,
  DevFrameVerificationEventData,
} from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/src/source-fingerprint.ts'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, TaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { TaskId as PluginTaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { MainTreeIntegrationRecord } from '@deepseek-ai/dsh-experimental-project-controller'
import { FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { createCommittedWorktree, drainWorktreeFixtures, executionFor } from '../../devframe/tests/completion-fixtures.ts'
import * as commandGoalBinding from '../src/index.ts'
import { GoalBindingComposition } from '../src/composition.ts'
import { renderCompletionSuccess, renderFinalMergeIncomplete } from '../src/command.ts'
const execFileAsync = promisify(execFile)

const WORKSPACE_ID = WorkspaceId('ws-v14-hostcmd')
const POLICY_VERSION = 'policy-v14hostcmd'

/** The approved checklist every composed evidence record declares and covers. */
const APPROVED_CONFIG: DevFrameRequiredChecksConfig = {
  version: 1,
  checks: [
    { checkId: 'lint', executable: 'pnpm', arguments: ['run', 'lint'], cwd: 'C:/ws-command-binding' },
    { checkId: 'typecheck', executable: 'node', arguments: ['node_modules/typescript/bin/tsc', '-b'], cwd: 'C:/ws-command-binding' },
  ],
}

const roots: string[] = []
const contexts: Context[] = []
let bootNumber = 0

/**
 * The approved start parameters every boot config now must carry (the config
 * requires them at activation). They feed only the /devframe-start lane,
 * which this spec does not exercise, so /goal-complete behavior is unchanged.
 */
const BOOT_START_CONFIG = {
  checks: {
    version: 1 as const,
    checks: [{
      checkId: 'boot-probe',
      executable: 'node',
      arguments: ['-e', 'process.exit(0)'],
      cwd: 'C:/ws-command-binding',
    }],
  },
  taskIds: [TaskId('task-v14-hostcmd')],
  maxAttempts: 3,
}

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
  await drainWorktreeFixtures()
})

interface TestComposition {
  readonly ctx: Context
  readonly agent: Agent
  readonly session: Session
  readonly composition: GoalBindingComposition
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
 * Boot one REAL composition: native session store, JSONL persistence, the
 * real command registry, the native goal service, the projection registry,
 * and the function plugin under test — then attach one live agent. A case
 * overrides only the workspace identity and root; BOOT_START_CONFIG fills
 * the start-lane parameters the activation now requires.
 */
async function boot(config: {
  readonly workspaceId: WorkspaceId
  readonly workspaceRoot?: string
  readonly gateRows?: readonly MainTreeIntegrationRecord[]
}): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  const storageRoot = mkdtempSync(join(tmpdir(), `dsh-command-goal-binding-${++bootNumber}-`))
  roots.push(storageRoot)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  const requiredChecksPath = join(storageRoot, 'required-checks.json')
  const startConfig = {
    ...BOOT_START_CONFIG,
    requiredChecksPath,
    workspaceId: config.workspaceId,
    ...(config.workspaceRoot === undefined ? {} : { workspaceRoot: config.workspaceRoot }),
  }
  let composition: GoalBindingComposition
  if (config.gateRows === undefined) {
    await ctx.plugin(commandGoalBinding, startConfig)
    composition = Reflect.get(ctx, 'commandGoalBinding') as GoalBindingComposition
  } else {
    const resolved = commandGoalBinding.resolveCommandGoalBindingConfig(startConfig)
    composition = new GoalBindingComposition(ctx, resolved, {
      requiredChecks: new FileRequiredChecksConfigStore({ path: requiredChecksPath }),
      goalCompletionIntegrations: () => config.gateRows ?? [],
      goalCompletionGuard: () => {},
    })
  }
  const session = ctx.sessions.create(SessionId(`controller-v14-hostcmd-${bootNumber}`))
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return { ctx, agent, session, composition }
}

/** Execute `/goal-complete` through the same registry boundary as a UI adapter. */
async function execute(test: TestComposition, line: string): Promise<CommandExecution> {
  const execution = await test.ctx.commands.execute(test.agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error('goal-complete command was not registered')
  return execution
}

/** Start one bound goal through the composition's start lane. */
function startBinding(test: TestComposition, fingerprint: SourceFingerprint): Promise<GoalBinding> {
  return test.composition.startBinding(test.agent, {
    objective: 'complete the bound work',
    taskIds: [TaskId('task-v14-hostcmd')],
    acceptanceHash: AcceptanceHash('acceptance-v14-hostcmd'),
    sourceFingerprint: fingerprint,
    snapshotId: DevFrameSnapshotId('snapshot-v14-hostcmd'),
    budget: { maxAttempts: 3 },
    confirmationId: 'confirm-v14-hostcmd',
  })
}

/** The projection-side result tuple of one controller binding. */
function resultBindingOf(binding: GoalBinding) {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: binding.taskIds,
    acceptanceHash: binding.acceptanceHash,
    workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
  }
}

/** The goal identity text of one binding, for no-id-leak assertions. */
function goalIdText(binding: GoalBinding): string {
  return binding.goalId
}

/** One role-policy snapshot authorizing the controller and one reviewer. */
function rolePolicyRecord(
  controllerSessionId: SessionId,
  reviewerSessionId: SessionId,
): DevFrameRolePolicyEventData {
  const emptyPolicy = { inheritedTools: [], denyScopedTools: [] }
  return {
    version: 1,
    workspaceId: WORKSPACE_ID,
    controllerSessionId,
    policyVersion: POLICY_VERSION,
    config: {
      controller: { ...emptyPolicy },
      worker: { ...emptyPolicy },
      reviewer: { ...emptyPolicy },
    },
    assignments: [
      { role: 'controller', sessionId: controllerSessionId },
      { role: 'reviewer', sessionId: reviewerSessionId },
    ],
  }
}

/** One verification record fully covering the approved configuration. */
function verificationRecord(
  binding: GoalBinding,
  overrides: Partial<Pick<DevFrameVerificationEventData, 'verificationId' | 'status' | 'checks'>> = {},
): DevFrameVerificationEventData {
  const checks: readonly DevFrameCheckResult[] = overrides.checks
    ?? APPROVED_CONFIG.checks.map(check => executionFor(check))
  return {
    version: 1,
    verificationId: overrides.verificationId ?? DevFrameVerificationId('verify-v14-hostcmd'),
    binding: resultBindingOf(binding),
    snapshotId: binding.snapshotId,
    status: overrides.status ?? 'passed',
    requiredChecks: { config: APPROVED_CONFIG, digest: requiredChecksDigest(APPROVED_CONFIG) },
    checks,
  }
}

/** One durable review record attributed to the binding's goal. */
function reviewRecord(
  binding: GoalBinding,
  reviewerSessionId: SessionId,
  decision: 'pass' | 'changes_required',
  overrides: { readonly reviewId?: DevFrameReviewEventData['reviewId'] } = {},
): DevFrameReviewEventData {
  return {
    version: 1,
    reviewId: overrides.reviewId ?? DevFrameReviewId('review-v14-hostcmd'),
    binding: resultBindingOf(binding),
    snapshotId: binding.snapshotId,
    reviewerSessionId,
    policyVersion: POLICY_VERSION,
    decision,
    findings: decision === 'pass' ? [] : [{
      id: 'finding-1',
      severity: 'blocking',
      message: 'the exported command surface is untested',
    }],
  }
}

/**
 * Append the evidence producer records the projection fold requires before
 * completion evidence exists: role policy, the controller binding, the
 * verification, and the review, plus the host-side registration backing the
 * declared digest. The production producers are no longer deferred — the
 * /devframe-start lane lands role policy, goal binding, and verification —
 * so these manual appends remain as test assembly for the /goal-complete
 * error-face coverage (events.spec append precedent). Returns the reviewer
 * session the appended policy authorizes.
 */
async function appendEvidence(test: TestComposition, binding: GoalBinding): Promise<{ readonly reviewerSessionId: SessionId }> {
  const reviewerSessionId = SessionId(`reviewer-v14-hostcmd-${bootNumber}`)
  await test.composition.requiredChecksStore.save(APPROVED_CONFIG)
  test.session.append('devframe/role-policy', rolePolicyRecord(binding.controllerSessionId, reviewerSessionId))
  test.session.append('devframe/goal-binding', binding)
  test.session.append('devframe/verification', verificationRecord(binding))
  test.session.append('devframe/review', reviewRecord(binding, reviewerSessionId, 'pass'))
  return { reviewerSessionId }
}

/** Whether the session log holds a goal completion receipt. */
function hasReceipt(test: TestComposition): boolean {
  return test.session.snapshotEvents().some(event =>
    event.type === 'goal/change' && event.data.operation === 'receipt')
}

/** The command/done event paired with one invocation's command/run. */
function doneOf(test: TestComposition, commandId: string) {
  const done = test.session.snapshotEvents().find(event =>
    event.type === 'command/done' && event.data.commandId === commandId)
  if (done === undefined || done.type !== 'command/done') throw new Error('command/done event is missing')
  return done.data
}

/** Mutate the worktree's tracked state so its fresh fingerprint diverges. */
async function tamperWorktree(root: string): Promise<void> {
  await writeFile(join(root, 'src.ts'), 'export const tampered = true\n', 'utf8')
  await execFileAsync('git', ['-C', root, 'add', '-A'], { encoding: 'utf8', windowsHide: true })
}

describe('/goal-complete host command composition', { timeout: 30_000 }, () => {
  it('completes the current goal through real dispatch and records the receipt', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    const revisionBefore = test.ctx.goals.get(test.agent)!.revision

    const execution = await execute(test, '/goal-complete')

    const result = execution.result
    if (result.kind !== 'success') throw new Error('expected a success result')
    expect(result.text).toBe(renderCompletionSuccess())
    expect(result.text).not.toContain(goalIdText(binding))
    const goal = test.ctx.goals.get(test.agent)!
    expect(goal.phase).toBe('complete')
    expect(goal.revision).toBe(revisionBefore + 1)

    const receipt = test.session.snapshotEvents().find(event =>
      event.type === 'goal/change' && event.data.operation === 'receipt')
    if (receipt === undefined || receipt.type !== 'goal/change' || receipt.data.operation !== 'receipt') {
      throw new Error('completion receipt is missing')
    }
    expect(receipt.data.ref).toEqual({ id: goal.id, revision: goal.revision })
    expect(receipt.data.evidence).toHaveLength(1)
    expect(receipt.data.evidence[0]?.kind).toBe('completion-admission')
    expect(receipt.data.evidence[0]?.summary).toContain(goalIdText(binding))

    const run = test.session.snapshotEvents().find(event => event.type === 'command/run')
    if (run === undefined || run.type !== 'command/run') throw new Error('command/run event is missing')
    expect(run.data.name).toBe('goal-complete')
    expect(doneOf(test, run.data.commandId).kind).toBe('success')

    const bindings = await test.composition.bindingStore.load(ControllerSessionId(test.agent.id))
    expect(bindings.find(record => record.goalId === goal.id)?.goalRevision).toBe(goal.revision)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')

    await test.ctx.sessions.flush(test.session)
    const stored = await test.ctx.sessionPersistence.inspect(test.agent.id)
    if (stored === undefined) throw new Error('persisted session log is missing')
    expect(stored.events.some(event => event.type === 'command/run' && event.data.name === 'goal-complete')).toBe(true)
    expect(stored.events.some(event =>
      event.type === 'goal/change' && event.data.operation === 'receipt')).toBe(true)
  })

  it('lets the command-line worktree override the configured workspace root', async () => {
    const configured = await createCommittedWorktree()
    const override = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: configured.root })
    const binding = await startBinding(test, override.fingerprint)
    await appendEvidence(test, binding)

    const execution = await execute(test, `/goal-complete ${override.root}`)

    expect(execution.result.kind).toBe('success')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('complete')
  })

  it('rejects at the source-fingerprint stage after the worktree changed', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    await tamperWorktree(fixture.root)

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('source-fingerprint')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
  })

  it('rejects at the required-checks stage when a required check failed', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    const reviewerSessionId = SessionId(`reviewer-v14-hostcmd-${bootNumber}`)
    await test.composition.requiredChecksStore.save(APPROVED_CONFIG)
    test.session.append('devframe/role-policy', rolePolicyRecord(binding.controllerSessionId, reviewerSessionId))
    test.session.append('devframe/goal-binding', binding)
    test.session.append('devframe/verification', verificationRecord(binding, {
      status: 'failed',
      checks: APPROVED_CONFIG.checks.map(check =>
        check.checkId === 'lint' ? executionFor(check, 'failed') : executionFor(check)),
    }))
    test.session.append('devframe/review', reviewRecord(binding, reviewerSessionId, 'pass'))

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('required-checks')
    expect(execution.result.text).toContain('REQUIRED_CHECKS_NOT_PASSED')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
  })

  it('rejects at the review stage when the authorized review requires changes', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    const reviewerSessionId = SessionId(`reviewer-v14-hostcmd-${bootNumber}`)
    await test.composition.requiredChecksStore.save(APPROVED_CONFIG)
    test.session.append('devframe/role-policy', rolePolicyRecord(binding.controllerSessionId, reviewerSessionId))
    test.session.append('devframe/goal-binding', binding)
    test.session.append('devframe/verification', verificationRecord(binding))
    test.session.append('devframe/review', reviewRecord(binding, reviewerSessionId, 'changes_required'))

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('review')
    expect(execution.result.text).toContain('changes_required')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
  })

  it('charges a fail-graded warning once across repeated completion attempts', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    test.session.append('devframe/task-warning', {
      version: 1,
      taskId: TaskId('task-v14-hostcmd'),
      warning: 'MEMORY_UNAVAILABLE',
      tool: 'memory_append',
      grade: 'fail',
    })

    const first = await execute(test, '/goal-complete')
    const second = await execute(test, '/goal-complete')
    const third = await execute(test, '/goal-complete')

    if (first.result.kind !== 'error' || second.result.kind !== 'error' || third.result.kind !== 'error') {
      throw new Error('expected error results')
    }
    expect(first.result.text).toContain('task-warning')
    expect(first.result.text).toContain('Repair round 1 was charged (1 remaining)')
    expect(second.result.text).toContain('Repair round 1 was charged (1 remaining)')
    expect(third.result.text).toContain('Repair round 1 was charged (1 remaining)')
    expect(test.session.snapshotEvents().filter(event => event.type === 'devframe/repair-admission')).toHaveLength(1)
    expect(third.result.text).toContain('human-authorized resume')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
  })

  it('renders the task-warning rejection without repair accounting for other stages', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    await tamperWorktree(fixture.root)

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('source-fingerprint')
    expect(execution.result.text).not.toContain('Repair round')
  })

  it('answers a stable data error when no goal is current', async () => {
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: 'C:/ws-command-binding' })

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('No goal is currently set')
    expect(hasReceipt(test)).toBe(false)
  })

  it('answers a stable data error when the current goal has no binding', async () => {
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: 'C:/ws-command-binding' })
    test.ctx.goals.create(test.agent, { objective: 'unbound goal' })

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('no completion binding')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
  })

  it('answers a stable data error when no verification evidence is attributed', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    await startBinding(test, fixture.fingerprint)

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('no attributed verification evidence')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
  })

  it('answers a stable data error when the goal is already complete', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    await execute(test, '/goal-complete')

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('already complete')
    expect(hasReceipt(test)).toBe(true)
  })

  it('propagates RequiredChecksError when the digest is unregistered', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    const reviewerSessionId = SessionId(`reviewer-v14-hostcmd-${bootNumber}`)
    // Evidence exists and is well-formed, but the host never registered the
    // declared checklist: the structural error must cross the boundary.
    test.session.append('devframe/role-policy', rolePolicyRecord(binding.controllerSessionId, reviewerSessionId))
    test.session.append('devframe/goal-binding', binding)
    test.session.append('devframe/verification', verificationRecord(binding))
    test.session.append('devframe/review', reviewRecord(binding, reviewerSessionId, 'pass'))

    await expect(execute(test, '/goal-complete')).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
    })
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
    const dones = test.session.snapshotEvents().filter(event => event.type === 'command/done')
    expect(dones).toHaveLength(1)
    const done = dones[0]
    if (done === undefined || done.type !== 'command/done') throw new Error('command/done event is missing')
    expect(done.data.kind).toBe('error')
  })

  it('propagates GoalBindingError when the latest review belongs to another goal', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    const { reviewerSessionId } = await appendEvidence(test, binding)
    // A second goal's complete evidence triple, appended after the current
    // goal's, makes the log's latest review foreign to the completing goal.
    const foreign: GoalBinding = {
      ...binding,
      goalId: GoalId('goal-foreign'),
      taskIds: [TaskId('task-foreign')],
      sourceFingerprint: SourceFingerprint('dsh-source-fp-v1-foreign'),
      snapshotId: DevFrameSnapshotId('snapshot-foreign'),
    }
    test.session.append('devframe/goal-binding', foreign)
    test.session.append('devframe/verification', verificationRecord(foreign, {
      verificationId: DevFrameVerificationId('verify-foreign'),
    }))
    test.session.append('devframe/review', reviewRecord(foreign, reviewerSessionId, 'pass', {
      reviewId: DevFrameReviewId('review-foreign'),
    }))

    const completion = execute(test, '/goal-complete')
    await expect(completion).rejects.toMatchObject({
      name: 'GoalBindingError',
    })
    await expect(completion).rejects.toThrow('completion review evidence is attributed to Goal')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
  })

  it('propagates SourceFingerprintError when the worktree path is unusable', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)

    await expect(execute(test, '/goal-complete D:/definitely-not-a-worktree-v14-hostcmd')).rejects
      .toMatchObject({ name: 'SourceFingerprintError' })
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
  })

  it('refuses fail-closed when the projection latched a replay failure', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({ workspaceId: WORKSPACE_ID, workspaceRoot: fixture.root })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    // A duplicate verification identity is unreadable evidence: the fold
    // latches a replay failure, and the command must refuse on it.
    test.session.append('devframe/verification', verificationRecord(binding))

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('replay failure')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(hasReceipt(test)).toBe(false)
  })

  it('answers a stable data error when neither config nor command line names a worktree', async () => {
    const test = await boot({ workspaceId: WORKSPACE_ID })
    const binding = await startBinding(test, SourceFingerprint('dsh-source-fp-v1-unreached'))
    await appendEvidence(test, binding)

    const execution = await execute(test, '/goal-complete')

    if (execution.result.kind !== 'error') throw new Error('expected an error result')
    expect(execution.result.text).toContain('worktree path')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
  })

  it('fails activation loudly on an empty workspace id', async () => {
    const ctx = new Context()
    contexts.push(ctx)
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-config-'))
    roots.push(storageRoot)
    await ctx.plugin(SessionStore)
    await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    await expect(ctx.plugin(commandGoalBinding, { ...BOOT_START_CONFIG, requiredChecksPath: join(storageRoot, 'required-checks.json'), workspaceId: '' }))
      .rejects.toThrow(/workspaceId/)
  })
})

/** One durable integration receipt for the bound task in the gate's reader. */
function integrationRow(overrides: Partial<MainTreeIntegrationRecord> = {}): MainTreeIntegrationRecord {
  const now = '2026-09-08T01:00:00.000Z'
  return {
    taskId: PluginTaskId('task-v14-hostcmd'),
    controllerSessionId: SessionId('controller-v14-hostcmd-0'),
    reviewId: DevFrameReviewId('review-v14-hostcmd'),
    verificationId: DevFrameVerificationId('verify-v14-hostcmd'),
    sourcePath: 'C:/wt-v14-hostcmd',
    targetPath: 'C:/controller-v14-hostcmd',
    sourceCommit: 'c'.repeat(40),
    targetHead: 'b'.repeat(40),
    state: 'applied',
    appliedHead: 'b'.repeat(40),
    createdAt: now,
    updatedAt: now,
    ...overrides,
  }
}

/** One explicit Worker delivery of the bound task's committed output. */
function deliveryRecord(binding: GoalBinding, workerSessionId: SessionId): DevFrameTaskDeliveryEventData {
  return {
    version: 1,
    deliveryId: DevFrameDeliveryId('delivery-v14-hostcmd'),
    taskId: TaskId('task-v14-hostcmd'),
    binding: resultBindingOf(binding),
    workerSessionId,
    worktreeId: WorktreeId('tree-v14-hostcmd'),
    worktreePath: 'C:/wt-v14-hostcmd',
    sourceCommit: 'c'.repeat(40),
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
  }
}

/** The whole-Goal result tuple re-anchored at the merged controller tree. */
function mergedBindingOf(binding: GoalBinding, merged: SourceFingerprint) {
  return {
    ...resultBindingOf(binding),
    sourceFingerprint: merged,
    snapshotId: DevFrameSnapshotId('snapshot-final-merge-v14-hostcmd'),
  }
}

describe('/goal-complete final-merge completion gate', { timeout: 30_000 }, () => {
  it('completes through the whole-Goal contract anchored at the merged tree', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      workspaceId: WORKSPACE_ID,
      workspaceRoot: fixture.root,
      gateRows: [integrationRow({ targetPath: fixture.root, controllerSessionId: SessionId(`controller-v14-hostcmd-${bootNumber + 1}`) })],
    })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)
    // The integration moved the controller tree past the start fingerprint.
    await writeFile(join(fixture.root, 'merged.ts'), 'export const merged = true\n', 'utf8')
    const { fingerprint: merged } = await computeSourceFingerprint({ worktreePath: fixture.root })
    const reviewerSessionId = SessionId(`reviewer-v14-hostcmd-${bootNumber}`)
    const mergedBinding = mergedBindingOf(binding, merged)
    test.session.append('devframe/task-delivery', deliveryRecord(binding, SessionId('worker-v14-hostcmd')))
    test.session.append('devframe/verification', {
      version: 1,
      verificationId: DevFrameVerificationId('verify-final-merge-v14-hostcmd'),
      binding: mergedBinding,
      snapshotId: mergedBinding.snapshotId,
      status: 'passed',
      requiredChecks: { config: APPROVED_CONFIG, digest: requiredChecksDigest(APPROVED_CONFIG) },
      checks: APPROVED_CONFIG.checks.map(check => executionFor(check)),
    })
    test.session.append('devframe/review', {
      version: 1,
      reviewId: DevFrameReviewId('review-final-merge-v14-hostcmd'),
      binding: mergedBinding,
      snapshotId: mergedBinding.snapshotId,
      reviewerSessionId,
      policyVersion: POLICY_VERSION,
      decision: 'pass',
      findings: [],
    })

    const execution = await execute(test, '/goal-complete')

    const result = execution.result
    expect(result.kind, result.text).toBe('success')
    expect(result.text).toBe(renderCompletionSuccess())
    const goal = test.ctx.goals.get(test.agent)!
    expect(goal.phase).toBe('complete')
    // The binding record keeps its start claim: completion anchored at the
    // merged tree through the evidence, never by rewriting the authorization.
    const bindings = await test.composition.bindingStore.load(ControllerSessionId(test.agent.id))
    expect(bindings.find(record => record.goalId === goal.id)?.sourceFingerprint).toBe(fixture.fingerprint)
  })

  it('refuses a prepared receipt by the named applied-receipt absence', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      workspaceId: WORKSPACE_ID,
      workspaceRoot: fixture.root,
      gateRows: [integrationRow({ controllerSessionId: SessionId(`controller-v14-hostcmd-${bootNumber + 1}`), state: 'prepared', appliedHead: undefined })],
    })
    const binding = await startBinding(test, fixture.fingerprint)
    await appendEvidence(test, binding)

    const execution = await execute(test, '/goal-complete')

    const result = execution.result
    if (result.kind !== 'error') throw new Error('expected an error result')
    expect(result.text).toBe(renderFinalMergeIncomplete(
      'Goal completion requires the applied integration receipt for task "task-v14-hostcmd"',
    ))
    expect(test.ctx.goals.get(test.agent)?.phase).not.toBe('complete')
  })
})

describe('/goal-complete registration lifetime', () => {
  it('registers through the effect and disappears with the plugin fiber', async () => {
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(SessionStore)
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const plugin = await ctx.plugin(commandGoalBinding, { ...BOOT_START_CONFIG, requiredChecksPath: join(tmpdir(), 'unused-required-checks.json'), workspaceId: WORKSPACE_ID })
    expect('default' in commandGoalBinding).toBe(false)
    const session = ctx.sessions.create(SessionId(`controller-lifetime-${++bootNumber}`))
    const agent = stubAgent(session)
    ctx.agents.register(agent)
    expect(ctx.commands.find(agent, 'goal-complete')).toBeDefined()

    await plugin.dispose()

    expect(ctx.commands.find(agent, 'goal-complete')).toBeUndefined()
  })
})
