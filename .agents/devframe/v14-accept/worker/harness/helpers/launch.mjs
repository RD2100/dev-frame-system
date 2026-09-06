/**
 * Acceptance harness launch helpers (v14-accept worker, design §1).
 *
 * Mechanism A: spawn the real CLI/profile entry (`apps/cli/src/bin.ts --profile
 * headless`) under an isolated env (`DSH_HOME`, `DSH_TELEMETRY_DISABLED=1`,
 * `TSX_TSCONFIG_PATH`) and an isolated cwd, capturing the real exit code and
 * stdout/stderr verbatim. Mechanism B: boot a real in-process Cordis
 * composition (`new Context()` + the caller's plugin sequence) over an
 * isolated root.
 *
 * Every run must pass `node --import tsx/esm` with `TSX_TSCONFIG_PATH` pointed
 * at the tree's tsconfig so the `@deepseek-ai/dsh-*` imports resolve to
 * workspace source (the repo's scripts-launch contract).
 * @module harness/lib/launch
 */

import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'

/** Absolute directory of this lib file (`<tree>/.agents/devframe/v14-accept/worker/harness/lib`). */
const LIB_DIR = dirname(fileURLToPath(import.meta.url))

/**
 * The worktree this harness ships in. The harness imports workspace source
 * relative to this root, so it always matches the tree the scripts live in.
 */
export const TREE_ROOT = resolve(LIB_DIR, '..', '..', '..', '..', '..', '..')

/** Absolute directory of the harness scripts (`<tree>/.../harness`). */
export const HARNESS_DIR = dirname(LIB_DIR)

/**
 * Create one isolated scenario root under the platform temp directory. The
 * caller owns everything created inside it; nothing outside it is written.
 * @param {string} label - short scenario tag used in the directory name.
 * @returns {string} the fresh root directory path.
 */
export function isolatedRoot(label) {
  return mkdtempSync(join(tmpdir(), `dsh-accept-${label}-`))
}

/**
 * Build one launch's isolated environment. `DSH_PERMISSION_MODE` is removed
 * unless the caller supplies it, so a leftover value in the lead's shell can
 * never silently change a run's permission facts (design S2 varies it
 * explicitly; S1/S3 run without it). A caller value of `null` deletes the key.
 * @param {object} options - same fields as {@link launchHeadless}.
 * @returns {NodeJS.ProcessEnv} the merged child environment.
 */
function isolatedEnv({ tree, dshHome, cwd, env = {} }) {
  const merged = {
    ...process.env,
    DSH_HOME: dshHome,
    // Skill scanning defaults to ~/.agents; point it inside the isolated root
    // (runLoaderSmoke / session-snapshot launcher precedent).
    DSH_AGENTS_HOME: join(cwd, '.agents'),
    DSH_TELEMETRY_DISABLED: '1',
    TSX_TSCONFIG_PATH: join(tree, 'tsconfig.json'),
    ...env,
  }
  for (const [key, value] of Object.entries(env)) {
    if (value === null) delete merged[key]
  }
  if (!('DSH_PERMISSION_MODE' in env)) delete merged.DSH_PERMISSION_MODE
  return merged
}

/**
 * Mechanism A: spawn the real `dsh --profile headless "<task>"` CLI from
 * source and capture its real exit code, stdout, and stderr verbatim.
 * @param {object} options - launch description.
 * @param {string} options.tree - worktree whose CLI is launched (its
 *   `apps/cli/src/bin.ts` and `tsconfig.json` are used).
 * @param {string} options.task - the task string passed to the profile.
 * @param {string} options.dshHome - isolated `DSH_HOME` (created if absent by
 *   the product).
 * @param {string} options.cwd - the child process's dedicated cwd.
 * @param {number} [options.timeoutMs=120000] - kill deadline for the child.
 * @param {NodeJS.ProcessEnv} [options.env] - extra env merged over the
 *   isolated base; `null` deletes a key.
 * @returns {Promise<{exitCode: number|null, signal: NodeJS.Signals|null, stdout: string,
 *   stderr: string, timedOut: boolean, durationMs: number, command: string,
 *   args: string[], cwd: string, dshHome: string, task: string,
 *   isolationEnv: Record<string, string|undefined>}>} the real run record.
 */
