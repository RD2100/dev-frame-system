/** The card's injected face: the status and conversation stores, the refresh and conversation read
 * verbs, and the chat post verb. */

import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ShadowConversationAccepted } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowStatusSnapshot } from './shadow-store.ts'
import type { ShadowConversationSnapshot } from './shadow-conversation-store.ts'

/** Live facts and verbs the sidebar footer-action slot hands the card. */
export interface ShadowCardFace {
  hooks: {
    /** The status store the renderer binds to `useStatus`. */
    status: SnapshotStore<ShadowStatusSnapshot>
    /** The conversation store the renderer binds to `useConversation`. */
    conversation: SnapshotStore<ShadowConversationSnapshot>
  }
  /** Issue one status read through the transport port. */
  onRefresh(): void
  /** Adopt the Shadow's permanent designated Session and select it — the one durable conversation of the independent agent. */
  onOpenConversation(): Promise<void>
  /** Load the conversation tail; the dialog issues this when it opens online. */
  onLoadConversation(): void
  /** Issue one incremental conversation read beyond the cursor. */
  onPollConversation(): void
  /** Post one human message into the Shadow session. */
  onPostMessage(text: string): Promise<RemoteResult<ShadowConversationAccepted>>
}
