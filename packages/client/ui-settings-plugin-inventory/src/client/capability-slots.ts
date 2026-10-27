/** Shared declaration for the capability center's keyed content pages. */

import type {} from '@deepseek-ai/dsh-client-ui-slots'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface SlotMap {
    /** One keyed content page inside the capability center. */
    'capabilities.center.tab': {
      kind: 'keyed'
      scope: 'root'
      owner: CapabilityCenterTabOwnerProps
    }
  }
}

/** Owner share of a capability-center page; the shell supplies no content props. */
export interface CapabilityCenterTabOwnerProps {
  /** Marker field: the slot owner intentionally supplies no children. */
  children?: never
}
