/**
 * AT1-08 repair limit: at most two correction/retest/review rounds follow the
 * initial review by default, the limit is a validated Config field rather than
 * a constant, exhaustion is rejection data that leaves the accounting
 * unchanged, and a different configured limit changes the admitted count.
 * @module dsh-experimental-devframe/tests/repair-limit
 */

import { describe, expect, it } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import {
  DEFAULT_REPAIR_LIMIT,
  ControllerSessionId,
  GoalBindingController,
  MemoryGoalBindingStore,
  RepairLimitError,
  TaskId,
  WorkspaceId,
  createHumanAuthorization,
  evaluateRepairRoundAdmission,
  resolveRepairLimit,
} from '../src/index.ts'
import type { GoalBindingIdentity, NativeGoalPort, NativeGoalState } from '../src/index.ts'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint } from '../src/shared/types.ts'

/** Minimal native Goal port standing in for the live Goal service. */
function fakeGoals(): NativeGoalPort {
  let current: NativeGoalState | undefined
  return {
    create() {
      current = { id: GoalId('goal-1'), revision: 1, phase: 'active' }
      return current
    },
    disarm() {
      return current
    },
    get() {
      return current
    },
    resume(ref) {
      if (current === undefined || current.id !== ref.id) throw new Error('resume target mismatch')
      current = { ...current, revision: current.revision + 1 }
      return current
    },
    complete(ref) {
      if (current === undefined || current.id !== ref.id) throw new Error('complete target mismatch')
      current = { ...current, revision: current.revision + 1, phase: 'complete' }
      return current
    },
  }
}

/** Build one controller over a fresh fake Goal and in-memory store. */
function repairController(repairLimit?: number): GoalBindingController {
  return new GoalBindingController({
    workspaceId: WorkspaceId('workspace-repair'),
    controllerSessionId: ControllerSessionId('controller-repair'),
    goals: fakeGoals(),
    store: new MemoryGoalBindingStore(),
    ...repairLimit === undefined ? {} : { repairLimit },
  })
}

/** Start one bound Goal so its identity is available for repair rounds. */
async function startedIdentity(controller: GoalBindingController): Promise<GoalBindingIdentity> {
  const binding = await controller.start({
    objective: 'implement task',
    taskIds: [TaskId('task-1')],
    acceptanceHash: AcceptanceHash('acceptance-a'),
    sourceFingerprint: SourceFingerprint('source-a'),
    snapshotId: DevFrameSnapshotId('snapshot-a'),
    budget: { maxAttempts: 3 },
    authorization: createHumanAuthorization('confirm-a'),
  })
  return { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId }
}

describe('resolveRepairLimit', () => {
  it('resolves the acceptance-defined default of two rounds when unconfigured', () => {
    expect(DEFAULT_REPAIR_LIMIT).toBe(2)
    expect(resolveRepairLimit()).toBe(2)
    expect(resolveRepairLimit({})).toBe(2)
  })

  it('fails loud on a limit outside the serviceable range', () => {
    for (const repairLimit of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => resolveRepairLimit({ repairLimit })).toThrow(RepairLimitError)
      try {
        resolveRepairLimit({ repairLimit })
        throw new Error(`expected repairLimit ${String(repairLimit)} to be rejected`)
      } catch (error: unknown) {
        expect((error as RepairLimitError).code).toBe('REPAIR_LIMIT_INVALID_CONFIG')
      }
    }
  })
})

describe('evaluateRepairRoundAdmission', () => {
  it('admits each round under the limit and reports the charged round and remaining count', () => {
    expect(evaluateRepairRoundAdmission({ repairLimit: 3, consumedRepairRounds: 0 })).toEqual({
      kind: 'admitted',
      repairRound: 1,
      remainingRepairRounds: 2,
    })
    expect(evaluateRepairRoundAdmission({ repairLimit: 3, consumedRepairRounds: 2 })).toEqual({
      kind: 'admitted',
      repairRound: 3,
      remainingRepairRounds: 0,
    })
  })

  it('rejects with exhaustion data exactly at the limit', () => {
    expect(evaluateRepairRoundAdmission({ repairLimit: 2, consumedRepairRounds: 2 })).toEqual({
      kind: 'rejected',
      reason: 'repair-limit-exhausted',
      repairLimit: 2,
      consumedRepairRounds: 2,
    })
  })

  it('fails loud on a limit or consumed count outside its range', () => {
    expect(() => evaluateRepairRoundAdmission({ repairLimit: 0, consumedRepairRounds: 0 })).toThrow(RepairLimitError)
    expect(() => evaluateRepairRoundAdmission({ repairLimit: 2, consumedRepairRounds: -1 })).toThrow(RepairLimitError)
    expect(() => evaluateRepairRoundAdmission({ repairLimit: 2, consumedRepairRounds: 0.5 })).toThrow(RepairLimitError)
  })
})

