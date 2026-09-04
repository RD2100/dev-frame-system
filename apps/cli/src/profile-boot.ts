/**
 * Shared profile boot for every `dsh` surface: resolve the profile, stack its
 * patch layers (bundle layers in `dsh.profile.bundles` order, the profile's
 * own `cordis.patch.yml`, `--patch` overlays, the telemetry switch), mount the
 * tree over the profile's empty root config, keep the profile patch layer
 * live, and wire fail-loud plus bounded shutdown.
 *
 * App flags are not the launcher's business: the invocation's inner arguments
 * are provided to the tree through `ctx.cmdlineArgs`, where any injected app
 * plugin may read the same immutable snapshot.
 * @module @deepseek-ai/dsh/profile-boot
 */

import { writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Context, FiberState } from '@deepseek-ai/cordis'
import type { PatchOptions } from '@deepseek-ai/cordis-plugin-include'
import type { EntryOptions } from '@deepseek-ai/cordis-plugin-loader'
import {
  boot,
  composeEntries,
  DSH_PROFILE_IDENTITY_KEY,
  ensureProfileIdentity,
  healProfilesModuleFallback,
  installFailLoud,
  loadOptionalPatches,
  loadOverlayPatches,
  loadProfile,
  PROFILE_PATCH_FILENAME,
  watchUserPatches,
  type Profile,
} from '@deepseek-ai/dsh-app-boot'
import { resolveDshHome } from '@deepseek-ai/dsh-home-paths'
import {
  acquireProfileHostFence,
  DSH_PROFILE_HOST_FENCE_KEY,
  type DevFrameGlobalBootstrapGeneration,
  type ProfileHostFence,
  type ProfileHostFenceLease,
} from '@deepseek-ai/dsh-devframe-control-session'

/** Shipped agent-preset root: beside this app's own config, in both source and built layouts. */
const SHIPPED_PRESET_ROOT = fileURLToPath(new URL('../config/agent-presets/', import.meta.url))

import { DSH_LAUNCH_ENVIRONMENT_KEY, type LaunchEnvironmentSnapshot } from '@deepseek-ai/dsh-launch-environment'
import { provideCmdline } from '@deepseek-ai/dsh-cmdline'
import { createProcessShutdown, type ProcessShutdown } from './process-shutdown.ts'

const NAME = 'dsh'

/** Cordis exposes FiberState as a const enum, so mirror the runtime value. */
const FIBER_ACTIVE = 2 as FiberState.ACTIVE

/** The Host service row whose effective presence activates the canonical DevFrame writer fence. */
const DEVFRAME_CONTROL_SESSION_ROW_ID = 'devframe-control-session'

/**
 * Web is the normal DevFrame surface. A one-shot `task` invocation keeps the
 * same model/session/workspace services but must not start a second command
 * parser or bind a browser server; these rows are the Web-only surface.
 */
const TASK_MODE_DISABLED_ROWS = [
  'directory-picker',
  'plugin-inventory',
  'api-gateway',
  'cordis-host-runner',
  'web-startup',
  'webserver',
  'web-runtime',
  'client-hmr',
  'modules',
  'connection',
  'api-remotes',
  'client-runtime',
  'cordis-client-runner',
  'ui-theme',
  'locale',
  'ui-layout',
  'ui-sidebar',
  'ui-settings',
  'ui-settings-general',
  'ui-settings-models',
  'ui-settings-plugin-inventory',
  'ui-conversation',
  'ui-tool',
  'ui-cordis',
  'ui-workflow-run',
  'ui-deliverables',
  'ui-workspace',
  'ui-input-trigger',
  'ui-commands',
  'ui-skill',
  'ui-subagent',
  'ui-jobs',
  'ui-goal',
  'ui-message-feedback',
  'ui-model-selection',
  'ui-permission',
  'ui-agent-preset',
  'ui-settings-plugins',
  'ui-plan',
  'ui-user-questions',
  'ui-trajectory',
  'client-ui-devframe-control-session',
] as const

