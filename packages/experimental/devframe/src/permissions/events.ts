/** DevFrame's persisted role and policy identity. */

import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { DevFrameRole } from './index.ts'

/** Role and policy identity recorded for one exact DevFrame Agent. */
export interface DevFrameRolePolicyEvent {
  /** Exact Agent/Session identity carrying the assignment. */
  readonly agentId: SessionId
  /** Role admitted by the profile policy. */
  readonly role: DevFrameRole
  /** Profile policy identity that must match before recovery admits work. */
  readonly policyVersion: string
}

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /**
     * Records one exact Agent's DevFrame role and policy identity. Recovery
     * must restore this lookup before execution and refuse resume when the
     * live identity or configured policy cannot be matched.
     */
    'devframe/role-policy': DevFrameRolePolicyEvent
  }
}
