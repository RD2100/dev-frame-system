/** DevFrame event schemas, Session journal durability, and cold projection replay. */

import { Context } from '@deepseek-ai/cordis'
import { GoalId } from '@deepseek-ai/dsh-goal'
import SessionStore, {
  KNOWN_SESSION_EVENT_TYPES,
  Session,
  SessionId,
  SessionLogOffset,
} from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import {
  decodeDevFramePayload,
  DevFrameOperationId,
  DevFrameReviewId,
  DevFrameSnapshotId,
  DevFrameVerificationId,
} from '../src/events.ts'
import { DevFrameSessionJournal } from '../src/session-journal.ts'
import type { DevFrameReviewGate } from '../src/session-journal.ts'
import { requiredChecksDigest } from '../src/required-checks.ts'
import type { DevFrameRequiredChecksConfig } from '../src/required-checks.ts'
import type {
  DevFrameLifecycleEventData,
  DevFrameReviewEventData,
  DevFrameRolePolicyEventData,
  DevFrameTaskWarningEventData,
  DevFrameUsageEventData,
  DevFrameVerificationEventData,
} from '../src/events.ts'
import {
  foldDevFrameState,
  devFrameProjectionDefinition,
} from '../src/projection.ts'
import {
  AcceptanceHash,
  ConfigurationConfirmationId,
  SourceFingerprint,
  WorkspaceId,
} from '../src/shared/types.ts'
import type {
  GoalBinding,
  GoalResultBinding,
} from '../src/controller/goal-binding.ts'
import { TaskId } from '../src/controller/goal-binding.ts'

const CONTROLLER = SessionId('devframe-controller')
const HEADER = {
  version: 0,
  id: CONTROLLER,
  createdAt: 0,
  isSeeded: false,
} as const
const WORKSPACE = WorkspaceId('workspace-one')
const ACCEPTANCE = AcceptanceHash('acceptance-one')
const SOURCE = SourceFingerprint('source-one')
const SNAPSHOT = DevFrameSnapshotId('snapshot-one')
const TASK = TaskId('task-1')
const REVIEWER = SessionId('reviewer-one')

function session(id: SessionId = CONTROLLER): Session {
  return Session.create(id, undefined, { ...HEADER, id })
}

/** The reviewer-role authority the journal consults; only REVIEWER passes. */
function reviewGate(): DevFrameReviewGate {
  return {
    requireReviewer(sessionId: SessionId): void {
      if (sessionId !== REVIEWER) throw new Error(`Session "${sessionId}" holds no reviewer role`)
    },
  }
}

function binding(overrides: Partial<GoalBinding> = {}): GoalBinding {
  return {
    version: 1,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    goalId: GoalId('goal-1'),
    goalRevision: 1,
    taskIds: [TASK],
    acceptanceHash: ACCEPTANCE,
    sourceFingerprint: SOURCE,
    snapshotId: SNAPSHOT,
    confirmation: {
      id: ConfigurationConfirmationId('confirmation-one'),
      acceptanceHash: ACCEPTANCE,
    },
    lifecycle: 'ambiguous',
    budget: { maxAttempts: 3, consumedAttempts: 0 },
    ...overrides,
  }
}

function resultBinding(value: GoalBinding = binding()): GoalResultBinding {
  return {
    controllerSessionId: value.controllerSessionId,
    goalId: value.goalId,
    goalRevision: value.goalRevision,
    taskIds: value.taskIds,
    acceptanceHash: value.acceptanceHash,
    workspaceId: value.workspaceId,
    sourceFingerprint: value.sourceFingerprint,
    snapshotId: value.snapshotId,
  }
}

function rolePolicy(overrides: Partial<DevFrameRolePolicyEventData> = {}): DevFrameRolePolicyEventData {
  return {
    version: 1,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    policyVersion: 'policy-one',
    config: {
      controller: { inheritedTools: ['read'], denyScopedTools: ['spawn_teammate'] },
      worker: { inheritedTools: ['read', 'write'], denyScopedTools: [] },
      reviewer: { inheritedTools: ['read'], denyScopedTools: ['write', 'shell'] },
    },
    assignments: [
      { role: 'controller', sessionId: CONTROLLER },
      { role: 'reviewer', sessionId: REVIEWER },
    ],
    ...overrides,
  }
}

