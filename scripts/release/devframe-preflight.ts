/**
 * Local, network-free preflight for the DevFrame self-contained release set.
 *
 * Runs `pnpm pack --dry-run` style assertions WITHOUT publishing and WITHOUT
 * touching the public registry. It fails loud (non-zero exit, per-package
 * detail) when any of the 20 publish objects does not match the detailed design
 * (docs/working/detailed-design-self-contained-distribution.md §A/§B/§C):
 *
 *  1. no `private: true` on any publish object;
 *  2. every object declares `engines`, `publishConfig.access=public`, `repository`;
 *  3. the four framework singletons never survive in `dependencies` (no nested
 *     host copy) on the packages that must promote them to peer;
 *  4. expert-pack-dev / expert-pack-paper actually carry their data files
 *     (experts/ skills/ team.yml/ schemas/) into the tarball, and the paper
 *     pack excludes its `team.m2-draft.yml` draft.
 *
 * `workspace:` ranges in source deps are expected: pnpm rewrites them to real
 * semver on pack. The double-instance guard is assertion 3 — the singletons are
 * never in `dependencies`, so packing cannot nest a second host copy.
 *
 * @module scripts/release/devframe-preflight
 */

import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { attempt, isEntry } from './process.ts'

interface PackSpec {
  readonly dir: string
  readonly name: string
  readonly version: string
  /** When true, run `pack --dry-run --json` and assert data-file coverage. */
  readonly packData?: boolean
  /** When true, assert the dry-run file list excludes the draft team file. */
  readonly excludeDraft?: boolean
}

/** The 20 publish objects, in detailed-design §A order. */
const PACKAGES: readonly PackSpec[] = [
  { dir: 'packages/experimental/project-contracts', name: '@deepseek-ai/dsh-experimental-project-contracts', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/session-identity', name: '@deepseek-ai/dsh-experimental-session-identity', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/devframe', name: '@deepseek-ai/dsh-experimental-devframe', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-evidence', name: '@deepseek-ai/dsh-experimental-agent-evidence', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-hierarchy', name: '@deepseek-ai/dsh-experimental-agent-hierarchy', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/project-controller', name: '@deepseek-ai/dsh-experimental-project-controller', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-routing', name: '@deepseek-ai/dsh-experimental-shadow-routing', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-router', name: '@deepseek-ai/dsh-experimental-shadow-router', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-controller', name: '@deepseek-ai/dsh-experimental-shadow-controller', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-dispatch', name: '@deepseek-ai/dsh-experimental-agent-dispatch', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/command-goal-binding', name: '@deepseek-ai/dsh-experimental-command-goal-binding', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/expert-team', name: '@deepseek-ai/dsh-experimental-expert-team', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/project-memory', name: '@deepseek-ai/dsh-experimental-project-memory', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/client-ui-expert-team', name: '@deepseek-ai/dsh-experimental-client-ui-expert-team', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/client-ui-project-memory', name: '@deepseek-ai/dsh-experimental-client-ui-project-memory', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/expert-pack-dev', name: '@deepseek-ai/dsh-experimental-expert-pack-dev', version: '0.1.6-alpha.1', packData: true },
  { dir: 'packages/experimental/expert-pack-paper', name: '@deepseek-ai/dsh-experimental-expert-pack-paper', version: '0.1.6-alpha.1', packData: true, excludeDraft: true },
  { dir: 'packages/experimental/devframe-profile', name: '@deepseek-ai/dsh-experimental-devframe-profile', version: '0.1.6-alpha.1' },
  { dir: 'packages/workflow/worktree-registry', name: '@deepseek-ai/dsh-worktree-registry', version: '0.1.6-alpha.1' },
  // logger-console keeps its own upstream version line (detailed design §F-D5).
  { dir: 'vendor/logger-console', name: '@deepseek-ai/cordis-plugin-logger-console', version: '1.0.2' },
]

/**
 * Framework singletons that must never ship inside a publish object's own
 * `dependencies`: packing them would nest a second copy under the host.
 */
const FORBIDDEN_DEPS = new Set([
  '@deepseek-ai/cordis',
  '@deepseek-ai/schemastery',
  '@deepseek-ai/dsh-brand',
  '@deepseek-ai/cosmokit',
])

interface Manifest {
  private?: boolean
  version?: string
  engines?: Record<string, unknown>
  publishConfig?: { access?: string }
  repository?: unknown
  dependencies?: Record<string, string>
  peerDependencies?: Record<string, string>
}

function readManifest(root: string, dir: string): Manifest {
  return JSON.parse(readFileSync(join(root, dir, 'package.json'), 'utf8')) as Manifest
}

/** One dry-run file entry as emitted by `pnpm pack --dry-run --json`. */
interface PackDryRun {
  readonly files?: ReadonlyArray<{ readonly path: string }>
}

function assert(condition: boolean, message: string, failures: string[]): void {
  if (!condition) failures.push(message)
}

function checkManifest(spec: PackSpec, root: string, failures: string[]): void {
  const manifest = readManifest(root, spec.dir)
  const tag = `${spec.name} (${spec.dir})`
  assert(manifest.private !== true, `${tag}: must not be private`, failures)
  assert(manifest.version === spec.version, `${tag}: version ${String(manifest.version)} !== ${spec.version}`, failures)
  assert(typeof manifest.engines?.node === 'string', `${tag}: missing engines.node`, failures)
  assert(manifest.publishConfig?.access === 'public', `${tag}: missing publishConfig.access=public`, failures)
  assert(manifest.repository !== undefined, `${tag}: missing repository`, failures)
  for (const forbidden of FORBIDDEN_DEPS) {
    assert(!(forbidden in (manifest.dependencies ?? {})), `${tag}: forbidden singleton ${forbidden} still in dependencies`, failures)
  }
}

function checkPackDryRun(spec: PackSpec, root: string, failures: string[]): void {
  const result = attempt('pnpm', ['--dir', join(root, spec.dir), 'pack', '--dry-run', '--json'])
  if (result.status !== 0) {
    failures.push(`${spec.name}: pack --dry-run failed (${String(result.status)}): ${result.stderr}`)
    return
  }
  let parsed: PackDryRun
  try {
    parsed = JSON.parse(result.stdout) as PackDryRun
  } catch {
    failures.push(`${spec.name}: pack --dry-run --json did not emit JSON`)
    return
  }
  const files = (parsed.files ?? []).map(entry => entry.path)
  const tag = spec.name
  for (const prefix of ['experts/', 'skills/', 'schemas/']) {
    assert(files.some(file => file.startsWith(prefix)), `${tag}: tarball missing ${prefix}*`, failures)
  }
  assert(files.includes('team.yml'), `${tag}: tarball missing team.yml`, failures)
  if (spec.excludeDraft === true) {
    assert(!files.includes('team.m2-draft.yml'), `${tag}: draft team.m2-draft.yml leaked into tarball`, failures)
  }
  console.log(`  pack dry-run: ${tag} (${String(files.length)} files)`)
}

function main(): void {
  const root = resolve(process.cwd())
  const failures: string[] = []
  for (const spec of PACKAGES) {
    checkManifest(spec, root, failures)
  }
  for (const spec of PACKAGES) {
    if (spec.packData === true) checkPackDryRun(spec, root, failures)
  }
  if (failures.length > 0) {
    console.error(`\nrelease:devframe:preflight FAILED with ${String(failures.length)} assertion(s):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    process.exit(1)
  }
  console.log(`release:devframe:preflight OK: ${String(PACKAGES.length)} objects verified`)
}

if (isEntry(import.meta.url)) main()