/** Return the final overlay that turns the Web profile into a headless task run. */
export function resolveTaskModePatches(args: readonly string[]): PatchOptions[] {
  if (args[0] !== 'task') return []
  return [
    ...TASK_MODE_DISABLED_ROWS.map(id => ({ id, disabled: true })),
    // The Web profile deliberately moves model-facing filesystem and shell
    // tools behind an agent preset. A one-shot CLI task has no browser session
    // to compose that preset, so restore the native host rows here. Global
    // DevFrame controllers still install their own empty-tool guard; these
    // rows only make the project Agent's DSH tool registry available.
    { id: 'tool-fs', disabled: false },
    { id: 'tool-fs-search', disabled: false },
    { id: 'tool-str-replace-editor', disabled: false },
    { id: 'tool-bash', disabled: process.platform === 'win32' },
    { id: 'tool-pwsh', disabled: process.platform !== 'win32' },
  ]
}

/**
 * The home-level user patch layer (`$DSH_HOME/cordis.patch.yml`), applied
 * over every profile's own layer. Resolved per call, not at module load:
 * `$DSH_HOME` may be set by the test or launcher after import.
 * @returns the absolute patch-file path.
 */
export function homePatchPath(): string {
  return join(resolveDshHome(), PROFILE_PATCH_FILENAME)
}

/** Absolute path of this dsh installation's package.json (both anchors: src/ and lib/ sit one level under apps/cli). */
export const INSTALL_ANCHOR = fileURLToPath(new URL('../package.json', import.meta.url))

/** The session-telemetry row id the DSH_TELEMETRY_DISABLED switch targets. */
const TELEMETRY_ROW_ID = 'session-telemetry-otel'

/** The empty root entry list every profile tree patches over. */
const PROFILE_ROOT_CONFIG = `# dsh profile root — an empty entry list. The tree is composed as patches:
# each bundle in package.json's dsh.profile.bundles, then cordis.patch.yml, then any
# --patch overlays. Edit cordis.patch.yml, not this file.
[]
`

/** Root config filename inside a profile directory. */
export const PROFILE_ROOT_FILENAME = 'cordis.yml'

/**
 * Resolve the telemetry opt-out switch into its boot patch. ANY non-empty
 * value (including `'0'`/`'false'`) disables: a privacy switch prefers
 * off-by-mistake over on-by-mistake. A composition without the telemetry row
 * exports nothing, so the switch is then trivially satisfied and no patch is
 * generated — custom profiles need not mount telemetry to run with the
 * switch set.
 * @param disabledEnv - the raw `DSH_TELEMETRY_DISABLED` value (`undefined` when unset).
 * @param hasRow - whether the composition carries the telemetry row.
 * @returns the disable patch, or `undefined` when no hard-disable patch is required.
 */
export function resolveTelemetryPatch(disabledEnv: string | undefined, hasRow: boolean): PatchOptions | undefined {
  if ((disabledEnv ?? '') === '' || !hasRow) return undefined
  return { id: TELEMETRY_ROW_ID, disabled: true }
}

/**
 * Load a resolved profile for `name`: heal the shared module fallback, then
 * (re)write the empty root config. The root is always rewritten: the whole
 * composition is patch layers, and the vendored Loader's tree write-back (a
 * plugin self-disposing persists the current tree) can bake composed rows
 * into this file — which would duplicate every bundle insert on the next
 * boot. The file exists on disk only because the Loader needs a real include
 * root to anchor `baseUrl` at the profile directory (the config dump anchors
 * on the same file, so both compose over the identical base).
 * @param name - the profile name.
 * @param userLayer - `false` skips parsing `cordis.patch.yml` (the default dump).
 * @returns the loaded profile.
 */
export function prepareProfile(name: string, userLayer = true): Profile {
  healProfilesModuleFallback(INSTALL_ANCHOR)
  const profile = loadProfile(NAME, name, INSTALL_ANCHOR, undefined, { userLayer })
  writeFileSync(join(profile.dir, PROFILE_ROOT_FILENAME), PROFILE_ROOT_CONFIG)
  return profile
}

