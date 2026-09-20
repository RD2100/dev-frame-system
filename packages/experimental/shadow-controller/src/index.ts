/**
 * Host Remote owner of the `shadow` namespace. One honest read (the aggregate
 * {@link ShadowRouterStatus} snapshot), three write faces the Web Shadow
 * card's panel drives (open a project, deliver one `work` message to a
 * project's controller, release/stop a project), and the conversation faces
 * the human's chat surface drives: post one message into the designated
 * Shadow session and read the conversation surface back. The project writes
 * delegate to shadow-router host bridges, so validation, the caller gate
 * (riding the designated Shadow's authority), replay, and the delivery
 * channel stay the router's own; request ids are minted here because each
 * panel action is one fresh intent. The conversation faces delegate to the
 * {@link ShadowAgent} host, which owns the persistent session. The controller
 * stays registered when the deployment mounts no shadow router or
 * conversation host: the read answers `mounted: false` and every other verb
 * fails loud, so a surface renders the honest disabled state instead of a
 * transport failure. Nothing here wakes a model directly — only the
 * conversation host's agent loop does.
 *
 * @module @deepseek-ai/dsh-experimental-shadow-controller
 */

import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
// The router service type and the receipts are the abstract seam contract of the Service Definition.
import type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowRouter,
} from '@deepseek-ai/dsh-experimental-shadow-routing'
import type {
  ShadowApproveTaskInput,
  ShadowApproveTaskResult,
  ShadowConversationAccepted,
  ShadowConversationPage,
  ShadowConversationPostInput,
  ShadowConversationReadInput,
  ShadowProjectOpenInput,
  ShadowProjectReleaseInput,
  ShadowProjectSendInput,
  ShadowRejectTaskInput,
  ShadowRejectTaskResult,
  ShadowStatusView,
} from './types.ts'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowAgent } from './shadow-agent.ts'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe'
import { resolveTaskStartAuthority, taskStartUnchanged } from '@deepseek-ai/dsh-experimental-project-controller'
import type {} from '@deepseek-ai/dsh-experimental-project-controller/delivery-consumer'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'

export type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowApproveTaskInput,
  ShadowApproveTaskResult,
  ShadowConversationAccepted,
  ShadowConversationMessage,
  ShadowConversationPage,
  ShadowRejectTaskInput,
  ShadowRejectTaskResult,
  ShadowConversationPostInput,
  ShadowConversationReadInput,
  ShadowProjectOpenInput,
  ShadowProjectReleaseInput,
  ShadowProjectSendInput,
  ShadowRouterStatus,
  ShadowStatusView,
} from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host owner of the `shadow` Remote namespace. */
    shadowController: ShadowController
  }
}

/**
 * Host service backing the generated `ctx.remote.shadow` namespace. The read
 * never mutates router state; every write runs through the router's host
 * bridges under the designated Shadow's authority, and the conversation verbs
 * run through the conversation host's persistent session.
 */
export class ShadowController extends TypertRemoteService {
  /**
   * Register the `shadow` namespace.
   * @param ctx - Host context whose optional `shadowRouter` owns the snapshot
   *   and whose optional `shadowAgent` owns the conversation.
   */
  constructor(ctx: Context) {
    super(ctx, 'shadowController', { namespace: 'shadow' })
  }

  /**
   * Read the aggregate Shadow status: mount presence, designation, controller
   * liveness, authorized roots, and open-project rows.
   * @returns the router's snapshot, or the honest `mounted: false` answer when
   *   this deployment composes no shadow router.
   */
  @Remote
  readStatus(): ShadowStatusView {
    const router = this.ctx.get('shadowRouter')
    if (router === undefined) {
      return {
        mounted: false,
        shadowLive: false,
        authorizedRoots: [],
        bindings: [],
      }
    }
    return { mounted: true, ...router.readStatus() }
  }

  /**
   * Open the project at one path under an authorized root: validate, provision
   * the project's controller session, and persist the controller role.
   * @param request - The project path to open.
   * @returns the controller association.
   */
  @Remote
  async openProject(request: ShadowProjectOpenInput): Promise<ProjectOpenResult> {
    return await this.requireRouter().openProjectForHost({ path: request.path, requestId: randomUUID() })
  }

  /**
   * Deliver one `work` message to a project's controller session through the
   * router's delivery channel, with the binding's current revision and
   * authorized open run supplied by the router.
   * @param request - Target workspace and bounded message text.
   * @returns the delivery receipt.
   */
  @Remote
  async sendToController(request: ShadowProjectSendInput): Promise<ProjectSendResult> {
    return await this.requireRouter().sendToProjectForHost({
      workspaceId: request.workspaceId,
      text: request.text,
      requestId: randomUUID(),
    })
  }

  /**
   * Release (stop and close) one project: cancel pending deliveries and land
   * the row on `stopped`, staying visible in the panel.
   * @param request - The workspace to release.
   * @returns the stop receipt.
   */
  @Remote
  async releaseProject(request: ShadowProjectReleaseInput): Promise<ProjectStopResult> {
    return await this.requireRouter().releaseProjectForHost({ workspaceId: request.workspaceId, requestId: randomUUID() })
  }

  /**
   * Post one human message into the designated Shadow session. The session's
   * agent loop claims it and runs the turn; the reply lands on the persisted
   * conversation surface.
   * @param request - The human's message text.
   * @returns the accepted message's stable id.
   */
  @Remote
  async postMessage(request: ShadowConversationPostInput): Promise<ShadowConversationAccepted> {
    return await this.requireConversationHost().postMessage(request.text)
  }

