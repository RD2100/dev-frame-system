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
import { DevFrameOperationId, DevFrameReviewId, DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type {
  DevFrameReviewEventData,
  DevFrameRolePolicyEventData,
  DevFrameUsageEventData,
} from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import * as commandGoalBinding from '../src/index.ts'
import type { GoalBindingComposition } from '../src/composition.ts'
import {
  GOAL_ALREADY_COMPLETE_TEXT,
  REVIEW_SUPERSEDED_TEXT,
  VERIFICATION_SUPERSEDED_TEXT,
  renderCompletionSuccess,
  renderResumeAdoptedSuccess,
  renderResumeSuccess,
  renderStartSuccess,
} from '../src/command.ts'
import { acceptanceHashOf, compositionRolePolicy, devFrameStateOf, resultTupleOf } from '../src/host-evidence.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-checks-change')
/** The deterministic policy version the composition lands (host-evidence). */
const POLICY_VERSION = `policy-${WORKSPACE_ID}-v1`

const roots: string[] = []
const contexts: Context[] = []
let bootNumber = 0

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
  await drainWorktreeFixtures()
})

/** The approved checklist v1: one real passing probe on the worktree. */
function startChecksV1(root: string): DevFrameRequiredChecksConfig {
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

/**
 * The changed approved checklist v2: a second check joins the approved set.
 * The canonical digest of the pair differs, so the acceptance hash of any
 * goal started under it differs too — the "new acceptance hash" the checks
 * change mints for future goals, never for the frozen running one.
 */
function startChecksV2(root: string): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [
      ...startChecksV1(root).checks,
      {
        checkId: 'probe-second',
        executable: 'node',
        arguments: ['-e', 'process.exit(0)'],
        cwd: root,
      },
    ],
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

/** Boot one REAL composition through the function plugin under test. */
async function boot(options: BootOptions): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: options.storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  await ctx.plugin(commandGoalBinding, {
    workspaceId: WORKSPACE_ID,
    requiredChecksPath: join(options.storageRoot, 'required-checks.json'),
    checks: options.checks,
    taskIds: ['task-v14-checks-change'],
    maxAttempts: 3,
    workspaceRoot: options.workspaceRoot,
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
  return {
    ctx,
    agent,
    session,
    composition: Reflect.get(ctx, 'commandGoalBinding') as GoalBindingComposition,
  }
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

/**
 * One schema-valid usage record attributed to a binding's result tuple: the
 * attempt-budget consumption face the projection folds per Goal identity
 * (the same judge shape the DevFrame event fixtures use).
 */
function usageRecord(
  binding: GoalBinding,
  operationId: string,
  fields: Pick<DevFrameUsageEventData, 'attempt' | 'consumedAttempts'>,
): DevFrameUsageEventData {
  return {
    version: 1,
    operationId: DevFrameOperationId(operationId),
    binding: resultTupleOf(binding),
    role: 'worker',
    attempt: fields.attempt,
    phase: 'reserved',
    consumedAttempts: fields.consumedAttempts,
    maxAttempts: binding.budget.maxAttempts,
  }
}

/**
 * The reviewer-authorized role-policy replacement the completion case
 * appends: the composition's deterministic policy under the same version,
 * plus one reviewer assignment (a legal replacement fold).
 */
function reviewerPolicyRecord(
  controllerSessionId: SessionId,
  reviewerSessionId: SessionId,
): DevFrameRolePolicyEventData {
  const policy = compositionRolePolicy(WORKSPACE_ID, controllerSessionId)
  return {
    ...policy,
    assignments: [
      { role: 'controller', sessionId: controllerSessionId },
      { role: 'reviewer', sessionId: reviewerSessionId },
    ],
  }
}

/** One passing review record attributed to the landed binding. */
function reviewRecord(
  binding: GoalBinding,
  reviewerSessionId: SessionId,
  reviewId: string,
): DevFrameReviewEventData {
  return {
    version: 1,
    reviewId: DevFrameReviewId(reviewId),
    binding: resultTupleOf(binding),
    snapshotId: binding.snapshotId,
    reviewerSessionId,
    policyVersion: POLICY_VERSION,
    decision: 'pass',
    findings: [],
  }
}

/**
 * Fold-probe the usage and acceptance criteria on one throwaway Session:
 * the records are re-attributed to the probe Session so the live projection
 * of the resumed goal never latches a deliberately invalid record.
 */
function foldProbe(
  test: TestComposition,
  probeId: string,
  build: (controllerSessionId: ControllerSessionId) => Array<{ readonly type: string; readonly data: unknown }>,
): string | null {
  const probe = test.ctx.sessions.create(SessionId(probeId))
  for (const record of build(ControllerSessionId(probeId))) probe.append(record.type as never, record.data)
  return devFrameStateOf(test.ctx, probe).failure
}

describe('checks change composition (AT1-10: the change invalidates evidence, keeps usage)', { timeout: 120_000 }, () => {
  it('adopts the changed checks into a new generation on resume, refuses superseded evidence, and keeps usage counting', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-checks-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-checks-change')
    const objective = 'fix the billing bug'

    // Boot 1: the goal starts under the approved v1 checklist, freezes the
    // acceptance hash of (objective, v1), produces its verification evidence
    // under the v1 digest, and consumes one charged attempt.
    const first = await boot({
      checks: startChecksV1(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
    })
    const started = await execute(first, `/devframe-start ${objective}`)
    if (started.result.kind !== 'success') throw new Error('expected a success result')
    expect(started.result.text).toBe(renderStartSuccess(1, 'passed'))
    const goal = first.ctx.goals.get(first.agent)
    if (goal === undefined) throw new Error('goal is missing after start')
    const bindingA = goalBindingEvents(first)[0]
    if (bindingA === undefined) throw new Error('started binding is missing')
    expect(bindingA.acceptanceHash).toBe(acceptanceHashOf(objective, startChecksV1(fixture.root)))
    first.session.append('devframe/usage', usageRecord(bindingA, 'operation-v14-checks-a', { attempt: 1, consumedAttempts: 1 }))
    expect(devFrameStateOf(first.ctx, first.session).failure).toBeNull()

    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    // Boot 2: the deployment's approved checks changed to v2 between boots.
    // The same Goal resumes on the same persistence root.
    const second = await boot({
      checks: startChecksV2(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    const resumed = await execute(second, '/devframe-resume')
    if (resumed.result.kind !== 'success') throw new Error('expected a success result')
    expect(resumed.result.text).toBe(renderResumeAdoptedSuccess())

    // The resume adopted the changed checks into a new generation: the
    // binding advances one revision under the recomputed (objective, v2)
    // acceptance behind a fresh resume-minted confirmation, and the lane
    // re-verified the real approved v2 checks for the new generation.
    const resumedBinding = goalBindingEvents(second).at(-1)
    if (resumedBinding === undefined) throw new Error('resumed binding is missing')
    expect(resumedBinding.goalId).toBe(goal.id)
    expect(resumedBinding.goalRevision).toBe(goal.revision + 1)
    expect(resumedBinding.lifecycle).toBe('admission_open')
    expect(resumedBinding.acceptanceHash).toBe(acceptanceHashOf(objective, startChecksV2(fixture.root)))
    expect(resumedBinding.acceptanceHash).not.toBe(bindingA.acceptanceHash)
    expect(resumedBinding.confirmation.acceptanceHash).toBe(resumedBinding.acceptanceHash)
    const adoptedVerification = devFrameStateOf(second.ctx, second.session).verifications.at(-1)
    if (adoptedVerification === undefined) throw new Error('adopted generation verification is missing')
    expect(adoptedVerification.binding.goalRevision).toBe(resumedBinding.goalRevision)
    expect(adoptedVerification.binding.acceptanceHash).toBe(resumedBinding.acceptanceHash)
    expect(adoptedVerification.status).toBe('passed')

    // Usage is not reset across the generation change: the bridging is by
    // Goal identity, so the next charge continues at 2 against the new
    // generation's tuple — a from-zero 1 refuses and would latch the fold.
    second.session.append('devframe/usage', usageRecord(resumedBinding, 'operation-v14-checks-a-2', { attempt: 2, consumedAttempts: 2 }))
    const stateAfterCharge = devFrameStateOf(second.ctx, second.session)
    expect(stateAfterCharge.failure).toBeNull()
    expect(stateAfterCharge.usage.map(record => record.consumedAttempts)).toEqual([1, 2])

    // The accounting criteria hold on the fold itself: the continuing charge
    // advances cleanly while a from-zero 1 refuses (the consumed base comes
    // from the generation's binding and prior usage, not from zero).
    const resetRefused = foldProbe(second, 'probe-reset-refused', controllerSessionId => [
      { type: 'devframe/goal-binding', data: { ...resumedBinding, controllerSessionId } },
      { type: 'devframe/usage', data: usageRecord({ ...resumedBinding, controllerSessionId }, 'operation-probe-1', { attempt: 1, consumedAttempts: 1 }) },
      { type: 'devframe/usage', data: usageRecord({ ...resumedBinding, controllerSessionId }, 'operation-probe-2', { attempt: 1, consumedAttempts: 1 }) },
    ])
    expect(resetRefused).toContain('did not advance consumed attempts by one')

    const hashRefused = foldProbe(second, 'probe-hash-refused', controllerSessionId => [
      { type: 'devframe/goal-binding', data: { ...resumedBinding, controllerSessionId } },
      {
        type: 'devframe/goal-binding',
        data: {
          ...resumedBinding,
          controllerSessionId,
          acceptanceHash: acceptanceHashOf(objective, startChecksV1(fixture.root)),
          confirmation: {
            ...resumedBinding.confirmation,
            acceptanceHash: acceptanceHashOf(objective, startChecksV1(fixture.root)),
          },
        },
      },
    ])
    expect(hashRefused).toContain('changed its immutable binding')

    // The reviewer's pass from the superseded generation cannot gate the
    // adopted generation: /goal-complete names the stale review.
    const reviewerSessionId = SessionId('reviewer-v14-checks-change')
    second.session.append('devframe/role-policy', reviewerPolicyRecord(second.session.id, reviewerSessionId))
    second.session.append('devframe/review', reviewRecord(bindingA, reviewerSessionId, 'review-v14-checks-stale'))
    const staleReview = await execute(second, '/goal-complete')
    expect(staleReview.result.kind).toBe('error')
    if (staleReview.result.kind === 'error') expect(staleReview.result.text).toBe(REVIEW_SUPERSEDED_TEXT)
    expect(devFrameStateOf(second.ctx, second.session).failure).toBeNull()

    // A late-arriving verification from the superseded generation cannot
    // satisfy the adopted acceptance either: /goal-complete names the stale
    // verification instead of completing on it.
    const staleVerification = devFrameStateOf(second.ctx, second.session).verifications.find(
      record => record.binding.acceptanceHash === bindingA.acceptanceHash,
    )
    if (staleVerification === undefined) throw new Error('superseded-generation verification is missing')
    second.session.append('devframe/verification', {
      ...staleVerification,
      verificationId: DevFrameVerificationId('verification-v14-checks-stale'),
    })
    const staleVerificationResult = await execute(second, '/goal-complete')
    expect(staleVerificationResult.result.kind).toBe('error')
    if (staleVerificationResult.result.kind === 'error') expect(staleVerificationResult.result.text).toBe(VERIFICATION_SUPERSEDED_TEXT)
    expect(devFrameStateOf(second.ctx, second.session).failure).toBeNull()

    // A fresh current-generation verification (the shape the evidence
    // journal lands) restores the newest-attributed position and completion
    // proceeds on the adopted generation: a current-generation authorized
    // review admits, the native goal completes, and the accounting stays
    // continuous — usage is [1, 2] across the change.
    second.session.append('devframe/verification', {
      ...adoptedVerification,
      verificationId: DevFrameVerificationId('verification-v14-checks-current'),
    })
    second.session.append('devframe/review', reviewRecord(resumedBinding, reviewerSessionId, 'review-v14-checks-current'))
    const completed = await execute(second, '/goal-complete')
    if (completed.result.kind !== 'success') {
      throw new Error(`expected a success result: ${completed.result.text} | projection failure: ${devFrameStateOf(second.ctx, second.session).failure}`)
    }
    expect(completed.result.text).toBe(renderCompletionSuccess())
    expect(second.ctx.goals.get(second.agent)?.phase).toBe('complete')
    expect(second.composition.admissionOf(second.agent)).toBe('closed')

    const stateAfterComplete = devFrameStateOf(second.ctx, second.session)
    expect(stateAfterComplete.usage.map(record => record.consumedAttempts)).toEqual([1, 2])
    expect(stateAfterComplete.failure).toBeNull()
  })

  it('keeps the plain resume text when the approved checks did not change', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-checks-same-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-checks-same')
    const first = await boot({
      checks: startChecksV1(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
    })
    expect((await execute(first, '/devframe-start fix the login bug')).result.kind).toBe('success')
    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    const second = await boot({
      checks: startChecksV1(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    const resumed = await execute(second, '/devframe-resume')
    if (resumed.result.kind !== 'success') throw new Error('expected a success result')
    expect(resumed.result.text).toBe(renderResumeSuccess())
  })

  it('refuses to complete a goal that is already complete after the checks change', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-checks-d1-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-checks-d1')
    const first = await boot({
      checks: startChecksV1(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
    })
    expect((await execute(first, '/devframe-start fix the login bug')).result.kind).toBe('success')
    const goal = first.ctx.goals.get(first.agent)
    if (goal === undefined) throw new Error('goal is missing after start')
    first.ctx.goals.complete(first.agent, { id: goal.id, revision: goal.revision })
    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    const second = await boot({
      checks: startChecksV2(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    const stale = await execute(second, '/goal-complete')
    if (stale.result.kind !== 'error') throw new Error('expected an error result')
    expect(stale.result.text).toBe(GOAL_ALREADY_COMPLETE_TEXT)
    expect(second.ctx.goals.get(second.agent)?.phase).toBe('complete')
  })
})
