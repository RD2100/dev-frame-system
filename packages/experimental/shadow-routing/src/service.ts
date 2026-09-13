/**
 * Service Definition for the shadow routing capability seam (`ctx.shadowRouter`):
 * the abstract router contract the family compiles against — controller
 * binding lifecycle, cross-root delivery with distinct `received` and
 * `completed` durable states, the request replay read face, and the
 * `shadow/delivery-received` observe-only event. Persistence, the durable
 * domain, provisioning side effects, and the model-facing tool whitelist
 * belong to the Service Provider (`@deepseek-ai/dsh-experimental-shadow-router`);
 * event-driven forwarding belongs to Consumers.
 * @module @deepseek-ai/dsh-experimental-shadow-routing/service
 */

import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { ShadowMessageId } from './ids.ts'
import type {
  ProjectOpenRequest,
  ProjectOpenResult,
  ProjectSendRequest,
  ProjectSendResult,
  ProjectStatusResult,
  ProjectStopRequest,
  ProjectStopResult,
  ShadowBindingRecord,
  ShadowDeliveryRecord,
  ShadowRouterStatus,
} from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** The mounted shadow router: binding store, delivery persistence, and the Shadow whitelist. */
    shadowRouter: ShadowRouter
  }

  interface Events {
    /**
     * One delivery entered `received` — the durable target-acceptance
     * transition. Observe-only: listeners forward or record the accepted
     * input, but the router's durable rows stay the only authority, and the
     * event never exposes a mutation verb. A listener mounted after the
     * transition (or a process restart) still converges through the
     * provider's recovery and index reads.
     * @param workspaceId - The project the delivery belongs to.
     * @param delivery - The frozen delivery record snapshot as it entered `received`.
     * @mode emit
     */
    'shadow/delivery-received'(workspaceId: WorkspaceId, delivery: ShadowDeliveryRecord): void
  }
}

/**
 * Abstract shadow router service. Subclass, implement the abstract methods,
 * and load the subclass as a plugin — it registers as `ctx.shadowRouter`
 * (one implementation per context; loading a second throws, which is cordis'
 * standard duplicate-service behavior).
 *
 * Implementations must honor these semantics:
 * - Every routing mutation is serialized on one operation chain and written
 *   through to the implementation's durable authority, so the durable rows
 *   stay the only record of truth and the in-memory index is a projection.
 * - {@link sendToProject} persists the delivery twice on purpose: first as
 *   the sender intent (`queued`), then as the target-accepted input
 *   (`received`) — and emits {@link Events['shadow/delivery-received']} at
 *   that transition, exactly once per real conversion, after the durable
 *   write commits. `completed` stays a separate durable state the
 *   controller side settles via {@link completeDelivery}.
 * - Recovery convergence ({@link recoverDeliveries}) that lands a queued row
 *   on `received` is the same transition and emits the same event, so
 *   event-driven consumers do not miss recovered work.
 */
export abstract class ShadowRouter extends Service {
  constructor(ctx: Context) {
    super(ctx, 'shadowRouter')
  }

  /**
   * Designate one live agent as the host's Shadow and install the four
   * project tools — and nothing else — into its scope. The host chooses the
   * profile; workers, leads, and reviewers are never marked, and marking is
   * idempotent.
   * @param agent - The live agent the host designates as Shadow.
   */
  abstract markShadow(agent: Agent): void

  /**
   * Whether one agent is the designated Shadow.
   * @param agent - The agent to check, or `undefined` when the caller has no attached agent.
   * @returns true when the agent is currently designated as the host's Shadow; the predicate also narrows `agent` to `Agent`.
   */
  abstract isShadow(agent: Agent | undefined): agent is Agent

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
  abstract openProject(caller: Agent | undefined, request: ProjectOpenRequest): Promise<ProjectOpenResult>

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
  abstract sendToProject(caller: Agent | undefined, request: ProjectSendRequest): Promise<ProjectSendResult>

  /**
   * Stop one project in isolation: close its receiving, cancel its pending
   * deliveries (kept visible, never dropped), and park the binding in
   * `stopping` until the host confirms quiescence via
   * {@link ShadowRouter.confirmProjectStopped}. Other projects are untouched.
   * @param caller - The designated Shadow session.
   * @param request - Target workspace, asserted revision, and stable request id.
   * @returns the stop receipt.
   */
  abstract stopProject(caller: Agent | undefined, request: ProjectStopRequest): Promise<ProjectStopResult>

  /**
   * Read one project or one bounded page of projects. The read never mutates
   * durable state, never appends a session event, and never wakes a model;
   * every row carries the observation instant, and a `received` receipt is
   * reported verbatim instead of being read as completion.
   * @param caller - The designated Shadow session.
   * @param request - Optional workspace id plus bounded page controls.
   * @returns the observed status.
   */
  abstract projectStatus(
    caller: Agent | undefined,
    request: { readonly workspaceId?: string; readonly cursor?: number; readonly limit?: number },
  ): Promise<ProjectStatusResult>

