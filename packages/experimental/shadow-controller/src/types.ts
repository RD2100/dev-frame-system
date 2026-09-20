/**
 * Client-safe request and result vocabulary of the `shadow` Remote namespace.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/types
 */

import type {
  ShadowRouterStatus,
  ShadowStatusBinding,
} from '@deepseek-ai/dsh-experimental-shadow-routing'

export type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowRouterStatus,
} from '@deepseek-ai/dsh-experimental-shadow-routing'

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

/** Host conversation input: one human message for the Shadow session. */
export interface ShadowConversationPostInput {
  readonly text: string
}

/** The accepted receipt of one posted human message. */
export interface ShadowConversationAccepted {
  readonly messageId: string
}

/** Host conversation read input: optional continuation cursor and page bound. */
export interface ShadowConversationReadInput {
  /** Sequence number to read beyond; absent reads the latest tail. */
  readonly after?: number
  /** Maximum rows in the page, 1 through 200; defaults to 50. */
  readonly limit?: number
}

/** One conversation row: a human message or the Shadow's reply. */
export interface ShadowConversationMessage {
  /** Sequence number of the session log event the row folds. */
  readonly seq: number
  /** `'user'` for the human's message, `'shadow'` for the agent's reply. */
  readonly role: 'user' | 'shadow'
  /** The row's text content. */
  readonly text: string
  /** ISO-8601 instant the event entered the log. */
  readonly at: string
}

/** One bounded conversation page plus the cursor to continue from. */
export interface ShadowConversationPage {
  readonly messages: readonly ShadowConversationMessage[]
  /** Pass back as `after` to read the next page. */
  readonly cursor: number
}
/** Host approve input: the workspace binding, the planned task id, and an optional commit-path scope. */
export interface ShadowApproveTaskInput {
  readonly workspaceId: ShadowWorkspaceId
  readonly taskId: string
  /**
   * Optional host-registered commit-path scope for the task. Omitted means the
   * checkset is registered but `project_commit` keeps failing closed until a
   * deployment pins a scope.
   */
  readonly commitPaths?: readonly string[]
}

/** Host reject input: the workspace binding, the planned task id, and the reason. */
export interface ShadowRejectTaskInput {
  readonly workspaceId: ShadowWorkspaceId
  readonly taskId: string
  readonly reason: string
}

/** Approve receipt: the task's state after development admission. */
export interface ShadowApproveTaskResult {
  readonly taskId: string
  readonly state: string
}

/** Reject receipt: the task's blocked state. */
export interface ShadowRejectTaskResult {
  readonly taskId: string
  readonly state: string
}
