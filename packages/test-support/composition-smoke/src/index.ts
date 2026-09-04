/**
 * Composition smoke bench: assembles the production client stack — Cordis
 * `Context`, the renderer-owned `SlotRegistry`, the UI renderer, the
 * `ui-session` adapter, and the typed Session/Workspace Controller doubles —
 * and mounts one feature plugin over it, so a cross-package smoke asserts the
 * assembled surface (slot ledger, locale registry, rendered DOM) instead of a
 * single component. Not part of the product plugin graph; consumer packages
 * depend on it in devDependencies only.
 * @module @deepseek-ai/dsh-composition-smoke
 */
import type { Plugin } from '@deepseek-ai/cordis'
import { SlotTestRuntime } from '@deepseek-ai/dsh-client-test-runtime'

/** Options for {@link mountComposition}. */
export interface CompositionOptions {
  /**
   * Bench customization between assembly and the plugin mount: provide the
   * services the plugin injects, script Remote namespaces, pin the locale, or
   * release bench defaults the feature replaces.
   * @param runtime - the assembled bench (provide services on
   * `runtime.ctx`; the doubles live on the runtime itself).
   */
  readonly provide?: (runtime: SlotTestRuntime) => void
}

/**
 * Assemble the composition bench and mount one feature plugin on it.
 * @param plugin - the feature plugin under composition (an
 * `{ inject, apply }` object, function plugin, or class).
 * @param options - bench customization; `provide` runs before the mount so
 * the mount's service precheck sees every injected service.
 * @returns the assembled runtime; declare slots, render, and dispose through
 * it (`runtime.dispose()`).
 */
export async function mountComposition(plugin: Plugin, options: CompositionOptions = {}): Promise<SlotTestRuntime> {
  const runtime = await SlotTestRuntime.create()
  options.provide?.(runtime)
  await runtime.mount(plugin)
  return runtime
}
