/** Prepare the disposable npm-project view used by an unpackaged Electron shell. */

import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'
import { createDevelopmentProjectMetadata } from '../src/project-manager.ts'
import type { DesktopRelease } from '../src/release.ts'

interface PackageManifest {
  readonly name?: string
  readonly version?: string
}

/** Inputs whose locations differ between the launcher and isolated tests. */
export interface DevelopmentProjectOptions {
  /** Directory replaced with the generated development project. */
  readonly projectDir: string
  /** Current workspace's `apps/cli` package directory. */
  readonly cliDir: string
  /** Current workspace's private Desktop Host application directory. */
  readonly hostDir: string
  /** pnpm's workspace-wide virtual-hoist directory. */
  readonly dependencyDir: string
  /** Release identity written into the disposable project metadata. */
  readonly release: DesktopRelease
  /**
   * Enable the machine-specific DevFrame local overlay (experimental packages,
   * expert-team/project-memory/shadow narrowing, mobile pairing). Off by
   * default so generic callers and the shared-link unit tests do not require a
   * DevFrame checkout; `dev:desktop` opts in.
   */
  readonly devframeOverlay?: boolean
}

function readManifest(path: string): PackageManifest {
  return JSON.parse(readFileSync(path, 'utf8')) as PackageManifest
}

function removeOwnedPath(path: string): void {
  let stat: ReturnType<typeof lstatSync>
  try {
    stat = lstatSync(path)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return
    throw error
  }
  if (stat.isSymbolicLink()) {
    unlinkSync(path)
    return
  }
  if (stat.isDirectory()) {
    rmSync(path, { recursive: true })
    return
  }
  unlinkSync(path)
}

function linkDirectory(source: string, destination: string): void {
  mkdirSync(dirname(destination), { recursive: true })
  symlinkSync(realpathSync(source), destination, process.platform === 'win32' ? 'junction' : 'dir')
}

function mirrorDependencyLinks(sourceRoot: string, destinationRoot: string): void {
  for (const entry of readdirSync(sourceRoot, { withFileTypes: true })) {
    if (entry.name === '.bin') continue
    const source = join(sourceRoot, entry.name)
    if (entry.name.startsWith('@') && (entry.isDirectory() || entry.isSymbolicLink())) {
      mkdirSync(join(destinationRoot, entry.name), { recursive: true })
      for (const scoped of readdirSync(source, { withFileTypes: true })) {
        if (!scoped.isDirectory() && !scoped.isSymbolicLink()) continue
        linkDirectory(join(source, scoped.name), join(destinationRoot, entry.name, scoped.name))
      }
      continue
    }
    if (entry.isDirectory() || entry.isSymbolicLink()) linkDirectory(source, join(destinationRoot, entry.name))
  }
}

/** Paths injected into the DevFrame deployment narrowing patch. */
interface DevFramePatchPaths {
  /** Repository root (two levels up from `apps/cli`). */
  readonly repoRoot: string
  /** Harness-home vault directory. */
  readonly vaultRoot: string
  /** Optional extra authorized root appended to `shadow-router` (env opt-in). */
  readonly extraAuthorizedRoot: string | undefined
  /** Optional cloudflared binary path (env opt-in); omitted when unset. */
  readonly cloudflaredPath: string | undefined
}

/**
 * Build the machine-specific DevFrame deployment patch. Paths are injected
 * (never hardcoded) and optional lines are omitted when their env is unset, so
 * a generic checkout does not pin another machine's directories.
 * @param paths - Derived repo/home paths and optional env opt-ins.
 * @returns the patch YAML text.
 */
