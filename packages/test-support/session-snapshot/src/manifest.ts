/** Parse and validate one recorded-session snapshot manifest. */

import { isAbsolute } from 'node:path'
import * as yaml from 'js-yaml'

/** Public `dsh` profile used to control a recorded-session scenario. */
export type SnapshotProfile = 'headless' | 'sdk' | 'acp' | 'web'

/** How a canonical session may be regenerated. */
export type SnapshotRecording = 'live' | 'authored'

/** Request-header ownership metadata for one composition. */
export interface SnapshotHeaderManifest {
  /** Stable class name shared only by byte-identical request headers. */
  class: string
  /** Whether this scenario owns the class's tokenized header sequence. */
  pin?: true
  /** Scenario that owns the readable system-prompt sidecar. */
  systemPromptSource?: string
  /** Scenario that owns the readable tool-schema sidecar. */
  toolSchemasSource?: string
  /** Child fixture indexes that own distinct system-prompt sidecars. */
  childSystemPrompts?: number[]
  /** Child fixture indexes that own distinct tool-schema sidecars. */
  childToolSchemas?: number[]
  /** Legitimate changed-header count after the initial request header. */
  changes?: number
}

/** Replay facts that cannot be reconstructed from successful model chunks. */
export interface SnapshotReplayManifest {
  /** A scenario-local `replay.override.json` replaces or patches the recorded model script. */
  override: true
}

/** Host requirements for a scenario's process-level controller. */
export type SnapshotPlatform = 'posix' | 'pwsh'

/** Pinned expected sidecar that a platform variant can replace. */
export type SnapshotExpectationKind = 'system-prompt' | 'tool-schemas' | 'ui'

/**
 * Host platform family that selects a scenario's expected-file variant, derived
 * from the reading host's `process.platform` (`win32`, otherwise `posix`).
 * Unlike `SnapshotPlatform` — a scenario-level host requirement that skips the
 * run on unsuitable hosts — this vocabulary classifies which committed expected
 * file each host platform reads; it never skips anything.
 */
export type SnapshotExpectationPlatform = 'win32' | 'posix'

/** Platform-keyed expected-file variant declarations for a pinned scenario. */
export interface SnapshotExpectationsManifest {
  /** Expected sidecar kinds that carry a variant file for each declared platform family. */
  variants: Partial<Record<SnapshotExpectationPlatform, SnapshotExpectationKind[]>>
}

/**
 * Platform-keyed declarations that the scenario's canonical session recording
 * carries a variant file (`session.<platform>.jsonl`) for a platform family.
 * The recording is both replay script and persisted-session comparison target,
 * so one variant file serves both roles.
 */
export type SnapshotSessionVariantsManifest = Partial<Record<SnapshotExpectationPlatform, true>>

/**
 * Platform-keyed declarations that specific child session fixtures carry
 * variant files (`session.<n>.<platform>.jsonl`) for a platform family. Each
 * listed 1-based child index names a committed variant file that replaces the
 * base child fixture of the same index on its platform; undeclared child
 * indexes keep their base fixtures on every platform. Only a session owner may
 * declare child variants.
 */
export type SnapshotChildSessionVariantsManifest = Partial<Record<SnapshotExpectationPlatform, number[]>>

/** Child-indexed sidecar kinds a platform variant can replace. */
export type SnapshotChildExpectationKind = 'system-prompt' | 'tool-schemas'

/**
 * Platform-keyed expected-file variant declarations for a scenario's own
 * child-indexed sidecars: a declared platform/kind pair commits one variant
 * file per child sidecar index the scenario declares for that kind
 * (`tool-schemas.<n>.<platform>.expected.json`). The base child sidecar of
 * every undeclared platform/kind pair stays authoritative on all platforms.
 */
export interface SnapshotChildExpectationsManifest {
  /** Child sidecar kinds that carry a variant file for each declared platform family. */
  variants: Partial<Record<SnapshotExpectationPlatform, SnapshotChildExpectationKind[]>>
}

/**
 * Platform-keyed declarations that the scenario's canonical stdout projection
 * carries a variant file (`stdout.<platform>.expected.jsonl`) for a platform
 * family. The variant replaces the base stdout expectation on its platform:
 * a platform-specific recording may differ in content, not only in cwd path
 * spelling, so the platform reads exactly one stdout expectation.
 */
export type SnapshotStdoutVariantsManifest = Partial<Record<SnapshotExpectationPlatform, true>>

