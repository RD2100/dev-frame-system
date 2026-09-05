/** Shared identity and persistence contracts for one DevFrame project run. */

import type { Branded } from '@deepseek-ai/dsh-brand'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { SessionId } from '@deepseek-ai/dsh-session'

/** Stable host-owned project identity. */
export type WorkspaceId = Branded<'WorkspaceId'>

/** Stable hash of the user-approved objective and check configuration. */
export type AcceptanceHash = Branded<'AcceptanceHash'>

/** Fingerprint of the source inputs used by verification and review. */
export type SourceFingerprint = Branded<'SourceFingerprint'>

/** Stable identifier for one captured source tree. */
export type DevFrameSnapshotId = Branded<'DevFrameSnapshotId'>

/** Stable identifier for one human-confirmed configuration preview. */
export type ConfigurationConfirmationId = Branded<'ConfigurationConfirmationId'>

/**
 * Brand a validated workspace identifier.
 * @param value - validated host-owned project identifier.
 * @returns the branded workspace identifier.
 */
export function WorkspaceId(value: string): WorkspaceId {
  return value as WorkspaceId
}

/**
 * Brand an approved configuration digest.
 * @param value - digest of the user-approved objective and check configuration.
 * @returns the branded acceptance digest.
 */
export function AcceptanceHash(value: string): AcceptanceHash {
  return value as AcceptanceHash
}

/**
 * Brand a source-content fingerprint.
 * @param value - fingerprint of the source inputs used by verification and review.
 * @returns the branded source fingerprint.
 */
export function SourceFingerprint(value: string): SourceFingerprint {
  return value as SourceFingerprint
}

/**
 * Brand one source snapshot identifier after its producer has validated it.
 * @param value - non-empty source snapshot identifier.
 * @returns the branded snapshot identifier.
 */
export function DevFrameSnapshotId(value: string): DevFrameSnapshotId {
  return value as DevFrameSnapshotId
}

/**
 * Brand a host-issued configuration confirmation identifier.
 * @param value - host-issued identifier for one confirmed configuration preview.
 * @returns the branded configuration confirmation identifier.
 */
export function ConfigurationConfirmationId(value: string): ConfigurationConfirmationId {
  return value as ConfigurationConfirmationId
}

/** Lifecycle states needed to distinguish open work from a safe stop. */
export type ProjectLifecycleState =
  | 'admission_open'
  | 'stop_requested'
  | 'quiescence_confirmed'
  | 'stopped'
  | 'ambiguous'
  | 'needs_attention'

/** The immutable work identity shared by dispatch, evidence, and completion. */
export interface ProjectWorkBinding {
  readonly workspaceId: WorkspaceId
  readonly controllerSessionId: SessionId
  readonly goalId: GoalId
  readonly goalRevision: number
  readonly acceptanceHash: AcceptanceHash
  readonly sourceFingerprint: SourceFingerprint
}

/** Human approval reference for one exact resolved project configuration. */
export interface ConfigurationConfirmation {
  readonly id: ConfigurationConfirmationId
  readonly acceptanceHash: AcceptanceHash
}

/** Durable project binding record owned by the native session persistence layer. */
export interface ProjectBindingRecord extends ProjectWorkBinding {
  readonly confirmation: ConfigurationConfirmation
  readonly lifecycle: ProjectLifecycleState
}

/** Minimal persistence seam for a workspace's current project binding. */
export interface ProjectBindingPersistence {
  /** Read the current record without creating or changing a workspace. */
  read(workspaceId: WorkspaceId): Promise<ProjectBindingRecord | undefined>
  /** Persist one already validated record atomically. */
  write(record: ProjectBindingRecord): Promise<void>
}
