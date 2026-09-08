/** Real process tree around the keyless ACP protocol fixture. */
import { spawn } from 'node:child_process'
import { writeFileSync } from 'node:fs'

const pidPath = process.env.OWNED_TREE_PID_PATH
if (pidPath === undefined) throw new Error('missing owned tree pid path')
const child = spawn(process.execPath, ['-e', `
  const { spawn } = require('node:child_process');
  const grandchild = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
  process.stdout.write(JSON.stringify([process.pid, grandchild.pid]) + '\\n');
  setInterval(() => {}, 1000);
`], { stdio: ['ignore', 'pipe', 'inherit'] })
let received = ''
child.stdout.on('data', (chunk: Buffer) => {
  received += chunk.toString()
  if (received.includes('\n')) writeFileSync(pidPath, JSON.stringify([process.pid, ...JSON.parse(received.trim()) as number[]]))
})
await import('../../../../subagent/subagent-acp/tests/mock-acp-server.ts')
