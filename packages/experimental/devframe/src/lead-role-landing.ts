/**
 * Host-assembly landing wave for lead reviewer assignments: when the project
 * controller successfully dispatches a lead (the `agent/created` publication
 * fact whose durable binding names that lead and the controller as parent),
 * the controller Session's role policy gains the lead assignment. The binding
 * facts come from `ctx.agentBindings` — the existing durable authority, not a
 * new store — and the landing appends one new role-policy snapshot through
 * the DevFrame journal, so the fold re-derives the assignment on cold restore
 * and the review gate's directory sees the lead the hierarchy actually
 * backed. Dispatches that are not controller-to-lead facts are skipped; a
 * DevFrame controller dispatching before its policy landed fails loud.
 * @module @deepseek-ai/dsh-experimental-devframe/lead-role-landing
 */

import type { Context } from '@deepseek-ai/cordis'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { AgentBindingRegistry } from '@deepseek-ai/dsh-experimental-session-identity/src/registry.ts'
import type { WorkspaceId } from './shared/types.ts'
import { DevFrameSessionJournal } from './session-journal.ts'
import type { DevFrameReviewGate } from './session-journal.ts'
import type { DevFrameRolePolicyEventData } from './events.ts'

/** The host seam the landing wave provides. */
export interface DevFrameLeadRoleLanding {
  /**
   * Land the role-policy snapshot assigning one agent's lead binding.
   * @param agentId - The published agent identity whose binding names a lead
   *   and its controller parent.
   * @returns What the landing did with the fact.
   * @throws When the binding is missing or not a controller-parented lead,
   *   the parent Session is gone, the DevFrame controller dispatched before
   *   its role policy landed, the recorded policy version scheme cannot be
   *   advanced, or the durable append failed.
   */
  land(agentId: SessionId): Promise<LandingOutcome>
  /**
   * The latched failure of the last landing for one controller Session, if
   * any; a latched failure is rethrown by the next landing for that Session.
   * @param controllerSessionId - The controller Session whose landing failed.
   * @returns The latched error, or undefined.
   */
  failureOf(controllerSessionId: SessionId): unknown
}

/** What one landing call did with a dispatch fact. */
export type LandingOutcome =
  /** The role policy gained the lead assignment. */
  | 'landed'
  /** The binding already held the assignment; the log stays untouched. */
  | 'assigned'
  /** The parent is not this project's controller; the fact is out of scope. */
  | 'skipped'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host seam landing lead reviewer assignments from hierarchy facts. */
    devframeLeadRoleLanding: DevFrameLeadRoleLanding
  }
}

/** Cordis plugin name. */
export const name = 'devframe-lead-role-landing'
/** The landing reads bindings, sessions, and folded projection state. */
export const inject: string[] = ['sessions', 'agentBindings', 'sessionProjections']

/**
 * The journal gate for the landing's role-policy appends. This journal must
 * never write a review event — its gate rejects every submission fail-loud.
 */
const rejectReviews: DevFrameReviewGate = {
  requireReviewer: (sessionId: SessionId): void => {
    throw new Error(`devframe lead role landing journal never writes review events (reviewer "${String(sessionId)}")`)
  },
}

/**
 * Advance the recorded policy version by one deterministic step: the trailing
 * decimal run increments (`policy-ws-v1` → `policy-ws-v2`). A version without
 * a trailing number cannot be advanced without guessing, so the landing
 * refuses rather than inventing a scheme.
 * @param prior - The currently recorded policy version.
 * @returns The next version string.
 */
function nextPolicyVersion(prior: string): string {
  const match = /(\d+)$/.exec(prior)
  if (match === null) {
    throw new Error(`DevFrame role policy version "${prior}" has no trailing number to advance`)
  }
  return `${prior.slice(0, match.index)}${String(Number(match[1]) + 1)}`
}

/** The role-policy snapshot the next landing appends, composed from the fold. */
function landedSnapshot(
  controllerSessionId: SessionId,
  workspaceId: WorkspaceId,
  policy: DevFrameRolePolicyEventData,
  leadSessionId: SessionId,
): DevFrameRolePolicyEventData {
  return {
    version: 1,
    workspaceId,
    controllerSessionId,
    policyVersion: nextPolicyVersion(policy.policyVersion),
    config: policy.config,
    assignments: [...policy.assignments, { role: 'lead', sessionId: leadSessionId }],
  }
}

/**
 * Plugin entry: provide the landing seam and listen for agent publications.
 * A publication whose durable binding names a controller-parented lead lands
 * the assignment on the parent's role policy; the append serializes through
 * the journal and a failure latches on the controller Session until the next
 * landing for it succeeds. Facts outside the controller-to-lead scope never
 * touch the log.
 * @param ctx - The mounting context.
 * @returns The plugin disposer.
 */
export function apply(ctx: Context): () => void {
  const bindings: AgentBindingRegistry = ctx.agentBindings
  const journal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), rejectReviews)
  const failures = new Map<string, unknown>()

  const land = async (agentId: SessionId): Promise<LandingOutcome> => {
    const record = bindings.find(agentId)
    if (record === undefined) {
      throw new Error(`devframe lead role landing: agent "${String(agentId)}" holds no durable binding`)
    }
    if (record.role !== 'lead' || record.parentSessionId === undefined) {
      throw new Error(`devframe lead role landing: agent "${String(agentId)}" is not a controller-parented lead`)
    }
    const controllerSessionId = record.parentSessionId
    try {
      const parent = ctx.sessions.get(controllerSessionId)
      if (parent === undefined) {
        // The dispatching parent holds no live Session: it is not this
        // project's controller face, and the fact is out of scope.
        return 'skipped'
      }
      const state = ctx.sessionProjections.stateOf(parent, 'devframe')
      if (state === undefined || String(state.controllerSessionId) !== String(controllerSessionId)) {
        // The parent is not this project's controller: the fact is real but
        // out of scope, and the log must stay untouched.
        return 'skipped'
      }
      if (state.rolePolicy === null || state.workspaceId === null) {
        throw new Error(`devframe lead role landing: controller Session "${String(controllerSessionId)}" dispatched a lead before its role policy landed`)
      }
      const policy = state.rolePolicy
      if (policy.assignments.some(assignment =>
        assignment.role === 'lead' && String(assignment.sessionId) === String(record.sessionId))) {
        return 'assigned'
      }
      await journal.append(parent, 'devframe/role-policy', landedSnapshot(
        state.controllerSessionId,
        state.workspaceId,
        policy,
        record.sessionId,
      ))
      return 'landed'
    } catch (error: unknown) {
      failures.set(String(controllerSessionId), error)
      throw error
    }
  }

  const disposers: Array<() => unknown> = [
    ctx.provide('devframeLeadRoleLanding', {
      land,
      failureOf: (controllerSessionId: SessionId) => failures.get(String(controllerSessionId)),
    }),
    ctx.on('agent/created', ({ agent }) => {
      const record = bindings.find(agent.id)
      if (record === undefined || record.role !== 'lead' || record.parentSessionId === undefined) return
      void land(agent.id).catch(() => {
        // The rejection is latched on the controller Session — the next
        // landing for it rethrows, and failureOf exposes it to the host.
      })
    }),
  ]
  return () => {
    failures.clear()
    for (const dispose of disposers.reverse()) void dispose()
  }
}
