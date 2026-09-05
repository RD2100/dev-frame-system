/**
 * S6 stop-path settlement contrast: two real projects travel the real
 * dispatcher; A additionally carries a queued crash-residue row seeded through
 * the real domain before the harness boots (a send whose acceptance never
 * landed). Stopping A cancels that residue visibly while A's accepted input
 * survives untouched, the stop replays and no-ops correctly, B stays fully
 * live, and per the 2026-09-06 ruling the settlement seam rejects a closed
 * receiver: `completeDelivery` on a `stopping` or `stopped` project fails
 * with `SHADOW_RECEIVER_CLOSED` and leaves the row `received`.
 * @module tests/s6-stop-settlement
 */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, realpath } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import type { ShadowBindingRecord, ShadowDeliveryRecord } from '../src/index.ts'
import { dispatch, failureCode, failureText, harness, seedHarness, seedWorkspaceFact } from './helpers.ts'

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

/** Read one number field off a rendered JSON object value. */
function numberOf(value: JsonValue, label: string): number {
  if (typeof value !== 'number') throw new Error(`${label} is not a number`)
  return value
}

describe('shadow-router S6 stop-path settlement contrast', () => {
  it('S6: stopping project A cancels only its queued residue, preserves its accepted input, replays and no-ops safely, and leaves live project B untouched', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-stop-'))
    const dirA = join(root, 's6-stop-project-a')
    const dirB = join(root, 's6-stop-project-b')
    await mkdir(dirA)
    await mkdir(dirB)
    const canonicalA = await realpath(dirA)

    // Crash residue for A, written through the real domain BEFORE the router
    // process exists (the delivery-limits seed pattern): a ready binding whose
    // goal is not yet authorized, plus one queued intent whose acceptance
    // never landed.
    const seed = await seedHarness(root)
    try {
      const now = new Date().toISOString()
      await seedWorkspaceFact(seed.workspaceDomain, 'ws-s6-stop-a', canonicalA)
      const binding: ShadowBindingRecord = {
        workspaceId: WorkspaceId('ws-s6-stop-a'),
        canonicalPath: canonicalA,
        controllerSessionId: SessionId('session-ctrl-s6-stop-a'),
        profileKey: 'devframe',
        bindingRevision: 1,
        requestId: 'seed-open-s6-stop-a',
        state: 'ready',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('bindings').put(binding.workspaceId, binding)
      const queued: ShadowDeliveryRecord = {
        messageId: ShadowMessageId('msg-s6-stop-queued-1'),
        requestId: ShadowRequestId('s6-stop-queued-1'),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId('ws-s6-stop-a'),
        bindingRevision: 1,
        goalId: 's6-stop-goal-a',
        acceptanceHash: AcceptanceHash('s6-stop-hash-a'),
        mode: 'work',
        text: 'S6 stop crash residue: a send whose acceptance never landed',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('deliveries').put(queued.messageId, queued)
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] })
    try {
      // A opens through the real dispatcher: the crash-residue binding converges.
      const openedAOutcome = await dispatch(h.ctx, h.shadow, 'project_open', { path: dirA, request_id: 's6-stop-open-a' })
      expect(openedAOutcome.isError, '[1] project_open for A succeeds through the real dispatcher').toBe(false)
      const openedA = successValue(openedAOutcome, 'project_open')
      const workspaceAText = textOf(fieldValue(openedA, 'workspaceId'), 'A workspaceId')
      const workspaceAId = WorkspaceId(workspaceAText)
      expect(textOf(fieldValue(openedA, 'state'), 'A state'), '[2] A is ready after the converged open').toBe('ready')
      expect(h.router.listDeliveries(workspaceAId), '[3] the queued crash residue is visible on A after cold restore').toHaveLength(1)

      // B opens through the real dispatcher: fresh provisioning.
      const openedBOutcome = await dispatch(h.ctx, h.shadow, 'project_open', { path: dirB, request_id: 's6-stop-open-b' })
      expect(openedBOutcome.isError, '[4] project_open for B succeeds through the real dispatcher').toBe(false)
      const openedB = successValue(openedBOutcome, 'project_open')
      const workspaceBText = textOf(fieldValue(openedB, 'workspaceId'), 'B workspaceId')
      const workspaceBId = WorkspaceId(workspaceBText)
      expect(textOf(fieldValue(openedB, 'state'), 'B state'), '[5] B is ready after the fresh open').toBe('ready')
      expect(workspaceBText, '[6] A and B resolve to distinct workspace identities').not.toBe(workspaceAText)

      // Both open runs are authorized by the host.
      await h.router.setActiveGoal(workspaceAId, 's6-stop-goal-a', 's6-stop-hash-a')
      await h.router.setActiveGoal(workspaceBId, 's6-stop-goal-b', 's6-stop-hash-b')

      // One accepted delivery each, through the real dispatcher.
      const revisionA = h.router.findBinding(workspaceAId)!.bindingRevision
      const sentAOutcome = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: workspaceAText,
        binding_revision: revisionA,
        goal_id: 's6-stop-goal-a',
        acceptance_hash: 's6-stop-hash-a',
        request_id: 's6-stop-send-a',
        mode: 'work',
        text: 'accepted input in A before the stop',
      })
      expect(sentAOutcome.isError, '[7] project_send to A succeeds').toBe(false)
      const sentA = successValue(sentAOutcome, 'project_send')
      const messageIdAText = textOf(fieldValue(sentA, 'messageId'), 'A messageId')
      expect(textOf(fieldValue(sentA, 'status'), 'A send status'), '[8] A\'s delivery receipt is received').toBe('received')
      const revisionB = h.router.findBinding(workspaceBId)!.bindingRevision
      const sentBOutcome = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: workspaceBText,
        binding_revision: revisionB,
        goal_id: 's6-stop-goal-b',
        acceptance_hash: 's6-stop-hash-b',
        request_id: 's6-stop-send-b',
        mode: 'work',
        text: 'accepted input in B',
      })
      expect(sentBOutcome.isError, '[9] project_send to B succeeds').toBe(false)
      const sentB = successValue(sentBOutcome, 'project_send')
      const messageIdBText = textOf(fieldValue(sentB, 'messageId'), 'B messageId')

      // Stop A through the real dispatcher.
      const stopOutcome = await dispatch(h.ctx, h.shadow, 'project_stop', {
        workspace_id: workspaceAText,
        expected_revision: revisionA,
        request_id: 's6-stop-a-1',
      })
      expect(stopOutcome.isError, '[10] project_stop for A succeeds').toBe(false)
      const stoppedA = successValue(stopOutcome, 'project_stop')
      expect(textOf(fieldValue(stoppedA, 'status'), 'A stop status'), '[11] the stop receipt reports stopping').toBe('stopping')
      expect(numberOf(fieldValue(stoppedA, 'cancelledDeliveries'), 'cancelledDeliveries'), '[12] the stop cancelled exactly the one queued residue').toBe(1)
      expect(numberOf(fieldValue(stoppedA, 'bindingRevision'), 'A stop bindingRevision'), '[13] the stop bumped A\'s binding revision').toBe(revisionA + 1)

      // The queued residue is cancelled with a visible project-stopped reason...
      const rowsAfterStop = h.router.listDeliveries(workspaceAId)
      const cancelledRow = rowsAfterStop.find(row => row.messageId === 'msg-s6-stop-queued-1')
      expect(cancelledRow?.state, '[14] the queued residue converged to cancelled').toBe('cancelled')
      expect(cancelledRow?.cancelReason, '[15] the cancellation carries the project-stopped reason').toBe('project-stopped')
      // ...while A's accepted input survives the stop untouched.
      const receivedRow = rowsAfterStop.find(row => row.messageId === messageIdAText)
      expect(receivedRow?.state, '[16] A\'s accepted delivery is still received after the stop').toBe('received')
      expect(receivedRow?.completedAt, '[17] the preserved row was not completed or dropped by the stop').toBeUndefined()

      // Replay discipline: repeating the same stop request id replays the same receipt.
      const stopReplayOutcome = await dispatch(h.ctx, h.shadow, 'project_stop', {
        workspace_id: workspaceAText,
        expected_revision: revisionA,
        request_id: 's6-stop-a-1',
      })
      expect(stopReplayOutcome.isError, '[18] the replayed stop dispatch succeeds').toBe(false)
      const stopReplay = successValue(stopReplayOutcome, 'project_stop replay')
      expect(stopReplay, '[19] the replayed stop returns the exact stored receipt').toEqual(stoppedA)
      // A second stop with a NEW request id is a no-op receipt.
      const stopAgainOutcome = await dispatch(h.ctx, h.shadow, 'project_stop', {
        workspace_id: workspaceAText,
        expected_revision: numberOf(fieldValue(stoppedA, 'bindingRevision'), 'A current revision'),
        request_id: 's6-stop-a-2',
      })
      expect(stopAgainOutcome.isError, '[20] the second stop with a new request id succeeds').toBe(false)
      const stopAgain = successValue(stopAgainOutcome, 'project_stop again')
      expect(textOf(fieldValue(stopAgain, 'status'), 'second stop status'), '[21] the second stop is a no-op stopping receipt').toBe('stopping')
      expect(numberOf(fieldValue(stopAgain, 'cancelledDeliveries'), 'second stop cancelledDeliveries'), '[22] the second stop cancels nothing').toBe(0)

      // The host confirms quiescence; A is stopped.
      await h.router.confirmProjectStopped(workspaceAId)
      expect(h.router.findBinding(workspaceAId)?.state, '[23] A\'s binding is stopped after the host confirmation').toBe('stopped')

      // Per the 2026-09-06 ruling (supersedes the earlier OBSERVED probe):
      // a closed receiver cannot settle. The settlement of A's accepted input
      // on the stopped project rejects with the structured code and the row
      // stays exactly as the stop left it — no write, no history rewrite.
      await expect(h.router.completeDelivery(workspaceAId, ShadowMessageId(messageIdAText)),
        '[24] the settlement of A\'s accepted input on the stopped project rejects',
      ).rejects.toMatchObject({ code: 'SHADOW_RECEIVER_CLOSED' })
      const preservedRow = h.router.listDeliveries(workspaceAId).find(row => row.messageId === messageIdAText)
      expect(preservedRow?.state, '[25] the rejected settlement left the row received').toBe('received')
      expect(preservedRow?.completedAt, '[26] the rejected settlement wrote no completedAt').toBeUndefined()

      // B isolation: binding ready, controller session live, queue untouched.
      expect(h.router.findBinding(workspaceBId)?.state, '[27] B\'s binding is still ready').toBe('ready')
      const controllerBId = textOf(fieldValue(openedB, 'controllerSessionId'), 'B controllerSessionId')
      const controllerB = h.ctx.sessions.get(SessionId(controllerBId))
      expect(controllerB, '[28] B\'s controller session is still live').toBeDefined()
      expect(controllerB!.header.cwd, '[29] B\'s controller session still roots at its canonical path').toBe(textOf(fieldValue(openedB, 'canonicalPath'), 'B canonicalPath'))
      expect(h.router.listDeliveries(workspaceBId).map(row => row.messageId), '[30] B still holds exactly its one accepted delivery').toEqual([messageIdBText])
      const sentB2Outcome = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: workspaceBText,
        binding_revision: revisionB,
        goal_id: 's6-stop-goal-b',
        acceptance_hash: 's6-stop-hash-b',
        request_id: 's6-stop-send-b-2',
        mode: 'note',
        text: 'B keeps receiving after A stopped',
      })
      expect(sentB2Outcome.isError, '[31] a NEW project_send to B still succeeds').toBe(false)
      const sentB2 = successValue(sentB2Outcome, 'project_send to B after the stop')
      expect(textOf(fieldValue(sentB2, 'status'), 'B second send status'), '[32] B\'s new delivery is received').toBe('received')
      expect(h.router.listDeliveries(workspaceBId), '[33] B\'s queue grew to two accepted rows').toHaveLength(2)
      expect(failureCode(sentB2Outcome), '[34] sanity: the successful send carried no failure code').toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('S6: the intermediate stopping state also rejects completeDelivery and leaves the row received', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-stopping-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('s6-stopping-project')
      const openedOutcome = await dispatch(h.ctx, h.shadow, 'project_open', { path: dir, request_id: 's6-stopping-open' })
      expect(openedOutcome.isError, '[1] project_open succeeds through the real dispatcher').toBe(false)
      const opened = successValue(openedOutcome, 'project_open')
      const workspaceText = textOf(fieldValue(opened, 'workspaceId'), 'workspaceId')
      const workspaceId = WorkspaceId(workspaceText)
      await h.router.setActiveGoal(workspaceId, 's6-stopping-goal', 's6-stopping-hash')
      const revision = h.router.findBinding(workspaceId)!.bindingRevision
      const sentOutcome = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: workspaceText,
        binding_revision: revision,
        goal_id: 's6-stopping-goal',
        acceptance_hash: 's6-stopping-hash',
        request_id: 's6-stopping-send',
        mode: 'work',
        text: 'accepted input before the stop',
      })
      expect(sentOutcome.isError, '[2] project_send succeeds and the delivery is received').toBe(false)
      const sent = successValue(sentOutcome, 'project_send')
      const messageIdText = textOf(fieldValue(sent, 'messageId'), 'messageId')
      const stopOutcome = await dispatch(h.ctx, h.shadow, 'project_stop', {
        workspace_id: workspaceText,
        expected_revision: revision,
        request_id: 's6-stopping-stop',
      })
      expect(stopOutcome.isError, '[3] project_stop succeeds').toBe(false)
      expect(h.router.findBinding(workspaceId)?.state, '[4] the binding is stopping before the host confirmation').toBe('stopping')
      // Per the 2026-09-06 ruling the closed-receiver guard covers the whole
      // stop window: the intermediate `stopping` state rejects settlement too.
      await expect(h.router.completeDelivery(workspaceId, ShadowMessageId(messageIdText)),
        '[5] the settlement on the stopping project rejects',
      ).rejects.toMatchObject({ code: 'SHADOW_RECEIVER_CLOSED' })
      const row = h.router.listDeliveries(workspaceId).find(candidate => candidate.messageId === messageIdText)
      expect(row?.state, '[6] the rejected settlement left the row received').toBe('received')
      expect(row?.completedAt, '[7] the rejected settlement wrote no completedAt').toBeUndefined()
    } finally {
      await h.dispose()
    }
  })
})