function fullEventSet(): {
  readonly usageReserved: DevFrameUsageEventData
  readonly usageSettled: DevFrameUsageEventData
  readonly verification: DevFrameVerificationEventData
  readonly review: DevFrameReviewEventData
  readonly taskWarning: DevFrameTaskWarningEventData
  readonly stopRequested: DevFrameLifecycleEventData
  readonly quiesced: DevFrameLifecycleEventData
} {
  const reference = resultBinding()
  const usageReserved: DevFrameUsageEventData = {
    version: 1,
    operationId: DevFrameOperationId('operation-one'),
    binding: reference,
    role: 'worker',
    attempt: 1,
    phase: 'reserved',
    consumedAttempts: 1,
    maxAttempts: 3,
  }
  const usageSettled: DevFrameUsageEventData = {
    ...usageReserved,
    phase: 'settled',
    outcome: 'succeeded',
    tokenUsage: { kind: 'measured', input: 10, output: 5, total: 15 },
  }
  const verificationCoverage: DevFrameRequiredChecksConfig = {
    version: 1,
    checks: [{
      checkId: 'typecheck',
      executable: 'pnpm',
      arguments: ['run', 'typecheck'],
      cwd: 'C:/workspace',
    }],
  }
  const verification: DevFrameVerificationEventData = {
    version: 1,
    verificationId: DevFrameVerificationId('verification-one'),
    binding: reference,
    snapshotId: DevFrameSnapshotId('snapshot-one'),
    status: 'passed',
    requiredChecks: { config: verificationCoverage, digest: requiredChecksDigest(verificationCoverage) },
    checks: [{
      checkId: 'typecheck',
      executable: 'pnpm',
      arguments: ['run', 'typecheck'],
      cwd: 'C:/workspace',
      status: 'passed',
      exitCode: 0,
      durationMs: 12,
      outputRef: 'artifact://check-one',
    }],
  }
  const review: DevFrameReviewEventData = {
    version: 1,
    reviewId: DevFrameReviewId('review-one'),
    binding: reference,
    snapshotId: verification.snapshotId,
    reviewerSessionId: SessionId('reviewer-one'),
    policyVersion: 'policy-one',
    decision: 'pass',
    findings: [],
  }
  const stopRequested: DevFrameLifecycleEventData = {
    version: 1,
    binding: reference,
    state: 'stop_requested',
    remaining: [],
  }
  const quiesced: DevFrameLifecycleEventData = {
    ...stopRequested,
    state: 'quiescence_confirmed',
  }
  const taskWarning: DevFrameTaskWarningEventData = {
    version: 1,
    taskId: TASK,
    warning: 'MEMORY_UNAVAILABLE',
    tool: 'memory_append',
    grade: 'fail',
  }
  return { usageReserved, usageSettled, verification, review, taskWarning, stopRequested, quiesced }
}