function buildDevFrameDeploymentPatch(paths: DevFramePatchPaths): string {
  const posix = (value: string): string => value.replaceAll('\\', '/')
  const authorizedRoots = [posix(paths.repoRoot), ...paths.extraAuthorizedRoot === undefined
    ? []
    : [posix(paths.extraAuthorizedRoot)]]
  const cloudflaredLine = paths.cloudflaredPath === undefined
    ? []
    : [`    cloudflaredPath: '${posix(paths.cloudflaredPath)}'`]
  return `# Machine-specific narrowing for the Desktop dev profile.
- id: expert-team
  config:
    packs:
      - '${posix(join(paths.repoRoot, 'packages/experimental/expert-pack-paper'))}'
      - '${posix(join(paths.repoRoot, 'packages/experimental/expert-pack-dev'))}'
    artifactsDir: !!js dshHomePath('expert-team-runs')
- id: project-memory
  config:
    workspaceId: dsh-devframe
    vaultRoot: '${posix(paths.vaultRoot)}'
    writeEnabled: true
    userScopeEnabled: true
- id: shadow-router
  config:
    shadowSessionId: session-0e48cb66-32d0-413f-a034-904e8997f6d5
    controllerProfile: 'standard'
    authorizedRoots:
${authorizedRoots.map(root => `      - ${root}`).join('\n')}
# Shadow closed-loop: forwards received work deliveries into the bound
# controllers' live agents (same overlay the web profile carries).
- insert:
    - id: shadow-bridge
      name: '@deepseek-ai/dsh-experimental-shadow-bridge'
      config:
        intervalMs: 60000
        followupMaxChars: 12000
- id: command-goal-binding
  config:
    workspaceId: dsh-devframe
    workspaceRoot: '${posix(paths.repoRoot)}'
    requiredChecksPath: !!js dshHomePath('required-checks.json')
    maxAttempts: 3
    maxGoalRounds: 8
    taskIds: ['devframe-goal']
    checks:
      version: 1
      checks:
        - checkId: git-diff-check
          executable: git
          arguments: ['diff', '--check']
          cwd: '${posix(paths.repoRoot)}'
- id: agent-hierarchy
  config:
    roleToolPolicies:
      controller:
        inheritedTools: ['pwsh', 'read', 'write', 'edit', 'read_image', 'glob', 'grep', 'todo_write', 'job_kill', 'job_list', 'job_output', 'project_task', 'project_integrate', 'agent_dispatch', 'worktree_create', 'worktree_list', 'worktree_prune', 'worktree_remove', 'worktree_status', 'create_goal', 'get_goal', 'update_goal']
      lead:
        inheritedTools: ['read', 'write', 'edit', 'read_image', 'glob', 'grep', 'agent_dispatch', 'project_evidence', 'project_review']
      worker:
        inheritedTools: ['pwsh', 'read', 'write', 'edit', 'read_image', 'glob', 'grep', 'project_deliver', 'project_commit']
    # Lead plugin scopes are pinned during the Stage B provisioning smoke once
    # the task pluginId convention is confirmed (v2 fixes one pluginId).
    leadPluginScopes: {}
# Shadow todo board v2: mounts the project-controller task loop beside the
# DevFrame profile so Shadow-sent work drives a real task board (the same
# overlay the shadow-loop example carries, minus the request-budget consumer;
# see docs/working/shadow-todo-board-v2-plan.zh.md).
- insert:
    # Append-only evidence ledger (ctx.agentEvidence): task/Goal binding
    # receipts, submission receipts, and verification snapshots.
    - id: agent-evidence
      name: '@deepseek-ai/dsh-experimental-agent-evidence'
    # The project task board service (ctx.projectController): task lifecycle,
    # the request budget, and the integration gate. It exposes no tool itself;
    # the consumer rows below mount the tool faces.
    - id: project-controller
      name: '@deepseek-ai/dsh-experimental-project-controller'
      config:
        maxActiveTasks: 2
        requestBudget: 64
    # Integration tool face: project_integrate, for the root controller.
    - id: project-controller-consumer
      name: '@deepseek-ai/dsh-experimental-project-controller/consumer'
      config:
        requiredChecksPath: !!js dshHomePath('required-checks.json')
        gitExecutable: git
        gitTimeoutMs: 60000
        gitMaxOutputBytes: 10485760
    # Task tool face: project_task (plan/start), for the root controller.
    # Takes no config; planning and start derive authority from the live Goal
    # binding, the hierarchy bindings, and the registered worktrees.
    - id: project-controller-task-consumer
      name: '@deepseek-ai/dsh-experimental-project-controller/task-consumer'
    # Delivery tool faces: project_deliver/project_commit for Workers,
    # project_evidence/project_review for their independent plugin leads.
    # requiredChecksByTask/commitPathsByTask stay empty: the host registers
    # each task's approved checkset (git-diff-check in its Worker worktree)
    # and commit scope at approval time via the dynamic registry.
    # defaultCommitPaths pins the scope of the first-round acceptance task
    # (which edits this file); a general task→scope mapping is deferred with
    # the multi-task mechanism (see docs/working/shadow-todo-board-v2-plan.zh.md §7).
    - id: project-controller-delivery-consumer
      name: '@deepseek-ai/dsh-experimental-project-controller/delivery-consumer'
      config:
        repairLimit: 3
        requiredChecksPath: !!js dshHomePath('required-checks.json')
        requiredChecksByTask: {}
        gitExecutable: git
        gitTimeoutMs: 60000
        gitMaxOutputBytes: 10485760
        checkTimeoutMs: 600000
        checkMaxOutputBytes: 1048576
        commitPathsByTask: {}
        defaultCommitPaths: ['packages/experimental/project-controller/src/index.ts']
# Web Shadow entry card: the devframe-profile overlay does not carry this
# row (it ships in the separate shadow-web-profile layer for web), so the
# Desktop profile inserts it here.
- insert:
    - id: ui-shadow-entry
      name: '@deepseek-ai/dsh-experimental-client-ui-shadow-entry'

# DSH Mobile pairing (remote access): same row the web profile carries, so
# the Desktop client keeps the remote-access surface.
- id: dsh-mobile-pairing
  name: '@dsh-mobile/pairing'
  config:
    appUrl: dsh-mobile://pair
    endpointMode: quick
${cloudflaredLine.join('\n')}
    gatewayBind: 127.0.0.1
    gatewayPort: 0
    dshHost: 127.0.0.1
    dshPort: 3080
    stunUrls:
      - stun:stun.cloudflare.com:3478
    enableDirect: true
`
}

