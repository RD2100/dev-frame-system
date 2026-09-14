/** The card's injected face: the status store, the refresh verb, and the
 * open-designated-session verb. */

import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ShadowStatusSnapshot } from './shadow-store.ts'

/** Live facts and verbs the sidebar footer-action slot hands the card. */
export interface ShadowCardFace {
  hooks: {
    /** The status store the renderer binds to `useStatus`. */
    status: SnapshotStore<ShadowStatusSnapshot>
  }
  /** Issue one status read through the transport port. */
  onRefresh(): void
  /** Adopt the Shadow's permanent designated Session and select it — the one durable conversation of the independent agent. */
  onOpenConversation(): Promise<void>
}
