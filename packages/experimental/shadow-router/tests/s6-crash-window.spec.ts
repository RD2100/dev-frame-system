/**
 * S6 crash-window adjudication: generation 1 opens a real project through the
 * real dispatcher, authorizes a goal, and persists one accepted delivery; the
 * context dies (root kept) and one queued intent whose acceptance never
 * landed is seeded through the real domain with a stable known request id.
 * Generation 2 converges the residue through the host recovery seam, then
 * adjudicates replay and conflict through the real dispatcher without
 * duplicating rows or rewriting acceptance instants.
 * @module tests/s6-crash-window
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import type { ShadowDeliveryRecord } from '../src/index.ts'
import { dispatch, failureCode, failureText, harness, resultText, seedHarness } from './helpers.ts'

/** One settled dispatch outcome: the real tool runtime's discriminated result. */
type DispatchOutcome = Awaited<ReturnType<typeof dispatch>>

/** Unwrap one successful dispatch's canonical value, or fail with the failure text. */
function successValue(outcome: DispatchOutcome, label: string): JsonValue {
  if (outcome.isError) throw new Error(`${label} failed: ${failureText(outcome)}`)
  return outcome.value
}

/** Read one key off a rendered JSON object value. */
function fieldValue(record: JsonValue, key: string): JsonValue {
  if (typeof record !== 'object' || record === null || Array.isArray(record)) {
    throw new Error(`expected a JSON object while reading "${key}"`)
  }
  const value = record[key]
  if (value === undefined) throw new Error(`the rendered value carries no "${key}"`)
  return value
}

/** Read one string field off a rendered JSON object value. */
function textOf(value: JsonValue, label: string): string {
  if (typeof value !== 'string') throw new Error(`${label} is not a string`)
  return value
}

