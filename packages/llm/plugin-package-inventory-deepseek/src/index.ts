/**
 * Active Loader-backed plugin package inventory for official DeepSeek requests.
 * Host entries and the requesting agent's standing preset are resolved at request time;
 * installed dependencies and plugin fibers without Loader package provenance are excluded.
 * @module @deepseek-ai/dsh-plugin-package-inventory-deepseek
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, isAbsolute, join, parse } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { FiberState, type Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { Entry, EntryTree } from '@deepseek-ai/cordis-plugin-loader'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-deepseek-llm-api-extensions'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-agent-presets'
import type { DeepSeekPluginPackageIdentity, DeepSeekPluginPackageInventoryExtension } from './types.ts'
import type {} from './types.ts'

export type * from './types.ts'

/** Cordis plugin name. */
export const name = 'plugin-package-inventory-deepseek'
/** Services required to locate host/requesting-agent entries and contribute the field. */
export const inject = ['agents', 'deepseekLlmApiExtensions', 'loader']

/** Plugin-package request contribution configuration. */
export interface Config {
  /** Contribute `dsh_plugin_packages` to official DeepSeek requests. Defaults to `true`. */
  enabled?: boolean
}

/** Validated plugin-package request contribution configuration. */
export const Config: z<Config> = z.object({
  enabled: z.boolean().default(true),
})

interface PackageManifest {
  readonly name?: unknown
  readonly version?: unknown
}

interface ActiveEntry {
  readonly entry: Entry
  /** Bare-package base used by the Loader path that activated this entry. */
  readonly bareBaseUrl?: string
}

/** Parse a bare package or package-subpath specifier into its package name. */
function barePackageName(specifier: string): string | undefined {
  if (specifier.startsWith('.') || specifier.includes(':') || isAbsolute(specifier)) return undefined
  const [first = '', second = ''] = specifier.split('/')
  // An active Loader entry already passed module resolution, so a scoped bare name has its package segment.
  return first.startsWith('@') ? `${first}/${second}` : first
}

/** Read one manifest identity, optionally treating an absent name as a loose-module marker. */
function identityFromManifest(path: string, allowAnonymous: boolean): DeepSeekPluginPackageIdentity | undefined {
  const manifest = JSON.parse(readFileSync(path, 'utf8')) as PackageManifest
  if (allowAnonymous && manifest.name === undefined) return undefined
  if (typeof manifest.name !== 'string' || manifest.name.length === 0
    || typeof manifest.version !== 'string' || manifest.version.length === 0) {
    throw new Error(`plugin-package-inventory-deepseek: ${path} must declare non-empty name and version`)
  }
  return { name: manifest.name, version: manifest.version }
}

/** The Node internal module loader the Loader drives for entry imports. */
type InternalModuleLoader = NonNullable<Entry['loader']['internal']>

/** Narrow a resolved module URL to the `file:` scheme a manifest lookup can read. */
function fileModuleUrl(url: string): string | undefined {
  return url.startsWith('file:') ? url : undefined
}

/**
 * Resolve one specifier through the Loader's own module loader — the surface
 * `EntryTree.import` drives for bare rows, where tsx registers its tsconfig
 * `paths` resolution — so a bare entry's identity reads the same resolution
 * fact its import already established instead of walking `node_modules` again.
 * @param loader - the Loader that imported (and owns) the entry.
 * @param specifier - the entry's own module specifier.
 * @param parentUrl - the base URL the Loader's import resolved the specifier against.
 * @returns the resolved `file:` URL, or `undefined` when the Loader exposes no
 * resolution face or resolves the row outside the filesystem.
 */
async function loaderResolvedModuleUrl(loader: Entry['loader'], specifier: string, parentUrl: string): Promise<string | undefined> {
  const internal: InternalModuleLoader | undefined = loader.internal
  if (internal === undefined) return undefined
  /* v8 ignore next 3 -- the primary lane runs Node 24 (v2 loader); Node 22 embedders keep the public async resolve */
  return internal.version === 'v2'
    ? fileModuleUrl(internal.resolveSync(parentUrl, { specifier }).url)
    : fileModuleUrl((await internal.resolve(specifier, parentUrl, {})).url)
}

/** Find the nearest owning manifest for a relative or absolute plugin module. */
function nearestManifest(modulePath: string): string | undefined {
  let current = dirname(modulePath)
  const root = parse(current).root
  while (true) {
    const manifest = join(current, 'package.json')
    if (existsSync(manifest)) return manifest
    if (current === root) return undefined
    current = dirname(current)
  }
}

/** Exact package identity resolver with immutable per-process manifest caching. */
class PackageIdentityResolver {
  // TODO: Invalidate manifest identities if in-process package-version replacement becomes a supported upgrade path.
  private readonly cache = new Map<string, DeepSeekPluginPackageIdentity | undefined>()

