import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { findSourceJsArtifacts, main } from './no-source-js.ts'

/**
 * Unit tests for the no-source-js gate: a clean source tree passes and every
 * misplaced emit artifact shape fails, while legitimate neighbors stay out of
 * scope.
 */

function makeTree(): string {
  return mkdtempSync(join(tmpdir(), 'no-source-js-spec-'))
}

function writeFile(root: string, relativePath: string, content = 'x'): void {
  const full = join(root, relativePath)
  mkdirSync(join(full, '..'), { recursive: true })
  writeFileSync(full, content)
}

describe('findSourceJsArtifacts', () => {
  it('accepts a source tree without JS artifacts', () => {
    const root = makeTree()
    try {
      writeFile(root, 'packages/attachment/attachment/src/index.ts')
      writeFile(root, 'packages/attachment/attachment/src/client/index.d.ts')
      writeFile(root, 'packages/attachment/attachment/lib/index.js')
      writeFile(root, 'packages/attachment/attachment/tests/fixtures/data.js')
      expect(findSourceJsArtifacts(root)).toEqual([])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('rejects .js and .js.map at any depth of a package src tree', () => {
    const root = makeTree()
    try {
      writeFile(root, 'packages/attachment/attachment/src/index.js')
      writeFile(root, 'packages/attachment/attachment/src/client/deep/x.js.map')
      expect(findSourceJsArtifacts(root)).toEqual([
        'packages/attachment/attachment/src/client/deep/x.js.map',
        'packages/attachment/attachment/src/index.js',
      ])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('ignores JS artifacts inside node_modules and outside src', () => {
    const root = makeTree()
    try {
      writeFile(root, 'packages/attachment/attachment/node_modules/dep/src/index.js')
      writeFile(root, 'packages/attachment/attachment/lib/index.js')
      writeFile(root, 'packages/attachment/attachment/src/index.ts')
      expect(findSourceJsArtifacts(root)).toEqual([])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('handles a tree without a packages directory', () => {
    const root = makeTree()
    try {
      expect(findSourceJsArtifacts(root)).toEqual([])
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
})

describe('main', () => {
  it('exits 0 and reports clean on a tree without artifacts', () => {
    const root = makeTree()
    try {
      writeFile(root, 'packages/attachment/attachment/src/index.ts')
      expect(main(root)).toBe(0)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('exits 1 and lists the offending artifacts', () => {
    const root = makeTree()
    try {
      writeFile(root, 'packages/llm/llm/src/index.js')
      expect(main(root)).toBe(1)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
})
