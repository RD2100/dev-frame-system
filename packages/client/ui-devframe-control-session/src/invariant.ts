/** Package invariant companion. @module @deepseek-ai/dsh-client-ui-devframe-control-session/invariant */
/* jscpd:ignore-start */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@deepseek-ai/dsh-client-ui-devframe-control-session'
/** Cordis companion plugin name. */
export const name = 'client-ui-devframe-control-session-invariant'
/** Service required before the companion can reserve package ownership. */
export const inject = ['invariants']
/**
 * No runtime invariant: the locale, event definition, and keyed renderer are
 * effect-owned registrations whose disposal is covered by focused tests.
 */
const install: InvariantInstaller = () => {}

/** Register the invariant companion. @param ctx - invariant service context. @returns registration disposer. */
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
/* jscpd:ignore-end */
