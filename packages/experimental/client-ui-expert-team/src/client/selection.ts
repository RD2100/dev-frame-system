/** New-session handoff for an expert chosen from the Expert center. */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { SessionId } from '@deepseek-ai/dsh-session/types'

/** Plain expert identity handed from the catalog into the new-session flow. */
export interface ExpertSelectionTarget {
  readonly teamId: string
  readonly teamTitle: string
  readonly expertId: string
  readonly expertName: string
}

/** State rendered by the composer selection chip. */
export interface ExpertSelectionState {
  readonly target: ExpertSelectionTarget | null
  readonly sessionId: SessionId | undefined
}

/** Registration-side face for the session-scoped selection chip. */
export interface ExpertSelectionInjected {
  hooks: {
    /** The selected expert and the blank Session that received it. */
    expertSelection: SnapshotStore<ExpertSelectionState>
  }
  /** Remove the staged expert without discarding the user's draft. */
  clear: () => void
}

const EMPTY_SELECTION: ExpertSelectionState = { target: null, sessionId: undefined }

/** Coordinates catalog actions with the existing new-session and input flows. */
export class ExpertSelectionController {
  readonly store = createSnapshotStore<ExpertSelectionState>(EMPTY_SELECTION)

  private pendingDraft: string | undefined
  private waitingForBlank = false

  /**
   * @param ctx - root client context carrying session, conversation, and workspace services.
   */
  constructor(private readonly ctx: ClientContext) {}

  /**
   * Stage an expert and open the normal blank-session flow.
   * @param target - expert identity selected in the catalog.
   * @param draft - optional prompt staged into the new composer.
   */
  summon(target: ExpertSelectionTarget, draft?: string): void {
    this.pendingDraft = draft
    this.waitingForBlank = true
    this.store.set({ target, sessionId: undefined })
    this.ctx.uiWorkspace.startSession()
    this.reconcile()
  }

  /** Reconcile a staged selection with the Session Controller's current blank Session. */
  reconcile(): void {
    const selected = this.store.getSnapshot().target
    if (selected === null) return

    const sessions = this.ctx.sessions.list.getSnapshot()
    const current = sessions.current
    if (current === undefined) return
    const summary = sessions.byId[current]
    if (summary === undefined) return

    // startSession() can be asynchronous. Keep the selection while the old
    // conversation is still visible, then apply it to the first blank Session.
    if (!summary.blank) {
      if (this.waitingForBlank) return
      this.clear()
      return
    }

    const previous = this.store.getSnapshot().sessionId
    if (previous !== undefined && previous !== current) {
      this.clear()
      return
    }

    if (this.pendingDraft !== undefined) {
      const scope = this.ctx.sessions.scope(current)
      if (scope === undefined) return
      this.ctx.conversation.input.for(scope).setDraft(this.pendingDraft)
      this.pendingDraft = undefined
    }
    this.waitingForBlank = false
    this.store.set({ target: selected, sessionId: current })
  }

  /** Clear the selection while preserving whatever text is currently in the composer. */
  clear(): void {
    this.pendingDraft = undefined
    this.waitingForBlank = false
    this.store.set(EMPTY_SELECTION)
  }

  /** Build the face consumed by the session-scoped chip registration. */
  injected(): ExpertSelectionInjected {
    return { hooks: { expertSelection: this.store }, clear: () => { this.clear() } }
  }
}
