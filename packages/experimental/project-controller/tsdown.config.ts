import { defineConfig } from 'tsdown'

/** Build the service and opt-in tool consumers as independent entry points. */
export default defineConfig({
  entry: { index: 'lib/types/index.js', consumer: 'lib/types/consumer.js', 'task-consumer': 'lib/types/task-consumer.js', 'delivery-consumer': 'lib/types/delivery-consumer.js' },
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
})
