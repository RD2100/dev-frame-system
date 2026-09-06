/**
 * The DevFrame evidence producer: honest verification records from a real
 * execution face, gated review records, and the write-to-projection seam the
 * hostcmd reading face folds — including the error paths that must write
 * nothing.
 */

import { tmpdir } from 'node:os'
import { describe, expect, it } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { Session, SessionId, SessionLogOffset } from '@deepseek-ai/dsh-session'
import { TaskId as EvidenceTaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AcceptanceHash, ConfigurationConfirmationId, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { decodeDevFramePayload, DevFrameSnapshotId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type { DevFrameRolePolicyEventData } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import {
  MemoryRequiredChecksConfigStore,
  RequiredChecksDigest,
  RequiredChecksError,
} from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import type { DevFrameRequiredChecksConfig, RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { TaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { GoalBinding, GoalResultBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { DevFrameFlush } from '@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts'
import { AgentEvidenceJournal } from '../src/journal.ts'
import type { RequiredChecksExecution } from '../src/check-runner.ts'
import type { EvidenceReviewerDirectory } from '../src/review-gate.ts'
import { harness } from './helpers.ts'

const CONTROLLER = SessionId('controller-evjournal')
const REVIEWER = SessionId('reviewer-evjournal')
const WORKSPACE = WorkspaceId('ws-evjournal')
const ACCEPTANCE = AcceptanceHash('acceptance-evjournal')
const SOURCE = SourceFingerprint('source-evjournal')
const SNAPSHOT = DevFrameSnapshotId('snapshot-evjournal')
const POLICY_VERSION = 'policy-evjournal'
const TASK = TaskId('task-evjournal')

/** The complete work tuple every producer payload attributes to. */
const BINDING: GoalResultBinding = {
  controllerSessionId: CONTROLLER,
  goalId: GoalId('goal-evjournal'),
  goalRevision: 1,
  taskIds: [TASK],
  acceptanceHash: ACCEPTANCE,
  workspaceId: WORKSPACE,
  sourceFingerprint: SOURCE,
  snapshotId: SNAPSHOT,
}

/** The single approved check the memory store registers for the producer. */
const APPROVED_CONFIG: DevFrameRequiredChecksConfig = {
  version: 1,
  checks: [{
    checkId: 'check-evjournal',
    executable: process.execPath,
    arguments: ['-e', 'process.exit(0)'],
    cwd: tmpdir(),
  }],
}

function session(): Session {
  return Session.create(CONTROLLER, undefined, { version: 0, id: CONTROLLER, createdAt: 0, isSeeded: false })
}

/** The reviewer authority wired into the journal; it records every consult. */
function reviewerDirectory(): {
  directory: EvidenceReviewerDirectory
  consulted: SessionId[]
} {
  const consulted: SessionId[] = []
  return {
    consulted,
    directory: {
      roleOf(sessionId) {
        consulted.push(sessionId)
        return sessionId === REVIEWER ? 'reviewer' : sessionId === CONTROLLER ? 'controller' : undefined
      },
    },
  }
}

/** A durability callback recording every flush and answering durably true. */
function durableFlush(): { flush: DevFrameFlush; flushed: Session[] } {
  const flushed: Session[] = []
  return { flushed, flush: async session => { flushed.push(session); return true } }
}

/** A fake execution echoing every configured check verbatim with the given statuses. */
function executionWith(statuses: readonly ('passed' | 'failed')[]): RequiredChecksExecution {
  return async config => config.checks.map((check, index) => ({
    checkId: check.checkId,
    executable: check.executable,
    arguments: [...check.arguments],
    cwd: check.cwd,
    status: statuses[index] ?? 'failed',
    ...(statuses[index] === 'passed' ? { exitCode: 0 } : { exitCode: 1 }),
    durationMs: 1,
  }))
}

/** The registered digest of {@link APPROVED_CONFIG} in a fresh memory store. */
async function registeredStore(): Promise<{ store: MemoryRequiredChecksConfigStore; digest: RequiredChecksDigest }> {
  const store = new MemoryRequiredChecksConfigStore()
  return { store, digest: await store.save(APPROVED_CONFIG) }
}

/** The role-policy snapshot the projection re-validates review records against. */
function rolePolicy(): DevFrameRolePolicyEventData {
  return {
    version: 1,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    policyVersion: POLICY_VERSION,
    config: {
      controller: { inheritedTools: ['read'], denyScopedTools: [] },
      worker: { inheritedTools: ['read', 'write'], denyScopedTools: [] },
      reviewer: { inheritedTools: ['read'], denyScopedTools: ['write'] },
    },
    assignments: [
      { role: 'controller', sessionId: CONTROLLER },
      { role: 'reviewer', sessionId: REVIEWER },
    ],
  }
}

/** The Goal binding the projection requires before any result tuple resolves. */
function goalBinding(): GoalBinding {
  return {
    version: 1,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    goalId: BINDING.goalId,
    goalRevision: BINDING.goalRevision,
    taskIds: [...BINDING.taskIds],
    acceptanceHash: ACCEPTANCE,
    sourceFingerprint: SOURCE,
    snapshotId: SNAPSHOT,
    confirmation: { id: ConfigurationConfirmationId('confirmation-evjournal'), acceptanceHash: ACCEPTANCE },
    lifecycle: 'ambiguous',
    budget: { maxAttempts: 3, consumedAttempts: 0 },
  }
}

describe('AgentEvidenceJournal recordVerification', () => {
  it('records one verification event from the executed stored checks and returns the accepted data', async () => {
    const h = await harness()
    try {
      const { store, digest } = await registeredStore()
      const { directory, consulted } = reviewerDirectory()
      const { flush, flushed } = durableFlush()
      const journal = new AgentEvidenceJournal({ flush, reviewerDirectory: directory, execution: executionWith(['passed']) })
      const current = session()

      const data = await journal.recordVerification({
        session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store,
      })

      const logged = current.snapshotEvents().filter(event => event.type === 'devframe/verification')
      expect(logged).toHaveLength(1)
      expect(data).toBe(logged[0]?.data)
      expect(consulted).toEqual([])
      expect(flushed).toEqual([current])
      expect(data.binding).toEqual(BINDING)
      expect(data.snapshotId).toBe(SNAPSHOT)
      expect(data.status).toBe('passed')
      expect(data.requiredChecks).toEqual({ config: APPROVED_CONFIG, digest })
      expect(data.checks).toEqual([{
        checkId: 'check-evjournal',
        executable: process.execPath,
        arguments: ['-e', 'process.exit(0)'],
        cwd: APPROVED_CONFIG.checks[0]?.cwd,
        status: 'passed',
        exitCode: 0,
        durationMs: 1,
      }])
      expect(decodeDevFramePayload('devframe/verification', data)).toEqual(data)
      // The ledger stays untouched: journal evidence and ledger receipts are
      // orthogonal record tracks.
      expect(h.ctx.agentEvidence.byTask(EvidenceTaskId('task-evjournal')).bindings).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('records honestly end-to-end through the default subprocess execution and the memory store', async () => {
    const h = await harness()
    try {
      const { store, digest } = await registeredStore()
      const { directory } = reviewerDirectory()
      // No execution injected: construction falls back to the reference
      // subprocess face, which really runs the approved command.
      const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory })
      const current = session()

      const data = await journal.recordVerification({
        session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store,
      })

      expect(data.status).toBe('passed')
      expect(data.requiredChecks.digest).toBe(digest)
      expect(data.checks).toEqual([expect.objectContaining({
        checkId: 'check-evjournal',
        executable: process.execPath,
        status: 'passed',
        exitCode: 0,
      })])
      expect(decodeDevFramePayload('devframe/verification', data)).toEqual(data)
    } finally {
      await h.dispose()
    }
  })

  it('folds the recorded evidence into the host projection with the correct Goal attribution', async () => {
    const { store, digest } = await registeredStore()
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()
    current.append('devframe/role-policy', rolePolicy())
    current.append('devframe/goal-binding', goalBinding())
    await journal.recordVerification({ session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store })
    await journal.recordReview({
      session: current, binding: BINDING, reviewerSessionId: REVIEWER,
      policyVersion: POLICY_VERSION, decision: 'pass', findings: [],
    })

    // The same pure definition the native projection registry drives: fold the
    // written log and read the evidence back the way the completion command does.
    const state = devFrameProjectionDefinition.init(current.header, SessionLogOffset(0))
    for (const event of current.snapshotEvents()) devFrameProjectionDefinition.apply(state, event)

    expect(state.failure).toBeNull()
    const verification = state.verifications.find(record => record.binding.goalId === BINDING.goalId)
    expect(verification?.status).toBe('passed')
    expect(verification?.requiredChecks.digest).toBe(digest)
    const review = state.reviews.find(record => record.binding.goalId === BINDING.goalId)
    expect(review?.decision).toBe('pass')
    expect(review?.reviewerSessionId).toBe(REVIEWER)
  })

  it('propagates REQUIRED_CHECKS_CONFIG_NOT_FOUND from an unregistered digest and writes no event', async () => {
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()

    await expect(journal.recordVerification({
      session: current,
      binding: BINDING,
      requiredChecksDigest: RequiredChecksDigest('dsh-required-checks-v1-unregistered'),
      requiredChecksStore: new MemoryRequiredChecksConfigStore(),
    })).rejects.toMatchObject({ name: 'RequiredChecksError', code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND' })

    expect(current.snapshotEvents()).toEqual([])
  })

  it('propagates the store failure REQUIRED_CHECKS_INVALID_CONFIG and writes no event', async () => {
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()
    const brokenStore: RequiredChecksConfigStore = {
      save: async () => RequiredChecksDigest('dsh-required-checks-v1-broken'),
      load: async () => {
        throw new RequiredChecksError('the registered bytes fail their schema', 'REQUIRED_CHECKS_INVALID_CONFIG')
      },
    }

    await expect(journal.recordVerification({
      session: current,
      binding: BINDING,
      requiredChecksDigest: RequiredChecksDigest('dsh-required-checks-v1-broken'),
      requiredChecksStore: brokenStore,
    })).rejects.toMatchObject({ name: 'RequiredChecksError', code: 'REQUIRED_CHECKS_INVALID_CONFIG' })

    expect(current.snapshotEvents()).toEqual([])
  })

  it('records an executed failing check as honest failed evidence that still decodes', async () => {
    const { store, digest } = await registeredStore()
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['failed']) })
    const current = session()

    const data = await journal.recordVerification({
      session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store,
    })

    expect(data.status).toBe('failed')
    expect(data.checks[0]).toMatchObject({ checkId: 'check-evjournal', status: 'failed', exitCode: 1 })
    expect(decodeDevFramePayload('devframe/verification', data)).toEqual(data)
    expect(current.snapshotEvents().filter(event => event.type === 'devframe/verification')).toHaveLength(1)
  })

  it('propagates the persistence failure and latches the journal for the Session', async () => {
    const { store, digest } = await registeredStore()
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({
      flush: async () => {
        throw new Error('backend unavailable')
      },
      reviewerDirectory: directory,
      execution: executionWith(['passed']),
    })
    const current = session()
    const request = { session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store }

    await expect(journal.recordVerification(request)).rejects.toMatchObject({
      name: 'DevFramePersistenceError', code: 'failed',
    })
    await expect(journal.recordVerification(request)).rejects.toMatchObject({
      name: 'DevFramePersistenceError', code: 'blocked',
    })
    expect(current.snapshotEvents().filter(event => event.type === 'devframe/verification')).toHaveLength(1)
  })

  it('appends two verifications in call order with distinct identities', async () => {
    const h = await harness()
    try {
      const { store, digest } = await registeredStore()
      const { directory } = reviewerDirectory()
      const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
      const current = session()

      const first = await journal.recordVerification({ session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store })
      const second = await journal.recordVerification({ session: current, binding: BINDING, requiredChecksDigest: digest, requiredChecksStore: store })

      expect(second.verificationId).not.toBe(first.verificationId)
      const logged = current.snapshotEvents().filter(event => event.type === 'devframe/verification')
      expect(logged.map(event => event.data.verificationId)).toEqual([first.verificationId, second.verificationId])
    } finally {
      await h.dispose()
    }
  })
})

describe('AgentEvidenceJournal recordReview', () => {
  it('records the authorized reviewer decision and consults the wired directory', async () => {
    const h = await harness()
    try {
      const { directory, consulted } = reviewerDirectory()
      const { flush, flushed } = durableFlush()
      const journal = new AgentEvidenceJournal({ flush, reviewerDirectory: directory, execution: executionWith(['passed']) })
      const current = session()

      const data = await journal.recordReview({
        session: current, binding: BINDING, reviewerSessionId: REVIEWER,
        policyVersion: POLICY_VERSION, decision: 'pass', findings: [],
      })

      const logged = current.snapshotEvents().filter(event => event.type === 'devframe/review')
      expect(logged).toHaveLength(1)
      expect(data).toBe(logged[0]?.data)
      expect(consulted).toEqual([REVIEWER])
      expect(flushed).toEqual([current])
      expect(data.reviewerSessionId).toBe(REVIEWER)
      expect(data.decision).toBe('pass')
      expect(data.findings).toEqual([])
      expect(decodeDevFramePayload('devframe/review', data)).toEqual(data)
    } finally {
      await h.dispose()
    }
  })

  it('rejects a review from a Session holding a non-reviewer role with AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED', async () => {
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()

    await expect(journal.recordReview({
      session: current, binding: BINDING, reviewerSessionId: CONTROLLER,
      policyVersion: POLICY_VERSION, decision: 'pass', findings: [],
    })).rejects.toMatchObject({ name: 'AgentEvidenceError', code: 'AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED' })

    expect(current.snapshotEvents()).toEqual([])
  })

  it('rejects a review from an unbound Session identity with AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED', async () => {
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()

    await expect(journal.recordReview({
      session: current, binding: BINDING, reviewerSessionId: SessionId('session-unbound'),
      policyVersion: POLICY_VERSION, decision: 'pass', findings: [],
    })).rejects.toMatchObject({ name: 'AgentEvidenceError', code: 'AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED' })

    expect(current.snapshotEvents()).toEqual([])
  })

  it('rejects a passing review that retains blocking findings and writes no event', async () => {
    const { directory } = reviewerDirectory()
    const journal = new AgentEvidenceJournal({ flush: async () => true, reviewerDirectory: directory, execution: executionWith(['passed']) })
    const current = session()

    await expect(journal.recordReview({
      session: current, binding: BINDING, reviewerSessionId: REVIEWER, policyVersion: POLICY_VERSION,
      decision: 'pass',
      findings: [{ id: 'finding-1', severity: 'blocking', message: 'the regression is uncovered' }],
    })).rejects.toThrow(/devframe\/review payload is invalid/)

    expect(current.snapshotEvents()).toEqual([])
  })
})
