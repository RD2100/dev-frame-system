/**
 * The shadow router (`ctx.shadowRouter`): the Cordis service that routes user
 * intent between independent project roots. It owns the durable controller
 * binding index (`shadow_router` domain: `bindings`, `deliveries`,
 * `requests`), the provisioning state machine with failure rollback, the
 * cross-root delivery persistence that keeps `received` and `completed` as
 * distinct durable states, the request deduplication ledger, and the
 * Shadow-only whitelist that installs the four project tools.
 *
 * Workspace facts (canonical identity, alias resolution) come from the native
 * workspace registry; controller role persistence comes from the
 * session-identity binding registry. Cross-root delivery does NOT reuse the
 * agent-team mailbox: unrelated root sessions are not teammates, and no
 * member-checking path is invoked. One workspace resolves to one current
 * controller; every mutation is serialized on one operation chain and written
 * through to the domain, so the tables stay the only durable authority.
 *
 * @module @deepseek-ai/dsh-experimental-shadow-router/service
 */

import { createHash, randomUUID } from 'node:crypto'
import { realpath, stat } from 'node:fs/promises'
import { isAbsolute, sep } from 'node:path'
import z from '@deepseek-ai/schemastery'
import { Service, type Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { SessionId, type Session } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
// Loads the session-identity Context augmentation so `ctx.agentBindings` types the controller-role bind.
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import { installShadowTools } from './tools.ts'
import { ShadowRouterError } from './errors.ts'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from './ids.ts'
import { shadowRouterDomainSpec } from './spec.ts'
import type {
  ShadowBindingRecord,
  ShadowBindingState,
  ShadowDeliveryMode,
  ShadowDeliveryRecord,
  ShadowDeliveryState,
  ShadowRequestKind,
  ShadowRequestRecord,
} from './spec.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** The mounted shadow router: binding store, delivery persistence, and the Shadow whitelist. */
    shadowRouter: ShadowRouter
  }
}

/** Plugin config (all optional — `static Config` supplies the defaults). */
export interface ShadowRouterConfig {
  /**
   * Absolute directories a project root may live in. Fail-closed default: an
   * empty list authorizes nothing. Every entry must be an existing directory
   * at load, or activation fails loud.
   */
  authorizedRoots?: string[]
  /** Controller profile the host serves for project root sessions. */
  controllerProfile?: string
  /**
   * Session id the host composition declares as its Shadow. The router
   * performs the real {@link ShadowRouter.markShadow} invocation itself at
   * the earliest resolvable point: immediately when that agent is already
   * live at activation, otherwise when it is created. An id that never
   * becomes live installs nothing (fail-closed, same as unconfigured);
   * marking is idempotent; disposal cleanup stays with the existing
   * `agent/disposed` effect.
   */
  shadowSessionId?: string
  /** Per-workspace limit of pending (queued, not yet received) deliveries. */
  maxPendingDeliveries?: number
  /** Maximum message text length in characters. */
  maxMessageChars?: number
  /** Maximum projects (and delivery rows) returned by one status read. */
  statusPageSize?: number
}

/** The config shape after schemastery applied the defaults; `shadowSessionId` keeps its optional face. */
type ResolvedConfig = Omit<Required<ShadowRouterConfig>, 'shadowSessionId'> & Pick<ShadowRouterConfig, 'shadowSessionId'>

/** The receipt `project_open` returns: one workspace's controller association. */
export interface ProjectOpenResult {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** The reserved (then actual) controller root session. */
  readonly controllerSessionId: SessionId
  /** Association version after the open. */
  readonly bindingRevision: number
  /** Provisioning state at return; `ready` is the usable one. */
  readonly state: ShadowBindingState
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
}

/**
 * The receipt `project_send` returns. `status` is `received`: durable target
 * acceptance of the input — never a claim that the work ran or succeeded.
 */
export interface ProjectSendResult {
  /** Stable delivery identity, derived from the request id. */
  readonly messageId: ShadowMessageId
  /** Receiving project. */
  readonly workspaceId: WorkspaceId
  /** The durable receipt state; always `received` at send time. */
  readonly status: 'received'
}

/** The receipt `project_stop` returns for one project's stop. */
export interface ProjectStopResult {
  /** The stopped project. */
  readonly workspaceId: WorkspaceId
  /** `stopping` until the host confirms quiescence, then `stopped`. */
  readonly status: 'stopping' | 'stopped'
  /** Pending deliveries cancelled by this stop; they stay visible, never dropped. */
  readonly cancelledDeliveries: number
  /** Association version after the stop. */
  readonly bindingRevision: number
}

/** One bounded delivery row inside a status read. */
export interface ProjectDeliverySummary {
  /** Stable delivery identity. */
  readonly messageId: ShadowMessageId
  /** Delivery mode. */
  readonly mode: ShadowDeliveryMode
  /** Work ownership the delivery asserts. */
  readonly goalId: string
  /** Durable delivery state; `received` is never read as `completed`. */
  readonly state: ShadowDeliveryState
  /** ISO-8601 sender-intent instant. */
  readonly createdAt: string
  /** ISO-8601 target-acceptance instant, when received. */
  readonly receivedAt?: string
  /** ISO-8601 completion instant, when completed. */
  readonly completedAt?: string
  /** Why the delivery was cancelled, when cancelled. */
  readonly cancelReason?: string
}

/** One project row inside a status read. */
export interface ProjectStatusEntry {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
  /** The current controller root session. */
  readonly controllerSessionId: SessionId
  /** Whether the controller session is live in this process right now. */
  readonly controllerLive: boolean
  /** Controller profile the binding pins. */
  readonly profileKey: string
  /** Association version. */
  readonly bindingRevision: number
  /** Provisioning/operation state. */
  readonly state: ShadowBindingState
  /** Durable failure reason, when `needs_attention` or `failed`. */
  readonly failureReason?: string
  /** The authorized open run's Goal, when one is recorded. */
  readonly activeGoalId?: string
  /** What blocks the project, computed from durable state at read time. */
  readonly blockedReason?: string
  /** First page of the project's deliveries, oldest first. */
  deliveries: ProjectDeliverySummary[]
  /** Whether more delivery rows exist beyond the bounded page. */
  readonly deliveriesTruncated: boolean
}

/** The bounded, read-only result `project_status` returns. */
export interface ProjectStatusResult {
  /** One page of authorized projects. */
  projects: ProjectStatusEntry[]
  /** Offset of the next page, when more projects exist. */
  readonly nextCursor?: number
  /** ISO-8601 instant the observation was taken. */
  readonly observedAt: string
}

/** One binding row projected for host status surfaces: association facts only. */
export interface ShadowStatusBinding {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
  /** Association version. */
  readonly bindingRevision: number
  /** Provisioning/operation state; see the type for the order. */
  readonly state: ShadowBindingState
}

