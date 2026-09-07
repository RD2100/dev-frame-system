/**
 * The `ctx.agentDispatch` service: the host's daily-dispatch entry over the
 * agent-hierarchy creation engine. The entry validates what the host
 * composition layer owns before any child exists — the requested worktree is
 * really registered and alive, its canonical path and single-writer binding
 * match the registry's authoritative rows (`status` for the live directory
 * and branch, `list` for the path and binding), and the
 * controller→lead→worker chain with its plugin scopes holds over the
 * engine's approved-set contract. When the request holds, the entry runs the
 * host assembly inside the engine's factory setup window — the child joins
 * its parent's preset composition (the subagent seam's `composeFrom`
 * convention, a no-op on a rosterless deployment), then takes the registered
 * worktree's single-writer binding, and only then does the engine persist
 * the prepared binding and publish — and delivers the requested prompt
 * strictly after the engine resolves. The engine owns the child's lifecycle;
 * the published {@link CreatedChildAgent} carries no disposer.
 *
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/service
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { brandString } from '@deepseek-ai/dsh-brand'
import { freezeMessage, createUserMessage, type MessageId } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {
  CreateChildAgentOptions,
  CreateChildAgentRequest,
  CreatedChildAgent,
} from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import type { AgentBindingRecord, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
// Type-only: resolve the opportunistic `ctx.get('agentPresets')` join to the
// preset roster when composed; a rosterless deployment keeps the no-op.
import type {} from '@deepseek-ai/dsh-agent-presets'
import type {} from '@deepseek-ai/dsh-session-persistence'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { WorktreeGitOperationError, WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree, WorktreeStatus } from '@deepseek-ai/dsh-worktree-registry'
import { AgentDispatchError } from './errors.ts'
import { evaluateDispatchEntry } from './entry.ts'
import { foldBriefingAck, type DispatchTaskAck } from './ack.ts'
import { deliverToAgent, followupMessageId, watchChildSettlement } from './child-settlement.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentDispatch: AgentDispatch
  }
}

/**
 * Engine creation options plus the owner workspace the daily entry needs:
 * the workspace the requested worktree is registered under, which anchors
 * the authoritative `list`-row proof of path and single-writer binding.
 */
export interface DispatchAgentOptions extends CreateChildAgentOptions {
  /** Workspace the requested worktree is registered under. */
  readonly workspaceId: WorkspaceId
  /**
   * Initial task briefing delivered through `Agent.followup()` once creation
   * resolves. Never queued before publication.
   */
  readonly prompt?: string | undefined
  /**
   * Explicit continuation instructions for the child an earlier dispatch
   * already published for this task. Delivered to that live child's inbox
   * as its next ordinary turn — queued behind any in-flight turn and
   * woken — and never re-tasks a fresh creation: on identity reuse without
   * this field nothing is delivered, exactly as before.
   */
  readonly followupPrompt?: string | undefined
}

/**
 * Recovery options: the reserved identity is required and the briefing is
 * structurally absent — recovery reinstalls the reservation, it never
 * re-tasks the child.
 */
export type RecoverDispatchAgentOptions = Omit<DispatchAgentOptions, 'prompt' | 'followupPrompt' | 'sessionId'> & {
  /** The reserved identity a previous dispatch returned. */
  readonly sessionId: SessionId
}

/**
 * The durable identity an earlier dispatch returned for one parent task.
 */
export interface DispatchedIdentity {
  /** The binding record the engine persisted for that child. */
  readonly record: AgentBindingRecord
  /** Whether the child agent is currently live in this process. */
  readonly live: boolean
}

/** The per-task gate key: one parent's one task (an absent task still gates per parent). */
function taskGateKey(parentId: SessionId, taskId: TaskId | undefined): string {
  return `dispatch:${String(parentId)}:${String(taskId ?? '')}`
}

/**
 * The deterministic briefing identity for one dispatched task. Both inputs
 * are durable facts of the binding record, so the identity is re-derivable
 * after a process restart or a recovery — the anchor that lets the
 * acknowledgment face find this task's briefing in a reloaded child log
 * without any parallel ledger.
 */
function briefingMessageId(parentId: SessionId, taskId: TaskId): MessageId {
  return brandString<MessageId>(`dispatch-briefing:${String(parentId)}:${String(taskId)}`)
}

/**
 * The host daily-dispatch entry. Hard-injects the real creation engine
 * (`ctx.agentHierarchy`), the role authority (`ctx.agentBindings`), and the
 * worktree registry whose rows make the worktree proof real, and fails at
 * activation when any is absent. Denials raised here are
 * {@link AgentDispatchError}s; the engine's own denials — including the
 * reserved-child recovery refusal for an identity whose session is no longer
 * live — propagate unchanged.
 */
