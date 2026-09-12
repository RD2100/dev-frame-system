/**
 * The Shadow card's conversation store: one snapshot-store over the settled
 * conversation reads the card issues through the transport port. Rows
 * accumulate across incremental polls beyond the cursor; a failed read keeps
 * the rows and publishes the failure. The latest issued read owns the store,
 * so a superseded read never publishes.
 */

import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type {
  ShadowConversationMessage,
  ShadowConversationPage,
  ShadowConversationReadInput,
} from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'

/** One settled-or-pending conversation state backing the card. */
export interface ShadowConversationSnapshot {
  /** The conversation rows, oldest first, folded across settled reads. */
  messages: readonly ShadowConversationMessage[]
  /** The cursor the next incremental read continues from; absent until one read settles. */
  cursor: number | undefined
  /** The last read failure, when the latest settled read failed. */
  error: string | undefined
}

/** Transport face the card reads the Shadow conversation through. */
export type ShadowConversationPort = (request: ShadowConversationReadInput) => Promise<RemoteResult<ShadowConversationPage>>

/** Publishes conversation reads through one snapshot store; the latest read wins. */
export class ShadowConversationController {
  /** Card snapshot consumed through a bound selector hook. */
  readonly store: SnapshotStore<ShadowConversationSnapshot> = createSnapshotStore({
    messages: [],
    cursor: undefined,
    error: undefined,
  })

  private sequence = 0

  /**
   * @param port - The transport read; one call per load or poll, never cached here.
   */
  constructor(private readonly port: ShadowConversationPort) {}

  /**
   * Load the latest tail, replacing whatever the store held. The panel issues
   * this when it opens while the Shadow is online.
   */
  async loadTail(): Promise<void> {
    const ticket = this.track()
    const result = await this.port({})
    if (ticket !== this.sequence) return
    this.apply(result, page => page.messages)
  }

  /**
   * Read the rows beyond the last cursor and append them. Before any read has
   * settled there is no cursor, so the first poll falls back to a tail load.
   */
  async poll(): Promise<void> {
    const state = this.store.getSnapshot()
    if (state.cursor === undefined) {  await this.loadTail(); return }
    const ticket = this.track()
    const result = await this.port({ after: state.cursor })
    if (ticket !== this.sequence) return
    this.apply(result, page => [...state.messages, ...page.messages])
  }

  private track(): number {
    this.sequence += 1
    return this.sequence
  }

  private apply(
    result: RemoteResult<ShadowConversationPage>,
    fold: (page: ShadowConversationPage) => readonly ShadowConversationMessage[],
  ): void {
    this.store.update((state) => {
      if (result.ok) {
        state.messages = fold(result.value)
        state.cursor = result.value.cursor
        state.error = undefined
      } else {
        state.error = result.error.message
      }
    })
  }
}