export function launchHeadless(options) {
  const { tree, task, dshHome, cwd, timeoutMs = 120_000, env = {} } = options
  const bin = join(tree, 'apps', 'cli', 'src', 'bin.ts')
  // Resolve the ESM tsx hook from this harness's tree (root node_modules).
  const tsxHref = import.meta.resolve('tsx/esm')
  const args = ['--import', tsxHref, bin, '--profile', 'headless', task]
  const childEnv = isolatedEnv({ tree, dshHome, cwd, env })
  const startedAt = Date.now()
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(process.execPath, args, {
      cwd,
      env: childEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let stdout = Buffer.alloc(0)
    let stderr = Buffer.alloc(0)
    let timedOut = false
    let settled = false
    const timer = setTimeout(() => {
      timedOut = true
      child.kill()
      // Windows fallback: a hung tree that ignores the termination signal.
      const forceTimer = setTimeout(() => {
        // The pid may already be gone or taskkill may be absent (POSIX);
        // either is fine — the kill attempt is best-effort by design.
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
          .on('error', () => {})
      }, 5_000)
      forceTimer.unref?.()
    }, timeoutMs)
    child.stdout.on('data', (chunk) => { stdout = Buffer.concat([stdout, chunk]) })
    child.stderr.on('data', (chunk) => { stderr = Buffer.concat([stderr, chunk]) })
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      rejectPromise(new Error(`launchHeadless: spawn failed for "${task}": ${error.message}`, { cause: error }))
    })
    child.on('close', (exitCode, signal) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolvePromise({
        exitCode,
        signal,
        stdout: stdout.toString('utf8'),
        stderr: stderr.toString('utf8'),
        timedOut,
        durationMs: Date.now() - startedAt,
        command: process.execPath,
        args,
        cwd,
        dshHome,
        task,
        isolationEnv: {
          DSH_HOME: childEnv.DSH_HOME,
          DSH_AGENTS_HOME: childEnv.DSH_AGENTS_HOME,
          DSH_TELEMETRY_DISABLED: childEnv.DSH_TELEMETRY_DISABLED,
          TSX_TSCONFIG_PATH: childEnv.TSX_TSCONFIG_PATH,
          DSH_PERMISSION_MODE: childEnv.DSH_PERMISSION_MODE,
        },
      })
    })
  })
}

/**
 * Mechanism B: boot one real in-process Cordis composition over an isolated
 * root: a fresh `Context` plus the caller's real plugin sequence, applied in
 * order. A failing plugin load disposes the context before rethrowing.
 * @param {Array<unknown | [unknown, unknown]>} plugins - plugin entries in
 *   mount order; an entry is a plugin or a `[plugin, config]` pair.
 * @param {string} root - the isolated root this composition is bound to
 *   (diagnostic identity; each plugin config carries its own paths).
 * @returns {Promise<{ctx: Context, root: string}>} the booted composition; the
 *   caller owns teardown via `ctx.fiber.dispose()`.
 */
export async function bootComposition(plugins, root) {
  const ctx = new Context()
  try {
    for (const entry of plugins) {
      const [plugin, config] = Array.isArray(entry) ? entry : [entry, undefined]
      if (config === undefined) await ctx.plugin(plugin)
      else await ctx.plugin(plugin, config)
    }
  } catch (error) {
    await ctx.fiber.dispose()
    throw error
  }
  return { ctx, root }
}

/**
 * Parse a scenario's fixed CLI (`--flag value` pairs only, per design §1).
 * @param {string[]} argv - raw argv after the script path.
 * @param {Record<string, {required?: boolean}>} flags - accepted value flags.
 * @param {string} usage - usage line shown on invalid input.
 * @returns {Record<string, string>} parsed flag values.
 */
export function parseCliArgs(argv, flags, usage) {
  const parsed = {}
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index]
    if (!token.startsWith('--')) throw new Error(`parseCliArgs: unexpected argument "${token}". ${usage}`)
    const name = token.slice(2)
    const value = argv[index + 1]
    if (value === undefined || value.startsWith('--')) {
      throw new Error(`parseCliArgs: flag "${token}" requires a value. ${usage}`)
    }
    if (!(name in flags)) throw new Error(`parseCliArgs: unknown flag "${token}". ${usage}`)
    parsed[name] = value
    index += 1
  }
  for (const [name, spec] of Object.entries(flags)) {
    if (spec.required === true && parsed[name] === undefined) {
      throw new Error(`parseCliArgs: missing required flag --${name}. ${usage}`)
    }
  }
  return parsed
}