export class AgentDispatch extends Service {
  static inject = ['agentHierarchy', 'agentBindings', 'worktreeRegistry', 'agents', 'sessions']

  /** One settled-before-run chain per parent task, serializing its full dispatch span. */
  private taskGates = new Map<string, Promise<unknown>>()

  /** Settlement watches already mounted, deduped by the exact child agent instance. */
  private settlementWatches = new WeakSet<Agent>()

  constructor(ctx: Context) {
    super(ctx, 'agentDispatch')
  }

  /**
   * Run one parent task's dispatch span — identity judgment, the engine call,
   * and the first briefing — under a per-task gate. Creation dedupe is not
   * delivery dedupe: two concurrent same-task requests both observe an empty
   * registry before the engine serializes their creations into one child, and
   * each would then deliver a prompt to that child. The gate makes the
   * identity observation atomic with the delivery decision, so exactly the
   * caller that held the gate while the identity was absent delivers, and
   * every later entrant re-reads the durable record and takes the reuse or
   * guidance path. Re-querying the record inside one span decides nothing
   * here; ownership of the first briefing belongs to the gate.
   * @param key - The parent-task gate key.
   * @param run - The span to serialize.
   * @returns Whatever `run` resolves to.
   */
  private async withTaskGate<T>(key: string, run: () => Promise<T>): Promise<T> {
    const previous = this.taskGates.get(key) ?? Promise.resolve()
    const result = previous.then(run, run)
    const tail = result.then(() => undefined, () => undefined)
    this.taskGates.set(key, tail)
    // Cleanup rides the never-rejecting tail: a finally() on `result` would
    // derive a second rejection with nobody attached to it.
    void tail.then(() => {
      if (this.taskGates.get(key) === tail) this.taskGates.delete(key)
    })
    return await result
  }

  /**
   * Mount the parent settlement watch for one live child exactly once per
   * child agent instance. Fresh dispatches, identity reuses, and cold
   * recoveries all run through here: the watch rides the child's actual
   * in-process lifecycle, so a restarted process re-mounts it when the
   * child is taken back, and a duplicate dispatch never mounts a second one.
   * @param parent - The exact live parent the child was dispatched for.
   * @param child - The exact live dispatched child.
   * @param taskId - The task the child owns, when the request carried one.
   */
  private ensureSettlementWatch(parent: Agent, child: Agent, taskId: TaskId | undefined): void {
    if (this.settlementWatches.has(child)) return
    this.settlementWatches.add(child)
    watchChildSettlement(this.ctx, this.ctx.sessions, parent, child, taskId)
  }

  /**
   * Find the durable identity an earlier dispatch returned for one parent
   * task, if any. The matching rule is the engine's own dedupe key
   * (`parentSessionId` + `taskId`). A retry reuses the identity only by
   * passing `record.agentId` back as `options.sessionId`; reuse never
   * re-delivers a prompt, and a child whose session is no longer live keeps
   * its engine-owned recovery lane instead of a replacement child.
   * @param parent - The dispatching parent the child was created for.
   * @param taskId - The task the child was created for.
   * @returns The durable identity and its live state, or `undefined` when
   *   no dispatched child exists for the pair.
   */
  findDispatchedChild(parent: Agent, taskId: TaskId): DispatchedIdentity | undefined {
    const record = this.ctx.agentBindings.list().find(
      candidate => candidate.parentSessionId === parent.id && candidate.taskId === taskId,
    )
    if (record === undefined) return undefined
    return { record, live: this.ctx.agents.get(record.agentId) !== undefined }
  }

  /**
   * Validate one dispatch request at the entry and, when it holds, create the
   * child through the real hierarchy engine. The authoritative registry rows
   * prove registration before any live observation runs; a git failure whose
   * refusal carries the registry's classified kind rethrows unchanged. A
   * parent task that already has a child refuses with
   * `DISPATCH_IDENTITY_EXISTS` until the caller passes the returned agent id
   * back as `sessionId` — the engine's own dedupe then answers with the same
   * child.
   * @param parent - The exact live dispatching agent.
   * @param request - The child creation request; `worktree` is required at
   *   this entry because the dispatched child owns one registered worktree.
   * @param options - Factory setup, route, cancellation, preallocated
   *   identity, the owner workspace anchoring the registry proof, and the
   *   optional initial prompt delivered after publication.
   * @returns The published child and its durable binding record.
   */
  async createChildAgent(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: DispatchAgentOptions,
  ): Promise<CreatedChildAgent> {
    return await this.withTaskGate(taskGateKey(parent.id, request.taskId), async () => {
      const { worktree, existing } = await this.entryProof(parent, request, options.workspaceId, options.sessionId)
      return await this.dispatch(parent, request, options, worktree, existing)
    })
  }

