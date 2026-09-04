/**
 * Package-owned invariant companion for `@deepseek-ai/dsh-devframe`.
 * @module @deepseek-ai/dsh-devframe/invariant
 */

import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@deepseek-ai/dsh-devframe'

/** Cordis companion plugin name. */
export const name = 'devframe-bundle-invariant'
/** Service required before the companion can register. */
export const inject = ['invariants']

// No runtime invariant: the package is a static patch-list carrier. The
// profile composer owns YAML parsing and every inserted plugin owns its live
// service relations; the focused bundle test pins the exact two-row patch.
const install: InvariantInstaller = () => {}

/** Register this package's invariant ownership with the shared registry. */
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
