/**
 * The dispatch seam's parent wake: when a dispatched child finishes a turn,
 * the parent learns about it on its own inbox. The agent-hierarchy engine
 * owns the child's lifecycle but ships no parent notification, so a parent
 * that delegated work had no external event to react to — the gap this
 * module closes with an explicit, durable notice of the child's settlement.
 *
 * The notice is deliberately a runtime account, not child-authored content:
 * it uses its own {@link DispatchSettledMessageSource} so a transcript can
 * never credit the child with words the dispatch service wrote.
 *
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/child-settlement
 */

import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { Session, SessionId } from '@deepseek-ai/dsh-session'
import type { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { createUserMessage, errorChain, type MessageId, type MessageSource, type UserMessage } from '@deepseek-ai/dsh-llm'

/** The checkpoint boundary settlement notices share with the acknowledgment face. */
export interface SettlementFlush {
  /**
   * Flush one session so every event appended so far is durable.
   * @param session - The session to checkpoint.
   * @returns Whether a durability backend participated and settled.
   */
  flush: (session: Session) => Promise<boolean>
}

/**
 * Durable attribution for the dispatch runtime's own account of one
 * dispatched child settling a turn. A different kind from a plugin or
 * agent message: the dispatch service states what became of the child,
 * and a transcript that merged them would credit the child with words
 * it never wrote.
 */
export interface DispatchSettledMessageSource {
  /** The dispatch runtime's settlement account (`notice` context form). */
  readonly kind: 'dispatch-settled'
  /** A runtime account shown without expanding the row. */
  readonly form: 'notice'
  /** One-line account of what settled. */
  readonly summary: string
  /** Session id of the child that settled. */
  readonly senderSessionId: SessionId
  /** The dispatched task the settling child owns. */
  readonly taskId: string
  /**
   * The stable identity of the settled turn (`<log seq>:<turn number>`),
   * read from the child's own log. Parent-side dedupe keys on this: the
   * parent's log is the ledger, so a re-mounted watch or a duplicate
   * dispatch cannot deliver the same settlement twice.
   */
  readonly turnIdentity: string
}

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap {
    'dispatch-settled': DispatchSettledMessageSource
  }
}

/** The readable prefix of every explicit followup message id. */
const FOLLOWUP_ID_PREFIX = 'dispatch-followup'

/**
 * The in-process delivery claims, scoped to the exact live child agent:
 * a claim is taken synchronously when the settlement is observed, so two
 * watches — the service's and a re-mounted one — cannot both pass the
 * pre-flush window. The key never leaks across hosts: an independent
 * context that reuses a session id holds a different Agent instance and
 * therefore its own claim set. Cross-restart dedupe stays on the parent's
 * durable facts, and a withheld delivery releases its claim so the next
 * idle edge can retry.
 */
const settlementClaims = new WeakMap<Agent, Set<string>>()

/**
 * Build one settlement notice for a parent's inbox: the account names the
 * task, the child, and the settled turn, and the source carries all three
 * as durable facts — the turn identity is the parent-side dedupe key.
 * @param taskId - The dispatched task the child owns, when the dispatch
 *   carried one.
 * @param childId - The settling child's session id.
 * @param turn - The settled turn's number.
 * @param turnIdentity - The settled turn's stable log identity.
 * @returns The notice message ready for delivery.
 */
export function settlementNotice(
  taskId: TaskId | undefined,
  childId: SessionId,
  turn: number | undefined,
  turnIdentity: string,
): UserMessage {
  const summary = taskId === undefined
    ? `Dispatch child ${String(childId)} settled turn ${String(turn ?? '?')}.`
    : `Dispatch task ${String(taskId)}: child ${String(childId)} settled turn ${String(turn ?? '?')}.`
  return createUserMessage({
    content: [{ type: 'text', text: summary }],
    source: {
      kind: 'dispatch-settled',
      form: 'notice',
      summary,
      senderSessionId: childId,
      taskId: taskId === undefined ? '' : String(taskId),
      turnIdentity,
    },
  })
}

/**
 * Deliver one message to an agent as its next ordinary turn. `followup()`
 * queues the message as the sole message of the agent's next turn and wakes
 * the driver — on an idle agent it opens a turn immediately, on a busy agent
 * it claims right after the in-flight turn ends. Steering is deliberately
 * not used: a steered message targets a step boundary the turn may never
 * reach, which would strand the notice unclaimed.
 * @param agent - The exact live agent to deliver to.
 * @param message - The message to deliver.
 */
export function deliverToAgent(agent: Agent, message: UserMessage): void {
  agent.followup(message)
}

