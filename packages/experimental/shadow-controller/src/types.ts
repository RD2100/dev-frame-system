/**
 * Client-safe request and result vocabulary of the `shadow` Remote namespace.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/types
 */

import type {
  ShadowRouterStatus,
  ShadowStatusBinding,
} from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { SessionId } from '@deepseek-ai/dsh-session'

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

/** One workspace binding row projected for the task board. */
export interface ShadowBoardBinding {
  readonly workspaceId: string
  /** Binding lifecycle state; the board highlights non-ready rows. */
  readonly state: string
  /** The controller session owning the binding; required in the record. */
  readonly controllerSessionId: SessionId
}

/** One task row projected for the board, folded from the task record plus host-derived facts. */
export interface ShadowBoardTask {
  readonly taskId: string
  readonly pluginId: string
  readonly title: string
  readonly state: string
  readonly blockedReason?: string
  readonly nextAction?: string
  readonly wakeCondition?: string
  readonly createdAt: string
  readonly updatedAt: string
  /**
   * Host-derived readiness of a planned task to start: true only when the full
   * start authority (live root controller, open Goal admitting the task,
   * exactly one Worker and lead, three independent locked worktrees) resolves.
   * Planned tasks only; any resolution failure or unavailable authority reads
   * false, so the board greys the approve action without advancing state.
   */
  readonly startReady?: boolean
  /**
   * Current branch of the Worker worktree. Assigned/developing tasks only;
   * absent when no worktree is registered or the registry read fails.
   */
  readonly branch?: string | null
}

/** The board snapshot read from the host: mount presence, binding digest, and the whole task board. */
export interface ShadowBoardSnapshot {
  /** Whether this deployment mounts a projectController at all; false answers an empty board. */
  readonly mounted: boolean
  /** Workspace binding digest in the router's stable order. */
  readonly bindings: readonly ShadowBoardBinding[]
  /** Whole board in stable (createdAt, taskId) order. */
  readonly tasks: readonly ShadowBoardTask[]
}