describe('DevFrame durable event vocabulary', () => {
  it('registers every project event in the generated native vocabulary', () => {
    expect([...KNOWN_SESSION_EVENT_TYPES].filter(type => type.startsWith('devframe/'))).toEqual([
      'devframe/goal-binding',
      'devframe/lifecycle',
      'devframe/review',
      'devframe/role-policy',
      'devframe/task-warning',
      'devframe/usage',
      'devframe/verification',
    ])
  })

  it('rejects malformed or non-canonical payloads before Session.append', () => {
    expect(() => decodeDevFramePayload('devframe/role-policy', {
      ...rolePolicy(),
      config: {
        ...rolePolicy().config,
        worker: { inheritedTools: ['read'], denyScopedTools: [] },
      },
      unexpected: true,
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/usage', {
      ...fullEventSet().usageReserved,
      phase: 'settled',
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/verification', {
      ...fullEventSet().verification,
      status: 'passed',
      checks: [{ ...fullEventSet().verification.checks[0], status: 'failed' }],
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/role-policy', {
      ...rolePolicy(),
      assignments: [
        { role: 'controller', sessionId: CONTROLLER },
        { role: 'controller', sessionId: SessionId('worker-one') },
      ],
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/goal-binding', {
      ...binding(),
      budget: { maxAttempts: 1, consumedAttempts: 2 },
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/usage', {
      ...fullEventSet().usageReserved,
      tokenUsage: { kind: 'unknown', total: 1 },
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/verification', {
      ...fullEventSet().verification,
      snapshotId: DevFrameSnapshotId('snapshot-other'),
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/review', {
      ...fullEventSet().review,
      snapshotId: DevFrameSnapshotId('snapshot-other'),
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/verification', {
      ...fullEventSet().verification,
      snapshotId: undefined,
    } as never)).toThrow(/payload is invalid/)
    // A weakened verification no longer decodes: the declared required check
    // is not exactly executed by the recorded checks.
    expect(() => decodeDevFramePayload('devframe/verification', {
      ...fullEventSet().verification,
      checks: [{
        ...fullEventSet().verification.checks[0],
        arguments: ['run', 'typecheck', '--fast'],
      }],
    })).toThrow(/payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/lifecycle', {
      ...fullEventSet().quiesced,
      state: 'stopped',
      remaining: [{ resource: 'worker', reason: 'timeout' }],
    })).toThrow(/payload is invalid/)
  })

  it('serializes concurrent appends and returns only after a durable flush', async () => {
    const current = session()
    const observed: number[] = []
    const journal = new DevFrameSessionJournal(async (value) => {
      observed.push(value.seq)
      return true
    }, reviewGate())

    const first = journal.append(current, 'devframe/role-policy', rolePolicy())
    const second = journal.append(current, 'devframe/goal-binding', binding())
    const [firstEvent, secondEvent] = await Promise.all([first, second])

    expect([firstEvent.seq, secondEvent.seq]).toEqual([0, 1])
    expect(observed).toEqual([1, 2])
    expect(current.snapshotEvents().map(event => event.type)).toEqual([
      'devframe/role-policy',
      'devframe/goal-binding',
    ])
  })

  it('latches a failed flush and never admits a later DevFrame mutation', async () => {
    const current = session()
    const flush = vi.fn(async () => false)
    const journal = new DevFrameSessionJournal(flush, reviewGate())

    await expect(journal.append(current, 'devframe/role-policy', rolePolicy()))
      .rejects.toMatchObject({ name: 'DevFramePersistenceError', code: 'unavailable' })
    await expect(journal.append(current, 'devframe/goal-binding', binding()))
      .rejects.toMatchObject({ name: 'DevFramePersistenceError', code: 'blocked' })
    expect(flush).toHaveBeenCalledTimes(1)
    expect(journal.isBlocked(current)).toBe(true)
    expect(current.seq).toBe(1)
  })

  it('rejects a review whose submitter holds no reviewer role and keeps the journal writable', async () => {
    const current = session()
    const flush = vi.fn(async () => true)
    const journal = new DevFrameSessionJournal(flush, reviewGate())
    const events = fullEventSet()

    await expect(journal.append(current, 'devframe/review', {
      ...events.review,
      reviewerSessionId: SessionId('worker-one'),
    })).rejects.toThrow(/holds no reviewer role/)
    expect(current.snapshotEvents().some(event => event.type === 'devframe/review')).toBe(false)
    expect(flush).not.toHaveBeenCalled()
    expect(journal.isBlocked(current)).toBe(false)

    await expect(journal.append(current, 'devframe/review', {
      ...events.review,
      reviewerSessionId: SessionId('session-404'),
    })).rejects.toThrow(/holds no reviewer role/)
    expect(current.seq).toBe(0)

    await journal.append(current, 'devframe/review', events.review)
    expect(current.snapshotEvents().filter(event => event.type === 'devframe/review')).toHaveLength(1)
    expect(flush).toHaveBeenCalledTimes(1)
  })

  it('round-trips all DevFrame event classes through the native Session restore path', () => {
    const current = session()
    const events = fullEventSet()
    current.append('devframe/role-policy', rolePolicy())
    current.append('devframe/goal-binding', binding())
    current.append('devframe/usage', events.usageReserved)
    current.append('devframe/usage', events.usageSettled)
    current.append('devframe/verification', events.verification)
    current.append('devframe/review', events.review)
    current.append('devframe/task-warning', events.taskWarning)
    current.append('devframe/lifecycle', events.stopRequested)
    current.append('devframe/lifecycle', events.quiesced)

    const restored = Session.fromRestore(
      current.id,
      structuredClone(current.snapshotEvents()),
      current.header,
      SessionLogOffset(0),
    )
    const state = foldDevFrameState(restored.snapshotEvents(), restored.header)

    expect(state.failure).toBeNull()
    expect(state.rolePolicy?.policyVersion).toBe('policy-one')
    expect(state.bindings).toHaveLength(1)
    expect(state.usage).toHaveLength(2)
    expect(state.verifications).toHaveLength(1)
    expect(state.reviews).toHaveLength(1)
    expect(state.taskWarnings).toEqual([events.taskWarning])
    expect(state.lifecycle?.state).toBe('quiescence_confirmed')
  })

  it('keeps a corrupted duplicate or identity change fail-closed during replay', () => {
    const duplicate = session()
    duplicate.append('devframe/role-policy', rolePolicy())
    duplicate.append('devframe/goal-binding', binding())
    duplicate.append('devframe/goal-binding', binding())
    expect(foldDevFrameState(duplicate.snapshotEvents(), duplicate.header).failure)
      .toMatch(/recorded twice/)

    const changed = session()
    changed.append('devframe/role-policy', rolePolicy())
    changed.append('devframe/goal-binding', binding())
    changed.append('devframe/goal-binding', binding({ taskIds: [TaskId('task-2')] }))
    expect(foldDevFrameState(changed.snapshotEvents(), changed.header).failure)
      .toMatch(/immutable binding/)
  })

  it('keeps a duplicated task warning fail-closed during replay', () => {
    const events = fullEventSet()
    const duplicate = session()
    duplicate.append('devframe/task-warning', events.taskWarning)
    duplicate.append('devframe/task-warning', events.taskWarning)
    expect(foldDevFrameState(duplicate.snapshotEvents(), duplicate.header).failure)
      .toMatch(/recorded twice/)
  })

  it('rejects cross-record budget and policy mismatches during replay', () => {
    const budget = session()
    budget.append('devframe/role-policy', rolePolicy())
    budget.append('devframe/goal-binding', binding())
    budget.append('devframe/usage', fullEventSet().usageReserved)
    budget.append('devframe/usage', {
      ...fullEventSet().usageReserved,
      operationId: DevFrameOperationId('operation-two'),
      consumedAttempts: 1,
    })
    expect(foldDevFrameState(budget.snapshotEvents(), budget.header).failure)
      .toMatch(/did not advance consumed attempts/)

    const policy = session()
    const events = fullEventSet()
    policy.append('devframe/role-policy', rolePolicy())
    policy.append('devframe/goal-binding', binding())
    policy.append('devframe/verification', events.verification)
    policy.append('devframe/review', { ...events.review, policyVersion: 'policy-two' })
    expect(foldDevFrameState(policy.snapshotEvents(), policy.header).failure)
      .toMatch(/unavailable role policy version/)
  })

  it('rejects reviews from sessions without the reviewer role and snapshot swaps during replay', () => {
    const impostor = session()
    const events = fullEventSet()
    impostor.append('devframe/role-policy', rolePolicy())
    impostor.append('devframe/goal-binding', binding())
    impostor.append('devframe/verification', events.verification)
    impostor.append('devframe/review', {
      ...events.review,
      reviewerSessionId: SessionId('worker-one'),
    })
    expect(foldDevFrameState(impostor.snapshotEvents(), impostor.header).failure)
      .toMatch(/without the reviewer role/)

    const swapped = session()
    swapped.append('devframe/role-policy', rolePolicy())
    swapped.append('devframe/goal-binding', binding())
    swapped.append('devframe/verification', events.verification)
    // The swapped pair is schema-consistent (event snapshot matches its
    // binding), so the projection's result-tuple assertion rejects it against
    // the stored Goal binding.
    swapped.append('devframe/review', {
      ...events.review,
      snapshotId: DevFrameSnapshotId('snapshot-other'),
      binding: {
        ...events.review.binding,
        snapshotId: DevFrameSnapshotId('snapshot-other'),
      },
    })
    expect(foldDevFrameState(swapped.snapshotEvents(), swapped.header).failure)
      .toMatch(/does not match its binding/)

    const swappedVerification = session()
    swappedVerification.append('devframe/role-policy', rolePolicy())
    swappedVerification.append('devframe/goal-binding', binding())
    swappedVerification.append('devframe/verification', {
      ...events.verification,
      snapshotId: DevFrameSnapshotId('snapshot-other'),
      binding: {
        ...events.verification.binding,
        snapshotId: DevFrameSnapshotId('snapshot-other'),
      },
    })
    expect(foldDevFrameState(swappedVerification.snapshotEvents(), swappedVerification.header).failure)
      .toMatch(/does not match its binding/)
  })

  it('resets the current lifecycle projection for a subsequent Goal', () => {
    const current = session()
    const first = binding()
    const second = binding({ goalId: GoalId('goal-2') })
    current.append('devframe/role-policy', rolePolicy())
    current.append('devframe/goal-binding', first)
    current.append('devframe/lifecycle', {
      version: 1,
      binding: resultBinding(first),
      state: 'stop_requested',
      remaining: [],
    })
    current.append('devframe/goal-binding', second)
    current.append('devframe/lifecycle', {
      version: 1,
      binding: resultBinding(second),
      state: 'stop_requested',
      remaining: [],
    })

    const state = foldDevFrameState(current.snapshotEvents(), current.header)
    expect(state.failure).toBeNull()
    expect(state.lifecycle?.binding.goalId).toBe(second.goalId)
    expect(state.lifecycle?.state).toBe('stop_requested')
  })
})