/**
 * The read-only aggregate host status surfaces (the Web Shadow card) display:
 * designation, controller liveness, authorized roots, and the binding index.
 * Unlike `projectStatus` it is host-plane (no Shadow-caller gate), synchronous,
 * and unpaginated — the deployment's own facts, not a model-facing readout.
 */
export interface ShadowRouterStatus {
  /** Controller session id the host composition declared, absent when unconfigured. */
  readonly shadowSessionId?: string
  /** Whether the designated session is currently marked as the Shadow. */
  readonly shadowLive: boolean
  /** Canonical authorized roots resolved at load, in configuration order. */
  readonly authorizedRoots: readonly string[]
  /** Every binding in stable (createdAt, workspaceId) order. */
  readonly bindings: readonly ShadowStatusBinding[]
}

/** Host-level request shapes; the model-facing wrappers live in `tools.ts`. */
export interface ProjectOpenRequest {
  /** Existing, authorized root directory. */
  readonly path: string
  /** Stable request id; replays return the prior result. */
  readonly requestId: string
}

/** Host-level request to deliver one message into an authorized project. */
export interface ProjectSendRequest {
  /** Receiving project. */
  readonly workspaceId: string
  /** Association version the sender asserts. */
  readonly bindingRevision: number
  /** Work ownership the message asserts. */
  readonly goalId: string
  /** Acceptance association the message asserts. */
  readonly acceptanceHash: string
  /** Stable request id; retries reuse it. */
  readonly requestId: string
  /** `work` schedules follow-up; `note` is quiet input. */
  readonly mode: ShadowDeliveryMode
  /** Bounded message text. */
  readonly text: string
}

/** Host-level request to stop one authorized project. */
export interface ProjectStopRequest {
  /** Project to stop. */
  readonly workspaceId: string
  /** Association version the caller asserts. */
  readonly expectedRevision: number
  /** Stable request id; replays return the prior result. */
  readonly requestId: string
}

/** The states that still admit deliveries. */
const ADMITTING_STATES: readonly ShadowBindingState[] = ['ready']

/**
 * Whether two canonical paths denote the same directory. Canonical paths
 * carry the filesystem's casing on Windows, so equality there ignores case.
 */
function samePath(left: string, right: string): boolean {
  return process.platform === 'win32'
    ? left.toLowerCase() === right.toLowerCase()
    : left === right
}

/**
 * Whether `child` equals or lives inside `parent`, compared segment-aware:
 * a string prefix alone would confuse `D:\a` with `D:\ab`.
 */
function isWithinPath(child: string, parent: string): boolean {
  if (samePath(child, parent)) return true
  const prefix = parent.endsWith(sep) ? parent : parent + sep
  return process.platform === 'win32'
    ? child.toLowerCase().startsWith(prefix.toLowerCase())
    : child.startsWith(prefix)
}

/** SHA-256 of one operation's normalized input, for request replay checks. */
function inputHash(kind: ShadowRequestKind, input: Record<string, string | number>): string {
  const canonical = Object.keys(input).sort()
    .map((key) => {
      const value = input[key]
      return `${key}=${String(value)}`
    })
    .join('\u0000')
  return createHash('sha256').update(`${kind}\u0000${canonical}`).digest('hex')
}

/** The shadow router: binding store, cross-root delivery, and the Shadow tool whitelist. */
export class ShadowRouter extends Service {
  static inject = ['sessions', 'storageDomain', 'workspaceRegistry', 'agentBindings', 'agents']

  static Config: z<ShadowRouterConfig> = z.object({
    authorizedRoots: z.array(z.string()).default([]),
    controllerProfile: z.string().default('devframe'),
    // Optional face: schemastery omits an absent key and validates a present
    // string, so the declared id reaches the constructor only when configured.
    shadowSessionId: z.string(),
    maxPendingDeliveries: z.number().default(16),
    maxMessageChars: z.number().default(20_000),
    statusPageSize: z.number().default(20),
  })

  /** Validated config (schemastery applied the defaults before construction). */
  private readonly config: ResolvedConfig

  private bindingsTable?: KvTable<WorkspaceId, ShadowBindingRecord>
  private deliveriesTable?: KvTable<ShadowMessageId, ShadowDeliveryRecord>
  private requestsTable?: KvTable<string, ShadowRequestRecord>
  private readonly bindings = new Map<WorkspaceId, ShadowBindingRecord>()
  private readonly deliveries = new Map<ShadowMessageId, ShadowDeliveryRecord>()
  private readonly requests = new Map<string, ShadowRequestRecord>()
  /** Canonical authorized roots, resolved once at load; empty authorizes nothing. */
  private authorizedRoots: readonly string[] = []
  /** Session ids of host-designated Shadow sessions, mapped to their tool disposer. */
  private readonly shadowAgents = new Map<SessionId, () => void>()
  private tail: Promise<unknown> = Promise.resolve()

  /**
   * @param ctx - Mounting context.
   * @param config - Schema-validated config; limits must be positive safe integers.
   */
  constructor(ctx: Context, config: ShadowRouterConfig) {
    super(ctx, 'shadowRouter')
    // Schemastery fills the defaults before construction; the type does not encode that step.
    this.config = config as ResolvedConfig
    if (!Number.isSafeInteger(this.config.maxPendingDeliveries) || this.config.maxPendingDeliveries < 1) {
      throw new ShadowRouterError('maxPendingDeliveries must be a positive safe integer', 'SHADOW_INVALID_CONFIG')
    }
    if (!Number.isSafeInteger(this.config.maxMessageChars) || this.config.maxMessageChars < 1) {
      throw new ShadowRouterError('maxMessageChars must be a positive safe integer', 'SHADOW_INVALID_CONFIG')
    }
    if (!Number.isSafeInteger(this.config.statusPageSize) || this.config.statusPageSize < 1) {
      throw new ShadowRouterError('statusPageSize must be a positive safe integer', 'SHADOW_INVALID_CONFIG')
    }
    if (this.config.controllerProfile.length === 0 || this.config.controllerProfile !== this.config.controllerProfile.trim()) {
      throw new ShadowRouterError('controllerProfile must be a non-empty trimmed string', 'SHADOW_INVALID_CONFIG')
    }
    if (this.config.shadowSessionId !== undefined
      && (this.config.shadowSessionId.length === 0 || this.config.shadowSessionId !== this.config.shadowSessionId.trim())) {
      throw new ShadowRouterError('shadowSessionId must be a non-empty trimmed string when configured', 'SHADOW_INVALID_CONFIG')
    }
  }

