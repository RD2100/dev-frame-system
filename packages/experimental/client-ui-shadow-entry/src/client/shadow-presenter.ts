/**
 * Pure presentation folds for the Shadow card. The wire snapshot becomes the
 * honest display model — one phase, the controller session, authorized roots,
 * and the multi-project list of open projects. No locale text is produced here;
 * keys are data the component renders through its `t` seat.
 */

import type { ShadowBindingState } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { ShadowKey } from './locales.ts'
import type { ShadowStatusSnapshot } from './shadow-store.ts'

/** The honest phases the card can render. */
export type ShadowPhase =
  | 'loading'
  | 'error'
  | 'unmounted'
  | 'disabled'
  | 'configured'
  | 'online'

/** One open-project row flattened for display; state keys are data, never copy. */
export interface ShadowProjectRow {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: string
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
  /** Association version. */
  readonly bindingRevision: number
  /** Locale key of a known durable state; the union covers every wire value. */
  readonly stateKey: ShadowKey
}

/** The display model the card renders. */
export interface ShadowCardModel {
  readonly phase: ShadowPhase
  /** Designated controller session id, present only when configured. */
  readonly shadowSessionId: string | null
  readonly authorizedRoots: readonly string[]
  /** Every open project, in the router's durable order. */
  readonly projects: readonly ShadowProjectRow[]
  /** The read failure message, present only on the error phase. */
  readonly error: string | null
}

/** Locale keys of the known durable project states. */
const STATE_KEYS: Record<ShadowBindingState, ShadowKey> = {
  reserving: 'state.reserving',
  provisioning: 'state.provisioning',
  ready: 'state.ready',
  stopping: 'state.stopping',
  stopped: 'state.stopped',
  needs_attention: 'state.needsAttention',
  failed: 'state.failed',
}

const EMPTY: Pick<ShadowCardModel, 'shadowSessionId' | 'authorizedRoots' | 'projects' | 'error'> = {
  shadowSessionId: null,
  authorizedRoots: [],
  projects: [],
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
  if (view.shadowSessionId === undefined) return { phase: 'disabled', ...EMPTY }
  return {
    phase: view.shadowLive ? 'online' : 'configured',
    shadowSessionId: view.shadowSessionId,
    authorizedRoots: view.authorizedRoots,
    projects: view.bindings.map(row => ({
      workspaceId: row.workspaceId,
      canonicalPath: row.canonicalPath,
      bindingRevision: row.bindingRevision,
      stateKey: STATE_KEYS[row.state],
    })),
    error: null,
  }
}