/** One profile's patch layers (application order) and the row index of its pre-flag composition. */
interface ComposedProfile {
  profile: Profile
  /** Bundle layers concatenated — the part below the user layers on a live reload. */
  bundlePatches: PatchOptions[]
  /** The home-level user layer (`$DSH_HOME/cordis.patch.yml`), applied after the profile's own. */
  homePatches: PatchOptions[]
  /** Layers above the user layers on a live reload: `--patch` overlays and the telemetry switch. */
  overlays: PatchOptions[]
  /**
   * id → row of the composed tree (bundles + user layers + overlays), for the
   * launcher's own row checks.
   */
  rows: ReadonlyMap<string, EntryOptions>
}

/** The full patch stack of one composed profile, in application order. */
function allPatches(composed: ComposedProfile): PatchOptions[] {
  return [
    ...composed.bundlePatches,
    ...composed.profile.patches,
    ...composed.homePatches,
    ...composed.overlays,
  ]
}

/**
 * Load `name` and compose its effective patch stack: bundle layers in
 * `dsh.profile.bundles` order (the base bundle gates the shell stacks by
 * platform on its own rows), the profile's user layer, the home-level user
 * layer (`$DSH_HOME/cordis.patch.yml` — machine-local preferences that apply
 * to every profile, so it outranks the per-profile layer), `--patch` overlays,
 * then the telemetry switch.
 * @param name - the profile name.
 * @param patchFiles - `--patch` overlay paths, in argv order.
 * @returns the profile, its patch layers, and the composed row index.
 */
function composeProfile(
  name: string,
  patchFiles: readonly string[],
  taskMode = false,
): ComposedProfile {
  const profile = prepareProfile(name)
  const homePatches = loadOptionalPatches(NAME, homePatchPath()) ?? []
  const overlays = patchFiles.flatMap(file => loadOverlayPatches(NAME, resolve(file)))
  const bundlePatches = profile.layers.flatMap(layer => layer.patches)
  const taskPatches = taskMode && name === 'devframe' ? resolveTaskModePatches(['task']) : []
  const rows = new Map<string, EntryOptions>()
  for (const row of composeEntries([bundlePatches, profile.patches, homePatches, overlays, taskPatches])) {
    if (typeof row.id === 'string') rows.set(row.id, row)
  }
  const composedOverlays = [...overlays, ...taskPatches]
  // The SHIPPED root is the part of the roster only this app can resolve: it
  // sits beside this app's own config, in both the source and built layouts.
  // The writable root the roster appends is `dsh-agent-presets`' own, so a
  // launcher that never reaches this patch still finds a person's presets.
  if (rows.has('agent-presets')) {
    composedOverlays.push({
      id: 'agent-presets',
      config: {
        ...(rows.get('agent-presets')?.config ?? {}) as Record<string, unknown>,
        roots: [{ path: SHIPPED_PRESET_ROOT, trust: 'system' }],
      },
    })
  }
  const telemetryPatch = resolveTelemetryPatch(process.env.DSH_TELEMETRY_DISABLED, rows.has(TELEMETRY_ROW_ID))
  if (telemetryPatch !== undefined) composedOverlays.push(telemetryPatch)
  return { profile, bundlePatches, homePatches, overlays: composedOverlays, rows }
}

/** Options for {@link runProfile}. */
export interface RunProfileOptions {
  /** This run's frozen environment snapshot, provided before any entry mounts. */
  environment: LaunchEnvironmentSnapshot
  /** The profile name to boot. */
  profile: string
  /** `--patch` overlay paths, in argv order. */
  patchFiles: readonly string[]
  /** The invocation's inner arguments, handed to the tree through `ctx.cmdlineArgs`. */
  args: readonly string[]
}

/**
 * Re-throw a watcher-setup failure unless a shutdown already owns the tree:
 * a signal aborted this invocation, or an app requested exit (`ctx.appExit`
 * from a fast one-shot) and the root's disposal rejected the in-flight setup
 * await. Either way the failure describes a tree that is exiting as asked,
 * not a broken watch.
 * @param ctx - the booted root context.
 * @param signal - this invocation's signal-shutdown fact.
 * @param error - the setup failure.
 */