describe('shadow-router S6 crash-window adjudication', () => {
  it('S6: recovery converges the interrupted queued intent and the real dispatcher adjudicates replay and conflict without duplicating rows', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-crash-'))

    // Generation 1: open through the real dispatcher, authorize the run, and
    // persist one accepted delivery. Then the process dies; the root stays.
    const h1 = await harness(root, { authorizedRoots: [root] })
    const gen1 = await (async () => {
      try {
        const dir = await h1.makeProjectDir('s6-crash-project')
        const openedOutcome = await dispatch(h1.ctx, h1.shadow, 'project_open', { path: dir, request_id: 's6-crash-open-1' })
        expect(openedOutcome.isError, '[1] generation 1 project_open succeeds through the real dispatcher').toBe(false)
        const opened = successValue(openedOutcome, 'project_open')
        expect(textOf(fieldValue(opened, 'state'), 'open state'), '[2] generation 1 opens the project ready').toBe('ready')
        const workspaceIdText = textOf(fieldValue(opened, 'workspaceId'), 'workspaceId')
        const workspaceId = WorkspaceId(workspaceIdText)
        const canonicalPath = textOf(fieldValue(opened, 'canonicalPath'), 'canonicalPath')
        const controllerSessionIdText = textOf(fieldValue(opened, 'controllerSessionId'), 'controllerSessionId')
        await h1.router.setActiveGoal(workspaceId, 's6-crash-goal-1', 's6-crash-hash-1')
        const revision = h1.router.findBinding(workspaceId)!.bindingRevision
        const sentOutcome = await dispatch(h1.ctx, h1.shadow, 'project_send', {
          workspace_id: workspaceIdText,
          binding_revision: revision,
          goal_id: 's6-crash-goal-1',
          acceptance_hash: 's6-crash-hash-1',
          request_id: 's6-crash-send-1',
          mode: 'work',
          text: 'generation 1 accepted delivery',
        })
        expect(sentOutcome.isError, '[3] generation 1 project_send succeeds through the real dispatcher').toBe(false)
        const sent = successValue(sentOutcome, 'project_send')
        const messageId1Text = textOf(fieldValue(sent, 'messageId'), 'messageId')
        expect(textOf(fieldValue(sent, 'status'), 'send status'), '[4] generation 1\'s delivery is received').toBe('received')
        expect(h1.router.listDeliveries(workspaceId), '[5] generation 1 ends with exactly its one accepted row').toHaveLength(1)
        return { workspaceIdText, workspaceId, canonicalPath, controllerSessionIdText, messageId1Text, revision }
      } finally {
        await h1.close()
      }
    })()

    // Crash-window residue: one queued intent whose acceptance never landed,
    // written through the real domain while no router process holds the root.
    const seed = await seedHarness(root)
    try {
      const now = new Date().toISOString()
      const queued: ShadowDeliveryRecord = {
        messageId: ShadowMessageId('msg-s6-crash-queued-1'),
        requestId: ShadowRequestId('s6-crash-queued-1'),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId(gen1.workspaceIdText),
        bindingRevision: gen1.revision,
        goalId: 's6-crash-goal-1',
        acceptanceHash: AcceptanceHash('s6-crash-hash-1'),
        mode: 'work',
        text: 'S6 crash window: a send whose acceptance never landed',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('deliveries').put(queued.messageId, queued)
    } finally {
      await seed.dispose()
    }

    // Generation 2: a fresh harness cold-restores the same root.
    const h2 = await harness(root, { authorizedRoots: [root] })
    try {
      // The binding restored row-for-row; the host re-creates the reserved
      // controller session on the SAME id (sessions are process-local).
      const binding = h2.router.findBinding(gen1.workspaceId)
      expect(binding?.state, '[6] the binding restored ready').toBe('ready')
      expect(binding?.controllerSessionId, '[7] the restored binding keeps generation 1\'s reserved controller id').toBe(gen1.controllerSessionIdText)
      h2.ctx.sessions.create(SessionId(binding!.controllerSessionId), { meta: { cwd: binding!.canonicalPath } })
      const queuedRow = h2.router.listDeliveries(gen1.workspaceId).find(row => row.messageId === 'msg-s6-crash-queued-1')
      expect(queuedRow?.state, '[8] the seeded intent is queued after cold restore').toBe('queued')
      expect(queuedRow?.receivedAt, '[9] the queued residue carries no receivedAt yet').toBeUndefined()

      // Recovery: the host seam converges the residue to received.
      const recovered = await h2.router.recoverDeliveries(gen1.workspaceId)
      expect(recovered.map(row => row.messageId), '[10] recovery converged exactly the one queued residue').toEqual(['msg-s6-crash-queued-1'])
      expect(recovered[0]!.state, '[11] the recovered row state is received').toBe('received')
      expect(recovered[0]!.receivedAt, '[12] the recovered row carries receivedAt').toBeDefined()
      const afterRecovery = h2.router.listDeliveries(gen1.workspaceId)
      expect(afterRecovery.filter(row => row.messageId === 'msg-s6-crash-queued-1'), '[13] exactly one row exists for the recovered message id').toHaveLength(1)
      expect(afterRecovery, '[14] the workspace holds exactly two rows after recovery').toHaveLength(2)
      const postRecoveryReceivedAt = afterRecovery.find(row => row.messageId === 'msg-s6-crash-queued-1')!.receivedAt!

      // Replay adjudication through the REAL dispatcher: the same request id
      // with identical input replays the receipt instead of re-delivering.
      const replayOutcome = await dispatch(h2.ctx, h2.shadow, 'project_send', {
        workspace_id: gen1.workspaceIdText,
        binding_revision: binding!.bindingRevision,
        goal_id: 's6-crash-goal-1',
        acceptance_hash: 's6-crash-hash-1',
        request_id: 's6-crash-queued-1',
        mode: 'work',
        text: 'S6 crash window: a send whose acceptance never landed',
      })
      expect(replayOutcome.isError, '[15] the replayed send dispatch succeeds').toBe(false)
      const replay = successValue(replayOutcome, 'project_send replay')
      expect(textOf(fieldValue(replay, 'messageId'), 'replay messageId'), '[16] the replay returns the same message id').toBe('msg-s6-crash-queued-1')
      expect(textOf(fieldValue(replay, 'status'), 'replay status'), '[17] the replay receipt is received').toBe('received')
      expect(h2.router.listDeliveries(gen1.workspaceId), '[18] the replay added no delivery row').toHaveLength(2)
      const afterReplay = h2.router.listDeliveries(gen1.workspaceId).find(row => row.messageId === 'msg-s6-crash-queued-1')!
      expect(afterReplay.receivedAt, '[19] the replay did not rewrite the recovery\'s receivedAt').toBe(postRecoveryReceivedAt)

      // Conflict adjudication: the same request id with DIFFERENT text.
      const conflictOutcome = await dispatch(h2.ctx, h2.shadow, 'project_send', {
        workspace_id: gen1.workspaceIdText,
        binding_revision: binding!.bindingRevision,
        goal_id: 's6-crash-goal-1',
        acceptance_hash: 's6-crash-hash-1',
        request_id: 's6-crash-queued-1',
        mode: 'work',
        text: 'a DIFFERENT text sent under the same request id',
      })
      expect(conflictOutcome.isError, '[20] the conflicting send dispatch fails loud').toBe(true)
      expect(failureCode(conflictOutcome), '[21] the conflict carries SHADOW_REQUEST_CONFLICT').toBe('SHADOW_REQUEST_CONFLICT')
      expect(failureText(conflictOutcome), '[22] the conflict names the reused request id').toContain('s6-crash-queued-1')
      expect(h2.router.listDeliveries(gen1.workspaceId), '[23] the conflict added no delivery row').toHaveLength(2)

      // Generation 1's accepted delivery survived the crash window intact, and
      // a same-requestId replay of it returns the same receipt without a row.
      const gen1Row = h2.router.listDeliveries(gen1.workspaceId).find(row => row.messageId === gen1.messageId1Text)!
      expect(gen1Row.state, '[24] generation 1\'s delivery row survived with state received').toBe('received')
      const gen1ReceivedAt = gen1Row.receivedAt!
      const gen1ReplayOutcome = await dispatch(h2.ctx, h2.shadow, 'project_send', {
        workspace_id: gen1.workspaceIdText,
        binding_revision: binding!.bindingRevision,
        goal_id: 's6-crash-goal-1',
        acceptance_hash: 's6-crash-hash-1',
        request_id: 's6-crash-send-1',
        mode: 'work',
        text: 'generation 1 accepted delivery',
      })
      expect(gen1ReplayOutcome.isError, '[25] the replayed generation 1 send succeeds').toBe(false)
      const gen1Replay = successValue(gen1ReplayOutcome, 'project_send generation 1 replay')
      expect(textOf(fieldValue(gen1Replay, 'messageId'), 'generation 1 replay messageId'), '[26] the generation 1 replay returns the same message id').toBe(gen1.messageId1Text)
      expect(resultText(gen1ReplayOutcome), '[27] the generation 1 replay receipt is the rendered received JSON').toBe(JSON.stringify(gen1Replay))
      expect(h2.router.listDeliveries(gen1.workspaceId), '[28] the generation 1 replay added no delivery row').toHaveLength(2)
      expect(h2.router.listDeliveries(gen1.workspaceId).find(row => row.messageId === gen1.messageId1Text)!.receivedAt, '[29] the generation 1 replay did not rewrite its receivedAt').toBe(gen1ReceivedAt)
    } finally {
      await h2.dispose()
    }
  })
})