/**
 * Watch one dispatched child and tell its parent every time the child
 * settles a real turn. Each settlement is one external event on the
 * parent's inbox — the decision point a goal-bound parent otherwise never
 * gets, because the engine ships no parent notification.
 *
 * The account is warranted, not assumed: the child's own log must hold a
 * `turn/end` (the finished turn), and that record must flush durably
 * before the notice is delivered — the same checkpoint boundary the
 * acknowledgment face uses. Dedupe is layered: an in-process delivery
 * claim keyed by child+turn identity stops concurrent watches (a duplicate
 * dispatch or a re-mount) from double-delivering, and the parent's own
 * durable facts — the logged notice, or the queued one still parked in its
 * inbox — stop re-delivery after a process restart. Delivery failure is
 * logged and dropped: retaining the child to retry a notice would pin
 * the parent, and the child's own session log stays the durable record
 * either way.
 * @param ctx - The host context the status events fire on.
 * @param sessions - The checkpoint boundary the notice's durability rides.
 * @param parent - The exact live parent the child was dispatched for.
 * @param child - The exact live dispatched child.
 * @param taskId - The task the child owns, when the dispatch carried one.
 */
export function watchChildSettlement(
  ctx: Context,
  sessions: SettlementFlush,
  parent: Agent,
  child: Agent,
  taskId: TaskId | undefined,
): void {
  /**
   * Whether the parent already holds this child's notice for one turn
   * identity. The parent's own durable facts are the dedupe ledger — no
   * parallel bookkeeping: the logged user message carries the typed
   * settlement source, and a steered-but-unclaimed notice still sits in
   * the inbox under the same identity.
   */
  const parentAlreadyNoticed = (turnIdentity: string): boolean => {
    const matches = (source: MessageSource | undefined): boolean =>
      source !== undefined && source.kind === 'dispatch-settled'
      && source.senderSessionId === child.id
      && source.turnIdentity === turnIdentity
    const logged = parent.session.snapshotEvents().some((event) => {
      if (event.type !== 'user/message') return false
      return matches((event.data as { source?: MessageSource }).source)
    })
    if (logged) return true
    const parked = [...parent.inbox.nextTurn, ...parent.inbox.nextStep]
      .some(message => matches(message.source))
    return parked
  }
  ctx.on('agent/status', (payload: { agent: Agent; status: string }) => {
    if (payload.agent !== child) return
    if (payload.status !== 'idle') return
    // The settlement must name a real finished turn: read the child's log
    // for its latest `turn/end` and report once per turn identity.
    const turnEnd = child.session.snapshotEvents()
      .filter(event => event.type === 'turn/end')
      .at(-1)
    if (turnEnd === undefined) return
    const turn = (turnEnd.data as { turn?: unknown }).turn
    const turnIdentity = `${String(turnEnd.seq)}:${String(typeof turn === 'number' ? turn : '')}`
    if (parentAlreadyNoticed(turnIdentity)) return
    // A parent that is no longer live is not an error; the child's own
    // session log stays the durable record either way.
    if (ctx.agents.get(parent.id) !== parent) return
    // One synchronous claim per child turn across every watch of THIS live
    // child: the concurrent deliveries cannot both pass the pre-flush
    // window, and a withheld delivery releases the claim for a retry.
    let claims = settlementClaims.get(child)
    if (claims === undefined) {
      claims = new Set()
      settlementClaims.set(child, claims)
    }
    if (claims.has(turnIdentity)) return
    claims.add(turnIdentity)
    void (async (): Promise<void> => {
      try {
        let durable = false
        try {
          durable = await sessions.flush(child.session)
        } catch {
          durable = false
        }
        if (!durable) {
          ctx.logger.warn(
            `agent-dispatch: settlement notice for child "${String(child.id)}" turn ${String(turn ?? '?')} `
            + 'was withheld: the turn\'s end record did not flush durably',
          )
          return
        }
        // The flush window may have outlived the parent or let another
        // watch deliver: re-check both against the same durable facts
        // before the delivery.
        if (ctx.agents.get(parent.id) !== parent) return
        if (parentAlreadyNoticed(turnIdentity)) return
        try {
          deliverToAgent(parent, settlementNotice(taskId, child.id, typeof turn === 'number' ? turn : undefined, turnIdentity))
        } catch (error: unknown) {
          ctx.logger.warn(
            `agent-dispatch: settlement notice for child "${String(child.id)}" was not delivered to its parent: `
            + errorChain(error),
          )
        }
      } finally {
        claims.delete(turnIdentity)
      }
    })()
  })
}

/**
 * The message id for one explicit followup delivery to an existing child.
 * Every followup is a distinct delivery, so the id carries a random suffix;
 * the durable facts (parent, task) stay in the readable prefix.
 * @param parentId - The dispatching parent's session id.
 * @param taskId - The task the child owns.
 * @returns A fresh, unique followup message id.
 */
export function followupMessageId(parentId: SessionId, taskId: TaskId): MessageId {
  return brandString<MessageId>(`${FOLLOWUP_ID_PREFIX}:${String(parentId)}:${String(taskId)}:${randomUUID()}`)
}