/**
 * Platform-keyed declarations that the scenario's SDK wire goldens
 * (`notifications.expected.jsonl` and `result.expected.json`) carry variant
 * files (`notifications.<platform>.expected.jsonl`,
 * `result.<platform>.expected.json`) for a platform family. A
 * platform-specific recording may diverge in the SDK-visible event stream and
 * run result, so the platform reads exactly one golden pair.
 */
export type SnapshotWireVariantsManifest = Partial<Record<SnapshotExpectationPlatform, true>>

/** Deployment permission preset selected before the scenario starts. */
export type SnapshotPermission = 'read-only' | 'workspace-write' | 'danger-full-access'

/** Scenario-local workspace preparation and expected-state metadata. */
export interface SnapshotWorkspaceManifest {
  /** Named setup needed for state Git cannot represent directly. */
  setup?: string
  /** Whether `workspace.expected/` owns the complete final world state. */
  final?: true
  /** Place the generated cwd under the user's home instead of a temporary root. */
  parent?: 'home'
}

/** Controller input that cannot enter a session because admission rejects it. */
export interface SnapshotInputAttachment {
  /** Content-addressed attachment id stored in the session message. */
  id: string
  /** MIME type supplied by the controlling interface. */
  mediaType: string
  /** Complete base64 payload needed to reconstruct the input block. */
  data: string
}

/** Controller input bytes or rejected text that the persisted session cannot retain. */
export interface SnapshotInputManifest {
  /** One-shot task absent from the canonical log only when no user event was accepted. */
  task?: string
  /** Binary inputs keyed by the content-addressed ids retained in session JSONL. */
  attachments?: SnapshotInputAttachment[]
}

/** Optional reference to another scenario's canonical session. */
export interface SnapshotSessionReference {
  /** Repository-relative POSIX path from this scenario directory to the owning `session.jsonl`. */
  source: string
}

/** Declarative ownership metadata stored beside a recorded session. */
export interface SnapshotManifest {
  /** Manifest format version. */
  version: 1
  /** Scenario directory name, repeated for reviewable move and copy diagnostics. */
  scenario?: string
  /** Shipped profile whose public interface controls the scenario. */
  profile: SnapshotProfile
  /** Composition id whose sole pin owns its profile patches. */
  composition?: string
  /** Whether the session is live-recordable or deliberately authored. */
  recording?: SnapshotRecording
  /** Request-header class and sidecar ownership. */
  header?: SnapshotHeaderManifest
  /**
   * Platform-variant expected files for the pinned sidecars, read by the host
   * platform instead of the base sidecar; every declared variant file must be
   * committed. Only meaningful on a pinned header.
   */
  expectations?: SnapshotExpectationsManifest
  /**
   * Platform-variant canonical session recordings, read by the host platform
   * instead of the base `session.jsonl` for both replay roles (script and
   * persisted-session comparison target); every declared variant file must be
   * committed. Only a session owner may declare variants.
   */
  sessionVariants?: SnapshotSessionVariantsManifest
  /**
   * Platform-variant child session recordings (`session.<n>.<platform>.jsonl`),
   * read by the host platform instead of the base child fixture of the same
   * index; every declared variant file must be committed. Only a session owner
   * may declare child variants.
   */
  childSessionVariants?: SnapshotChildSessionVariantsManifest
  /**
   * Platform-variant child-indexed sidecars, read by the host platform instead
   * of the base child sidecar of the same index; every declared variant file
   * must be committed.
   */
  childExpectations?: SnapshotChildExpectationsManifest
  /**
   * Platform-variant canonical stdout projections, replacing the base
   * `stdout.expected.jsonl` on their platform; every declared variant file
   * must be committed.
   */
  stdoutVariants?: SnapshotStdoutVariantsManifest
  /**
   * Platform-variant SDK wire goldens, replacing the base
   * `notifications.expected.jsonl` / `result.expected.json` pair on their
   * platform; every declared variant file must be committed.
   */
  wireVariants?: SnapshotWireVariantsManifest
  /** Exceptional replay metadata absent for ordinary successful recordings. */
  replay?: SnapshotReplayManifest
  /** Optional host requirement; portable scenarios omit it. */
  platform?: SnapshotPlatform
  /** Explicit process fallback permission preset. */
  permission?: SnapshotPermission
  /** Test-only string environment additions needed by the declared composition. */
  environment?: Record<string, string>
  /** Workspace setup and external final-state ownership. */
  workspace?: SnapshotWorkspaceManifest
  /** Exceptional controller input absent for ordinary log-driven scenarios. */
  input?: SnapshotInputManifest
  /** Absent when this directory owns `session.jsonl`; present for a read-only borrower. */
  session?: SnapshotSessionReference
}

