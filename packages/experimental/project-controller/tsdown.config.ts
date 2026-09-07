import { defineConfig } from 'tsdown'

/** Build the service and opt-in consumer as independent entry points. */
export default defineConfig({
  entry: { index: 'lib/types/index.js', consumer: 'lib/types/consumer.js' },
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
})