  protected async [Service.init](): Promise<void> {
    await this.validateAuthorizedRoots()
    const domain = await this.ctx.storageDomain.open(shadowRouterDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'shadow-router.domainClose')
    this.bindingsTable = domain.table('bindings')
    this.deliveriesTable = domain.table('deliveries')
    this.requestsTable = domain.table('requests')
    // Cold restore: rebuild every index from the durable tables in stable
    // (createdAt, key) order. The maps hold detached frozen copies so the
    // durable rows stay untouched.
    for (const [id, record] of [...this.bindingsTable.entries()]
      .sort(([, left], [, right]) => left.createdAt.localeCompare(right.createdAt) || left.workspaceId.localeCompare(right.workspaceId))) {
      this.bindings.set(id, Object.freeze({ ...record }))
    }
    for (const [id, record] of [...this.deliveriesTable.entries()]
      .sort(([, left], [, right]) => left.createdAt.localeCompare(right.createdAt) || left.messageId.localeCompare(right.messageId))) {
      this.deliveries.set(id, Object.freeze({ ...record }))
    }
    for (const [id, record] of [...this.requestsTable.entries()]
      .sort(([, left], [, right]) => left.createdAt.localeCompare(right.createdAt) || left.requestId.localeCompare(right.requestId))) {
      this.requests.set(id, Object.freeze({ ...record }))
    }
    await this.reconcileProvisioningOnRestore()
    this.ctx.effect(() => this.ctx.on('agent/disposed', ({ agent }) => {
      const dispose = this.shadowAgents.get(agent.id)
      if (dispose !== undefined) {
        this.shadowAgents.delete(agent.id)
        dispose()
      }
    }), 'shadow-router.shadowAgentDispose')
    if (this.config.shadowSessionId !== undefined) {
      const shadowId = SessionId(this.config.shadowSessionId)
      // Declarative designation: mark immediately when the declared agent is
      // already live at activation (created before this mount), otherwise
      // when its `agent/created` arrives. `markShadow` is idempotent, so
      // both paths converge; an id that never becomes live installs nothing.
      const live = this.ctx.agents.get(shadowId)
      if (live !== undefined) this.markShadow(live)
      this.ctx.effect(() => this.ctx.on('agent/created', ({ agent }) => {
        if (agent.id === shadowId) this.markShadow(agent)
      }), 'shadow-router.shadowDesignation')
    }
  }

  /** Canonicalize every authorized root; a missing or relative entry fails the load. */
  private async validateAuthorizedRoots(): Promise<void> {
    const canonical: string[] = []
    for (const root of this.config.authorizedRoots) {
      if (!isAbsolute(root)) {
        throw new ShadowRouterError(`authorized root "${root}" must be an absolute path`, 'SHADOW_INVALID_CONFIG')
      }
      let resolved: string
      try {
        resolved = await realpath(root)
        if (!(await stat(resolved)).isDirectory()) throw new Error('not a directory')
      } catch (error: unknown) {
        throw new ShadowRouterError(
          `authorized root "${root}" must be an existing directory at load`,
          'SHADOW_INVALID_CONFIG',
          { cause: error },
        )
      }
      canonical.push(resolved)
    }
    this.authorizedRoots = canonical
  }

  /**
   * Cold-restore reconciliation for rows that were mid-provisioning when the
   * previous process ended. A reserved session that exists and matches the
   * row completes to `ready` (the bind is the role persistence); a mismatch
   * parks the project as `needs_attention`. A missing session stays as-is —
   * creating sessions during restore would be a side effect the host did not
   * ask for; the next `project_open` or {@link ShadowRouter.reconcileProject}
   * converges around the same reserved id.
   */
  private async reconcileProvisioningOnRestore(): Promise<void> {
    for (const record of this.bindings.values()) {
      if (record.state !== 'reserving' && record.state !== 'provisioning') continue
      const session = this.ctx.sessions.get(record.controllerSessionId)
      if (session === undefined) continue
      if (session.header.cwd === undefined || !samePath(session.header.cwd, record.canonicalPath)) {
        await this.markNeedsAttention(record, `controller session "${record.controllerSessionId}" cwd does not match the binding's canonical root`)
        continue
      }
      await this.completeProvisioning(record)
    }
  }

  // ---- Shadow whitelist --------------------------------------------------

  /**
   * Designate one live agent as the host's Shadow and install the four
   * project tools — and nothing else — into its scope. The host chooses the
   * profile; workers, leads, and reviewers are never marked, and marking is
   * idempotent.
   * @param agent - The live agent the host designates as Shadow.
   */
  markShadow(agent: Agent): void {
    if (this.shadowAgents.has(agent.id)) return
    this.shadowAgents.set(agent.id, installShadowTools(agent, this.ctx, this))
  }

  /**
   * Whether one agent is the designated Shadow.
   * @param agent - The agent to check, or `undefined` when the caller has no attached agent.
   * @returns true when the agent is currently designated as the host's Shadow; the predicate also narrows `agent` to `Agent`.
   */
  isShadow(agent: Agent | undefined): agent is Agent {
    return agent !== undefined && this.shadowAgents.has(agent.id)
  }

  /** The calling session must be the host-designated Shadow; the checked agent flows on. */
  private requireShadow(caller: Agent | undefined): Agent {
    if (!this.isShadow(caller)) {
      throw new ShadowRouterError('the calling session is not the designated Shadow router', 'SHADOW_CALLER_FORBIDDEN')
    }
    return caller
  }

  // ---- project_open ------------------------------------------------------

  /**
   * Open (or resolve) one project: canonicalize and authorize the root, reuse
   * the workspace registry's identity, and converge the controller binding —
   * reserving a controller session id and persisting the in-creation
   * association before the session exists. Repeated opens deduplicate; a
   * request id replayed with different input conflicts.
   * @param caller - The designated Shadow session.
   * @param request - Existing authorized path and stable request id.
   * @returns the controller association.
   */
  async openProject(caller: Agent | undefined, request: ProjectOpenRequest): Promise<ProjectOpenResult> {
    this.requireShadow(caller)
    const requestId = ShadowRequestId(request.requestId)
    if (typeof request.path !== 'string' || request.path.length === 0 || request.path !== request.path.trim()) {
      throw new ShadowRouterError('path must be a non-empty trimmed string', 'SHADOW_INVALID_REQUEST')
    }
    if (!isAbsolute(request.path)) {
      throw new ShadowRouterError(`path "${request.path}" must be absolute; nothing is created implicitly`, 'SHADOW_INVALID_REQUEST')
    }
    let canonical: string
    try {
      canonical = await realpath(request.path)
      if (!(await stat(canonical)).isDirectory()) throw new Error('not a directory')
    } catch (error: unknown) {
      throw new ShadowRouterError(
        `path "${request.path}" does not resolve to an existing directory`,
        'SHADOW_ROOT_MISSING',
        { cause: error },
      )
    }
    if (!this.authorizedRoots.some(root => isWithinPath(canonical, root))) {
      throw new ShadowRouterError(`root "${canonical}" is not covered by any authorized root`, 'SHADOW_ROOT_UNAUTHORIZED')
    }
    const workspace = await this.ctx.workspaceRegistry.create(canonical)
    return await this.enqueue(async () => {
      const replay = this.replayRequest('open', requestId, { path: canonical })
      if (replay !== undefined) return replay as ProjectOpenResult
      const existing = this.bindings.get(workspace.id)
      if (existing === undefined) {
        // Overlapping simultaneous writers are rejected segment-aware, against
        // every claimed root — a bare string prefix would confuse `D:\a` with
        // `D:\ab`, and this workspace's own row is checked by convergence.
        const overlapping = [...this.bindings.values()].find(
          claim => isWithinPath(canonical, claim.canonicalPath) || isWithinPath(claim.canonicalPath, canonical),
        )
        if (overlapping !== undefined) {
          throw new ShadowRouterError(
            `root "${canonical}" physically overlaps project "${overlapping.workspaceId}" at "${overlapping.canonicalPath}"`,
            'SHADOW_ROOTS_OVERLAP',
          )
        }
      }
      const record = existing !== undefined
        ? await this.convergeBinding(existing, requestId)
        : await this.provisionNewBinding(workspace.id, workspace.path, requestId)
      const result: ProjectOpenResult = {
        workspaceId: record.workspaceId,
        controllerSessionId: record.controllerSessionId,
        bindingRevision: record.bindingRevision,
        state: record.state,
        canonicalPath: record.canonicalPath,
      }
      await this.storeRequest('open', requestId, { path: canonical }, result)
      return result
    })
  }