describe('DevFrame host projection', () => {
  it('drives the native projection registry and validates its checkpoint on cold restore', async () => {
    const ctx = new Context()
    await ctx.plugin(SessionStore)
    await ctx.plugin(SessionProjectionRegistry)
    ctx.sessionProjections.register(devFrameProjectionDefinition)
    const current = ctx.sessions.create(CONTROLLER, { meta: { createdAt: 0 } })
    current.append('devframe/role-policy', rolePolicy())
    current.append('devframe/goal-binding', binding())

    const live = ctx.sessionProjections.stateOf(current, 'devframe')
    expect(live?.failure).toBeNull()
    expect(live?.bindings).toHaveLength(1)
    const checkpoint = ctx.sessionProjections.checkpoint(current)
    const row = checkpoint.devframe
    expect(row?.ver).toBe(1)
    expect(ctx.sessionProjections.restore(
      checkpoint,
      current.snapshotEvents(),
      SessionLogOffset(0),
      current.header,
      SessionLogOffset(0),
    ).checkpoint.devframe?.val).toEqual(row?.val)
    await ctx.fiber.dispose()
  })

  it('round-trips the journal through the JSONL persistence backend', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-events-'))
    const ctx = new Context()
    try {
      await ctx.plugin(SessionStore)
      await ctx.plugin(JsonlSessionPersistence, { root, compression: 'none' })
      const current = ctx.sessions.create(CONTROLLER, { meta: { createdAt: 0 } })
      const journal = new DevFrameSessionJournal(value => ctx.sessions.flush(value), reviewGate())

      await journal.append(current, 'devframe/role-policy', rolePolicy())
      await journal.append(current, 'devframe/goal-binding', binding())

      const loaded = await ctx.sessionPersistence.load(current.id)
      expect(loaded.events.map(event => event.type)).toEqual([
        'devframe/role-policy',
        'devframe/goal-binding',
      ])
      const restored = Session.fromRestore(
        loaded.meta.id,
        loaded.events,
        loaded.meta,
        loaded.inheritedEventCount,
      )
      expect(foldDevFrameState(restored.snapshotEvents(), restored.header).failure).toBeNull()
    } finally {
      await ctx.fiber.dispose()
      await rm(root, { recursive: true, force: true })
    }
  })
})
