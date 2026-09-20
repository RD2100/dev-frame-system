/** The card's injected face: the status store, the refresh verb, and the
 * open-designated-session verb. */

import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ShadowBoardSnapshotState, ShadowStatusSnapshot } from './shadow-store.ts'

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

/** Live facts and verbs the board view slot hands the view. */
export interface BoardViewFace {
  hooks: {
    /** The board snapshot the renderer binds to `useBoard`. */
    board: SnapshotStore<ShadowBoardSnapshotState>
    /** The status snapshot the renderer binds to `useStatus` (self-check). */
    status: SnapshotStore<ShadowStatusSnapshot>
  }
  /** Issue one board read through the transport port. */
  onRefresh(): void
  /** Approve one planned card, or re-approve one blocked card. */
  onApprove(taskId: string): Promise<void>
  /** Reject one planned card with the human's note. */
  onReject(taskId: string, reason: string): Promise<void>
}

/** Live verbs the conversation header action hands the toggle. */
export interface BoardToggleFace {
  /** Reopen the Shadow conversation from the board view. */
  onOpen(): Promise<void>
}