  // ---- project_send ------------------------------------------------------

  /**
   * Deliver one bounded message to a project's controller. The delivery is
   * persisted twice on purpose: first as the sender intent (`queued`), then as
   * the target-accepted input (`received`). The receipt never claims
   * completion; `completed` is a separate durable state the controller side
   * settles via {@link ShadowRouter.completeDelivery}.
   * @param caller - The designated Shadow session.
   * @param request - Target workspace, asserted revision and work ownership, mode, and text.
   * @returns the delivery receipt.
   */
  async sendToProject(caller: Agent | undefined, request: ProjectSendRequest): Promise<ProjectSendResult> {
    const shadow = this.requireShadow(caller)
    const requestId = ShadowRequestId(request.requestId)
    const workspaceId = this.requireWorkspaceId(request.workspaceId)
    const acceptanceHash = AcceptanceHash(request.acceptanceHash)
    const goalId = GoalId(this.requireField(request.goalId, 'goalId'))
    if (request.mode !== 'work' && request.mode !== 'note') {
      throw new ShadowRouterError(`mode "${String(request.mode)}" must be "work" or "note"`, 'SHADOW_INVALID_REQUEST')
    }
    if (typeof request.text !== 'string' || request.text.length === 0 || request.text !== request.text.trim()) {
      throw new ShadowRouterError('text must be a non-empty trimmed string', 'SHADOW_INVALID_REQUEST')
    }
    if (request.text.length > this.config.maxMessageChars) {
      throw new ShadowRouterError(
        `text is ${request.text.length} chars; the limit is ${this.config.maxMessageChars}`,
        'SHADOW_MESSAGE_TOO_LARGE',
      )
    }
    if (!Number.isSafeInteger(request.bindingRevision) || request.bindingRevision < 1) {
      throw new ShadowRouterError('bindingRevision must be a positive safe integer', 'SHADOW_INVALID_REQUEST')
    }
    const sourceSessionId = shadow.id
    return await this.enqueue(async () => {
      const input = {
        workspaceId, bindingRevision: request.bindingRevision, goalId,
        acceptanceHash, mode: request.mode, text: request.text, source: sourceSessionId,
      }
      const replay = this.replayRequest('send', requestId, input)
      if (replay !== undefined) return replay as ProjectSendResult
      const binding = this.requireBinding(workspaceId)
      this.requireAdmitting(binding)
      if (binding.bindingRevision !== request.bindingRevision) {
        throw new ShadowRouterError(
          `bindingRevision ${request.bindingRevision} is stale; workspace "${workspaceId}" is at revision ${binding.bindingRevision}`,
          'SHADOW_STALE_REVISION',
        )
      }
      if (binding.activeGoalId === undefined) {
        throw new ShadowRouterError(
          `workspace "${workspaceId}" records no authorized open run; nothing can be delivered against one`,
          'SHADOW_GOAL_NOT_AUTHORIZED',
        )
      }
      if (binding.activeGoalId !== goalId || binding.activeAcceptanceHash !== acceptanceHash) {
        throw new ShadowRouterError(
          `the message's Goal/acceptance association does not match workspace "${workspaceId}"'s authorized open run; a previous Goal's message is never forwarded to the current Goal`,
          'SHADOW_GOAL_STALE',
        )
      }
      // Identity and ownership are fixed here, before first persistence, and
      // a retried request converges on the same message row.
      const messageId = ShadowMessageId(`msg-${requestId}`)
      const crashed = this.deliveries.get(messageId)
      if (crashed !== undefined) {
        this.assertSameDelivery(crashed, input)
      } else {
        // Queue and size limits apply to NEW input only, before it is accepted;
        // a crashed intent is converged, never re-admitted through the queue.
        const pending = [...this.deliveries.values()]
          .filter(record => record.workspaceId === workspaceId && record.state === 'queued').length
        if (pending >= this.config.maxPendingDeliveries) {
          throw new ShadowRouterError(
            `workspace "${workspaceId}" already holds ${pending} pending deliveries; the queue limit is ${this.config.maxPendingDeliveries}`,
            'SHADOW_QUEUE_FULL',
          )
        }
        const now = new Date().toISOString()
        const intent: ShadowDeliveryRecord = Object.freeze({
          messageId,
          requestId,
          sourceSessionId,
          workspaceId,
          bindingRevision: request.bindingRevision,
          goalId,
          acceptanceHash,
          mode: request.mode,
          text: request.text,
          state: 'queued',
          createdAt: now,
          updatedAt: now,
        })
        await this.persistDelivery(intent)
      }
      const current = this.requireDelivery(messageId)
      if (current.state === 'queued') await this.markDeliveryReceived(current)
      const result: ProjectSendResult = { messageId, workspaceId, status: 'received' }
      await this.storeRequest('send', requestId, input, result)
      return result
    })
  }

  // ---- project_stop ------------------------------------------------------