  /**
   * Recover one reserved child through the engine's fixed recovery lane after
   * the same entry proof the creation path runs. The caller must pass the
   * reserved identity back as `sessionId`; recovery reuses the same host
   * assembly as creation — the preset composition join and the registered
   * worktree's single-writer binding are re-established by the composed
   * setup on the recovered session — and never delivers a prompt (the type
   * omits one). The engine decides between resuming the existing session
   * and, only on a typed missing-log result, republishing under the same
   * identity. Corruption, cancellation, and foreign-identity failures
   * propagate unchanged — no replacement child.
   * @param parent - The exact live dispatching agent recorded by the reservation.
   * @param request - The original creation request, unchanged.
   * @param options - The reserved identity, the owner workspace anchoring the
   *   registry proof, and the factory setup, route, and cancellation to
   *   reinstall with the recovered session.
   * @returns The recovered child and its unchanged durable binding record.
   */
  async recoverChildAgent(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: RecoverDispatchAgentOptions,
  ): Promise<CreatedChildAgent> {
    return await this.withTaskGate(taskGateKey(parent.id, request.taskId), async () => {
      const { worktree } = await this.entryProof(parent, request, options.workspaceId, options.sessionId)
      const recovered = await this.ctx.agentHierarchy.recoverChildAgent(parent, request, {
        sessionId: options.sessionId,
        setup: this.composedSetup(parent, worktree, options.setup),
        ...(options.agentOptions === undefined ? {} : { agentOptions: options.agentOptions }),
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      })
      // A cold-recovered child re-mounts its settlement watch on the new
      // in-process instance, so post-restart turns still wake the parent.
      this.ensureSettlementWatch(parent, recovered.agent, request.taskId)
      return recovered
    })
  }

