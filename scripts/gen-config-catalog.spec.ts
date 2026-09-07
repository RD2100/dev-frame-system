/** Public plugin subpaths share the main-entry config checks without replacing its catalog record. */

import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { collectConfigCatalog } from './gen-config-catalog.ts'

const roots: string[] = []
afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

function fixture(exported: unknown = { default: './lib/consumer.js' }, source = true, taskExported: unknown = './lib/task-consumer.js') {
  const root = mkdtempSync(join(tmpdir(), 'dsh-config-catalog-'))
  roots.push(root)
  const dir = join(root, 'packages/experimental/project-controller')
  mkdirSync(join(dir, 'src'), { recursive: true })
  writeFileSync(join(dir, 'package.json'), JSON.stringify({
    name: '@deepseek-ai/dsh-experimental-project-controller',
    exports: { ...(exported === null ? {} : { './consumer': exported }), './task-consumer': taskExported, './delivery-consumer': './lib/delivery-consumer.js' },
  }))
  writeFileSync(join(dir, 'src/delivery-consumer.ts'), '/** Delivery plugin. */\nexport function apply(): void {}\n')
  writeFileSync(join(dir, 'src/index.ts'), '/** Main library. */\nexport const main = true\n')
  writeFileSync(join(dir, 'src/task-consumer.ts'), `
export const inject = ['tools', 'projectController']
export function apply(_ctx: unknown): void {}
`)
  if (source) writeFileSync(join(dir, 'src/consumer.ts'), `
/** Consumer configuration. */
export interface Config {
  /** Approved checks ledger. */
  requiredChecksPath: string
}
export const inject = ['tools']
export const Config = z.object({ requiredChecksPath: z.string() })
export function apply(_ctx: unknown, config: Config): void { void config }
`)
  return { root, dir }
}

describe('supplemental plugin config entries', () => {
  it.each([{ default: './lib/consumer.js' }, './lib/consumer.js'])('retains the main entry and catalogs the exported consumer: %j', (exported) => {
    const { root } = fixture(exported)
    const entries = collectConfigCatalog(root)
    expect(entries.map(entry => [entry.pkg, entry.kind])).toEqual([
      ['@deepseek-ai/dsh-experimental-project-controller', 'library'],
      ['@deepseek-ai/dsh-experimental-project-controller/consumer', 'config'],
      ['@deepseek-ai/dsh-experimental-project-controller/delivery-consumer', 'no-config'],
      ['@deepseek-ai/dsh-experimental-project-controller/task-consumer', 'no-config'],
    ])
    expect(entries[1]).toMatchObject({
      entry: 'packages/experimental/project-controller/src/consumer.ts',
      inject: ['tools'], schemaKeys: ['requiredChecksPath'],
    })
    expect(entries[1]?.pastes?.[0]?.text).toContain('requiredChecksPath: string')
  })

  it.each([null, { types: './lib/types/task-consumer.d.ts' }, './lib/consumer.js'])('rejects an absent or mismatched task-consumer runtime: %j', (exported) => {
    const { root } = fixture(undefined, true, exported)
    expect(() => collectConfigCatalog(root)).toThrow('supplemental plugin must export ./lib/task-consumer.js')
  })

  it('requires source for the exported task consumer', () => {
    const { root, dir } = fixture()
    rmSync(join(dir, 'src/task-consumer.ts'))
    expect(() => collectConfigCatalog(root)).toThrow('src/task-consumer.ts is missing or unreadable')
  })

  it.each([null, { default: './lib/other.js' }, { types: './lib/types/consumer.d.ts' }])('rejects a missing or mismatched runtime export: %j', (exported) => {
    const { root } = fixture(exported)
    expect(() => collectConfigCatalog(root)).toThrow('supplemental plugin must export ./lib/consumer.js')
  })

  it('rejects an exported consumer without its source', () => {
    const { root } = fixture(undefined, false)
    expect(() => collectConfigCatalog(root)).toThrow('src/consumer.ts is missing or unreadable')
  })

  it('applies the existing schema/type consistency gate to a supplemental entry', () => {
    const { root, dir } = fixture()
    writeFileSync(join(dir, 'src/consumer.ts'), `
/** Consumer configuration. */
export interface Config {
  /** Approved checks ledger. */
  requiredChecksPath: string
}
export const Config = z.object({ undeclared: z.string() })
export function apply(_ctx: unknown, config: Config): void { void config }
`)
    expect(() => collectConfigCatalog(root)).toThrow(/undeclared/)
  })
})

describe('default plugin re-exports', () => {
  it('reads the class Config and inject from the declaring module behind a barrel', () => {
    const { root, dir } = fixture()
    writeFileSync(join(dir, 'src/index.ts'), "export { Controller as default } from './controller.ts'\n")
    writeFileSync(join(dir, 'src/controller.ts'), `
/** Controller configuration. */
export interface ControllerConfig {
  /** Concurrent task budget. */
  maxActiveTasks: number
}
export class Controller {
  static inject = ['storageDomain']
  static Config = z.object({ maxActiveTasks: z.number().default(2) })
  constructor(_ctx: unknown, _config: ControllerConfig) {}
}
`)
    const entry = collectConfigCatalog(root)[0]
    expect(entry).toMatchObject({
      kind: 'config', className: 'Controller', configTypeName: 'ControllerConfig',
      inject: ['storageDomain'], schemaKeys: ['maxActiveTasks'],
    })
    expect(entry?.pastes?.[0]?.source).toContain('src/controller.ts:')
  })

  it.each([
    ["export { Controller as default } from './absent.ts'\n", '', 'missing or unreadable'],
    ["export { Controller as default } from './controller.ts'\n", 'export const other = true\n', 'has no class/function declaration'],
    ["export { Controller as default } from './controller.ts'\n", "export { default as Controller } from './index.ts'\n", 'cyclic plugin re-export'],
    ["export { Controller as default } from './controller.js'\n", '', 'explicit .ts extension'],
    ["export { Controller as default } from 'external-plugin'\n", '', 'package-relative'],
  ])('rejects an unresolved plugin barrel: %s', (index, declaration, error) => {
    const { root, dir } = fixture()
    writeFileSync(join(dir, 'src/index.ts'), index)
    writeFileSync(join(dir, 'src/controller.ts'), declaration)
    expect(() => collectConfigCatalog(root)).toThrow(error)
  })
})


it('rejects the delivery export without its independently mounted source', () => {
  const { root, dir } = fixture()
  rmSync(join(dir, 'src/delivery-consumer.ts'))
  expect(() => collectConfigCatalog(root)).toThrow('src/delivery-consumer.ts is missing or unreadable')
})
