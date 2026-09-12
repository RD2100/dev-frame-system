/** Durable correction admissions share a Goal budget across writers and cold restore. */
import { describe, expect, it } from 'vitest'
import { Session, SessionId, SessionLogOffset, SessionSeq } from '@deepseek-ai/dsh-session'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { DevFrameSessionJournal } from '../src/session-journal.ts'
import { devFrameProjectionDefinition, foldDevFrameState } from '../src/projection.ts'
import { DevFrameReviewId, DevFrameVerificationId, type DevFrameRepairCause } from '../src/events.ts'
import { GoalBindingController, MemoryGoalBindingStore, TaskId, type GoalBinding } from '../src/controller/goal-binding.ts'
import { AcceptanceHash, ConfigurationConfirmationId, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '../src/shared/types.ts'
import { requiredChecksDigest } from '../src/required-checks.ts'

/** Create one real Session containing Goal-bound failure evidence. */
async function fixture() {
  const session = Session.create(SessionId('repair-controller'))
  const journal = new DevFrameSessionJournal(async () => true, { requireReviewer() {} })
  const identity = { controllerSessionId: session.id, goalId: GoalId('repair-goal') }
  const binding: GoalBinding = {
    version: 1, ...identity, workspaceId: WorkspaceId('repair-workspace'), goalRevision: 1,
    taskIds: [TaskId('task-a'), TaskId('task-b'), TaskId('task-c')],
    acceptanceHash: AcceptanceHash('acceptance'), sourceFingerprint: SourceFingerprint('source'),
    snapshotId: DevFrameSnapshotId('snapshot'), lifecycle: 'admission_open',
    budget: { maxAttempts: 10, consumedAttempts: 0 },
    confirmation: { id: ConfigurationConfirmationId('approved'), acceptanceHash: AcceptanceHash('acceptance') },
  }
  await journal.append(session, 'devframe/goal-binding', binding)
  for (const taskId of binding.taskIds) await journal.append(session, 'devframe/task-warning', {
    version: 1, taskId, warning: 'MEMORY_WRITE_FAILED', tool: 'memory', grade: 'fail',
  })
  const cause = (task: string): DevFrameRepairCause => ({ kind: 'task-warning', taskId: TaskId(task) })
  return { session, journal, identity, binding, cause }
}

/** Land a verified independent negative review of the fixture's Goal snapshot. */
async function negativeReview(value: Awaited<ReturnType<typeof fixture>>) {
  const { session, journal, binding } = value
  const reviewerSessionId = SessionId('reviewer')
  await journal.append(session, 'devframe/role-policy', {
    version: 1, workspaceId: binding.workspaceId, controllerSessionId: session.id, policyVersion: 'policy',
    config: {
      controller: { inheritedTools: [], denyScopedTools: [] }, worker: { inheritedTools: [], denyScopedTools: [] },
      reviewer: { inheritedTools: [], denyScopedTools: [] },
    },
    assignments: [{ role: 'controller', sessionId: session.id }, { role: 'reviewer', sessionId: reviewerSessionId }],
  })
  const reference = {
    controllerSessionId: session.id, goalId: binding.goalId, goalRevision: binding.goalRevision,
    taskIds: binding.taskIds, acceptanceHash: binding.acceptanceHash, workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint, snapshotId: binding.snapshotId,
  }
  const config = { version: 1 as const, checks: [{ checkId: 'check', executable: 'node', arguments: ['--version'], cwd: 'C:/test' }] }
  await journal.append(session, 'devframe/verification', {
    version: 1, verificationId: DevFrameVerificationId('verified'), binding: reference, snapshotId: binding.snapshotId,
    status: 'passed', requiredChecks: { config, digest: requiredChecksDigest(config) },
    checks: [{ ...config.checks[0]!, status: 'passed', exitCode: 0, durationMs: 0 }],
  })
  const reviewId = DevFrameReviewId('negative-review')
  await journal.append(session, 'devframe/review', {
    version: 1, reviewId, binding: reference, snapshotId: binding.snapshotId,
    reviewerSessionId, policyVersion: 'policy', decision: 'changes_required', findings: [],
  })
  return { kind: 'review' as const, reviewId }
}

describe('durable correction admission', () => {
  it('reconstructs the controller accounting from its injected journal after controller replacement', async () => {
    const { session, journal, identity, cause, binding } = await fixture()
    const store = new MemoryGoalBindingStore()
    await store.save(binding)
    const native = { id: identity.goalId, revision: 1, phase: 'active' as const }
    const options = {
      workspaceId: binding.workspaceId, controllerSessionId: session.id, store, repairLimit: 1,
      goals: { get: () => native, create: () => native, disarm: () => native, resume: () => native, complete: () => native },
      repairAdmissions: {
        admit: (target: typeof identity, evidence: DevFrameRepairCause, repairLimit: number) =>
          journal.admitRepair(session, { identity: target, cause: evidence, repairLimit }),
        state: (target: typeof identity, repairLimit: number) => journal.repairRoundState(session, target, repairLimit),
      },
    }
    const original = new GoalBindingController(options)
    const receipt = await original.beginRepairRound(identity, cause('task-a'))
    const replacement = new GoalBindingController(options)
    expect(await replacement.beginRepairRound(identity, cause('task-a'))).toEqual(receipt)
    expect(await replacement.beginRepairRound(identity, cause('task-b'))).toMatchObject({ kind: 'rejected' })
    expect(replacement.repairRoundState(identity).consumedRepairRounds).toBe(1)
  })

  it('shares the last allowance and idempotent causes across independent journals', async () => {
    const { session, journal, identity, cause } = await fixture()
    const second = new DevFrameSessionJournal(async () => true, { requireReviewer() {} })
    let release!: () => void
    let entered!: () => void
    const barrier = new Promise<void>((resolve) => { release = resolve })
    const ready = new Promise<void>((resolve) => { entered = resolve })
    const request = { identity, cause: cause('task-a'), repairLimit: 1 }
    const first = journal.admitRepair(session, request, { prepare: async () => { entered(); await barrier } })
    await ready
    const retry = second.admitRepair(session, request)
    const competing = second.admitRepair(session, { ...request, cause: cause('task-b') })
    release()
    expect(await first).toEqual({ kind: 'admitted', repairRound: 1, remainingRepairRounds: 0 })
    expect(await retry).toEqual(await first)
    expect(await competing).toMatchObject({ kind: 'rejected', reason: 'repair-limit-exhausted' })
    expect(session.snapshotEvents().filter(event => event.type === 'devframe/repair-admission')).toHaveLength(1)
  })

  it('restores consumption and the same cause receipt after a cold Session restore and Goal revision', async () => {
    const { session, journal, identity, cause, binding } = await fixture()
    const request = { identity, cause: cause('task-a'), repairLimit: 2 }
    const first = await journal.admitRepair(session, request)
    await journal.append(session, 'devframe/goal-binding', { ...binding, goalRevision: 2 })
    const restored = Session.fromRestore(
      session.id, structuredClone(session.snapshotEvents()), structuredClone(session.header), SessionLogOffset(0),
    )
    const fresh = new DevFrameSessionJournal(async () => true, { requireReviewer() {} })
    expect(await fresh.admitRepair(restored, request)).toEqual(first)
    expect(await fresh.admitRepair(restored, { ...request, cause: cause('task-b') })).toMatchObject({ repairRound: 2 })
    expect(await fresh.admitRepair(restored, { ...request, cause: cause('task-c') })).toMatchObject({ kind: 'rejected' })
    expect(fresh.repairRoundState(restored, identity, 2).consumedRepairRounds).toBe(2)
  })

  it('charges task warnings and independent negative reviews to the same Goal allowance', async () => {
    const value = await fixture()
    const { session, journal, identity, cause } = value
    const review = await negativeReview(value)
    await journal.admitRepair(session, { identity, cause: cause('task-a'), repairLimit: 2 })
    expect(await journal.admitRepair(session, { identity, cause: review, repairLimit: 2 })).toMatchObject({ repairRound: 2 })
    expect(await journal.admitRepair(session, { identity, cause: cause('task-b'), repairLimit: 2 })).toMatchObject({ kind: 'rejected' })
  })

  it('starts a fresh Goal at round one and refuses every admission for the previous Goal', async () => {
    const { session, journal, identity, cause, binding } = await fixture()
    const original = { identity, cause: cause('task-a'), repairLimit: 1 }
    await journal.admitRepair(session, original)
    const nextIdentity = { ...identity, goalId: GoalId('next-goal') }
    const taskId = TaskId('next-task')
    await journal.append(session, 'devframe/goal-binding', { ...binding, ...nextIdentity, taskIds: [taskId] })
    await journal.append(session, 'devframe/task-warning', {
      version: 1, taskId, warning: 'MEMORY_WRITE_FAILED', tool: 'memory', grade: 'fail',
    })
    // A historical receipt remains readable but cannot reopen work for a superseded Goal.
    await expect(journal.admitRepair(session, original)).rejects.toThrow('current controller Goal')
    await expect(journal.admitRepair(session, { ...original, cause: cause('task-b') })).rejects.toThrow('current controller Goal')
    expect(await journal.admitRepair(session, {
      identity: nextIdentity, cause: { kind: 'task-warning', taskId }, repairLimit: 1,
    })).toEqual({ kind: 'admitted', repairRound: 1, remainingRepairRounds: 0 })
    expect(journal.repairRoundState(session, identity, 1).consumedRepairRounds).toBe(1)
    expect(journal.repairRoundState(session, nextIdentity, 1).consumedRepairRounds).toBe(1)
    expect(session.snapshotEvents().filter(event => event.type === 'devframe/repair-admission')).toHaveLength(2)
  })

  it('does not charge when authority is revoked during queued preparation', async () => {
    const { session, journal, identity, cause } = await fixture()
    let live = true
    await expect(journal.admitRepair(session, { identity, cause: cause('task-a'), repairLimit: 2 }, {
      beforeAppend: () => { if (!live) throw new Error('authority revoked') },
      prepare: async () => { live = false },
    })).rejects.toThrow('authority revoked')
    expect(journal.repairRoundState(session, identity, 2).consumedRepairRounds).toBe(0)
    expect(await journal.admitRepair(session, { identity, cause: cause('task-a'), repairLimit: 2 })).toMatchObject({ repairRound: 1 })
  })

  it('shares uncertain flush failures across writers and refuses apparently recorded retries', async () => {
    const { session, journal, identity, cause } = await fixture()
    const broken = new DevFrameSessionJournal(async () => { throw new Error('disk failure') }, { requireReviewer() {} })
    const request = { identity, cause: cause('task-a'), repairLimit: 2 }
    await expect(broken.admitRepair(session, request)).rejects.toMatchObject({ code: 'failed' })
    await expect(journal.admitRepair(session, request)).rejects.toMatchObject({ code: 'blocked' })
    expect(() => journal.repairRoundState(session, identity, 2)).toThrow('blocked')
    expect(session.snapshotEvents().filter(event => event.type === 'devframe/repair-admission')).toHaveLength(1)
  })

  it('rejects foreign identities, unknown causes, budget changes, duplicate and skipped admission records', async () => {
    const { session, journal, identity, cause } = await fixture()
    const request = { identity, cause: cause('task-a'), repairLimit: 2 }
    await expect(journal.admitRepair(session, { ...request, identity: { ...identity, controllerSessionId: SessionId('other') } })).rejects.toThrow('current controller Goal')
    await expect(journal.admitRepair(session, { ...request, cause: cause('missing') })).rejects.toThrow('failed task warning')
    await journal.admitRepair(session, request)
    await expect(journal.admitRepair(session, { ...request, repairLimit: 3 })).rejects.toThrow('Repair limit changed')
    await expect(journal.append(session, 'devframe/repair-admission', { version: 1, ...request, repairRound: 2 })).rejects.toThrow('admitted twice')
    await expect(journal.append(session, 'devframe/repair-admission', { version: 1, ...request, cause: cause('task-b'), repairRound: 3 })).rejects.toThrow('repair budget')
  })

  it('rejects duplicate durable admissions on replay and invalidates older checkpoint states', async () => {
    const { session, journal, identity, cause } = await fixture()
    await journal.admitRepair(session, { identity, cause: cause('task-a'), repairLimit: 2 })
    const event = session.snapshotEvents().at(-1)!
    const state = foldDevFrameState([...session.snapshotEvents(), { ...event, seq: SessionSeq(session.seq) }], session.header)
    expect(state.failure).toContain('admitted twice')
    const valid = foldDevFrameState(session.snapshotEvents(), session.header)
    const { repairAdmissions: _admissions, ...oldCheckpoint } = valid
    expect(devFrameProjectionDefinition.stateVersion).toBe(5)
    expect(devFrameProjectionDefinition.stateSchema.safeParse(oldCheckpoint).success).toBe(false)
    expect(devFrameProjectionDefinition.stateSchema.safeParse(valid).success).toBe(true)
  })
})
