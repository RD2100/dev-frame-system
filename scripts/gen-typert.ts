/** Generate Typert Host-face artifacts before the Host aggregate type-build consumes them. */

import { resolve } from 'node:path'
import { typertPlugin } from '../packages/typert/generator/src/tsdown-plugin.ts'

/**
 * The Host type-check resolves each contributor's `./remote` export through
 * generated `lib/typert.remote-client.d.ts`, which a clean tree lacks until
 * generation runs. The plugin's workspace mode analyzes package sources
 * directly, so this pass needs no prior build output; the later tsdown pass
 * regenerates the same artifacts through this same code path.
 */
function main(): void {
  // Workspace mode emits every explicit contributor once; the plugin resolves
  // the workspace root as the nearest directory owning `tsconfig.host.json`.
  const plugin = typertPlugin({ mode: 'workspace', faces: ['host'] })
  plugin.writeBundle({ dir: resolve(import.meta.dirname, '..') })
}

if (import.meta.main) main()
