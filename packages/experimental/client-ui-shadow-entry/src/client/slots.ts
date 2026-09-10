/** The card's injected face: the status store, the refresh verb, and the three panel write verbs. */

import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ProjectOpenResult, ProjectSendResult, ProjectStopResult } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowProjectSendInput } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowStatusSnapshot } from './shadow-store.ts'

/** The workspace identity vocabulary a status row carries into a write verb. */
export type ShadowWorkspaceId = ShadowProjectSendInput['workspaceId']

/** Live facts and verbs the sidebar footer-action slot hands the card. */
export interface ShadowCardFace {
  hooks: {
    /** The status store the renderer binds to `useStatus`. */
    status: SnapshotStore<ShadowStatusSnapshot>
  }
  /** Issue one status read through the transport port. */
  onRefresh(): void
  /** Open the project at one path under an authorized root. */
  onOpenProject(path: string): Promise<RemoteResult<ProjectOpenResult>>
  /** Deliver one `work` message to a project's controller. */
  onSendToController(workspaceId: ShadowWorkspaceId, text: string): Promise<RemoteResult<ProjectSendResult>>
  /** Release (stop and close) one open project. */
  onReleaseProject(workspaceId: ShadowWorkspaceId): Promise<RemoteResult<ProjectStopResult>>
}
