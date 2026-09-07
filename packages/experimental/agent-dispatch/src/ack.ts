/**
 * Durable acknowledgment for one dispatched child's task briefing.
 *
 * The dispatch entry answers the parent's standing question — has my
 * dispatched task's terminal state reached durable storage, and how did the
 * turn that consumed my briefing end? — by DERIVING the answer from the
 * child's own session log instead of keeping a parallel ledger. Every fact
 * the derivation reads is already a durable session event (the briefing's
 * `agent/inbox/spliced` delivery, the claiming splice, the consuming turn's
 * `turn/end`), so the ack survives process restarts and the engine's
 * recovery lane by construction: after a recovery republishes the session,
 * the same derivation runs over the reloaded log and reports exactly what
 * the log proves, never more.
 *
 * Durability itself is not inferred from the log: the caller drives the
 * session store's flush barrier (`ctx.sessions.flush`) and only a
 * participating durability listener lets an ack carry `durable: true`.
 *
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/ack
 */

import type { MessageId } from '@deepseek-ai/dsh-llm'
import type { SessionEvent, SessionEventMap, TurnEndReason } from '@deepseek-ai/dsh-session'

/** What the child's log proves about one dispatched task's briefing. */
export type DispatchAckState =
  /** The delivery splice is in the log; no turn has claimed the briefing yet. */
  | 'briefed'
  /** A turn claimed the briefing and is still open — execution in progress. */
  | 'claimed'
  /** The claiming turn closed; `turnEnd` carries its recorded ending. */
  | 'terminal'
  /** A cancellation removed the briefing before any turn could run it. */
  | 'dropped'
  /** The log records no delivery of this task's briefing (a cold recovery republished an empty session). */
  | 'unbriefed'
  /** Service-level: the child is not live in this process; the recovery lane owns the log. */
  | 'unavailable'

/** One derived briefing account from a child log. */
export interface BriefingAckFold {
  /** The account state the log proves. */
  readonly state: DispatchAckState
  /** The claiming turn's recorded ending, when the state is `terminal`. */
  readonly turnEnd?: {
    readonly turn: number
    readonly seq: number
    readonly reason: TurnEndReason
  }
}

/**
 * The durable acknowledgment one parent task's dispatched child exposes:
 * the derived log account plus the flush barrier's verdict.
 */
export interface DispatchTaskAck {
  /** The account state the child's log proves. */
  readonly state: DispatchAckState
  /** The deterministic briefing identity the dispatch entry delivered. */
  readonly briefingMessageId: MessageId
  /** The claiming turn's recorded ending, when the state is `terminal`. */
  readonly turnEnd?: {
    readonly turn: number
    readonly seq: number
    readonly reason: TurnEndReason
  }
  /** Whether the terminal ending is `completed` — the task finished cleanly. */
  readonly completed?: boolean
  /**
   * Whether a durability listener participated in the flush barrier over the
   * facts this ack reports. `false` means no durability backend answered —
   * the log facts stand, but durable storage cannot be claimed.
   */
  readonly durable: boolean
  /**
   * Set when the flush barrier itself refused or failed: the durability
   * backend is broken, and durable storage cannot be claimed even though a
   * backend is deployed.
   */
  readonly degraded?: true
}

/**
 * Fold one child log into the account for one briefing identity, mirroring
 * the engine's own work accounting: the claiming splice is the one that
 * removes the briefing's identity without a cancellation outcome, the
 * claiming turn is the turn open at that splice, and the account turns
 * terminal exactly when that turn's `turn/end` closes the log.
 * @param events - the child's session events, in log order.
 * @param briefingId - the string identity of the briefing to account for.
 * @returns the account the log proves.
 */
export function foldBriefingAck(events: readonly SessionEvent[], briefingId: string): BriefingAckFold {
  const pending: Record<SessionEventMap['agent/inbox/spliced']['target'], string[]> = {
    'next-turn': [],
    'next-step': [],
  }
  let openTurn: number | undefined
  let claimedTurn: number | undefined
  let delivered = false
  let dropped = false
  let end: SessionEvent<'turn/end'> | undefined
  for (const event of events) {
    switch (event.type) {
      case 'turn/start':
        openTurn = event.data.turn
        break
      case 'agent/inbox/spliced': {
        const { target, start, removedCount, inserted, outcome } = event.data
        const list = pending[target]
        const removed = list.splice(start, removedCount ?? 0, ...inserted.map(message => String(message.id)))
        if (inserted.some(message => String(message.id) === briefingId)) delivered = true
        if (end === undefined && !dropped && removed.includes(briefingId)) {
          if (outcome === 'canceled') dropped = true
          else claimedTurn = openTurn
        }
        break
      }
      case 'turn/end':
        if (claimedTurn !== undefined && event.data.turn === claimedTurn) end = event
        openTurn = undefined
        break
      default:
        break
    }
  }
  if (end !== undefined) {
    return {
      state: 'terminal',
      turnEnd: { turn: end.data.turn, seq: end.seq, reason: end.data.reason },
    }
  }
  if (dropped) return { state: 'dropped' }
  if (claimedTurn !== undefined) return { state: 'claimed' }
  if (delivered) return { state: 'briefed' }
  return { state: 'unbriefed' }
}
