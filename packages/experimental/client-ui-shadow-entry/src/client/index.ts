/** Browser entry binding the generated Shadow Remote artifact to its entry card. */

import shadowRemote from '@deepseek-ai/dsh-experimental-shadow-controller/remote'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import { mountShadowEntryUi } from './mount.ts'

export { inject } from './mount.ts'
export type { BoardToggleFace, BoardViewFace, ShadowCardFace } from './slots.ts'
export type { BoardToggleProps } from './BoardToggle.tsx'
export type { BoardViewProps } from './BoardView.tsx'
export type { ShadowCardProps } from './ShadowCard.tsx'
export type { ShadowBoardSnapshotState, ShadowStatusSnapshot, ShadowStatusPort } from './shadow-store.ts'
export type { ShadowKey } from './locales.ts'

/** Mount the generated Shadow Remote contribution and the sidebar entry card. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return await mountShadowEntryUi(ctx, shadowRemote)
}