/**
 * Replace one disposable project with links to the current built workspace.
 * @param options - Project destination, CLI package, and release identity.
 * @returns the absolute project directory supplied by the caller.
 */
export function prepareDevelopmentProject(options: DevelopmentProjectOptions): string {
  const cliManifest = readManifest(join(options.cliDir, 'package.json'))
  if (cliManifest.name !== '@deepseek-ai/dsh' || cliManifest.version !== options.release.version) {
    throw new Error(
      `desktop development: apps/cli must be @deepseek-ai/dsh@${options.release.version}, found `
      + `${String(cliManifest.name)}@${String(cliManifest.version)}`,
    )
  }
  if (!existsSync(options.dependencyDir)) {
    throw new Error('desktop development: workspace dependency links are missing; run pnpm install')
  }
  const hostManifest = readManifest(join(options.hostDir, 'package.json'))
  if (hostManifest.name !== '@deepseek-ai/dsh-desktop-host' || hostManifest.version !== options.release.version) {
    throw new Error(
      `desktop development: apps/desktop-host must be @deepseek-ai/dsh-desktop-host@${options.release.version}, found `
      + `${String(hostManifest.name)}@${String(hostManifest.version)}`,
    )
  }
  if (!existsSync(join(options.hostDir, 'lib', 'index.js'))) {
    throw new Error('desktop development: apps/desktop-host/lib/index.js is missing; run pnpm run build')
  }

  removeOwnedPath(options.projectDir)
  createDevelopmentProjectMetadata(options.projectDir, options.release)
  const destinationModules = join(options.projectDir, 'node_modules')
  mkdirSync(destinationModules, { recursive: true })
  mirrorDependencyLinks(options.dependencyDir, destinationModules)
  const dshLink = join(destinationModules, '@deepseek-ai', 'dsh')
  removeOwnedPath(dshLink)
  linkDirectory(options.cliDir, dshLink)
  const hostLink = join(destinationModules, '@deepseek-ai', 'dsh-desktop-host')
  removeOwnedPath(hostLink)
  linkDirectory(options.hostDir, hostLink)
  // --- DevFrame local overlay (dev-only; see desktop-product-delivery.md) ---
  if (options.devframeOverlay === true) {
    const devframeRoot = resolve(options.cliDir, '..', '..')
    const dshHome = process.env.DSH_HOME ?? join(homedir(), '.dsh')
    const webModules = join(dshHome, 'profiles', 'web', 'node_modules')
    // Third-party community plugins already installed in the web profile; the
    // desktop dev profile links them from there so both surfaces ship the same
    // plugin set. External packages, not repo assets.
    const externalWebPlugins: ReadonlyArray<string> = [
      'dsh-usage-monitor',
      'dsh-codex-sidebar',
      'dsh-external-agents',
      'dsh-model-switch',
    ]
    const devframeLinks: ReadonlyArray<readonly [string, string]> = [
      ['@deepseek-ai/dsh-experimental-devframe-profile', 'packages/experimental/devframe-profile'],
      ['@deepseek-ai/dsh-experimental-agent-dispatch', 'packages/experimental/agent-dispatch'],
      ['@deepseek-ai/dsh-experimental-agent-hierarchy', 'packages/experimental/agent-hierarchy'],
      ['@deepseek-ai/dsh-experimental-command-goal-binding', 'packages/experimental/command-goal-binding'],
      ['@deepseek-ai/dsh-experimental-client-ui-expert-team', 'packages/experimental/client-ui-expert-team'],
      ['@deepseek-ai/dsh-experimental-client-ui-shadow-entry', 'packages/experimental/client-ui-shadow-entry'],
      ['@dsh-mobile/pairing', 'vendor/dsh-mobile-pairing'],
      ['qrcode', join(webModules, 'qrcode')],
      ['tweetnacl', join(webModules, 'tweetnacl')],
      ['werift', join(webModules, 'werift')],
      ['@dsh-mobile/e2e-tunnel', join(webModules, '@dsh-mobile', 'e2e-tunnel')],

      // Web-profile third-party plugins, linked (not vendored) from webModules.
      ...externalWebPlugins.map(name => [name, join(webModules, name)] as const),

      ['@deepseek-ai/dsh-experimental-expert-pack-dev', 'packages/experimental/expert-pack-dev'],
      ['@deepseek-ai/dsh-experimental-expert-pack-paper', 'packages/experimental/expert-pack-paper'],
      ['@deepseek-ai/dsh-experimental-expert-team', 'packages/experimental/expert-team'],
      ['@deepseek-ai/dsh-experimental-project-memory', 'packages/experimental/project-memory'],
      ['@deepseek-ai/dsh-experimental-session-identity', 'packages/experimental/session-identity'],
      ['@deepseek-ai/dsh-experimental-shadow-controller', 'packages/experimental/shadow-controller'],
      ['@deepseek-ai/dsh-experimental-shadow-router', 'packages/experimental/shadow-router'],
      ['@deepseek-ai/dsh-experimental-shadow-bridge', 'packages/experimental/shadow-bridge'],
      ['@deepseek-ai/dsh-experimental-agent-evidence', 'packages/experimental/agent-evidence'],
      ['@deepseek-ai/dsh-experimental-project-controller', 'packages/experimental/project-controller'],
      ['@deepseek-ai/dsh-experimental-project-contracts', 'packages/experimental/project-contracts'],
      ['@deepseek-ai/dsh-experimental-devframe', 'packages/experimental/devframe'],
      ['@deepseek-ai/dsh-worktree-registry', 'packages/workflow/worktree-registry'],
      ['js-yaml', 'node_modules/js-yaml'],
    ]
    for (const [name, relative] of devframeLinks) {
      const source = resolve(devframeRoot, relative)
      const destination = join(destinationModules, ...name.split('/'))
      removeOwnedPath(destination)
      linkDirectory(source, destination)
    }
    // Mobile-pairing vendor package needs its direct deps resolvable from its own
    // tree (it lives outside the project), so junction them into the vendor package.
    const pairingDeps: ReadonlyArray<readonly [string, string]> = [
      ['@deepseek-ai/schemastery', join(destinationModules, '@deepseek-ai', 'schemastery')],
      ['@dsh-mobile/e2e-tunnel', join(destinationModules, '@dsh-mobile', 'e2e-tunnel')],
      ['qrcode', join(destinationModules, 'qrcode')],
      ['tweetnacl', join(destinationModules, 'tweetnacl')],
      ['werift', join(destinationModules, 'werift')],
      ['ws', join(destinationModules, 'ws')],
    ]
    for (const [name, source] of pairingDeps) {
      const destination = join(devframeRoot, 'vendor/dsh-mobile-pairing/node_modules', ...name.split('/'))
      removeOwnedPath(destination)
      linkDirectory(source, destination)
    }
    const devframeManifestPath = join(options.projectDir, 'package.json')
    const devframeManifest = JSON.parse(readFileSync(devframeManifestPath, 'utf8')) as {
      dependencies: Record<string, string>
      dsh: { profile: { bundles: string[] } }
    }
    for (const [name, relative] of devframeLinks) {
      if (name.startsWith('@deepseek-ai/dsh-experimental-') || name === '@deepseek-ai/dsh-worktree-registry') {
        const linked = readManifest(join(devframeRoot, relative, 'package.json'))
        if (typeof linked.version !== 'string' || linked.version === '') {
          throw new Error(`desktop development: ${relative} package.json has no version`)
        }
        devframeManifest.dependencies[name] = linked.version
      }
    }
    devframeManifest.dependencies['@dsh-mobile/pairing'] = '0.1.15'
    // Read the third-party plugin versions from their installed web-profile
    // manifests so a web-profile upgrade flows through without editing this script.
    for (const external of externalWebPlugins) {
      const linked = readManifest(join(webModules, external, 'package.json'))
      if (typeof linked.version !== 'string' || linked.version === '') {
        throw new Error(`desktop development: web-profile ${external} package.json has no version`)
      }
      devframeManifest.dependencies[external] = linked.version
    }

    const bundles = devframeManifest.dsh.profile.bundles
    if (!bundles.includes('@deepseek-ai/dsh-experimental-devframe-profile')) {
      bundles.push('@deepseek-ai/dsh-experimental-devframe-profile')
    }
    if (!bundles.includes('@dsh-mobile/pairing')) {
      bundles.push('@dsh-mobile/pairing')
    }
    for (const external of externalWebPlugins) {
      if (!bundles.includes(external)) bundles.push(external)
    }
    writeFileSync(devframeManifestPath, `${JSON.stringify(devframeManifest, undefined, 2)}\n`)
    // Machine-specific deployment narrowing for the Desktop dev profile
    // (same semantics as the web deployment layer; a patch replaces the whole row).
    writeFileSync(join(options.projectDir, PROFILE_PATCH_FILENAME_DEVFRAME), `${buildDevFrameDeploymentPatch({
      repoRoot: devframeRoot,
      vaultRoot: join(dshHome, 'vault'),
      extraAuthorizedRoot: process.env.DSH_DESKTOP_EXTRA_AUTHORIZED_ROOT,
      cloudflaredPath: process.env.DSH_CLOUDFLARED_PATH,
    })}\n`)
  }
  // --- end DevFrame overlay ---
  return options.projectDir
}

const PROFILE_PATCH_FILENAME_DEVFRAME = 'cordis.patch.yml'
