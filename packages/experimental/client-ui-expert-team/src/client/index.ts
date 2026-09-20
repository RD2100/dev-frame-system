/** Browser entry binding the generated expert-team Remote to its sidebar card. */

import { expertTeamRemote } from '@deepseek-ai/dsh-experimental-expert-team/client'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { mountExpertTeamUi } from './mount.ts'

export { inject } from './mount.ts'
export type { ExpertTeamCardFace, ExpertTeamCardProps } from './ExpertTeamCard.tsx'
export type { ExpertTeamKey } from './locales.ts'
export type { ExpertSelectionInjected, ExpertSelectionState, ExpertSelectionTarget } from './selection.ts'

/** Mount the generated expert-team Remote contribution and Expert center entry. */
export async function apply(ctx: ClientContext): Promise<() => Promise<void>> {
  return await mountExpertTeamUi(ctx, expertTeamRemote as TypertRemoteContribution)
}

