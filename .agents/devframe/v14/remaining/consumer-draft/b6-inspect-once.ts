import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs'
import { scanLog } from '../../../../../packages/session/session-persistence-jsonl/src/format.ts'
import { createZstdFrameDecoder, scanZstdFrames } from '../../../../../packages/session/session-persistence-jsonl/src/zstd.ts'
const root = String.raw`C:\Users\25313\.dsh\sessions\--D-dsh-devframe-candidate-b6--`
let best = ''
let bestM = 0
for (const dir of readdirSync(root)) {
  const base = `${root}\\${dir}`
  if (!existsSync(`${base}\\session.jsonl.zstd`) && !existsSync(`${base}\\session.jsonl`)) continue
  const files = readdirSync(base)
  const logFile = files.includes('session.jsonl.zstd') ? 'session.jsonl.zstd' : 'session.jsonl'
  const m = statSync(`${base}\\${logFile}`).mtimeMs
  if (m <= bestM) continue
  const b = readFileSync(`${base}\\${logFile}`)
  let raw = b
  if (logFile.endsWith('.zstd')) {
    const d = createZstdFrameDecoder()
    try { raw = Buffer.concat(Array.from(d.decode(b, scanZstdFrames(b).frames), x => Buffer.from(x))) } finally { d.close() }
  }
  const scan = scanLog(raw)
  const wf = scan.events.filter((e: any) => e.type === 'tool/call' && e.data?.name === 'workflow').length
  if (wf >= 2) { bestM = m; best = String(scan.meta.id) }
}
console.log(`NEWEST_PARENT=${best}`)