  /**
   * Stop one project in isolation: close its receiving, cancel its pending
   * deliveries (kept visible, never dropped), and park the binding in
   * `stopping` until the host confirms quiescence via
   * {@link ShadowRouter.confirmProjectStopped}. Other projects are untouched.
   * @param caller - The designated Shadow session.
   * @param request - Target workspace, asserted revision, and stable request id.
   * @returns the stop receipt.
   */
  async stopProject(caller: Agent | undefined, request: ProjectStopRequest): Promise<ProjectStopResult> {
    this.requireShadow(caller)
    const requestId = ShadowRequestId(request.requestId)
    const workspaceId = this.requireWorkspaceId(request.workspaceId)
    if (!Number.isSafeInteger(request.expectedRevision) || request.expectedRevision < 1) {
      throw new ShadowRouterError('expectedRevision must be a positive safe integer', 'SHADOW_INVALID_REQUEST')
    }
    return await this.enqueue(async () => {
      const replay = this.replayRequest('stop', requestId, { workspaceId, expectedRevision: request.expectedRevision })
      if (replay !== undefined) return replay as ProjectStopResult
      const binding = this.requireBinding(workspaceId)
      if (binding.state === 'stopped') {
        // An already-stopped project has nothing left to mutate, so the
        // repeat is safe regardless of the revision the caller asserts.
        const result: ProjectStopResult = {
          workspaceId, status: 'stopped', cancelledDeliveries: 0, bindingRevision: binding.bindingRevision,
        }
        await this.storeRequest('stop', requestId, { workspaceId, expectedRevision: request.expectedRevision }, result)
        return result
      }
      if (binding.state === 'stopping') {
        if (binding.bindingRevision !== request.expectedRevision) {
          throw new ShadowRouterError(
            `expectedRevision ${request.expectedRevision} is stale; workspace "${workspaceId}" is at revision ${binding.bindingRevision}`,
            'SHADOW_STALE_REVISION',
          )
        }
        const result: ProjectStopResult = {
          workspaceId, status: 'stopping', cancelledDeliveries: 0, bindingRevision: binding.bindingRevision,
        }
        await this.storeRequest('stop', requestId, { workspaceId, expectedRevision: request.expectedRevision }, result)
        return result
      }
      if (binding.bindingRevision !== request.expectedRevision) {
        throw new ShadowRouterError(
          `expectedRevision ${request.expectedRevision} is stale; workspace "${workspaceId}" is at revision ${binding.bindingRevision}`,
          'SHADOW_STALE_REVISION',
        )
      }
      const pending = [...this.deliveries.values()].filter(record =>
        record.workspaceId === workspaceId && record.state === 'queued')
      for (const record of pending) {
        await this.persistDelivery({ ...record, state: 'cancelled', cancelReason: 'project-stopped', updatedAt: new Date().toISOString() })
      }
      const stopped = await this.persistBinding({
        ...binding,
        state: 'stopping',
        bindingRevision: binding.bindingRevision + 1,
        updatedAt: new Date().toISOString(),
      })
      const result: ProjectStopResult = {
        workspaceId,
        status: 'stopping',
        cancelledDeliveries: pending.length,
        bindingRevision: stopped.bindingRevision,
      }
      await this.storeRequest('stop', requestId, { workspaceId, expectedRevision: request.expectedRevision }, result)
      return result
    })
  }

  // ---- project_status ----------------------------------------------------

