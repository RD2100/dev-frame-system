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
  ShadowConversationAccepted,
  ShadowConversationPage,
  ShadowConversationPostInput,
  ShadowConversationReadInput,
  ShadowProjectOpenInput,
  ShadowProjectReleaseInput,
  ShadowProjectSendInput,
  ShadowStatusView,
} from './types.ts'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowAgent } from './shadow-agent.ts'

export type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowConversationAccepted,
  ShadowConversationMessage,
  ShadowConversationPage,
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