  /**
   * Run the entry proof both dispatch lanes share: the durable identity
   * question, the authoritative registry rows, the live observation, and the
   * dispatch discipline. The engine's own reservation and recovery semantics
   * stay engine-owned; this proof covers only what the host composition
   * layer owns.
   * @param parent - The exact live dispatching agent.
   * @param request - The child creation request; `worktree` is required at
   *   this entry because the dispatched child owns one registered worktree.
   * @param workspaceId - Workspace the requested worktree is registered under.
   * @param sessionId - The identity a retry passes back, when reusing one.
   * @returns The proven worktree and the durable identity for the parent
   *   task, when one exists.
   */
  private async entryProof(
    parent: Agent,
    request: CreateChildAgentRequest,
    workspaceId: WorkspaceId,
    sessionId: SessionId | undefined,
  ): Promise<{
    worktree: NonNullable<CreateChildAgentRequest['worktree']>
    existing: DispatchedIdentity | undefined
  }> {
    const worktree = request.worktree
    if (worktree === undefined) {
      throw new AgentDispatchError(
        'agent-dispatch: a dispatched child requires a registered worktree',
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    if (workspaceId === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" proof requires the owner workspace id`,
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    const existing = request.taskId === undefined
      ? undefined
      : this.findDispatchedChild(parent, request.taskId)
    if (existing !== undefined && sessionId === undefined) {
      // A blind same-task retry must not re-create or silently adopt: the
      // caller learns the returned identity and passes it back explicitly.
      throw new AgentDispatchError(
        `agent-dispatch: parent task already has the dispatched child "${existing.record.agentId}"; `
        + 'retry by passing that id as sessionId (use findDispatchedChild to recover it)',
        'DISPATCH_IDENTITY_EXISTS',
      )
    }
    const row = this.registeredRow(workspaceId, worktree.worktreeId)
    const status = await this.observedStatus(worktree.worktreeId)
    if (!status.directoryExists) {
      throw new AgentDispatchError(
        `agent-dispatch: registered worktree "${worktree.worktreeId}" no longer exists on disk`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    if (worktree.branch !== undefined && status.branch !== undefined && status.branch !== worktree.branch) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is on branch "${status.branch}", not the requested "${worktree.branch}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    if (row.path !== worktree.worktreePath) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is registered at "${row.path}", not the requested "${worktree.worktreePath}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    // Brands differ by design (WorktreeLockHolder vs SessionId); the
    // registry's holder contract is string equality, and an unallocated
    // child identity cannot match any existing binding.
    if (row.lockedBy !== undefined
      && (sessionId === undefined || String(row.lockedBy) !== String(sessionId))) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is bound to writer "${row.lockedBy}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    const creator = this.ctx.agentBindings.find(parent.id)
    if (creator === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: parent session "${parent.id}" has no role binding`,
        'DISPATCH_PARENT_UNBOUND',
      )
    }
    const approvedScopes = this.ctx.agentHierarchy.config.leadPluginScopes[creator.agentId] ?? []
    const decision = evaluateDispatchEntry(creator, request, approvedScopes)
    if (!decision.allowed) {
      throw new AgentDispatchError(
        decision.reason ?? 'agent-dispatch: dispatch refused',
        'DISPATCH_HIERARCHY_DENIED',
      )
    }
    return { worktree, existing }
  }

  /**
   * Compose the engine-facing factory setup both dispatch lanes share: the
   * child joins its parent's preset composition, then takes the registered
   * worktree's single-writer binding, and the caller's own setup runs last.
   * A caller setup failure releases the binding this composition took.
   * @param parent - The exact live dispatching agent, for the composition join.
   * @param worktree - The proven registered worktree the child will own.
   * @param hostSetup - The caller's own factory setup, run after the assembly.
   * @returns The composed setup for the engine's factory window.
   */
  private composedSetup(
    parent: Agent,
    worktree: NonNullable<CreateChildAgentRequest['worktree']>,
    hostSetup: CreateChildAgentOptions['setup'],
  ): NonNullable<CreateChildAgentOptions['setup']> {
    return async (childCtx) => {
      const child = childCtx.agent
      if (child === undefined) throw new Error('agent-dispatch: factory setup has no Agent')
      childCtx.get('agentPresets')?.composeFrom(childCtx, parent.ctx)
      const holder = WorktreeLockHolder(child.session.id)
      await this.ctx.worktreeRegistry.bind(worktree.worktreeId, holder)
      try {
        return await hostSetup?.(childCtx)
      } catch (error) {
        await this.ctx.worktreeRegistry.unbind(worktree.worktreeId, holder).catch(() => {
          // The setup failure is the reportable outcome; a refused release
          // leaves the holder-mismatch diagnosis to the registry's own error.
        })
        throw error
      }
    }
  }

  /**
   * Run the real engine with the host assembly installed. Inside the factory
   * setup window the child joins its parent's preset composition, then takes
   * the registered worktree's single-writer binding, and the caller's own
   * setup runs last; the engine persists the prepared binding and publishes
   * afterwards. The initial prompt is delivered only once creation has
   * resolved, so a refused or failed dispatch never queues one.
   */
  private async dispatch(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: DispatchAgentOptions,
    worktree: NonNullable<CreateChildAgentRequest['worktree']>,
    existing: DispatchedIdentity | undefined,
  ): Promise<CreatedChildAgent> {
    const engineOptions: CreateChildAgentOptions = {
      ...(options.sessionId === undefined ? {} : { sessionId: options.sessionId }),
      ...(options.agentOptions === undefined ? {} : { agentOptions: options.agentOptions }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
      setup: this.composedSetup(parent, worktree, options.setup),
    }
    const created = await this.ctx.agentHierarchy.createChildAgent(parent, request, engineOptions)
    // Identity reuse answers with the engine's already-published child;
    // re-delivering the briefing would re-task a running worker. Engine
    // errors — including the reserved-child recovery refusal and a typed
    // session-persistence miss — propagate unchanged; no fallback child.
    if (options.prompt !== undefined && existing === undefined) {
      // The briefing carries a deterministic identity derived from the
      // durable binding facts, so the acknowledgment face can find exactly
      // this task's briefing in the child's log — including a log reloaded
      // by a recovery — without a parallel in-memory ledger.
      const message = request.taskId === undefined
        ? createUserMessage({
          content: [{ type: 'text', text: options.prompt }],
          source: { kind: 'plugin', plugin: 'agent-dispatch' },
        })
        : freezeMessage({
          id: briefingMessageId(parent.id, request.taskId),
          role: 'user',
          content: [{ type: 'text', text: options.prompt }],
          source: { kind: 'plugin', plugin: 'agent-dispatch' },
        })
      created.agent.followup(message)
    }
    // The explicit continuation contract: an existing child receives new
    // instructions on its inbox without any re-creation. Recovery never
    // passes this field, so a recovery lane cannot re-task a child.
    if (existing !== undefined && options.followupPrompt !== undefined) {
      const message = request.taskId === undefined
        ? createUserMessage({
          content: [{ type: 'text', text: options.followupPrompt }],
          source: { kind: 'plugin', plugin: 'agent-dispatch' },
        })
        : freezeMessage({
          id: followupMessageId(parent.id, request.taskId),
          role: 'user',
          content: [{ type: 'text', text: options.followupPrompt }],
          source: { kind: 'plugin', plugin: 'agent-dispatch' },
        })
      deliverToAgent(created.agent, message)
    }
    // A dispatched child reports its settlements to its parent: each one is
    // the external event a goal-bound parent's continuation needs to make
    // its next decision. Mounted per child instance, on every lane that
    // hands a live child back.
    this.ensureSettlementWatch(parent, created.agent, request.taskId)
    return created
  }

  /**
   * The durable acknowledgment for one dispatched task: what the child's own
   * log proves about the briefing this entry delivered, backed by the
   * session store's flush barrier. The derivation is durable by
   * construction — delivery splice, claiming splice, and the claiming
   * turn's `turn/end` are all durable session events — and `durable` is
   * claimed only when a durability listener participates in the barrier. A
   * barrier refusal or a durability failure never hides the primary
   * dispatch outcome behind an exception: the ack reports `durable: false`
   * with `degraded: true`, so a broken backend is visible exactly where the
   * parent looks, and the child's own turn checkpoints fail loud on their
   * own boundaries.
   * @param parent - The exact live dispatching agent the child was created for.
   * @param taskId - The task the child was created for.
   * @returns The acknowledgment, or `undefined` when no dispatched child
   *   exists for the pair.
   */
  async taskAck(parent: Agent, taskId: TaskId): Promise<DispatchTaskAck | undefined> {
    const record = this.ctx.agentBindings.list().find(
      candidate => candidate.parentSessionId === parent.id && candidate.taskId === taskId,
    )
    if (record === undefined) return undefined
    const briefingId = briefingMessageId(parent.id, taskId)
    const child = this.ctx.agents.get(record.agentId)
    if (child === undefined) {
      // Not live: the log facts are engine-owned recovery territory. The
      // recovery lane reinstates the identity, and this derivation runs
      // unchanged over the reloaded log afterwards.
      return { state: 'unavailable', briefingMessageId: briefingId, durable: false }
    }
    // Snapshot first, then flush: the barrier covers every event appended
    // before it, so facts present in the snapshot are durable once it
    // settles; facts appended after it are not in the snapshot and are
    // never claimed.
    const events = child.session.snapshotEvents()
    let durable = false
    let degraded: true | undefined
    try {
      durable = await this.ctx.sessions.flush(child.session)
    } catch {
      degraded = true
    }
    const fold = foldBriefingAck(events, String(briefingId))
    return {
      state: fold.state,
      briefingMessageId: briefingId,
      durable,
      ...degraded === undefined ? {} : { degraded },
      ...(fold.turnEnd === undefined ? {} : {
        turnEnd: fold.turnEnd,
        completed: fold.turnEnd.reason.kind === 'completed',
      }),
    }
  }

  /**
   * Read one registry status observation for an already-proven registration.
   * The registry's classified git failures rethrow unchanged; any other
   * failed observation on a registered worktree is a live mismatch, not an
   * unregistered dispatch.
   */
  private async observedStatus(worktreeId: WorktreeId): Promise<WorktreeStatus> {
    try {
      return await this.ctx.worktreeRegistry.status(worktreeId)
    } catch (error) {
      if (error instanceof WorktreeGitOperationError) throw error
      throw new AgentDispatchError(
        `agent-dispatch: the live status observation of registered worktree "${worktreeId}" failed`,
        'DISPATCH_WORKTREE_MISMATCH',
        { cause: error },
      )
    }
  }

  /**
   * Read the authoritative registry row for one id within its owner
   * workspace — a status observation alone cannot prove the canonical path
   * or the single-writer binding.
   */
  private registeredRow(workspaceId: WorkspaceId, worktreeId: WorktreeId): Worktree {
    let rows: readonly Worktree[]
    try {
      rows = this.ctx.worktreeRegistry.list(workspaceId)
    } catch (error) {
      throw new AgentDispatchError(
        `agent-dispatch: workspace "${workspaceId}" is not a registered workspace`,
        'DISPATCH_WORKTREE_UNREGISTERED',
        { cause: error },
      )
    }
    const row = rows.find(entry => entry.id === worktreeId)
    if (row === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktreeId}" is not registered under workspace "${workspaceId}"`,
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    return row
  }
}
