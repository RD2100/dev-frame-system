/**
 * Client-safe request and result vocabulary of the `shadow` Remote namespace.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/types
 */

import type {
  ShadowRouterStatus,
  ShadowStatusBinding,
} from '@deepseek-ai/dsh-experimental-shadow-router'

export type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowRouterStatus,
} from '@deepseek-ai/dsh-experimental-shadow-router'

/** The workspace id vocabulary the status rows and write inputs carry. */
export type ShadowWorkspaceId = ShadowStatusBinding['workspaceId']

/** The status vocabulary a Client reads: the router snapshot plus mount presence. */
export interface ShadowStatusView extends ShadowRouterStatus {
  /** Whether the deployment mounts a shadow router at all. */
  readonly mounted: boolean
}

/** Host open input: an existing path under one authorized root; canonicalization is the router's job. */
export interface ShadowProjectOpenInput {
  readonly path: string
}

/** Host send input: one `work` message to a project's controller. */
export interface ShadowProjectSendInput {
  readonly workspaceId: ShadowWorkspaceId
  readonly text: string
}

/** Host release input: the project to stop and close. */
export interface ShadowProjectReleaseInput {
  readonly workspaceId: ShadowWorkspaceId
}