  /**
   * Confirm one `stopping` project quiescent and finish its stop. The host
   * calls this once the project's own work has drained; no model tool does.
   * Already-stopped bindings resolve without writing.
   * @param workspaceId - The project whose stop completes.
   * @returns the stopped binding.
   */
  abstract confirmProjectStopped(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

  /**
   * Host-plane open: the same gated flow the `project_open` tool path runs,
   * driven by the designated Shadow's authority for host status surfaces (the
   * Web Shadow card) and the Shadow conversation's `shadow_open_project`
   * tool. Path canonicalization, authorization, replay, and provisioning are
   * identical to the tool path. A human-initiated open is the authorization
   * action: when the open lands `ready` and the binding records no authorized
   * open run, the bridge records one — the model-facing tool path never
   * self-authorizes.
   * @param request - Existing authorized path and stable request id.
   * @returns the controller association.
   */
  abstract openProjectForHost(request: ProjectOpenRequest): Promise<ProjectOpenResult>

  /**
   * Host-plane delivery: one `work` message to a project's controller through
   * the same delivery channel the `project_send` tool runs, with the binding's
   * current revision and authorized open run supplied by the router itself.
   * @param request - Target workspace, bounded message text, and stable request id.
   * @returns the delivery receipt.
   */
  abstract sendToProjectForHost(
    request: { readonly workspaceId: string; readonly text: string; readonly requestId: string },
  ): Promise<ProjectSendResult>

  /**
   * Host-plane release: stop the project through the same gated flow the
   * `project_stop` tool runs and confirm quiescence in one step, so the
   * host surface's release closes the project instead of parking it
   * mid-stop. Pending deliveries stay visible as cancelled.
   * @param request - Target workspace and stable request id.
   * @returns the stop receipt; `status` reflects the completed stop.
   */
  abstract releaseProjectForHost(
    request: { readonly workspaceId: string; readonly requestId: string },
  ): Promise<ProjectStopResult>

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
  abstract setActiveGoal(workspaceId: WorkspaceId, goalId: string, acceptanceHash: string): Promise<ShadowBindingRecord>

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
  abstract completeDelivery(workspaceId: WorkspaceId, messageId: ShadowMessageId): Promise<ShadowDeliveryRecord>

  /**
   * Converge one workspace's queued deliveries after a restart or a Goal
   * switch: a still-authorized delivery becomes `received`; a stale one is
   * cancelled with a visible reason instead of being forwarded to a Goal it
   * was never bound to.
   * @param workspaceId - One project, or omitted for every project.
   * @returns the converged deliveries.
   */
  abstract recoverDeliveries(workspaceId?: WorkspaceId): Promise<readonly ShadowDeliveryRecord[]>

  /**
   * Converge one workspace's provisioning row around its reserved session id:
   * create the reserved session when it is still missing, complete the bind
   * when the session matches, and park mismatches as `needs_attention`. The
   * host calls this after a restart; `project_open` runs it implicitly.
   * @param workspaceId - The project to converge.
   * @returns the converged binding.
   */
  abstract reconcileProject(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

  /**
   * Read one binding from the restored index.
   * @param workspaceId - The project whose binding to read.
   * @returns the binding record, or `undefined` when the workspace has no binding.
   */
  abstract findBinding(workspaceId: WorkspaceId): ShadowBindingRecord | undefined

  /**
   * Read every binding in stable (createdAt, workspaceId) order.
   * @returns every binding record in the index.
   */
  abstract listBindings(): readonly ShadowBindingRecord[]

  /**
   * Read every delivery of one project (or all projects), oldest first.
   * @param workspaceId - Limits the result to one project; omit it to read every recorded delivery.
   * @returns the matching delivery records in stable (createdAt, messageId) order.
   */
  abstract listDeliveries(workspaceId?: WorkspaceId): readonly ShadowDeliveryRecord[]

  /**
   * Read the host-facing aggregate status: the configured Shadow designation,
   * its liveness, the canonical authorized roots, and every binding row. The
   * read is synchronous and side-effect free, and never model-facing — host
   * status surfaces (the Web Shadow card) consume it through the Shadow
   * controller, so it carries no Shadow-caller gate and no page bounds.
   * @returns the aggregate status snapshot.
   */
  abstract readStatus(): ShadowRouterStatus

  /**
   * Emit {@link Events['shadow/delivery-received']} while containing and
   * logging each listener failure: an observe-only event must never turn a
   * broken consumer into a routing failure.
   * @param workspaceId - The project the delivery belongs to.
   * @param delivery - The frozen delivery record snapshot as it entered `received`.
   */
  protected emitDeliveryReceived(workspaceId: WorkspaceId, delivery: ShadowDeliveryRecord): void {
    for (const callback of this.ctx.events.dispatch('emit', ['shadow/delivery-received', workspaceId, delivery])) {
      try {
        const returned: unknown = (callback as (...payload: unknown[]) => unknown)(workspaceId, delivery)
        void Promise.resolve(returned).catch((error: unknown) => {
          this.ctx.logger.warn(`shadow: shadow/delivery-received listener rejected: ${renderListenerError(error)}`)
        })
      } catch (error: unknown) {
        this.ctx.logger.warn(`shadow: shadow/delivery-received listener threw: ${renderListenerError(error)}`)
      }
    }
  }
}

/**
 * Render any thrown value without violating listener containment.
 * @param error - any thrown value.
 * @returns `String(error)`, or a fixed label when even coercion throws.
 */
function renderListenerError(error: unknown): string {
  try {
    return String(error)
  } catch {
    // String coercion itself may throw.
    return '[unrenderable thrown value]'
  }
}

export default ShadowRouter
