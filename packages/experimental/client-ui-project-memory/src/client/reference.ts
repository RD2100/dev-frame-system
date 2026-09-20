/** Conversation-reference action for the Library page. */

import type { Context as ClientContext } from '@deepseek-ai/cordis'

/**
 * Append a library path reference into the current conversation composer.
 * The action never creates or switches sessions: without a current session
 * scope it is an explicit no-op that reports false, so the card can show a
 * hint instead of a dead control.
 */
export class LibraryReferenceController {
  constructor(private readonly ctx: ClientContext) {}

  /**
   * Append one reference line to the current conversation's draft, preserving
   * whatever the human already typed.
   * @param line - the reference text to append (the card composes the label).
   * @returns true when the draft was updated; false when no session scope
   *   exists and the reference could not be placed.
   */
  reference(line: string): boolean {
    const sessions = this.ctx.sessions.list.getSnapshot()
    const current = sessions.current
    if (current === undefined) return false
    const scope = this.ctx.sessions.scope(current)
    if (scope === undefined) return false
    const input = this.ctx.conversation.input.for(scope)
    const existing = input.state.getSnapshot().draft
    input.setDraft(existing === '' ? line : `${existing}\n${line}`)
    return true
  }
}