function suppressShutdownError(ctx: Context, signal: AbortSignal, error: unknown): void {
  if (signal.aborted) return
  if (ctx.fiber.state !== FIBER_ACTIVE || ctx.get('loader') === undefined) return
  throw error
}

function createProfileHostDisposer(
  app: { current?: Context },
  fence: ProfileHostFenceLease | undefined,
  bootstrap: { current?: DevFrameGlobalBootstrapGeneration },
): () => Promise<void> {
  let operation: Promise<void> | undefined
  return () => {
    operation ??= (async () => {
      const failures: unknown[] = []
      try {
        await bootstrap.current?.stop()
      } catch (failure) {
        failures.push(failure)
      }
      try {
        await app.current?.fiber.dispose()
      } catch (failure) {
        failures.push(failure)
      }
      try {
        await fence?.release()
      } catch (fenceFailure) {
        failures.push(fenceFailure)
      }
      if (failures.length === 1) {
        const failure = failures[0]
        throw failure instanceof Error
          ? failure
          : new Error('dsh: Profile Host teardown failed', { cause: failure })
      }
      if (failures.length > 1) throw new AggregateError(failures, 'dsh: Profile Host teardown failed')
    })()
    return operation
  }
}

/**
 * Boot one profile invocation end to end and leave process lifetime to the
 * mounted plugins (or to a one-shot runner the composition mounts).
 * @param options - environment snapshot, profile name, overlays, and the booted app's own arguments.
 * @returns the settled root context and the shutdown controller.
 */
