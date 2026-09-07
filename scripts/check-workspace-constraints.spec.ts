/** Experimental-package publication and dependency constraints. */

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  checkExperimentalDependencyIsolation,
  checkExperimentalManifest,
  expectedDshPackageFiles,
  type PackageManifest,
  type WorkspaceManifest,
} from './check-workspace-constraints.ts'

const experimental: WorkspaceManifest = {
  dir: 'packages/experimental/prototype',
  manifest: { name: '@deepseek-ai/dsh-experimental-prototype', private: true },
}

describe('experimental workspace constraints', () => {
  it('requires the experimental package-name prefix', () => {
    expect(checkExperimentalManifest({
      ...experimental,
      manifest: { ...experimental.manifest, name: '@deepseek-ai/dsh-prototype' },
    })).toEqual([
      '@deepseek-ai/dsh-prototype: experimental package name must start with "@deepseek-ai/dsh-experimental-"',
    ])
  })

  it('requires private manifests without publication metadata', () => {
    expect(checkExperimentalManifest(experimental)).toEqual([])
    expect(checkExperimentalManifest({
      ...experimental,
      manifest: { ...experimental.manifest, private: false, publishConfig: { access: 'public' } },
    })).toEqual([
      '@deepseek-ai/dsh-experimental-prototype: experimental package must set "private": true',
      '@deepseek-ai/dsh-experimental-prototype: experimental package must omit publishConfig',
    ])
  })

  it.each(['dependencies', 'optionalDependencies', 'peerDependencies'] as const)(
    'rejects release %s on an experimental package',
    (section) => {
      expect(checkExperimentalDependencyIsolation([experimental, {
        dir: 'packages/core/consumer',
        manifest: {
          name: '@deepseek-ai/dsh-consumer',
          [section]: { '@deepseek-ai/dsh-experimental-prototype': 'workspace:^' },
        },
      }])).toEqual([
        `@deepseek-ai/dsh-consumer: ${section}.@deepseek-ai/dsh-experimental-prototype must not reference an experimental package`,
      ])
    },
  )

  it('allows development and experimental consumers but rejects the Python release runtime', () => {
    const manifests: WorkspaceManifest[] = [experimental, {
      dir: 'packages/core/test-only',
      manifest: {
        name: '@deepseek-ai/dsh-test-only',
        devDependencies: { '@deepseek-ai/dsh-experimental-prototype': 'workspace:^' },
      },
    }, {
      dir: 'packages/experimental/consumer',
      manifest: {
        name: '@deepseek-ai/dsh-experimental-consumer',
        dependencies: { '@deepseek-ai/dsh-experimental-prototype': 'workspace:^' },
      },
    }, {
      dir: 'python/sdk-runtime',
      manifest: {
        name: '@deepseek-ai/dsh-python-runtime',
        dependencies: { '@deepseek-ai/dsh-experimental-prototype': 'workspace:^' },
      },
    }]

    expect(checkExperimentalDependencyIsolation(manifests)).toEqual([
      '@deepseek-ai/dsh-python-runtime: dependencies.@deepseek-ai/dsh-experimental-prototype must not reference an experimental package',
    ])
  })
})

describe('package payload constraints', () => {
  it.each([
    [{ './delivery-consumer': './lib/delivery-consumer.js' }, true],
    [{ './delivery-consumer': { default: './lib/delivery-consumer.js', types: './lib/types/delivery-consumer.d.ts' } }, true],
    [{ './delivery-consumer': './src/delivery-consumer.ts' }, false],
    [{ './delivery-consumer': { types: './lib/types/delivery-consumer.d.ts' } }, false],
    [{ './other': './lib/delivery-consumer.js' }, false],
  ] as const)('matches the delivery consumer payload to its runtime export: %j', (exports, included) => {
    expect(expectedDshPackageFiles({ exports })).toEqual([
      'lib/index.js', ...(included ? ['lib/delivery-consumer.js'] : []), 'lib/types/**/*.d.ts',
    ])
  })

  it.each([
    { './task-consumer': './lib/task-consumer.js' },
    { './task-consumer': { types: './lib/types/task-consumer.d.ts', default: './lib/task-consumer.js' } },
  ])('requires the task consumer bundle for its runtime export: %j', (exports) => {
    expect(expectedDshPackageFiles({ exports })).toEqual([
      'lib/index.js', 'lib/task-consumer.js', 'lib/types/**/*.d.ts',
    ])
  })

  it.each([
    { './task-consumer': './src/task-consumer.ts' },
    { './task-consumer': { types: './lib/types/task-consumer.d.ts' } },
    { './task-consumer': { default: './lib/index.js' } },
    { './other': './lib/task-consumer.js' },
  ])('excludes the task consumer bundle without its exact runtime export: %j', (exports) => {
    expect(expectedDshPackageFiles({ exports })).toEqual([
      'lib/index.js', 'lib/types/**/*.d.ts',
    ])
  })

  it.each([
    { './consumer': './lib/consumer.js' },
    { './consumer': { types: './lib/types/consumer.d.ts', default: './lib/consumer.js' } },
  ])('requires the independent consumer bundle for its runtime export: %j', (exports) => {
    expect(expectedDshPackageFiles({ exports })).toEqual([
      'lib/index.js', 'lib/consumer.js', 'lib/types/**/*.d.ts',
    ])
  })

  it.each([
    {},
    { './consumer': './src/consumer.ts' },
    { './consumer': { types: './lib/types/consumer.d.ts' } },
    { './consumer': { default: './lib/index.js' } },
    { './other': './lib/consumer.js' },
  ])('excludes the consumer bundle without its exact runtime export: %j', (exports) => {
    expect(expectedDshPackageFiles({ exports })).toEqual([
      'lib/index.js', 'lib/types/**/*.d.ts',
    ])
  })

  it('matches the project controller payload to its independent consumer export', () => {
    const manifest = JSON.parse(readFileSync(new URL(
      '../packages/experimental/project-controller/package.json', import.meta.url,
    ), 'utf8')) as PackageManifest
    expect(manifest.files).toEqual(expectedDshPackageFiles(manifest))
  })

  it('includes a declared profile patch without a package-name allowlist', () => {
    expect(expectedDshPackageFiles({
      name: '@deepseek-ai/dsh-private-profile',
      dsh: { bundle: { patch: './cordis.patch.yml' } },
    })).toEqual([
      'lib/index.js',
      'cordis.patch.yml',
      'lib/types/**/*.d.ts',
    ])
  })
})
