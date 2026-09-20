import { defineConfig } from 'tsdown'

/**
 * This vendored plugin ships prebuilt runtime output (`lib/*.js`) with no
 * local TypeScript project or `lib/types` intermediates, so the workspace-wide
 * host entry (`lib/types/{index,invariant,startup}.js`) does not apply. Bundle
 * the shipped loader entry as-is; its dependencies stay external exactly as
 * the prebuilt artifact already resolves them at runtime.
 */
export default defineConfig({
  entry: ['lib/index.js'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
})
