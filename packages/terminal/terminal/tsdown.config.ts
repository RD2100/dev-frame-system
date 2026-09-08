import { defineConfig } from 'tsdown'

/**
 * Emit each Loader entry independently so published files need no shared chunk.
 * The ownership entry imports the root entry's TerminalError by package name,
 * and both entries keep that import external: without it, the root entry's
 * inlined registry copy resolves the self-import against the stale on-disk
 * lib and inlines a second TerminalError class, splitting instanceof identity
 * for consumers that take the registry from the root entry.
 */
export default defineConfig(['index', 'ownership'].map(name => ({
  entry: [`lib/types/${name}.js`],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
  // Preserve one TerminalError class identity across both published bundles.
  deps: { neverBundle: ['@deepseek-ai/dsh-terminal'] },
})))
