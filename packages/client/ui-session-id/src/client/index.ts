/**
 * SessionID badge plugin, browser half: contributes one session-header
 * utilities entry showing this session's id with a copy control. The id is
 * the standard session-scope currency — no RPC, no store, no state beyond
 * the transient copied flag.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import { SessionIdBadge } from './SessionIdBadge.tsx'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import { en, NS, zh, type SessionIdKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** SessionID badge copy. */
    'session-id': SessionIdKey
  }
}

export type { SessionIdBadgeProps } from './SessionIdBadge.tsx'

/** Required services for locale registration and header-slot contribution. */
export const inject = ['sessions', 'slots', 'locale']

/**
 * Client plugin body: register the dictionaries and the header utility.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-session-id: dictionaries')
  ctx.slots.inject(
    'conversation.session.header.utilities',
    () => ctx.slots.register({
      name: 'conversation.session.header.utilities',
      id: 'session-id-badge',
      // Before the download action: passive identity info reads first.
      order: -10,
      locale: NS,
    }, SessionIdBadge),
  )
}