const PROFILES = new Set<SnapshotProfile>(['headless', 'sdk', 'acp', 'web'])
const RECORDINGS = new Set<SnapshotRecording>(['live', 'authored'])
const PLATFORMS = new Set<SnapshotPlatform>(['posix', 'pwsh'])
const PERMISSIONS = new Set<SnapshotPermission>(['read-only', 'workspace-write', 'danger-full-access'])
const EXPECTATION_PLATFORMS = ['win32', 'posix'] as const
const EXPECTATION_KINDS = new Set<SnapshotExpectationKind>(['system-prompt', 'tool-schemas', 'ui'])
const CHILD_EXPECTATION_KINDS = new Set<SnapshotChildExpectationKind>(['system-prompt', 'tool-schemas'])
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be a mapping`)
  }
  return value as Record<string, unknown>
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const unknown = Object.keys(value).filter(key => !allowed.includes(key)).sort()
  if (unknown.length > 0) throw new Error(`${label} has unknown field(s): ${unknown.join(', ')}`)
}

function name(value: unknown, label: string): string {
  if (typeof value !== 'string' || !NAME_RE.test(value)) {
    throw new Error(`${label} must be a lower-kebab-case name`)
  }
  return value
}

function scenarioSource(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.split('/').every(segment => NAME_RE.test(segment))) {
    throw new Error(`${label} must be a lower-kebab-case name or corpus-relative path`)
  }
  return value
}

function positiveIndexes(value: unknown, label: string): number[] {
  if (!Array.isArray(value)
    || value.some(item => !Number.isInteger(item) || Number(item) < 1)
    || new Set(value).size !== value.length) {
    throw new Error(`${label} must be an array of unique positive integers`)
  }
  return [...value as number[]]
}

/**
 * Parse one `snapshot.yml` without admitting JavaScript YAML tags or unknown fields.
 * @param source - complete manifest text.
 * @param path - diagnostic path.
 * @returns validated manifest metadata.
 */
export function parseSnapshotManifest(source: string, path = 'snapshot.yml'): SnapshotManifest {
  let parsed: unknown
  try {
    parsed = yaml.load(source, { schema: yaml.JSON_SCHEMA })
  } catch (error) {
    throw new Error(`session-snapshot: ${path}: invalid YAML: ${String(error)}`)
  }

  try {
    const root = record(parsed, 'manifest')
    exactKeys(root, [
      'version',
      'scenario',
      'profile',
      'composition',
      'recording',
      'header',
      'expectations',
      'sessionVariants',
      'childSessionVariants',
      'childExpectations',
      'stdoutVariants',
      'wireVariants',
      'replay',
      'platform',
      'permission',
      'environment',
      'workspace',
      'input',
      'session',
    ], 'manifest')
    if (root.version !== 1) throw new Error('manifest.version must equal 1')
    const scenario = root.scenario === undefined ? undefined : name(root.scenario, 'manifest.scenario')
    if (typeof root.profile !== 'string' || !PROFILES.has(root.profile as SnapshotProfile)) {
      throw new Error('manifest.profile must be headless, sdk, acp, or web')
    }

    const composition = root.composition === undefined
      ? undefined
      : name(root.composition, 'manifest.composition')
    let recording: SnapshotRecording | undefined
    if (root.recording !== undefined) {
      if (typeof root.recording !== 'string' || !RECORDINGS.has(root.recording as SnapshotRecording)) {
        throw new Error('manifest.recording must be live or authored')
      }
      recording = root.recording as SnapshotRecording
    }

    let header: SnapshotHeaderManifest | undefined
    if (root.header !== undefined) {
      const value = record(root.header, 'manifest.header')
      exactKeys(value, [
        'class',
        'pin',
        'systemPromptSource',
        'toolSchemasSource',
        'childSystemPrompts',
        'childToolSchemas',
        'changes',
      ], 'manifest.header')
      if (value.pin !== undefined && value.pin !== true) {
        throw new Error('manifest.header.pin must equal true when present')
      }
      if (value.changes !== undefined && (!Number.isInteger(value.changes) || Number(value.changes) < 0)) {
        throw new Error('manifest.header.changes must be a non-negative integer')
      }
      header = {
        class: name(value.class, 'manifest.header.class'),
        ...(value.pin === true ? { pin: true as const } : {}),
        ...(value.systemPromptSource === undefined
          ? {}
          : { systemPromptSource: scenarioSource(value.systemPromptSource, 'manifest.header.systemPromptSource') }),
        ...(value.toolSchemasSource === undefined
          ? {}
          : { toolSchemasSource: scenarioSource(value.toolSchemasSource, 'manifest.header.toolSchemasSource') }),
        ...(value.childSystemPrompts === undefined
          ? {}
          : { childSystemPrompts: positiveIndexes(value.childSystemPrompts, 'manifest.header.childSystemPrompts') }),
        ...(value.childToolSchemas === undefined
          ? {}
          : { childToolSchemas: positiveIndexes(value.childToolSchemas, 'manifest.header.childToolSchemas') }),
        ...(value.changes === undefined ? {} : { changes: Number(value.changes) }),
      }
    }

    let expectations: SnapshotExpectationsManifest | undefined
    if (root.expectations !== undefined) {
      if (header?.pin !== true) throw new Error('manifest.expectations must be declared on a pinned header')
      const value = record(root.expectations, 'manifest.expectations')
      exactKeys(value, ['variants'], 'manifest.expectations')
      const variants = record(value.variants, 'manifest.expectations.variants')
      exactKeys(variants, EXPECTATION_PLATFORMS, 'manifest.expectations.variants')
      if (Object.keys(variants).length === 0) {
        throw new Error('manifest.expectations.variants must declare at least one platform')
      }
      const parsed: Partial<Record<SnapshotExpectationPlatform, SnapshotExpectationKind[]>> = {}
      for (const [variant, kinds] of Object.entries(variants)) {
        const label = `manifest.expectations.variants.${variant}`
        if (!Array.isArray(kinds) || kinds.length === 0) {
          throw new Error(`${label} must be a non-empty array of expectation kinds`)
        }
        if (kinds.some(kind => typeof kind !== 'string' || !EXPECTATION_KINDS.has(kind as SnapshotExpectationKind))) {
          throw new Error(`${label} must list system-prompt, tool-schemas, or ui kinds`)
        }
        if (new Set(kinds).size !== kinds.length) {
          throw new Error(`${label} must not repeat expectation kinds`)
        }
        parsed[variant as SnapshotExpectationPlatform] = [...kinds as SnapshotExpectationKind[]]
      }
      expectations = { variants: parsed }
    }

    let sessionVariants: SnapshotSessionVariantsManifest | undefined
    if (root.sessionVariants !== undefined) {
      if (root.session !== undefined) {
        throw new Error('manifest.sessionVariants cannot be declared by a session borrower')
      }
      const value = record(root.sessionVariants, 'manifest.sessionVariants')
      exactKeys(value, EXPECTATION_PLATFORMS, 'manifest.sessionVariants')
      if (Object.keys(value).length === 0) {
        throw new Error('manifest.sessionVariants must declare at least one platform')
      }
      const parsed: SnapshotSessionVariantsManifest = {}
      for (const [variant, declared] of Object.entries(value)) {
        if (declared !== true) {
          throw new Error(`manifest.sessionVariants.${variant} must equal true when present`)
        }
        parsed[variant as SnapshotExpectationPlatform] = true
      }
      sessionVariants = parsed
    }

    let childSessionVariants: SnapshotChildSessionVariantsManifest | undefined
    if (root.childSessionVariants !== undefined) {
      if (root.session !== undefined) {
        throw new Error('manifest.childSessionVariants cannot be declared by a session borrower')
      }
      const value = record(root.childSessionVariants, 'manifest.childSessionVariants')
      exactKeys(value, EXPECTATION_PLATFORMS, 'manifest.childSessionVariants')
      if (Object.keys(value).length === 0) {
        throw new Error('manifest.childSessionVariants must declare at least one platform')
      }
      const parsed: SnapshotChildSessionVariantsManifest = {}
      for (const [variant, indexes] of Object.entries(value)) {
        parsed[variant as SnapshotExpectationPlatform] = positiveIndexes(
          indexes,
          `manifest.childSessionVariants.${variant}`,
        )
      }
      childSessionVariants = parsed
    }

    let childExpectations: SnapshotChildExpectationsManifest | undefined
    if (root.childExpectations !== undefined) {
      const value = record(root.childExpectations, 'manifest.childExpectations')
      exactKeys(value, ['variants'], 'manifest.childExpectations')
      const variants = record(value.variants, 'manifest.childExpectations.variants')
      exactKeys(variants, EXPECTATION_PLATFORMS, 'manifest.childExpectations.variants')
      if (Object.keys(variants).length === 0) {
        throw new Error('manifest.childExpectations.variants must declare at least one platform')
      }
      const childIndexesFor = (kind: SnapshotChildExpectationKind): number[] | undefined =>
        kind === 'system-prompt' ? header?.childSystemPrompts : header?.childToolSchemas
      const parsed: Partial<Record<SnapshotExpectationPlatform, SnapshotChildExpectationKind[]>> = {}
      for (const [variant, kinds] of Object.entries(variants)) {
        const label = `manifest.childExpectations.variants.${variant}`
        if (!Array.isArray(kinds) || kinds.length === 0) {
          throw new Error(`${label} must be a non-empty array of child expectation kinds`)
        }
        if (kinds.some(kind => typeof kind !== 'string' || !CHILD_EXPECTATION_KINDS.has(kind as SnapshotChildExpectationKind))) {
          throw new Error(`${label} must list system-prompt or tool-schemas kinds`)
        }
        if (new Set(kinds).size !== kinds.length) {
          throw new Error(`${label} must not repeat child expectation kinds`)
        }
        for (const kind of kinds as SnapshotChildExpectationKind[]) {
          if ((childIndexesFor(kind) ?? []).length === 0) {
            throw new Error(`${label} declares ${kind} without a child ${kind} sidecar index`)
          }
        }
        parsed[variant as SnapshotExpectationPlatform] = [...kinds as SnapshotChildExpectationKind[]]
      }
      childExpectations = { variants: parsed }
    }

    let stdoutVariants: SnapshotStdoutVariantsManifest | undefined
    if (root.stdoutVariants !== undefined) {
      const value = record(root.stdoutVariants, 'manifest.stdoutVariants')
      exactKeys(value, EXPECTATION_PLATFORMS, 'manifest.stdoutVariants')
      if (Object.keys(value).length === 0) {
        throw new Error('manifest.stdoutVariants must declare at least one platform')
      }
      const parsed: SnapshotStdoutVariantsManifest = {}
      for (const [variant, declared] of Object.entries(value)) {
        if (declared !== true) {
          throw new Error(`manifest.stdoutVariants.${variant} must equal true when present`)
        }
        parsed[variant as SnapshotExpectationPlatform] = true
      }
      stdoutVariants = parsed
    }

    let wireVariants: SnapshotWireVariantsManifest | undefined
    if (root.wireVariants !== undefined) {
      const value = record(root.wireVariants, 'manifest.wireVariants')
      exactKeys(value, EXPECTATION_PLATFORMS, 'manifest.wireVariants')
      if (Object.keys(value).length === 0) {
        throw new Error('manifest.wireVariants must declare at least one platform')
      }
      const parsed: SnapshotWireVariantsManifest = {}
      for (const [variant, declared] of Object.entries(value)) {
        if (declared !== true) {
          throw new Error(`manifest.wireVariants.${variant} must equal true when present`)
        }
        parsed[variant as SnapshotExpectationPlatform] = true
      }
      wireVariants = parsed
    }

    let replay: SnapshotReplayManifest | undefined
    if (root.replay !== undefined) {
      const value = record(root.replay, 'manifest.replay')
      exactKeys(value, ['override'], 'manifest.replay')
      if (value.override !== true) throw new Error('manifest.replay.override must equal true')
      replay = { override: true }
    }

    let platform: SnapshotPlatform | undefined
    if (root.platform !== undefined) {
      if (typeof root.platform !== 'string' || !PLATFORMS.has(root.platform as SnapshotPlatform)) {
        throw new Error('manifest.platform must be posix or pwsh')
      }
      platform = root.platform as SnapshotPlatform
    }

    let permission: SnapshotPermission | undefined
    if (root.permission !== undefined) {
      if (typeof root.permission !== 'string' || !PERMISSIONS.has(root.permission as SnapshotPermission)) {
        throw new Error('manifest.permission must be read-only, workspace-write, or danger-full-access')
      }
      permission = root.permission as SnapshotPermission
    }

    let environment: Record<string, string> | undefined
    if (root.environment !== undefined) {
      const value = record(root.environment, 'manifest.environment')
      if (Object.entries(value).some(([key, item]) => !/^[A-Z][A-Z0-9_]*$/.test(key) || typeof item !== 'string')) {
        throw new Error('manifest.environment must map uppercase environment names to strings')
      }
      environment = value as Record<string, string>
    }

    let workspace: SnapshotWorkspaceManifest | undefined
    if (root.workspace !== undefined) {
      const value = record(root.workspace, 'manifest.workspace')
      exactKeys(value, ['setup', 'final', 'parent'], 'manifest.workspace')
      if (value.final !== undefined && value.final !== true) {
        throw new Error('manifest.workspace.final must equal true when present')
      }
      if (value.parent !== undefined && value.parent !== 'home') {
        throw new Error('manifest.workspace.parent must equal home')
      }
      workspace = {
        ...(value.setup === undefined ? {} : { setup: name(value.setup, 'manifest.workspace.setup') }),
        ...(value.final === true ? { final: true as const } : {}),
        ...(value.parent === 'home' ? { parent: 'home' as const } : {}),
      }
      if (Object.keys(workspace).length === 0) throw new Error('manifest.workspace must not be empty')
    }

    let input: SnapshotInputManifest | undefined
    if (root.input !== undefined) {
      const value = record(root.input, 'manifest.input')
      exactKeys(value, ['task', 'attachments'], 'manifest.input')
      if (value.task !== undefined && (typeof value.task !== 'string' || value.task.trim() === '')) {
        throw new Error('manifest.input.task must be a non-empty string when present')
      }
      let attachments: SnapshotInputAttachment[] | undefined
      if (value.attachments !== undefined) {
        if (!Array.isArray(value.attachments) || value.attachments.length === 0) {
          throw new Error('manifest.input.attachments must be a non-empty array')
        }
        attachments = value.attachments.map((item, index) => {
          const attachment = record(item, `manifest.input.attachments[${index}]`)
          exactKeys(attachment, ['id', 'mediaType', 'data'], `manifest.input.attachments[${index}]`)
          if (typeof attachment.id !== 'string' || !attachment.id.startsWith('sha256:')) {
            throw new Error(`manifest.input.attachments[${index}].id must start with sha256:`)
          }
          if (typeof attachment.mediaType !== 'string' || !attachment.mediaType.includes('/')) {
            throw new Error(`manifest.input.attachments[${index}].mediaType must be a MIME type`)
          }
          if (typeof attachment.data !== 'string' || attachment.data.length === 0) {
            throw new Error(`manifest.input.attachments[${index}].data must be non-empty base64`)
          }
          return { id: attachment.id, mediaType: attachment.mediaType, data: attachment.data }
        })
        if (new Set(attachments.map(attachment => attachment.id)).size !== attachments.length) {
          throw new Error('manifest.input.attachments must have unique ids')
        }
      }
      if (value.task === undefined && attachments === undefined) {
        throw new Error('manifest.input must declare task or attachments')
      }
      input = {
        ...(value.task === undefined ? {} : { task: value.task }),
        ...(attachments === undefined ? {} : { attachments }),
      }
    }

    let session: SnapshotSessionReference | undefined
    if (root.session !== undefined) {
      const value = record(root.session, 'manifest.session')
      exactKeys(value, ['source'], 'manifest.session')
      if (typeof value.source !== 'string' || value.source.trim() === '') {
        throw new Error('manifest.session.source must be a non-empty string')
      }
      if (isAbsolute(value.source) || value.source.includes('\\') || value.source.includes('\0')) {
        throw new Error('manifest.session.source must be a relative POSIX path')
      }
      session = { source: value.source }
    }

    return {
      version: 1,
      ...(scenario === undefined ? {} : { scenario }),
      profile: root.profile as SnapshotProfile,
      ...(composition === undefined ? {} : { composition }),
      ...(recording === undefined ? {} : { recording }),
      ...(header === undefined ? {} : { header }),
      ...(expectations === undefined ? {} : { expectations }),
      ...(sessionVariants === undefined ? {} : { sessionVariants }),
      ...(childSessionVariants === undefined ? {} : { childSessionVariants }),
      ...(childExpectations === undefined ? {} : { childExpectations }),
      ...(stdoutVariants === undefined ? {} : { stdoutVariants }),
      ...(wireVariants === undefined ? {} : { wireVariants }),
      ...(replay === undefined ? {} : { replay }),
      ...(platform === undefined ? {} : { platform }),
      ...(permission === undefined ? {} : { permission }),
      ...(environment === undefined ? {} : { environment }),
      ...(workspace === undefined ? {} : { workspace }),
      ...(input === undefined ? {} : { input }),
      ...(session === undefined ? {} : { session }),
    }
  } catch (error) {
    /* v8 ignore next -- every parser and validator above throws Error instances. */
    throw new Error(`session-snapshot: ${path}: ${error instanceof Error ? error.message : String(error)}`)
  }
}
