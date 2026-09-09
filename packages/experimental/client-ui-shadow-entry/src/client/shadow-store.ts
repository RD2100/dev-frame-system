/**
 * The Shadow card's status store: one snapshot-store over the settled reads
 * the controller issues through the transport port. The view stays the last
 * good answer; a failed read replaces it with the failure message.
 */

import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'

/** One settled-or-pending status state backing the card. */
export interface ShadowStatusSnapshot {
  /** The last good wire answer, until a failed read replaces it. */
  view: ShadowStatusView | undefined
  /** The last read failure, when the latest settled read failed. */
  error: string | undefined
}

/** Transport face the card reads the Host status through. */
export type ShadowStatusPort = () => Promise<RemoteResult<ShadowStatusView>>

/** Publishes status reads through one snapshot store; the latest read wins. */
export class ShadowStatusController {
  /** Card snapshot consumed through a bound selector hook. */
  readonly store: SnapshotStore<ShadowStatusSnapshot> = createSnapshotStore({
    view: undefined,
    error: undefined,
  })

  private sequence = 0

  /**
   * @param port - The transport read; one call per refresh, never cached here.
   */
  constructor(private readonly port: ShadowStatusPort) {}

  /**
   * Issue one status read and publish its settled answer. A superseded read
   * (one issued after it) never publishes: the latest issued read owns the
   * store.
   */
  async refresh(): Promise<void> {
    const ticket = this.sequence + 1
    this.sequence = ticket
    const result = await this.port()
    if (ticket !== this.sequence) return
    this.store.update((state) => {
      if (result.ok) {
        state.view = result.value
        state.error = undefined
      } else {
        state.error = result.error.message
      }
    })
  }
}
