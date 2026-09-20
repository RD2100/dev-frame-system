/**
 * Pure presentation folds for the Shadow card. The wire snapshot becomes the
 * honest display model — one phase, the designated session, and the
 * authorized roots. No locale text is produced here; keys are data the
 * component renders through its `t` seat.
 */

import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { ShadowStatusSnapshot } from './shadow-store.ts'

/** The honest phases the card can render. */
export type ShadowPhase =
  | 'loading'
  | 'error'
  | 'unmounted'
  | 'disabled'
  | 'configured'
  | 'online'
  | 'issue'

/** The display model the card renders. */
export interface ShadowCardModel {
  readonly phase: ShadowPhase
  /** Designated controller session id, present only when configured. */
  readonly shadowSessionId: string | null
  readonly authorizedRoots: readonly string[]
  /** The read failure message, present only on the error phase. */
  readonly error: string | null
}

const EMPTY: Pick<ShadowCardModel, 'shadowSessionId' | 'authorizedRoots' | 'error'> = {
  shadowSessionId: null,
  authorizedRoots: [],
  error: null,
}

/**
 * Fold one store snapshot into the display model.
 * @param snapshot - the store's latest state.
 * @returns the phase plus the facts the card shows.
 */
export function presentShadowStatus(snapshot: ShadowStatusSnapshot): ShadowCardModel {
  if (snapshot.error !== undefined) return { phase: 'error', ...EMPTY, error: snapshot.error }
  const view = snapshot.view
  if (view === undefined) return { phase: 'loading', ...EMPTY }
  return presentView(view)
}

/** Fold one wire answer into the display model. */
function presentView(view: ShadowStatusView): ShadowCardModel {
  if (!view.mounted) return { phase: 'unmounted', ...EMPTY }
  // A mounted router without a designation still reports the roots it
  // authorizes; only the session fact is absent.
  if (view.shadowSessionId === undefined) {
    return { phase: 'disabled', shadowSessionId: null, authorizedRoots: view.authorizedRoots, error: null }
  }
  // The designated session cannot be rendered by workspace-scoped surfaces;
  // report the issue instead of opening a conversation that shows fresh.
  if (view.designIssue !== undefined) {
    return {
      phase: 'issue',
      shadowSessionId: view.shadowSessionId,
      authorizedRoots: view.authorizedRoots,
      error: null,
    }
  }
  return {
    phase: view.shadowLive ? 'online' : 'configured',
    shadowSessionId: view.shadowSessionId,
    authorizedRoots: view.authorizedRoots,
    error: null,
  }
}