export async function runProfile(options: RunProfileOptions): Promise<{ ctx: Context; shutdown: ProcessShutdown }> {
  const composed = composeProfile(options.profile, options.patchFiles, options.args[0] === 'task')
  const profileIdentity = await ensureProfileIdentity(NAME, options.profile)
  const profileHostFence = composed.rows.has(DEVFRAME_CONTROL_SESSION_ROW_ID)
    ? await acquireProfileHostFence()
    : undefined
  // Only the immutable owner proof enters the plugin tree. The launcher keeps
  // the release capability private so a config plugin cannot surrender the
  // process-wide writer fence while the tree is still live.
  const profileHostProof: ProfileHostFence | undefined = profileHostFence === undefined
    ? undefined
    : { owner: profileHostFence.owner }
  const app: { current?: Context } = {}
  const globalBootstrap: { current?: DevFrameGlobalBootstrapGeneration } = {}
  const disposeProfileHost = createProfileHostDisposer(app, profileHostFence, globalBootstrap)
  const shutdown = createProcessShutdown(disposeProfileHost)
  const signalShutdown = new AbortController()
  const interrupt = (code: number): void => {
    signalShutdown.abort()
    shutdown.interrupt(code)
  }
  // Signals own teardown throughout the startup window, not only after boot()
  // settles: an inserted provider can publish before sibling rows finish mounting.
  // SIGTERM is a supervisor's ordinary stop request and exits 0 on every
  // surface — the launcher does not know whether the app considered its work
  // complete; SIGINT is a user interrupt and reports 130.
  process.on('SIGTERM', () => { interrupt(0) })
  process.on('SIGINT', () => { interrupt(130) })
  installFailLoud(NAME, process, disposeProfileHost)

  const rootConfig = join(composed.profile.dir, PROFILE_ROOT_FILENAME)
  // Recomposition for the live user layers: bundle layers below, overlays
  // above, so a user edit can never displace them. Parsed app arguments are
  // not in here at all — they live in app-provided services that survive a
  // recomposition. BOTH
  // user files are re-read per generation (the HMR watcher hands us only the
  // changed file's patches, which one of the reads duplicates — fresh reads
  // keep the two watchers from stitching in each other's stale copy).
  // Fresh clones per generation: the include pushes `insert` rows into the
  // mounted tree BY REFERENCE and later id-targeted patches mutate those
  // objects in place. Reusing one parsed patch object across applications
  // would bake a user override into the bundle's in-memory insert row, so
  // removing the override could never revert the row to the bundle default.
  const composeLive = (): PatchOptions[] => structuredClone([
    ...composed.bundlePatches,
    ...loadOptionalPatches(NAME, composed.profile.patchPath) ?? [],
    ...loadOptionalPatches(NAME, homePatchPath()) ?? [],
    ...composed.overlays,
  ])
  // Cloned for the same insert-aliasing reason as composeLive: the boot
  // application must not mutate the objects later reloads recompose from.
  let ctx: Context
  try {
    ctx = await boot(NAME, rootConfig, structuredClone(allPatches(composed)), (hostCtx) => {
      app.current = hostCtx
      // Before any config-tree entry mounts, so plugins resolve all launch-time
      // environment values from the same immutable provenance snapshot.
      hostCtx.provide(DSH_LAUNCH_ENVIRONMENT_KEY, options.environment)
      hostCtx.provide(DSH_PROFILE_IDENTITY_KEY, profileIdentity)
      if (profileHostProof !== undefined) {
        hostCtx.provide(DSH_PROFILE_HOST_FENCE_KEY, profileHostProof)
      }
      // The command line and bounded exit request are launcher facts available
      // to every app plugin that injects the argument snapshot.
      provideCmdline(hostCtx, {
        args: options.args,
        exit: code => void shutdown.shutdown(code),
      })
    })
  } catch (failure) {
    try {
      await disposeProfileHost()
    } catch (cleanupFailure) {
      throw new AggregateError([failure, cleanupFailure], 'dsh: Profile Host startup cleanup failed')
    }
    throw failure
  }
  app.current = ctx
  // The DevFrame bundle owns one profile-scoped Global Controller. Start it
  // only after the Loader has settled every row so identity publication and
  // readiness are observed through the same live tree that serves the client.
  // The generation is retained by the launcher so shutdown fences admission,
  // releases the Agent, and only then disposes the tree and Host lease.
  if (!signalShutdown.signal.aborted && profileHostFence !== undefined) {
    const controlSessions = ctx.get('devframeControlSessions')
    if (controlSessions !== undefined) {
      const generation = controlSessions.beginGlobalBootstrap()
      globalBootstrap.current = generation
      try {
        await generation.open(profileIdentity.id)
      } catch (failure) {
        try {
          await disposeProfileHost()
        } catch (cleanupFailure) {
          throw new AggregateError([failure, cleanupFailure], 'dsh: Global Controller startup cleanup failed')
        }
        throw failure
      }
    }
  }
  // A surface can dispose the whole tree while boot or this post-boot watcher
  // setup is still in flight — a signal, or a fast one-shot's appExit. Loader
  // presence and fiber state own liveness; the initial check skips a tree
  // that already exited, and the catch below re-checks for an exit that
  // landed mid-setup. Watching is unconditional: a one-shot surface exits
  // through its bounded shutdown, which disposes the watchers before the
  // loop drains.
  if (!signalShutdown.signal.aborted
    && ctx.fiber.state === FIBER_ACTIVE
    && ctx.get('loader') !== undefined) {
    try {
      // Config-only HMR for the live profile patch layer: the web bundle
      // disables the shared module-reload `hmr` row (its reload lifecycle is
      // untested), so when the composition leaves no HMR service, mount a
      // watch-only instance with no module roots — cordis.patch.yml edits stay
      // live on every long-lived surface. A silent skip would break the
      // documented hot-reload contract. HMR injects the timer service, which a
      // bare custom profile may not mount either.
      if (ctx.get('hmr') === undefined) {
        if (ctx.get('timer') === undefined) {
          await ctx.loader.create({ name: '@deepseek-ai/cordis-plugin-timer' })
        }
        await ctx.loader.create({ name: '@deepseek-ai/cordis-plugin-hmr', config: { root: [] } })
      }
      await watchUserPatches(ctx, {
        binName: NAME,
        filename: composed.profile.patchPath,
        compose: composeLive,
      })
      await watchUserPatches(ctx, {
        binName: NAME,
        filename: homePatchPath(),
        compose: composeLive,
      })
    } catch (error) {
      suppressShutdownError(ctx, signalShutdown.signal, error)
    }
  }
  return { ctx, shutdown }
}
