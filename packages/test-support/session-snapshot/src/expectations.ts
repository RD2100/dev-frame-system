/** Platform-variant expected-file resolution for pinned snapshot scenarios. */

import { existsSync } from 'node:fs'
import { join } from 'node:path'
import type {
  SnapshotChildExpectationKind,
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
export function declaredExpectationVariantFiles(
  manifest: Pick<SnapshotManifest, 'childSessionVariants' | 'expectations' | 'sessionVariants'>,
): string[] {
  const declared = manifest.expectations?.variants ?? {}
  const entries = Object.entries(declared) as Array<[SnapshotExpectationPlatform, SnapshotExpectationKind[]]>
  const names = entries.flatMap(([variant, kinds]) => kinds.map(kind => expectationFileName(kind, variant)))
  for (const variant of Object.keys(manifest.sessionVariants ?? {})) {
    names.push(`session.${variant}.jsonl`)
  }
  for (const [variant, indexes] of Object.entries(manifest.childSessionVariants ?? {})) {
    for (const index of indexes) names.push(`session.${index}.${variant}.jsonl`)
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

/**
 * Build the committed file name of the canonical session fixture, preferring
 * the declared platform-variant name for the host's platform family. Unlike
 * {@link resolveSessionFixturePath} this never consults the filesystem, so
 * refresh write-backs can name a variant target that does not exist yet.
 * @param manifest - the parsed scenario manifest carrying optional session-variant declarations.
 * @param platform - the writing host's `process.platform`, injected so any variant stays pinnable on any host.
 * @returns the file name (not a path) inside the scenario directory.
 */
export function sessionFixtureFileName(
  manifest: Pick<SnapshotManifest, 'sessionVariants'>,
  platform: NodeJS.Platform,
): string {
  const variant = platformExpectationVariant(platform)
  return manifest.sessionVariants?.[variant] === true ? `session.${variant}.jsonl` : 'session.jsonl'
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
  const fileName = sessionFixtureFileName(manifest, platform)
  if (fileName === 'session.jsonl') return join(dir, fileName)
  const variantPath = join(dir, fileName)
  if (!existsSync(variantPath)) {
    throw new Error(`session-snapshot: ${dir}: declared platform session fixture variant file is missing: ${fileName}`)
  }
  return variantPath
}

/**
 * Build the committed file name of child session fixture `index`, preferring
 * the declared child-variant name for the host's platform family. Like
 * {@link sessionFixtureFileName} this never consults the filesystem, so
 * refresh write-backs can name a child-variant target that does not exist yet.
 * @param manifest - the parsed scenario manifest carrying optional child-variant declarations.
 * @param index - 1-based child fixture index.
 * @param platform - the writing host's `process.platform`, injected so any variant stays pinnable on any host.
 * @returns the file name (not a path) inside the scenario directory.
 */
export function childSessionFixtureFileName(
  manifest: Pick<SnapshotManifest, 'childSessionVariants'>,
  index: number,
  platform: NodeJS.Platform,
): string {
  const variant = platformExpectationVariant(platform)
  return manifest.childSessionVariants?.[variant]?.includes(index) === true
    ? `session.${index}.${variant}.jsonl`
    : `session.${index}.jsonl`
}

/** Inputs for {@link resolveChildSessionFixturePath}. */
export interface ResolveChildSessionFixturePathOptions {
  /** Absolute scenario directory that owns the committed session fixtures. */
  dir: string
  /** The scenario's parsed manifest carrying optional child-variant declarations. */
  manifest: Pick<SnapshotManifest, 'childSessionVariants'>
  /** 1-based child fixture index to resolve. */
  index: number
  /** The reading host's `process.platform`; injected so any variant is pinnable on any host. */
  platform: NodeJS.Platform
}

/**
 * Resolve the child session fixture `index` the current host platform must use
 * for replay: a declared child variant for the host's platform family selects
 * `session.<index>.<variant>.jsonl`, every other case falls back to the base
 * child fixture `session.<index>.jsonl` (whose absence the caller's own read
 * reports).
 * @param options - scenario directory, manifest, child index, and injected host platform.
 * @returns the absolute path of the child session fixture to read.
 * @throws when the host platform has a declared child variant for `index` but the variant file is missing.
 */
export function resolveChildSessionFixturePath(options: ResolveChildSessionFixturePathOptions): string {
  const { dir, manifest, index, platform } = options
  const fileName = childSessionFixtureFileName(manifest, index, platform)
  if (fileName === `session.${index}.jsonl`) return join(dir, fileName)
  const variantPath = join(dir, fileName)
  if (!existsSync(variantPath)) {
    throw new Error(`session-snapshot: ${dir}: declared platform child session fixture variant file is missing: ${fileName}`)
  }
  return variantPath
}

/**
 * Build the committed file name of one child-indexed expected sidecar.
 * @param kind - which pinned child sidecar to name.
 * @param index - 1-based child fixture index the sidecar belongs to.
 * @param variant - platform family for a variant file; omit for the base file.
 * @returns the file name (not a path) inside the scenario directory.
 */
export function childExpectationFileName(
  kind: SnapshotChildExpectationKind,
  index: number,
  variant?: SnapshotExpectationPlatform,
): string {
  const { stem, extension } = EXPECTATION_FILES[kind]
  return variant === undefined
    ? `${stem}.${index}.expected.${extension}`
    : `${stem}.${index}.${variant}.expected.${extension}`
}

/** Inputs for {@link resolveChildExpectationPath}. */
export interface ResolveChildExpectationPathOptions {
  /** Absolute scenario directory that owns the committed child sidecar. */
  dir: string
  /** Which pinned child sidecar to resolve. */
  kind: SnapshotChildExpectationKind
  /** 1-based child fixture index the sidecar belongs to. */
  index: number
  /** The scenario's parsed manifest carrying optional child-expectation declarations. */
  manifest: Pick<SnapshotManifest, 'childExpectations'>
  /** The reading host's `process.platform`; injected so any variant is pinnable on any host. */
  platform: NodeJS.Platform
}

/**
 * Resolve the child sidecar `kind`/`index` the current host platform must
 * compare against: a declared child-expectation variant for the host's
 * platform family selects the variant file, every other case falls back to the
 * base child sidecar.
 * @param options - scenario directory, sidecar kind, child index, manifest, and injected host platform.
 * @returns the absolute path of the child sidecar to read.
 * @throws when the host platform has a declared child variant for `kind` but the variant file is missing.
 */
export function resolveChildExpectationPath(options: ResolveChildExpectationPathOptions): string {
  const { dir, kind, index, manifest, platform } = options
  const variant = platformExpectationVariant(platform)
  if (manifest.childExpectations?.variants[variant]?.includes(kind) === true) {
    const fileName = childExpectationFileName(kind, index, variant)
    const variantPath = join(dir, fileName)
    if (!existsSync(variantPath)) {
      throw new Error(`session-snapshot: ${dir}: declared platform child expectation variant file is missing: ${fileName}`)
    }
    return variantPath
  }
  return join(dir, childExpectationFileName(kind, index))
}
