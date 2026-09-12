import { defineConfig } from 'tsdown'

/** Build the Remote controller and the Shadow conversation host as independent entry points. */
export default defineConfig({
  entry: { index: 'lib/types/index.js', 'shadow-agent': 'lib/types/shadow-agent.js' },
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
})
