/** Web subagent catalog, navigation, addressed-session composer owner, and the `@subagent` mention source. */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { SubagentAddress } from '@deepseek-ai/dsh-subagent/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ComposerChainProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { InputTriggerService } from '@deepseek-ai/dsh-client-ui-input-trigger/client'
// Type-only: pulls the generated `subagents` Remote namespace (the provider
// directory face) into this compilation; the artifact exists post host build.
import type {} from '@deepseek-ai/dsh-subagent/remote'
// Type-only: merges ctx.remote into the client Context through the assembly boundary.
import type {} from '@deepseek-ai/dsh-api-gateway/client'
import { SubagentHeaderLineage, type SubagentCatalogInjected } from './SubagentHeaderLineage.tsx'
import {
  SubagentReadOnlyComposer, type SubagentReadOnlyMatch,
} from './SubagentReadOnlyComposer.tsx'
import { createSubagentMentionSource } from './mentions.ts'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import { en, NS, zh, type SubagentKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Subagent catalog and read-only composer copy. */
    'subagent': SubagentKey
  }
}

export type {
  SubagentCatalogInjected, SubagentHeaderLineageProps,
} from './SubagentHeaderLineage.tsx'
export type {
  SubagentReadOnlyComposerProps, SubagentReadOnlyMatch,
} from './SubagentReadOnlyComposer.tsx'

/** Required services for conversation slots, session navigation, and the trigger registry. */
export const inject = ['sessions', 'slots', 'locale', 'inputTriggers', 'remote', 'remote.subagents']

/**
 * Register the `@subagent` mention source over the Host provider directory.
 * @param ctx - client root context.
 */
function registerMentionSource(ctx: ClientContext): void {
  const readProviders = async (): Promise<readonly string[]> => {
    const answered = await ctx.remote.subagents.providers()
    if (!answered.ok) throw new Error(`${answered.error.code}: ${answered.error.message}`)
    return answered.value
  }
  const triggers = ctx.get('inputTriggers') as InputTriggerService
  ctx.effect(
    () => triggers.registerSource(createSubagentMentionSource(readProviders)),
    'ui-subagent: @subagent mention source',
  )
}

/** Claim the composer for one-shot history or an unavailable continuation owner. */
function selectReadOnlySubagent(owner: ComposerChainProps): SubagentReadOnlyMatch | null {
  const subagent = owner.session?.subagent
  if (subagent === undefined || subagent === null) return null
  if (subagent.address.mode === 'one-shot') return { reason: 'one-shot' }
  // The parent catalog is fetched ahead of the selected Session. Until it
  // resolves, leave the normal disabled composer in place instead of briefly
  // claiming that the parent is offline.
  if (subagent.parentAvailable !== false) return null
  // A RUNNING parent-offline continuable child keeps the default composer:
  // its input is disabled there, but the same primary Stop stays available so
  // the child can be interrupted. Once it stops, this takeover returns.
  return owner.session?.running === true ? null : { reason: 'parent-unavailable' }
}

/**
 * Client plugin body: register the subagent catalog and read-only composer seats.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-subagent: dictionaries')
  registerMentionSource(ctx)
  const sessions = ctx.sessions
  const catalogActions = (_parentSessionId: SessionId): SubagentCatalogInjected => ({
    openChild(address: SubagentAddress) {
      sessions.openSubagent(address)
    },
    refresh(parentSessionId: SessionId) {
      void sessions.refreshSubagents(parentSessionId)
    },
    setCatalogOpen(parentSessionId: SessionId, open: boolean) {
      sessions.setSubagentCatalogOpen(parentSessionId, open)
    },
  })
  ctx.slots.inject(
    'conversation.session.header.lineage',
    () => ctx.slots.register({
      name: 'conversation.session.header.lineage',
      locale: NS,
      inject: catalogActions,
    }, SubagentHeaderLineage),
  )
  ctx.slots.inject(
    'conversation.composer',
    () => ctx.slots.register({
      name: 'conversation.composer',
      priority: -10,
      locale: NS,
      select: selectReadOnlySubagent,
    }, SubagentReadOnlyComposer),
  )
}