  /**
   * Read the Shadow conversation surface, bounded and cursor-addressed.
   * @param request - Optional continuation cursor and page bound.
   * @returns the page of conversation rows plus the continuation cursor.
   */
  @Remote
  async readConversation(request: ShadowConversationReadInput): Promise<ShadowConversationPage> {
    return await this.requireConversationHost().readConversation(request)
  }

  /**
   * Approve a planned task for development from the board. Resolves the same
   * start authority the `project_task start` tool enforces (live root
   * controller, open Goal admitting the task, exactly one Worker and lead,
   * three independent locked worktrees), persists the host-approved
   * `git diff --check` checkset into the required-checks ledger, registers it
   * with the delivery registry, then assigns and starts development under
   * write-boundary drift re-checks. The Worker receives one briefing; the
   * designated Shadow session receives a structured message (best-effort: a
   * conversation-host failure does not fail an already-admitted start).
   * A task that is not planned, or whose provisioning is incomplete, fails
   * loud without advancing state.
   * @param request - The workspace binding and the planned task id.
   * @returns the task's state after admission.
   */
  @Remote
  async approveTask(request: ShadowApproveTaskInput): Promise<ShadowApproveTaskResult> {
    const router = this.requireRouter()
    const binding = router.findBinding(request.workspaceId)
    if (binding === undefined || binding.state !== 'ready') throw new Error('approveTask requires a ready workspace binding')
    const taskId = TaskId(request.taskId)
    const authority = resolveTaskStartAuthority(this.ctx, this.ctx.agents.get(binding.controllerSessionId), taskId, () => false)
    if (authority.task.state !== 'planned') throw new Error('approveTask requires a planned task')
    const registry = this.ctx.get('projectDeliveryRegistry')
    if (registry === undefined) throw new Error('approveTask requires the project delivery registry (delivery consumer mounted)')
    const cwd = await realpathNormalize(authority.source.path)
    const checks: DevFrameRequiredChecksConfig = {
      version: 1,
      checks: [{ checkId: 'git-diff-check', executable: 'git', arguments: ['diff', '--check'], cwd }],
    }
    const store = new FileRequiredChecksConfigStore({ path: registry.ledgerPath })
    const digest = await store.save(checks)
    // The commit scope is host-optional: omitting it registers the checkset
    // only and keeps `project_commit` failing closed, because the desktop
    // board cannot enumerate a task's output files before the Worker writes
    // them. Deployments that pin a scope pass it in the request.
    registry.registerTask(taskId, {
      digest: String(digest),
      ...(request.commitPaths === undefined ? {} : { commitPaths: request.commitPaths }),
    })
    const unchanged = taskStartUnchanged(this.ctx, authority, () => false)
    await this.ctx.projectController.assign(taskId, authority.worker.sessionId, { beforePersist: unchanged })
    unchanged()
    const started = await this.ctx.projectController.startDevelopment(taskId, { beforePersist: unchanged })
    unchanged()
    authority.workerAgent.followup(createUserMessage({
      content: [{ type: 'text', text: `Task ${String(taskId)} "${authority.task.title}" is approved; start the work in your worktree now.` }],
      source: { kind: 'plugin', plugin: 'shadow-board' },
    }))
    this.boardNotify(`Approved task ${String(taskId)}: ${authority.task.title}. The Worker is starting development.`)
    return { taskId: String(taskId), state: started.state }
  }

  /**
   * Reject a planned task from the board: block it with the host reason so
   * the board shows the recovery triple instead of silently dropping the
   * task. Only a planned task may be rejected; anything already started
   * fails loud (recovery of active tasks uses the project tools).
   * @param request - The workspace binding, the planned task id, and the reason.
   * @returns the task's blocked state.
   */
  @Remote
  async rejectTask(request: ShadowRejectTaskInput): Promise<ShadowRejectTaskResult> {
    const router = this.requireRouter()
    const binding = router.findBinding(request.workspaceId)
    if (binding === undefined || binding.state !== 'ready') throw new Error('rejectTask requires a ready workspace binding')
    const taskId = TaskId(request.taskId)
    const task = this.ctx.projectController.find(taskId)
    if (task === undefined || task.state !== 'planned') throw new Error('rejectTask requires a planned task')
    const blocked = await this.ctx.projectController.block(taskId, {
      blockedReason: request.reason,
      nextAction: 'The user revises the task or its approval request',
      wakeCondition: 'The user re-approves or revises the task',
    })
    this.boardNotify(`Rejected task ${String(taskId)}: ${task.title}.`)
    return { taskId: String(taskId), state: blocked.state }
  }
  /**
   * Best-effort board notification into the designated Shadow session. The
   * conversation host owns the persistent session; a missing host or a
   * post failure degrades silently because the state change it announces has
   * already happened and must not fail with it.
   * @param text - Structured notification text for the Shadow conversation.
   */
  private boardNotify(text: string): void {
    const host = this.ctx.get('shadowAgent')
    if (host === undefined) return
    void host.postMessage(text).catch(() => {})
  }
  /** The mounted router, or a loud honest failure for the project write faces. */
  private requireRouter(): ShadowRouter {
    const router = this.ctx.get('shadowRouter')
    if (router === undefined) {
      throw new Error('this deployment has no shadow router mounted; host project writes are unavailable')
    }
    return router
  }

  /** The mounted conversation host, or a loud honest failure for the conversation faces. */
  private requireConversationHost(): ShadowAgent {
    const host = this.ctx.get('shadowAgent')
    if (host === undefined) {
      throw new Error('this deployment has no shadow conversation host mounted; the conversation is unavailable')
    }
    return host
  }
}

export default ShadowController