  constructor(private readonly hostBaseUrl: string) {}

  /** Resolve one Loader entry's owning package, or absence for a non-package loose module. */
  async resolve({ entry, bareBaseUrl }: ActiveEntry): Promise<DeepSeekPluginPackageIdentity | undefined> {
    /* v8 ignore next -- Loader entry trees inherit a base URL; the fallback supports direct embedders. */
    const treeBase = entry.parent.tree.ctx.baseUrl ?? this.hostBaseUrl
    // Bare rows re-resolve against the same parent URL their import used: the
    // tree base for ordinary trees, the recorded harness base for standing
    // preset mounts (`PresetTree.import`, mirrored by `bareBaseUrl`).
    const parentUrl = bareBaseUrl ?? treeBase
    const key = `${parentUrl}\u0000${treeBase}\u0000${entry.options.name}`
    if (this.cache.has(key)) return this.cache.get(key)

    const packageName = barePackageName(entry.options.name)
    let manifest: string | undefined
    if (packageName !== undefined) {
      const moduleUrl = await loaderResolvedModuleUrl(entry.loader, entry.options.name, parentUrl)
      if (moduleUrl === undefined) {
        throw new Error(`plugin-package-inventory-deepseek: cannot resolve active package ${JSON.stringify(packageName)}`)
      }
      manifest = nearestManifest(fileURLToPath(moduleUrl))
      if (manifest === undefined) {
        throw new Error(`plugin-package-inventory-deepseek: cannot resolve active package ${JSON.stringify(packageName)}`)
      }
    } else if (!entry.options.name.startsWith('cordis:')) {
      const moduleUrl = isAbsolute(entry.options.name)
        ? pathToFileURL(entry.options.name)
        : new URL(entry.options.name, treeBase)
      if (moduleUrl.protocol === 'file:') manifest = nearestManifest(fileURLToPath(moduleUrl))
    }
    const identity = manifest === undefined ? undefined : identityFromManifest(manifest, packageName === undefined)
    this.cache.set(key, identity)
    return identity
  }
}

/** Yield active, non-structural entries from one Loader tree. */
function activeEntries(tree: EntryTree, rootBareBaseUrl?: string): ActiveEntry[] {
  return [...tree.entries()]
    .filter(entry => !entry.options.group
      && !entry.disabled
      && entry.fiber?.state === FiberState.ACTIVE)
    .map(entry => ({
      entry,
      ...entry.parent.tree === tree && rootBareBaseUrl !== undefined
        ? { bareBaseUrl: rootBareBaseUrl }
        : {},
    }))
}

/** Deterministic text order independent of the host's ICU data and locale. */
function compareWireText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

/** Collect the full active package set for one request. */
async function collectActivePluginPackages(
  ctx: Context,
  resolver: PackageIdentityResolver,
  hostBaseUrl: string,
  sessionId?: string,
): Promise<DeepSeekPluginPackageIdentity[]> {
  const entries = activeEntries(ctx.loader)
  if (sessionId !== undefined && ctx.get('agentPresets') !== undefined) {
    const agent = ctx.agents.get(brandString<SessionId>(sessionId))
    if (agent !== undefined) {
      // The optional peer is loaded only when its service is present. Its existing
      // mount query keeps Loader internals off the public AgentPresets service.
      const { standingMountFor } = await import('@deepseek-ai/dsh-agent-presets')
      const presetTree = standingMountFor(agent.ctx)?.tree
      // PresetTree deliberately resolves its root bare rows from the harness;
      // nested ordinary includes retain their own tree base.
      if (presetTree !== undefined) entries.push(...activeEntries(presetTree, hostBaseUrl))
    }
  }
  const unique = new Map<string, DeepSeekPluginPackageIdentity>()
  for (const activeEntry of entries) {
    const identity = await resolver.resolve(activeEntry)
    if (identity === undefined) continue
    unique.set(`${identity.name}\u0000${identity.version}`, identity)
  }
  return [...unique.values()].sort((left, right) => (
    compareWireText(left.name, right.name) || compareWireText(left.version, right.version)
  ))
}

/**
 * Register the complete `dsh_plugin_packages` request contribution when enabled.
 * @param ctx - plugin context carrying Loader provenance and the DeepSeek request-extension registry.
 * @param config - validated default-on configuration.
 */
export function apply(ctx: Context, config: Config): void {
  if (config.enabled === false) return
  const hostBaseUrl = ctx.baseUrl ?? import.meta.url
  const resolver = new PackageIdentityResolver(hostBaseUrl)
  ctx.deepseekLlmApiExtensions.register('dsh_plugin_packages', {
    prepare: async (request) => {
      const value: DeepSeekPluginPackageInventoryExtension = {
        version: 1,
        packages: await collectActivePluginPackages(ctx, resolver, hostBaseUrl, request.sessionId),
      }
      return { value }
    },
  })
}
