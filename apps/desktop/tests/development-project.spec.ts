import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { prepareDevelopmentProject } from '../scripts/development-project.ts'
import { DESKTOP_HOST_PROTOCOL_VERSION } from '../src/host-protocol.ts'
import type { DesktopRelease } from '../src/release.ts'

const roots: string[] = []

function temporaryRoot(): string {
  const root = mkdtempSync(join(tmpdir(), 'dsh-desktop-development-test-'))
  roots.push(root)
  return root
}

function release(version = '1.2.3'): DesktopRelease {
  return {
    schemaVersion: 1,
    version,
    hostProtocolVersion: DESKTOP_HOST_PROTOCOL_VERSION,
    nodeVersion: '24.17.0',
    pnpmVersion: '11.7.0',
  }
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('desktop development project', () => {
  it('projects the built dsh and Desktop Host applications with their dependency graph', () => {
    const root = temporaryRoot()
    const cli = join(root, 'apps', 'cli')
    const host = join(root, 'apps', 'desktop-host')
    const dependencies = join(root, 'workspace-dependencies')
    mkdirSync(join(cli, 'lib'), { recursive: true })
    mkdirSync(join(host, 'lib'), { recursive: true })
    mkdirSync(join(dependencies, '@scope'), { recursive: true })
    mkdirSync(join(dependencies, '@deepseek-ai', 'dsh'), { recursive: true })
    writeFileSync(join(cli, 'package.json'), '{"name":"@deepseek-ai/dsh","version":"1.2.3"}\n')
    writeFileSync(join(host, 'package.json'), '{"name":"@deepseek-ai/dsh-desktop-host","version":"1.2.3"}\n')
    writeFileSync(join(host, 'lib', 'index.js'), '')
    writeFileSync(join(dependencies, '@deepseek-ai', 'dsh', 'package.json'), '{}\n')
    mkdirSync(join(dependencies, 'plain-dependency'))
    writeFileSync(join(dependencies, 'plain-dependency', 'package.json'), '{}\n')
    mkdirSync(join(dependencies, '@scope', 'dependency'))
    writeFileSync(join(dependencies, '@scope', 'dependency', 'package.json'), '{}\n')

    const project = prepareDevelopmentProject({
      projectDir: join(root, 'development'),
      cliDir: cli,
      hostDir: host,
      dependencyDir: dependencies,
      release: release(),
    })
    expect(realpathSync(join(project, 'node_modules', '@deepseek-ai', 'dsh'))).toBe(realpathSync(cli))
    expect(realpathSync(join(project, 'node_modules', '@deepseek-ai', 'dsh-desktop-host'))).toBe(realpathSync(host))
    expect(realpathSync(join(project, 'node_modules', 'plain-dependency')))
      .toBe(realpathSync(join(dependencies, 'plain-dependency')))
    expect(realpathSync(join(project, 'node_modules', '@scope', 'dependency')))
      .toBe(realpathSync(join(dependencies, '@scope', 'dependency')))
    const manifest = JSON.parse(readFileSync(join(project, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>
    }
    expect(manifest.dependencies['@deepseek-ai/dsh']).toBe('1.2.3')
    expect(manifest.dependencies['@deepseek-ai/dsh-desktop-host']).toBe('1.2.3')
  })

  it('rejects a CLI package from another release', () => {
    const root = temporaryRoot()
    const cli = join(root, 'apps', 'cli')
    const host = join(root, 'apps', 'desktop-host')
    const dependencies = join(root, 'workspace-dependencies')
    mkdirSync(join(cli, 'lib'), { recursive: true })
    mkdirSync(join(host, 'lib'), { recursive: true })
    mkdirSync(dependencies, { recursive: true })
    writeFileSync(join(cli, 'package.json'), '{"name":"@deepseek-ai/dsh","version":"2.0.0"}\n')
    writeFileSync(join(host, 'package.json'), '{"name":"@deepseek-ai/dsh-desktop-host","version":"1.2.3"}\n')
    writeFileSync(join(host, 'lib', 'index.js'), '')
    expect(() => prepareDevelopmentProject({
      projectDir: join(root, 'development'),
      cliDir: cli,
      hostDir: host,
      dependencyDir: dependencies,
      release: release(),
    })).toThrow(/must be @deepseek-ai\/dsh@1\.2\.3/u)
  })

  it('reads experimental versions from source package.json and omits machine-only patch lines', () => {
    const root = temporaryRoot()
    const repo = join(root, 'repo')
    const cli = join(repo, 'apps', 'cli')
    const host = join(repo, 'apps', 'desktop-host')
    const dependencies = join(repo, 'workspace-dependencies')
    mkdirSync(join(cli, 'lib'), { recursive: true })
    mkdirSync(join(host, 'lib'), { recursive: true })
    writeFileSync(join(cli, 'package.json'), '{"name":"@deepseek-ai/dsh","version":"1.2.3"}\n')
    writeFileSync(join(host, 'package.json'), '{"name":"@deepseek-ai/dsh-desktop-host","version":"1.2.3"}\n')
    writeFileSync(join(host, 'lib', 'index.js'), '')
    const experimental: ReadonlyArray<readonly [string, string]> = [
      ['packages/experimental/devframe-profile', '7.7.7'],
      ['packages/experimental/agent-dispatch', '1.0.0'],
      ['packages/experimental/agent-hierarchy', '1.0.0'],
      ['packages/experimental/command-goal-binding', '1.0.0'],
      ['packages/experimental/client-ui-expert-team', '1.0.0'],
      ['packages/experimental/client-ui-shadow-entry', '1.0.0'],
      ['packages/experimental/expert-pack-dev', '1.0.0'],
      ['packages/experimental/expert-pack-paper', '1.0.0'],
      ['packages/experimental/expert-team', '1.0.0'],
      ['packages/experimental/project-memory', '1.0.0'],
      ['packages/experimental/session-identity', '1.0.0'],
      ['packages/experimental/shadow-controller', '1.0.0'],
      ['packages/experimental/shadow-router', '1.0.0'],
      ['packages/experimental/shadow-bridge', '0.1.2-alpha.4'],
      ['packages/experimental/agent-evidence', '0.1.6-alpha.1'],
      ['packages/experimental/project-controller', '0.1.6-alpha.1'],
      ['packages/experimental/project-contracts', '0.1.6-alpha.1'],
      ['packages/experimental/devframe', '0.1.6-alpha.1'],
      ['packages/workflow/worktree-registry', '8.8.8'],
    ]
    for (const [relative, version] of experimental) {
      mkdirSync(join(repo, relative), { recursive: true })
      writeFileSync(join(repo, relative, 'package.json'), `{"name":"@deepseek-ai/x","version":"${version}"}\n`)
    }
    mkdirSync(join(repo, 'vendor/dsh-mobile-pairing'), { recursive: true })
    writeFileSync(join(repo, 'vendor/dsh-mobile-pairing/package.json'), '{"name":"@dsh-mobile/pairing","version":"0.1.15"}\n')
    mkdirSync(join(repo, 'node_modules', 'js-yaml'), { recursive: true })
    const dshHome = join(root, 'dsh-home')
    for (const pkg of ['qrcode', 'tweetnacl', 'werift']) {
      mkdirSync(join(dshHome, 'profiles', 'web', 'node_modules', pkg), { recursive: true })
    }
    mkdirSync(join(dshHome, 'profiles', 'web', 'node_modules', '@dsh-mobile', 'e2e-tunnel'), { recursive: true })
    // The external web-profile plugins the dev overlay links from webModules.
    for (const mod of ['dsh-usage-monitor', 'dsh-codex-sidebar', 'dsh-external-agents', 'dsh-model-switch']) {
      mkdirSync(join(dshHome, 'profiles', 'web', 'node_modules', mod), { recursive: true })
      writeFileSync(join(dshHome, 'profiles', 'web', 'node_modules', mod, 'package.json'), '{"name":"@deepseek-ai/x","version":"9.9.9"}\n')
    }
    for (const mod of ['@deepseek-ai/schemastery', '@dsh-mobile/e2e-tunnel', 'qrcode', 'tweetnacl', 'werift', 'ws']) {
      mkdirSync(join(dependencies, mod), { recursive: true })
    }
    const previousHome = process.env.DSH_HOME
    const previousExtra = process.env.DSH_DESKTOP_EXTRA_AUTHORIZED_ROOT
    const previousCloud = process.env.DSH_CLOUDFLARED_PATH
    process.env.DSH_HOME = dshHome
    delete process.env.DSH_DESKTOP_EXTRA_AUTHORIZED_ROOT
    delete process.env.DSH_CLOUDFLARED_PATH
    try {
      const project = prepareDevelopmentProject({
        projectDir: join(root, 'development'),
        cliDir: cli,
        hostDir: host,
        dependencyDir: dependencies,
        release: release(),
        devframeOverlay: true,
      })
      const manifest = JSON.parse(readFileSync(join(project, 'package.json'), 'utf8')) as {
        dependencies: Record<string, string>
      }
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-devframe-profile']).toBe('7.7.7')
      expect(manifest.dependencies['@deepseek-ai/dsh-worktree-registry']).toBe('8.8.8')
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-shadow-bridge']).toBe('0.1.2-alpha.4')
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-agent-evidence']).toBe('0.1.6-alpha.1')
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-project-controller']).toBe('0.1.6-alpha.1')
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-project-contracts']).toBe('0.1.6-alpha.1')
      expect(manifest.dependencies['@deepseek-ai/dsh-experimental-devframe']).toBe('0.1.6-alpha.1')
      expect(manifest.dependencies['dsh-usage-monitor']).toBe('9.9.9')
      expect(manifest.dependencies['@dsh-mobile/pairing']).toBe('0.1.15')
      const patch = readFileSync(join(project, 'cordis.patch.yml'), 'utf8')
      expect(patch).not.toContain('shadow-trial')
      expect(patch).not.toContain('cloudflaredPath')
      expect(patch).toContain(root.replaceAll('\\', '/'))
      expect(patch).not.toContain('D:/dsh-devframe')
      // Shadow todo board v2 rows: the four project-controller faces are
      // mounted, the request-budget consumer is not, and the hierarchy faces
      // carry the project-loop tools.
      expect(patch).toContain('id: agent-evidence')
      expect(patch).toContain('id: project-controller')
      expect(patch).toContain('id: project-controller-consumer')
      expect(patch).toContain('id: project-controller-task-consumer')
      expect(patch).toContain('id: project-controller-delivery-consumer')
      expect(patch).not.toContain('project-controller-request-budget-consumer')
      expect(patch).toContain("'project_task'")
      expect(patch).toContain("'project_integrate'")
      expect(patch).toContain("'agent_dispatch'")
      expect(patch).toContain("'worktree_create'")
      expect(patch).toContain("'create_goal'")
      expect(patch).toContain("'project_evidence'")
      expect(patch).toContain("'project_review'")
      expect(patch).toContain("'project_deliver'")
      expect(patch).toContain("'project_commit'")
    } finally {
      process.env.DSH_HOME = previousHome
      if (previousExtra === undefined) delete process.env.DSH_DESKTOP_EXTRA_AUTHORIZED_ROOT
      else process.env.DSH_DESKTOP_EXTRA_AUTHORIZED_ROOT = previousExtra
      if (previousCloud === undefined) delete process.env.DSH_CLOUDFLARED_PATH
      else process.env.DSH_CLOUDFLARED_PATH = previousCloud
    }
  })
})
