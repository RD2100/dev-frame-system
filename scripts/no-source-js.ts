/**
 * Fail when compiler-emitted JS artifacts sit inside a package source tree.
 *
 * A tsc run whose resolved options carry the base facade's emit flags but no
 * `outDir` writes `.js`, `.js.map`, `.d.ts`, and `.d.ts.map` beside the
 * sources — the 2026-09-06 pollution of 85 package `src` files. Bundler
 * extension resolution orders `.js` before `.ts`, so one stray `index.js`
 * shadows `index.ts` under vite-tsconfig-paths and silently replaces a
 * package's source. Hand-authored `.d.ts` files are legitimate and stay out
 * of scope, as do built `lib/` outputs and non-`src` fixtures.
 * @module scripts/no-source-js
 */

import { existsSync, readdirSync } from 'node:fs'
import { join, relative, resolve, sep } from 'node:path'

/** File suffixes a misplaced emit leaves in a source tree. */
const EMIT_SUFFIXES = ['.js', '.js.map'] as const

/** Traversal roots that can never own package sources. */
const SKIPPED_DIRS = new Set(['node_modules'])

function isInsideSrc(root: string, full: string): boolean {
  return relative(root, full).split(sep).includes('src')
}

/**
 * Collect compiler-emitted JS artifacts inside every package `src` tree.
 * @param root - repository root to scan.
 * @returns artifact paths relative to the root, sorted.
 */
export function findSourceJsArtifacts(root: string): string[] {
  const artifacts: string[] = []
  const visit = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (!SKIPPED_DIRS.has(entry.name)) visit(full)
      } else if (EMIT_SUFFIXES.some(suffix => entry.name.endsWith(suffix)) && isInsideSrc(root, full)) {
        artifacts.push(relative(root, full).replaceAll(sep, '/'))
      }
    }
  }
  const packagesDir = join(root, 'packages')
  if (existsSync(packagesDir)) visit(packagesDir)
  return artifacts.sort()
}

/**
 * Scan the repository and fail loud when a source tree carries emit artifacts.
 * @param root - repository root to scan; defaults to this checkout.
 * @returns the process exit code: 0 clean, 1 when artifacts exist.
 */
export function main(root: string = resolve(import.meta.dirname, '..')): number {
  const artifacts = findSourceJsArtifacts(root)
  if (artifacts.length === 0) {
    console.log('no-source-js: package source trees carry no compiler-emitted JS artifacts.')
    return 0
  }
  console.error(`no-source-js: ${artifacts.length} compiler-emitted JS artifact(s) inside package source trees:`)
  for (const artifact of artifacts) console.error(`  ${artifact}`)
  console.error(
    'no-source-js: remove them and fix the producer; never gitignore them'
    + ' (a stray src/*.js shadows the .ts source under bundler extension resolution).',
  )
  return 1
}

if (import.meta.main) process.exitCode = main()
