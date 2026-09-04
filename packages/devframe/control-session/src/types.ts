/** Client-safe DevFrame Controller Session event contract. @module @deepseek-ai/dsh-devframe-control-session/types */

import type { SessionId } from '@deepseek-ai/dsh-session/types'

/** Controller roles supported by the Slice 0 identity tracer. */
export type ControllerRole = 'global' | 'project'

/** Profile-scoped Global Controller identity. */
export interface GlobalControllerIdentityV1 {
  readonly schemaVersion: 1
  readonly role: 'global'
  readonly sessionId: SessionId
  readonly profileId: string
  readonly cwd: string
}

/** Workspace-scoped Project Controller identity. */
export interface ProjectControllerIdentityV1 {
  readonly schemaVersion: 1
  readonly role: 'project'
  readonly sessionId: SessionId
  readonly profileId: string
  readonly workspaceId: string
  readonly cwd: string
}

/** Exact versioned payload stored in the required log-only identity event. */
export type ControllerIdentityV1 = GlobalControllerIdentityV1 | ProjectControllerIdentityV1

/** Finite, client-safe reasons why the Global Controller is unavailable. */
export type DevFrameReadinessBlockedCode =
  | 'BOOTSTRAP_NOT_STARTED'
  | 'PROFILE_IDENTITY_UNAVAILABLE'
  | 'PROFILE_LEASE_UNAVAILABLE'
  | 'LOADER_UNAVAILABLE'
  | 'CONTROLLER_UNAVAILABLE'

/** Global Controller startup has begun but no navigable Session is ready. */
export interface DevFrameReadinessStarting {
  readonly status: 'starting'
  readonly generation: number
  readonly revision: number
}

/** Global Controller startup completed and its Session may be opened. */
export interface DevFrameReadinessReady {
  readonly status: 'ready'
  readonly generation: number
  readonly revision: number
  readonly sessionId: string
}

/** Global Controller startup stopped at one bounded failure category. */
export interface DevFrameReadinessBlocked {
  readonly status: 'blocked'
  readonly generation: number
  readonly revision: number
  readonly code: DevFrameReadinessBlockedCode
}

/** The current bootstrap generation is withdrawing its owned Controller. */
export interface DevFrameReadinessStopping {
  readonly status: 'stopping'
  readonly generation: number
  readonly revision: number
}

/** Pathless, credential-free Global Controller readiness projection. */
export type DevFrameReadinessSnapshot =
  | DevFrameReadinessStarting
  | DevFrameReadinessReady
  | DevFrameReadinessBlocked
  | DevFrameReadinessStopping

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /**
     * First durable event of a DevFrame Controller Session. It binds the
     * deterministic Session id to one profile or workspace. The canonical cwd
     * duplicates the native Session header contract; credentials, prompts, and
     * mutable readiness claims remain excluded.
     */
    'controller/identity': ControllerIdentityV1
  }
}
