/** Platform-variant expected-file resolution for pinned snapshot scenarios. */

import { existsSync } from 'node:fs'
import { join } from 'node:path'
import type {
  SnapshotExpectationKind,
  SnapshotExpectationPlatform,
  SnapshotManifest,
} from './manifest.ts'

const EXPECTATION_FILES: Record<SnapshotExpectationKind, { stem: string; extension: string }> = {
  'system-prompt': { stem: 'system-prompt', extension: 'md' },
  'tool-schemas': { stem: 'tool-schemas', extension: 'json' },
  ui: { stem: 'ui', extension: 'md' },
}

/**
 * Map the reading host's `process.platform` onto the expectation-variant vocabulary.
 * @param platform - host platform injected by the caller, so every variant stays pinnable on any host.
 * @returns `win32` on Windows hosts, `posix` everywhere else.
 */
export function platformExpectationVariant(platform: NodeJS.Platform): SnapshotExpectationPlatform {
  return platform === 'win32' ? 'win32' : 'posix'
}

/**
 * Build the committed file name of one expected sidecar.
 * @param kind - which pinned sidecar to name.
 * @param variant - platform family for a variant file; omit for the base file.
 * @returns the file name (not a path) inside the scenario directory.
 */
export function expectationFileName(kind: SnapshotExpectationKind, variant?: SnapshotExpectationPlatform): string {
  const { stem, extension } = EXPECTATION_FILES[kind]
  return variant === undefined
    ? `${stem}.expected.${extension}`
    : `${stem}.${variant}.expected.${extension}`
}

/**
 * Every variant file name the manifest declares, for inventory guards that must
 * admit exactly the committed platform-variant files: declared expected-sidecar
 * variants plus the declared platform-variant canonical session recording (the
 * recording is an expected file in its persisted-replay comparison role).
 * @param manifest - the parsed scenario manifest (its declarations are already validated).
 * @returns deduplicated, sorted variant file names; empty without declarations.
 */
export function declaredExpectationVariantFiles(manifest: Pick<SnapshotManifest, 'expectations' | 'sessionVariants'>): string[] {
  const declared = manifest.expectations?.variants ?? {}
  const entries = Object.entries(declared) as Array<[SnapshotExpectationPlatform, SnapshotExpectationKind[]]>
  const names = entries.flatMap(([variant, kinds]) => kinds.map(kind => expectationFileName(kind, variant)))
  for (const variant of Object.keys(manifest.sessionVariants ?? {})) {
    names.push(`session.${variant}.jsonl`)
  }
  return [...new Set(names)].sort()
}

/** Inputs for {@link resolveExpectationPath}. */
export interface ResolveExpectationPathOptions {
  /** Absolute scenario directory that owns the committed expected files. */
  dir: string
  /** Which pinned sidecar to resolve. */
  kind: SnapshotExpectationKind
  /** The scenario's parsed manifest carrying optional variant declarations. */
  manifest: Pick<SnapshotManifest, 'expectations'>
  /** The reading host's `process.platform`; injected so any variant is pinnable on any host. */
  platform: NodeJS.Platform
}

/**
 * Resolve the expected file the current host platform must compare against: a
 * declared variant for the host's platform family selects the variant file,
 * every other case falls back to the base expected file (whose absence the
 * caller's own read reports).
 * @param options - scenario directory, sidecar kind, manifest, and injected host platform.
 * @returns the absolute path of the expected file to read.
 * @throws when the host platform has a declared variant for `kind` but the variant file is missing.
 */
export function resolveExpectationPath(options: ResolveExpectationPathOptions): string {
  const { dir, kind, manifest, platform } = options
  const variant = platformExpectationVariant(platform)
  if (manifest.expectations?.variants[variant]?.includes(kind) === true) {
    const fileName = expectationFileName(kind, variant)
    const variantPath = join(dir, fileName)
    if (!existsSync(variantPath)) {
      throw new Error(`session-snapshot: ${dir}: declared platform expectation variant file is missing: ${fileName}`)
    }
    return variantPath
  }
  return join(dir, expectationFileName(kind))
}

/** Inputs for {@link resolveSessionFixturePath}. */
export interface ResolveSessionFixturePathOptions {
  /** Absolute scenario directory that owns the committed session fixtures. */
  dir: string
  /** The scenario's parsed manifest carrying optional session-variant declarations. */
  manifest: Pick<SnapshotManifest, 'sessionVariants'>
  /** The reading host's `process.platform`; injected so any variant is pinnable on any host. */
  platform: NodeJS.Platform
}

/**
 * Resolve the canonical session fixture the current host platform must use for
 * both replay roles: a declared variant for the host's platform family selects
 * `session.<variant>.jsonl`, every other case falls back to `session.jsonl`
 * (whose absence the caller's own read reports). Unlike the pinned sidecars,
 * the recording's script side is usable without a header pin, so this
 * resolution does not require one.
 * @param options - scenario directory, manifest, and injected host platform.
 * @returns the absolute path of the session fixture to read.
 * @throws when the host platform has a declared session variant but the variant file is missing.
 */
export function resolveSessionFixturePath(options: ResolveSessionFixturePathOptions): string {
  const { dir, manifest, platform } = options
  const variant = platformExpectationVariant(platform)
  if (manifest.sessionVariants?.[variant] === true) {
    const fileName = `session.${variant}.jsonl`
    const variantPath = join(dir, fileName)
    if (!existsSync(variantPath)) {
      throw new Error(`session-snapshot: ${dir}: declared platform session fixture variant file is missing: ${fileName}`)
    }
    return variantPath
  }
  return join(dir, 'session.jsonl')
}
