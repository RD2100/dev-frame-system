/** Browser entry binding the generated Library Remote to its sidebar card. */

import memoryLibraryRemote from '@deepseek-ai/dsh-experimental-project-memory/remote'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import { mountLibraryUi } from './mount.ts'

export { inject } from './mount.ts'
export type { LibraryCardFace, LibraryCardProps } from './LibraryCard.tsx'
export type { LibraryKey } from './locales.ts'

/** Mount the generated Library Remote contribution and the Library page entry. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return await mountLibraryUi(ctx, memoryLibraryRemote)
}