describe('GoalBindingController repair rounds (AT1-08)', () => {
  it('admits the default two rounds after the initial review and rejects the third as data', async () => {
    const controller = repairController()
    const identity = await startedIdentity(controller)

    expect(controller.repairRoundState(identity)).toEqual({
      repairLimit: 2,
      consumedRepairRounds: 0,
      remainingRepairRounds: 2,
    })
    await expect(controller.beginRepairRound(identity)).resolves.toEqual({
      kind: 'admitted',
      repairRound: 1,
      remainingRepairRounds: 1,
    })
    await expect(controller.beginRepairRound(identity)).resolves.toEqual({
      kind: 'admitted',
      repairRound: 2,
      remainingRepairRounds: 0,
    })

    const rejected = await controller.beginRepairRound(identity)
    expect(rejected).toEqual({
      kind: 'rejected',
      reason: 'repair-limit-exhausted',
      repairLimit: 2,
      consumedRepairRounds: 2,
    })
    // Exhaustion is data, not a state change: the accounting stays at the
    // limit and every further attempt is rejected identically.
    expect(controller.repairRoundState(identity)).toEqual({
      repairLimit: 2,
      consumedRepairRounds: 2,
      remainingRepairRounds: 0,
    })
    await expect(controller.beginRepairRound(identity)).resolves.toEqual(rejected)
  })

  it('admits exactly one round when the configured limit is 1 (boundary)', async () => {
    const controller = repairController(1)
    const identity = await startedIdentity(controller)

    await expect(controller.beginRepairRound(identity)).resolves.toEqual({
      kind: 'admitted',
      repairRound: 1,
      remainingRepairRounds: 0,
    })
    await expect(controller.beginRepairRound(identity)).resolves.toEqual({
      kind: 'rejected',
      reason: 'repair-limit-exhausted',
      repairLimit: 1,
      consumedRepairRounds: 1,
    })
  })

  it('applies a higher configured limit and keeps per-Goal accounting', async () => {
    const controller = repairController(3)
    const identity = await startedIdentity(controller)

    const rounds = [
      await controller.beginRepairRound(identity),
      await controller.beginRepairRound(identity),
      await controller.beginRepairRound(identity),
    ]
    expect(rounds).toEqual([
      { kind: 'admitted', repairRound: 1, remainingRepairRounds: 2 },
      { kind: 'admitted', repairRound: 2, remainingRepairRounds: 1 },
      { kind: 'admitted', repairRound: 3, remainingRepairRounds: 0 },
    ])
    await expect(controller.beginRepairRound(identity)).resolves.toEqual({
      kind: 'rejected',
      reason: 'repair-limit-exhausted',
      repairLimit: 3,
      consumedRepairRounds: 3,
    })
    expect(controller.repairRoundState(identity)).toMatchObject({ repairLimit: 3, consumedRepairRounds: 3 })
  })

  it('fails loud on an invalid configured limit at construction', () => {
    expect(() => repairController(0)).toThrow(RepairLimitError)
    expect(() => repairController(2.5)).toThrow(RepairLimitError)
  })

  it('rejects repair rounds for unknown or foreign identities', async () => {
    const controller = repairController()
    const identity = await startedIdentity(controller)

    await expect(controller.beginRepairRound({
      controllerSessionId: ControllerSessionId('controller-other'),
      goalId: identity.goalId,
    })).rejects.toMatchObject({
      name: 'GoalBindingError',
      code: 'GOAL_BINDING_IDENTITY_MISMATCH',
    })
    await expect(controller.beginRepairRound({
      controllerSessionId: identity.controllerSessionId,
      goalId: GoalId('goal-unknown'),
    })).rejects.toMatchObject({
      name: 'GoalBindingError',
      code: 'GOAL_BINDING_NOT_FOUND',
    })
    // The rejection paths consumed nothing: the bound Goal stays at zero.
    expect(controller.repairRoundState(identity)).toMatchObject({ consumedRepairRounds: 0 })
  })
})
