import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-devframe-control-session/remote'
import { ControlIdentityView } from './ControlIdentityView.tsx'
import { controllerIdentityDefinition } from './definition.ts'
import { GlobalControllerAction } from './GlobalControllerAction.tsx'
import { en, NS, zh } from './locales.ts'
import { GlobalControllerReadiness } from './readiness.ts'

/** Required browser services. */
export const inject = ['slots', 'conversationEvents', 'locale', 'sessions', 'remote']

/** Register the identity definition and its keyed renderer. @param ctx - browser context. */
export function apply(ctx: Context): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-devframe-control-session: dictionaries')
  ctx.conversationEvents.register(controllerIdentityDefinition)
  const readiness = new GlobalControllerReadiness()
  ctx.effect(() => {
    readiness.start(ctx.remote)
    return () => { readiness.stop() }
  }, 'ui-devframe-control-session: Host readiness')
  ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
    name: 'conversation.chat.node',
    key: 'devframe-controller-identity',
    locale: NS,
    inject: () => ({
      openFile: () => {},
      inspectCall: () => {},
      forkAt: () => {},
      loadImage: () => Promise.resolve(''),
      fileMentions: () => undefined,
    }),
  }, ControlIdentityView))
  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
    name: 'sidebar.footer.action',
    id: 'devframe-global-controller',
    order: -100,
    locale: NS,
    inject: () => ({
      open: (sessionId: Parameters<typeof ctx.sessions.open>[0]) => { ctx.sessions.open(sessionId) },
      hooks: { sessions: ctx.sessions.list, readiness: readiness.store },
    }),
  }, GlobalControllerAction))
}