  /**
   * Read one project or one bounded page of projects. The read never mutates
   * durable state, never appends a session event, and never wakes a model;
   * every row carries the observation instant, and a `received` receipt is
   * reported verbatim instead of being read as completion.
   * @param caller - The designated Shadow session.
   * @param request - Optional workspace id plus bounded page controls.
   * @returns the observed status.
   */
  async projectStatus(
    caller: Agent | undefined,
    request: { readonly workspaceId?: string; readonly cursor?: number; readonly limit?: number },
  ): Promise<ProjectStatusResult> {
    this.requireShadow(caller)
    const observedAt = new Date().toISOString()
    const limit = request.limit ?? this.config.statusPageSize
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > this.config.statusPageSize) {
      throw new ShadowRouterError(`limit must be an integer from 1 through ${this.config.statusPageSize}`, 'SHADOW_INVALID_REQUEST')
    }
    const cursor = request.cursor ?? 0
    if (!Number.isSafeInteger(cursor) || cursor < 0) {
      throw new ShadowRouterError('cursor must be a non-negative safe integer', 'SHADOW_INVALID_REQUEST')
    }
    const requested = request.workspaceId
    const ordered = [...this.bindings.values()].sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt) || left.workspaceId.localeCompare(right.workspaceId))
    const selected = requested === undefined
      ? ordered.slice(cursor, cursor + limit)
      : ordered.filter(record => record.workspaceId === this.requireWorkspaceId(requested))
    if (requested !== undefined && selected.length === 0) {
      throw new ShadowRouterError(`no controller binding exists for workspace "${requested}"`, 'SHADOW_WORKSPACE_UNKNOWN')
    }
    const projects = selected.map(record => this.projectEntry(record))
    const result: ProjectStatusResult = {
      projects,
      ...(requested === undefined && cursor + limit < ordered.length ? { nextCursor: cursor + limit } : {}),
      observedAt,
    }
    return result
  }

  // ---- host seams (never model-facing) -----------------------------------

  /**
   * Confirm one `stopping` project quiescent and finish its stop. The host
   * calls this once the project's own work has drained; no model tool does.
   * Already-stopped bindings resolve without writing.
   * @param workspaceId - The project whose stop completes.
   * @returns the stopped binding.
   */
  async confirmProjectStopped(workspaceId: WorkspaceId): Promise<ShadowBindingRecord> {
    return await this.enqueue(async () => {
      const binding = this.requireBinding(workspaceId)
      if (binding.state === 'stopped') return binding
      if (binding.state !== 'stopping') {
        throw new ShadowRouterError(
          `workspace "${workspaceId}" is ${binding.state}; confirmProjectStopped requires stopping`,
          'SHADOW_INVALID_REQUEST',
        )
      }
      return await this.persistBinding({ ...binding, state: 'stopped', updatedAt: new Date().toISOString() })
    })
  }

  /**
   * Record the workspace's authorized open run. Deliveries may only arrive
   * while the asserted Goal/acceptance association matches this record, which
   * is what keeps a previous Goal's message out of the controller's current
   * Goal. The host (controller side) calls this; no model tool reaches it.
   * @param workspaceId - The project to authorize the run for.
   * @param goalId - The authorized Goal.
   * @param acceptanceHash - The authorized acceptance association.
   * @returns the updated binding.
   */
  async setActiveGoal(workspaceId: WorkspaceId, goalId: string, acceptanceHash: string): Promise<ShadowBindingRecord> {
    return await this.enqueue(async () => {
      const binding = this.requireBinding(workspaceId)
      this.requireAdmitting(binding)
      return await this.persistBinding({
        ...binding,
        activeGoalId: this.requireField(goalId, 'goalId'),
        activeAcceptanceHash: AcceptanceHash(acceptanceHash),
        bindingRevision: binding.bindingRevision + 1,
        updatedAt: new Date().toISOString(),
      })
    })
  }

  /**
   * Settle one received delivery as completed. `completed` is a controller
   * side durable fact, distinct from the `received` receipt; the host calls
   * this, and no model tool does. A receiver that is `stopping` or `stopped`
   * cannot settle: the call rejects with `SHADOW_RECEIVER_CLOSED` and the row
   * stays `received`.
   * @param workspaceId - The project the delivery belongs to.
   * @param messageId - The delivery to settle.
   * @returns the updated delivery.
   */
  async completeDelivery(workspaceId: WorkspaceId, messageId: ShadowMessageId): Promise<ShadowDeliveryRecord> {
    return await this.enqueue(async () => {
      const delivery = this.requireDelivery(messageId)
      if (delivery.workspaceId !== workspaceId) {
        throw new ShadowRouterError(`delivery "${messageId}" does not belong to workspace "${workspaceId}"`, 'SHADOW_INVALID_REQUEST')
      }
      if (delivery.state !== 'received') {
        throw new ShadowRouterError(
          `delivery "${messageId}" is ${delivery.state}; only a received delivery can complete`,
          'SHADOW_INVALID_REQUEST',
        )
      }
      const binding = this.requireBinding(delivery.workspaceId)
      if (binding.state === 'stopping' || binding.state === 'stopped') {
        throw new ShadowRouterError(
          `workspace "${delivery.workspaceId}" is ${binding.state}; a ${binding.state} receiver cannot settle deliveries`,
          'SHADOW_RECEIVER_CLOSED',
        )
      }
      return await this.persistDelivery({
        ...delivery,
        state: 'completed',
        completedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    })
  }

  /**
   * Converge one workspace's queued deliveries after a restart or a Goal
   * switch: a still-authorized delivery becomes `received`; a stale one is
   * cancelled with a visible reason instead of being forwarded to a Goal it
   * was never bound to.
   * @param workspaceId - One project, or omitted for every project.
   * @returns the converged deliveries.
   */
  async recoverDeliveries(workspaceId?: WorkspaceId): Promise<readonly ShadowDeliveryRecord[]> {
    return await this.enqueue(async () => {
      const converged: ShadowDeliveryRecord[] = []
      for (const record of [...this.deliveries.values()].sort((left, right) =>
        left.createdAt.localeCompare(right.createdAt) || left.messageId.localeCompare(right.messageId))) {
        if (record.state !== 'queued') continue
        if (workspaceId !== undefined && record.workspaceId !== workspaceId) continue
        const binding = this.bindings.get(record.workspaceId)
        const authorized = binding !== undefined
          && binding.state === 'ready'
          && binding.activeGoalId === record.goalId
          && binding.activeAcceptanceHash === record.acceptanceHash
          && this.ctx.sessions.get(binding.controllerSessionId) !== undefined
        converged.push(authorized
          ? await this.markDeliveryReceived(record)
          : await this.persistDelivery({
            ...record,
            state: 'cancelled',
            cancelReason: binding === undefined
              ? 'binding-unknown'
              : binding.state !== 'ready'
                ? `binding-${binding.state}`
                : 'goal-no-longer-authorized',
            updatedAt: new Date().toISOString(),
          }))
      }
      return converged
    })
  }

  /**
   * Converge one workspace's provisioning row around its reserved session id:
   * create the reserved session when it is still missing, complete the bind
   * when the session matches, and park mismatches as `needs_attention`. The
   * host calls this after a restart; `project_open` runs it implicitly.
   * @param workspaceId - The project to converge.
   * @returns the converged binding.
   */
  async reconcileProject(workspaceId: WorkspaceId): Promise<ShadowBindingRecord> {
    return await this.enqueue(async () => {
      const binding = this.requireBinding(workspaceId)
      if (binding.state !== 'reserving' && binding.state !== 'provisioning' && binding.state !== 'failed') return binding
      return await this.convergeBinding(binding, ShadowRequestId(binding.requestId))
    })
  }

  /**
   * Read one binding from the restored index.
   * @param workspaceId - The project whose binding to read.
   * @returns the binding record, or `undefined` when the workspace has no binding.
   */
  findBinding(workspaceId: WorkspaceId): ShadowBindingRecord | undefined {
    return this.bindings.get(workspaceId)
  }

  /**
   * Read every binding in stable (createdAt, workspaceId) order.
   * @returns every binding record in the index.
   */
  listBindings(): readonly ShadowBindingRecord[] {
    return [...this.bindings.values()].sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt) || left.workspaceId.localeCompare(right.workspaceId))
  }

  /**
   * Read every delivery of one project (or all projects), oldest first.
   * @param workspaceId - Limits the result to one project; omit it to read every recorded delivery.
   * @returns the matching delivery records in stable (createdAt, messageId) order.
   */
  listDeliveries(workspaceId?: WorkspaceId): readonly ShadowDeliveryRecord[] {
    return [...this.deliveries.values()]
      .filter(record => workspaceId === undefined || record.workspaceId === workspaceId)
      .sort((left, right) =>
        left.createdAt.localeCompare(right.createdAt) || left.messageId.localeCompare(right.messageId))
  }

  /**
   * Read the host-facing aggregate status: the configured Shadow designation,
   * its liveness, the canonical authorized roots, and every binding row. The
   * read is synchronous and side-effect free, and never model-facing — host
   * status surfaces (the Web Shadow card) consume it through the Shadow
   * controller, so it carries no Shadow-caller gate and no page bounds.
   * @returns the aggregate status snapshot.
   */
  readStatus(): ShadowRouterStatus {
    const configured = this.config.shadowSessionId
    return {
      ...(configured === undefined ? {} : { shadowSessionId: configured }),
      shadowLive: configured !== undefined && this.shadowAgents.has(SessionId(configured)),
      authorizedRoots: [...this.authorizedRoots],
      bindings: this.listBindings().map(record => ({
        workspaceId: record.workspaceId,
        canonicalPath: record.canonicalPath,
        bindingRevision: record.bindingRevision,
        state: record.state,
      })),
    }
  }

  // ---- internals ---------------------------------------------------------

  /** Serialize mutations so concurrent routing operations cannot interleave. */
  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.tail.then(operation, operation)
    this.tail = run.then(() => undefined, () => undefined)
    return run
  }

  /** The workspace id from the tool boundary: validated here, branded by the registry's own factory. */
  private requireWorkspaceId(value: string): WorkspaceId {
    return WorkspaceId(this.requireField(value, 'workspaceId'))
  }

  /** Require one non-empty trimmed field or fail loud. */
  private requireField(value: string, field: string): string {
    if (typeof value !== 'string' || value.length === 0 || value !== value.trim()) {
      throw new ShadowRouterError(`${field} must be a non-empty trimmed string`, 'SHADOW_INVALID_REQUEST')
    }
    return value
  }

  /** The binding, or a loud unknown-workspace failure. */
  private requireBinding(workspaceId: WorkspaceId): ShadowBindingRecord {
    const record = this.bindings.get(workspaceId)
    if (record === undefined) {
      throw new ShadowRouterError(`no controller binding exists for workspace "${workspaceId}"`, 'SHADOW_WORKSPACE_UNKNOWN')
    }
    return record
  }

  /** The delivery, or a loud unknown-delivery failure. */
  private requireDelivery(messageId: ShadowMessageId): ShadowDeliveryRecord {
    const record = this.deliveries.get(messageId)
    if (record === undefined) {
      throw new ShadowRouterError(`no delivery exists for message "${messageId}"`, 'SHADOW_INVALID_REQUEST')
    }
    return record
  }

  /** Deliveries are admitted only while the project is `ready`. */
  private requireAdmitting(binding: ShadowBindingRecord): void {
    if (!ADMITTING_STATES.includes(binding.state)) {
      const code = binding.state === 'needs_attention' ? 'SHADOW_NEEDS_ATTENTION' : 'SHADOW_RECEIVER_CLOSED'
      throw new ShadowRouterError(
        `workspace "${binding.workspaceId}" is ${binding.state} and does not admit deliveries`,
        code,
      )
    }
  }

  /** Replay a stored result for one request id, or conflict on different input. */
  private replayRequest(kind: ShadowRequestKind, requestId: ShadowRequestId, input: Record<string, string | number>): unknown {
    const stored = this.requests.get(requestId)
    if (stored === undefined) return undefined
    const hash = inputHash(kind, input)
    if (stored.kind !== kind || stored.inputHash !== hash) {
      throw new ShadowRouterError(
        `requestId "${requestId}" was already used with different input`,
        'SHADOW_REQUEST_CONFLICT',
      )
    }
    return stored.result
  }

  /** Persist one successful request result for replay. */
  private async storeRequest(
    kind: ShadowRequestKind,
    requestId: ShadowRequestId,
    input: Record<string, string | number>,
    result: unknown,
  ): Promise<void> {
    const record: ShadowRequestRecord = Object.freeze({
      requestId,
      kind,
      inputHash: inputHash(kind, input),
      result,
      createdAt: new Date().toISOString(),
    })
    await this.persistRequest(record)
  }

  /**
   * Converge an existing row: `ready` (and the profile pin) is returned as
   *-is, terminal rows are rejected, `failed` rows may re-provision after the
   * old reservation is proven gone, and mid-provisioning rows reconcile
   * around their reserved session id — never by minting a second writer.
   */
  private async convergeBinding(record: ShadowBindingRecord, requestId: ShadowRequestId): Promise<ShadowBindingRecord> {
    switch (record.state) {
      case 'ready': {
        if (record.profileKey !== this.config.controllerProfile) {
          throw new ShadowRouterError(
            `workspace "${record.workspaceId}" is bound to profile "${record.profileKey}", not "${this.config.controllerProfile}"`,
            'SHADOW_PROFILE_CONFLICT',
          )
        }
        return record
      }
      case 'stopping':
      case 'stopped':
        throw new ShadowRouterError(
          `workspace "${record.workspaceId}" is ${record.state}; restart follows the host recovery policy`,
          'SHADOW_PROJECT_STOPPED',
        )
      case 'needs_attention':
        throw new ShadowRouterError(
          `workspace "${record.workspaceId}" needs attention: ${record.failureReason ?? 'unspecified'}`,
          'SHADOW_NEEDS_ATTENTION',
        )
      case 'failed': {
        const reserved = this.ctx.sessions.get(record.controllerSessionId)
        if (reserved !== undefined) {
          // The reserved session came to exist after all; converge around it
          // instead of minting a replacement writer.
          return await this.reconcileReserved(record)
        }
        return await this.provisionNewBinding(record.workspaceId, record.canonicalPath, requestId)
      }
      case 'reserving':
      case 'provisioning':
        return await this.reconcileReserved(record)
    }
  }

  /**
   * Reconcile one mid-provisioning or failed-with-live-reservation row around
   * its reserved controller session id: complete to `ready` when the session
   * matches the row, park it as `needs_attention` when it does not, and
   * create the still-missing session on the SAME reserved id otherwise.
   */
  private async reconcileReserved(record: ShadowBindingRecord): Promise<ShadowBindingRecord> {
    const session = this.ctx.sessions.get(record.controllerSessionId)
    if (session !== undefined) {
      if (session.header.cwd === undefined || !samePath(session.header.cwd, record.canonicalPath)) {
        return await this.markNeedsAttention(
          record,
          `controller session "${record.controllerSessionId}" cwd does not match the binding's canonical root`,
        )
      }
      return await this.completeProvisioning(record)
    }
    await this.createControllerSession(record)
    return await this.completeProvisioning(record)
  }

  /** Reserve (or, after a failure, re-reserve) the binding row before any session exists. */
  private async reserveBinding(workspaceId: WorkspaceId, canonicalPath: string, requestId: ShadowRequestId): Promise<ShadowBindingRecord> {
    const existing = this.bindings.get(workspaceId)
    const controllerSessionId = SessionId(`shadow-${randomUUID()}`)
    const now = new Date().toISOString()
    const record: ShadowBindingRecord = Object.freeze({
      workspaceId,
      canonicalPath,
      controllerSessionId,
      profileKey: this.config.controllerProfile,
      bindingRevision: existing === undefined ? 1 : existing.bindingRevision + 1,
      requestId,
      state: 'reserving',
      createdAt: existing === undefined ? now : existing.createdAt,
      updatedAt: now,
    })
    return await this.persistBinding(record)
  }

  /**
   * Run one fresh binding through its full provisioning: reserve, create the
   * reserved controller root session, persist the controller role, and land
   * `ready` — the same persistence order a crash-residue recovery follows.
   */
  private async provisionNewBinding(
    workspaceId: WorkspaceId,
    canonicalPath: string,
    requestId: ShadowRequestId,
  ): Promise<ShadowBindingRecord> {
    const reserved = await this.reserveBinding(workspaceId, canonicalPath, requestId)
    await this.createControllerSession(reserved)
    return await this.completeProvisioning({ ...reserved, state: 'provisioning' })
  }

  /**
   * Run one provisioning attempt: mark the row in-creation, create the
   * reserved controller root session (never parented to Shadow), persist the
   * controller role through the session-identity registry, and only then save
   * `ready`. A creation failure rolls the row to a visible `failed` state.
   */
  private async createControllerSession(record: ShadowBindingRecord): Promise<Session> {
    await this.persistBinding({ ...record, state: 'provisioning', updatedAt: new Date().toISOString() })
    try {
      return this.ctx.sessions.create(record.controllerSessionId, {
        meta: { cwd: record.canonicalPath, agentPreset: this.config.controllerProfile },
      })
    } catch (error: unknown) {
      await this.markFailed(record, `the session store rejected the controller creation: ${String(error)}`)
      throw new ShadowRouterError(
        `the controller session for workspace "${record.workspaceId}" could not be created`,
        'SHADOW_INVALID_REQUEST',
        { cause: error },
      )
    }
  }

  /** Finish provisioning: persist the controller role and only then `ready`. */
  private async completeProvisioning(record: ShadowBindingRecord): Promise<ShadowBindingRecord> {
    try {
      await this.ctx.agentBindings.bind({ agentId: record.controllerSessionId, role: 'controller' })
    } catch (error: unknown) {
      return await this.markNeedsAttention(
        record,
        `the controller role for "${record.controllerSessionId}" could not be persisted: ${String(error)}`,
      )
    }
    return await this.persistBinding({ ...record, state: 'ready', updatedAt: new Date().toISOString() })
  }

  /** Park one binding as `needs_attention`; the durable reason explains what the host must resolve. */
  private async markNeedsAttention(record: ShadowBindingRecord, reason: string): Promise<ShadowBindingRecord> {
    return await this.persistBinding({
      ...record,
      state: 'needs_attention',
      failureReason: reason,
      updatedAt: new Date().toISOString(),
    })
  }

  /** Roll a failed provisioning attempt to a visible `failed` row. */
  private async markFailed(record: ShadowBindingRecord, reason: string): Promise<ShadowBindingRecord> {
    return await this.persistBinding({
      ...record,
      state: 'failed',
      failureReason: reason,
      updatedAt: new Date().toISOString(),
    })
  }

  /** Mark one queued delivery received (durable target acceptance). */
  private async markDeliveryReceived(record: ShadowDeliveryRecord): Promise<ShadowDeliveryRecord> {
    const now = new Date().toISOString()
    return await this.persistDelivery({
      ...record,
      state: 'received',
      receivedAt: now,
      updatedAt: now,
    })
  }

  /** Assert a crashed delivery row carries the retried request's exact ownership. */
  private assertSameDelivery(record: ShadowDeliveryRecord, input: Record<string, string | number>): void {
    const matches = record.workspaceId === input.workspaceId
      && record.bindingRevision === input.bindingRevision
      && record.goalId === input.goalId
      && record.acceptanceHash === input.acceptanceHash
      && record.mode === input.mode
      && record.text === input.text
      && record.sourceSessionId === input.source
    if (!matches) {
      throw new ShadowRouterError(
        `message "${record.messageId}" already exists with different content`,
        'SHADOW_REQUEST_CONFLICT',
      )
    }
  }

  /** Build one bounded status row from durable state plus live-session presence. */
  private projectEntry(record: ShadowBindingRecord): ProjectStatusEntry {
    const all = this.listDeliveries(record.workspaceId)
    const page = all.slice(0, this.config.statusPageSize)
    const blockedReason = record.state === 'needs_attention'
      ? record.failureReason ?? 'the project needs attention'
      : record.state === 'stopping'
        ? 'stop requested; quiescence confirmation is pending'
        : undefined
    return {
      workspaceId: record.workspaceId,
      canonicalPath: record.canonicalPath,
      controllerSessionId: record.controllerSessionId,
      controllerLive: this.ctx.sessions.get(record.controllerSessionId) !== undefined,
      profileKey: record.profileKey,
      bindingRevision: record.bindingRevision,
      state: record.state,
      ...(record.failureReason === undefined ? {} : { failureReason: record.failureReason }),
      ...(record.activeGoalId === undefined ? {} : { activeGoalId: record.activeGoalId }),
      ...(blockedReason === undefined ? {} : { blockedReason }),
      deliveries: page.map(delivery => this.deliverySummary(delivery)),
      deliveriesTruncated: all.length > page.length,
    }
  }

  /** Project one delivery row into its bounded summary. */
  private deliverySummary(record: ShadowDeliveryRecord): ProjectDeliverySummary {
    return {
      messageId: record.messageId,
      mode: record.mode,
      goalId: record.goalId,
      state: record.state,
      createdAt: record.createdAt,
      ...(record.receivedAt === undefined ? {} : { receivedAt: record.receivedAt }),
      ...(record.completedAt === undefined ? {} : { completedAt: record.completedAt }),
      ...(record.cancelReason === undefined ? {} : { cancelReason: record.cancelReason }),
    }
  }

  /** Write one binding through to the durable table, then mirror it into the index. */
  private async persistBinding(record: ShadowBindingRecord): Promise<ShadowBindingRecord> {
    const frozen = Object.freeze(record)
    try {
      await this.requireBindingsTable().put(frozen.workspaceId, frozen)
    } catch (error: unknown) {
      throw new ShadowRouterError(
        `binding for workspace "${frozen.workspaceId}" could not be persisted`,
        'SHADOW_PERSISTENCE',
        { cause: error },
      )
    }
    this.bindings.set(frozen.workspaceId, frozen)
    return frozen
  }

  /** Write one delivery through to the durable table, then mirror it into the index. */
  private async persistDelivery(record: ShadowDeliveryRecord): Promise<ShadowDeliveryRecord> {
    const frozen = Object.freeze(record)
    try {
      await this.requireDeliveriesTable().put(frozen.messageId, frozen)
    } catch (error: unknown) {
      throw new ShadowRouterError(
        `delivery "${frozen.messageId}" could not be persisted`,
        'SHADOW_PERSISTENCE',
        { cause: error },
      )
    }
    this.deliveries.set(frozen.messageId, frozen)
    return frozen
  }

  /** Write one request result through to the durable table, then mirror it into the index. */
  private async persistRequest(record: ShadowRequestRecord): Promise<void> {
    const frozen = Object.freeze(record)
    try {
      await this.requireRequestsTable().put(frozen.requestId, frozen)
    } catch (error: unknown) {
      throw new ShadowRouterError(
        `request "${frozen.requestId}" result could not be persisted`,
        'SHADOW_PERSISTENCE',
        { cause: error },
      )
    }
    this.requests.set(frozen.requestId, frozen)
  }

  /** The opened bindings table; absent only before Service.init completed. */
  private requireBindingsTable(): KvTable<WorkspaceId, ShadowBindingRecord> {
    if (this.bindingsTable === undefined) {
      throw new ShadowRouterError('the shadow_router domain is not open yet', 'SHADOW_PERSISTENCE')
    }
    return this.bindingsTable
  }

  /** The opened deliveries table; absent only before Service.init completed. */
  private requireDeliveriesTable(): KvTable<ShadowMessageId, ShadowDeliveryRecord> {
    if (this.deliveriesTable === undefined) {
      throw new ShadowRouterError('the shadow_router domain is not open yet', 'SHADOW_PERSISTENCE')
    }
    return this.deliveriesTable
  }

  /** The opened requests table; absent only before Service.init completed. */
  private requireRequestsTable(): KvTable<string, ShadowRequestRecord> {
    if (this.requestsTable === undefined) {
      throw new ShadowRouterError('the shadow_router domain is not open yet', 'SHADOW_PERSISTENCE')
    }
    return this.requestsTable
  }
}
