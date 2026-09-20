/**
 * Load-time guard that fails loud when a loaded DevFrame bundle declares a
 * framework-singleton peer the host does not actually provide at a compatible
 * version. The whole point of self-contained distribution is that cordis,
 * schemastery, dsh-brand, and cosmokit resolve to exactly one copy in the host
 * runtime; a published plugin pinning a mismatched range must never silently
 * load against a different host copy.
 *
 * Ranges written `workspace:*` are the in-repo form. They cannot denote a
 * published mismatch (the workspace links guarantee a single in-repo copy), so
 * the guard only enforces concrete semver ranges produced by packing/publishing.
 * @module @deepseek-ai/dsh-desktop-host/peer-satisfaction
 */

/** Framework singletons that must resolve to a single host copy. */
export const DEVFRAME_HOST_SINGLETONS: readonly string[] = [
  '@deepseek-ai/cordis',
  '@deepseek-ai/schemastery',
  '@deepseek-ai/dsh-brand',
  '@deepseek-ai/cosmokit',
  '@deepseek-ai/dsh-session',
  '@deepseek-ai/dsh-agent',
  '@deepseek-ai/dsh-tools',
  '@deepseek-ai/dsh-goal',
  '@deepseek-ai/dsh-worktree-registry',
]

/** One loaded plugin's peer requirements, projected from its package.json. */
export interface PluginPeerRow {
  readonly pluginName: string
  readonly pluginVersion: string | undefined
  readonly requires: Readonly<Record<string, string>>
}

/** Resolved host singleton versions; absent means the host does not provide it. */
export type HostSingletonVersions = Readonly<Record<string, string | undefined>>

interface ParsedVersion {
  readonly major: number
  readonly minor: number
  readonly patch: number
}

function parseVersion(value: string): ParsedVersion | undefined {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(value.trim())
  if (match === null) return undefined
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) }
}

function isWorkspaceRange(range: string): boolean {
  return range.startsWith('workspace:')
}

/**
 * Minimal semver subset covering the ranges pnpm/npm actually emit for packed
 * workspace deps: `^x.y.z`, `~x.y.z`, `>=x.y.z`, exact `x.y.z`, and `*`.
 * Unknown range forms fail open rather than crash boot on syntax we did not
 * model; unparseable host versions fail closed (a real mismatch cannot hide).
 */
function satisfiesVersion(version: string, range: string): boolean {
  const trimmed = range.trim()
  if (trimmed === '' || trimmed === '*' || isWorkspaceRange(trimmed)) return true
  const candidate = parseVersion(version)
  if (candidate === undefined) return false

  let match = /^\^\s*(\d+)\.(\d+)\.(\d+)/.exec(trimmed)
  if (match !== null) {
    const major = Number(match[1])
    const minor = Number(match[2])
    const patch = Number(match[3])
    if (candidate.major !== major) return false
    // ^0.y.z pins to that minor; ^0.0.z pins to that patch.
    if (major === 0) {
      if (candidate.minor !== minor) return false
      return candidate.patch >= patch
    }
    if (candidate.minor !== minor) return candidate.minor > minor
    return candidate.patch >= patch
  }

  match = /^~\s*(\d+)\.(\d+)\.(\d+)/.exec(trimmed)
  if (match !== null) {
    return candidate.major === Number(match[1])
      && candidate.minor === Number(match[2])
      && candidate.patch >= Number(match[3])
  }

  match = /^>=\s*(\d+)\.(\d+)\.(\d+)/.exec(trimmed)
  if (match !== null) {
    const major = Number(match[1])
    const minor = Number(match[2])
    const patch = Number(match[3])
    if (candidate.major !== major) return candidate.major > major
    if (candidate.minor !== minor) return candidate.minor > minor
    return candidate.patch >= patch
  }

  match = /^(\d+)\.(\d+)\.(\d+)/.exec(trimmed)
  if (match !== null) {
    return candidate.major === Number(match[1])
      && candidate.minor === Number(match[2])
      && candidate.patch === Number(match[3])
  }

  return true
}

function renderPeerFailure(row: PluginPeerRow, name: string, range: string, host: string | undefined): string {
  const hostText = host === undefined ? 'NOT INSTALLED' : host
  return `[devframe-plugin] peer dependency not satisfied:
  plugin: ${row.pluginName}@${row.pluginVersion ?? 'unknown'}
  requires: ${name}@${range}
  host provides: ${name}@${hostText}
  action: upgrade host Desktop to a release bundling ${name}@${range},
          or pin this plugin to a version compatible with the host.`
}

/**
 * Assert every loaded plugin's framework-singleton peers are satisfied by the
 * host before cordis instantiates the plugin. Throws (never degrades) on the
 * first unsatisfied peer so a mixed-version bundle fails loud at load.
 * @param rows - one row per loaded plugin bundle.
 * @param hostVersions - host-installed version of each tracked singleton.
 */
export function assertHostPeerSatisfaction(rows: readonly PluginPeerRow[], hostVersions: HostSingletonVersions): void {
  for (const row of rows) {
    for (const [name, range] of Object.entries(row.requires)) {
      if (!DEVFRAME_HOST_SINGLETONS.includes(name)) continue
      if (isWorkspaceRange(range)) continue
      const host = hostVersions[name]
      if (host === undefined || !satisfiesVersion(host, range)) {
        throw new Error(renderPeerFailure(row, name, range, host))
      }
    }
  }
}
