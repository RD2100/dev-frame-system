/**
 * S6 real delivery journey: one project travels the full cross-root delivery
 * path through the package's real machinery — real JSON storage on disk, the
 * real tool dispatcher, and a controller session created by `project_open` —
 * from the model-facing open through host goal authorization, a dispatched
 * send, the host settlement, and a read-back through the model face.
 * @module tests/s6-delivery-flow
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { ShadowMessageId } from '../src/index.ts'
import { dispatch, failureText, harness, resultText } from './helpers.ts'

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

describe('shadow-router S6 real delivery journey', () => {
  it('S6: open → authorize → send → settle → status runs end to end through the real dispatcher, real storage, and a real controller session', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-flow-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('s6-flow-project')

      // Step 1 — open through the real dispatcher; the rendered JSON carries
      // the ready association.
      const openedOutcome = await dispatch(h.ctx, h.shadow, 'project_open', {
        path: dir,
        request_id: 's6-flow-open-1',
      })
      expect(openedOutcome.isError, '[1] project_open dispatch succeeds').toBe(false)
      const opened = successValue(openedOutcome, 'project_open')
      expect(resultText(openedOutcome), '[2] the rendered model face is the same JSON object the dispatcher returned').toBe(JSON.stringify(opened))
      expect(textOf(fieldValue(opened, 'state'), 'state'), '[3] the open receipt carries state ready').toBe('ready')
      const workspaceIdText = textOf(fieldValue(opened, 'workspaceId'), 'workspaceId')
      expect(workspaceIdText.length, '[4] the open receipt carries a workspace id').toBeGreaterThan(0)
      const controllerIdText = textOf(fieldValue(opened, 'controllerSessionId'), 'controllerSessionId')
      expect(controllerIdText.length, '[5] the open receipt carries a controller session id').toBeGreaterThan(0)
      const bindingRevision = numberOf(fieldValue(opened, 'bindingRevision'), 'bindingRevision')
      expect(bindingRevision, '[6] the open receipt carries a binding revision').toBeGreaterThanOrEqual(1)
      const workspaceId = WorkspaceId(workspaceIdText)

      // Step 2 — the controller session is real: live in the session store,
      // rooted at the canonical path, unparented, and durably a controller.
      const canonicalPath = textOf(fieldValue(opened, 'canonicalPath'), 'canonicalPath')
      const controller = h.ctx.sessions.get(SessionId(controllerIdText))
      expect(controller, '[7] the controller session exists in the real session store').toBeDefined()
      expect(controller!.header.cwd, '[8] the controller session cwd is the canonical project path').toBe(canonicalPath)
      expect(controller!.header.parentSession, '[9] the controller session has no parent session').toBeUndefined()
      expect(h.ctx.agentBindings.find(SessionId(controllerIdText))?.role, '[10] the controller session is durably bound with role controller').toBe('controller')

      // Step 3 — the host authorizes the one open run.
      const goalId = 's6-flow-goal-1'
      const acceptanceHash = 's6-flow-hash-1'
      await h.router.setActiveGoal(workspaceId, goalId, acceptanceHash)
      const authorized = h.router.findBinding(workspaceId)
      expect(authorized?.activeGoalId, '[11] the host authorization recorded the open run\'s Goal').toBe(goalId)
      expect(authorized?.activeAcceptanceHash, '[12] the host authorization recorded the acceptance association').toBe(acceptanceHash)

      // Step 4 — send through the real dispatcher at the current revision.
      const currentRevision = h.router.findBinding(workspaceId)!.bindingRevision
      const sentOutcome = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: workspaceIdText,
        binding_revision: currentRevision,
        goal_id: goalId,
        acceptance_hash: acceptanceHash,
        request_id: 's6-flow-send-1',
        mode: 'work',
        text: 'S6 real delivery journey message',
      })
      expect(sentOutcome.isError, '[13] project_send dispatch succeeds').toBe(false)
      const sent = successValue(sentOutcome, 'project_send')
      expect(textOf(fieldValue(sent, 'status'), 'send status'), '[14] the send receipt status is received').toBe('received')
      const messageIdText = textOf(fieldValue(sent, 'messageId'), 'messageId')
      expect(messageIdText.length, '[15] the send receipt carries a message id').toBeGreaterThan(0)
      const messageId = ShadowMessageId(messageIdText)
      const deliveries = h.router.listDeliveries(workspaceId)
      expect(deliveries, '[16] exactly one delivery row exists after the send').toHaveLength(1)
      expect(deliveries[0]!.state, '[17] the delivery row state is received').toBe('received')
      expect(deliveries[0]!.receivedAt, '[18] the received row carries receivedAt').toBeDefined()
      expect(deliveries[0]!.completedAt, '[19] the received row carries no completedAt yet').toBeUndefined()
      const receivedAtBeforeSettle = deliveries[0]!.receivedAt!

      // Step 5 — the host settles the accepted input as completed; the
      // two-write history survives settlement.
      const settled = await h.router.completeDelivery(workspaceId, messageId)
      expect(settled.state, '[20] the settled record state is completed').toBe('completed')
      expect(settled.completedAt, '[21] the settled record carries completedAt').toBeDefined()
      expect(settled.receivedAt, '[22] settlement preserved the original receivedAt').toBe(receivedAtBeforeSettle)
      const afterSettle = h.router.listDeliveries(workspaceId)
      expect(afterSettle[0]!.state, '[23] the durable row reads completed after settlement').toBe('completed')
      expect(afterSettle[0]!.receivedAt, '[24] the durable row kept receivedAt through settlement').toBe(receivedAtBeforeSettle)

      // Step 6 — read back through the model face.
      const statusOutcome = await dispatch(h.ctx, h.shadow, 'project_status', { workspace_id: workspaceIdText })
      expect(statusOutcome.isError, '[25] project_status dispatch succeeds').toBe(false)
      const status = successValue(statusOutcome, 'project_status')
      const projects = fieldValue(status, 'projects')
      if (!Array.isArray(projects)) throw new Error('projects is not an array')
      expect(projects, '[26] the status page lists exactly one project').toHaveLength(1)
      const entry = projects[0]!
      expect(textOf(fieldValue(entry, 'workspaceId'), 'status workspaceId'), '[27] the rendered entry is the opened workspace').toBe(workspaceIdText)
      expect(textOf(fieldValue(entry, 'state'), 'project state'), '[28] the rendered project state is ready').toBe('ready')
      const statusDeliveries = fieldValue(entry, 'deliveries')
      if (!Array.isArray(statusDeliveries)) throw new Error('deliveries is not an array')
      expect(statusDeliveries, '[29] the rendered entry lists exactly one delivery').toHaveLength(1)
      expect(textOf(fieldValue(statusDeliveries[0]!, 'messageId'), 'status messageId'), '[30] the rendered delivery is the settled message').toBe(messageIdText)
      expect(textOf(fieldValue(statusDeliveries[0]!, 'state'), 'delivery state'), '[31] the rendered delivery state is completed').toBe('completed')
      expect(fieldValue(statusDeliveries[0]!, 'completedAt'), '[32] the rendered delivery carries completedAt').toBeDefined()
    } finally {
      await h.dispose()
    }
  })
})
