// Read-only DSH session log extractor: multi-frame zstd via the repo's own
// scanZstdFrames (Node zstdDecompressSync only reads the first frame).
// Usage: node read-session-log.mjs <sessionDir>
// Prints event-type counts, the session header, and every event whose payload
// mentions a provider (huoshan-1/huoshan-2) with seq/time for lane evidence.
import { readFileSync, existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const ZSTD_SRC = 'D:/dsh-devframe/packages/session/session-persistence-jsonl/src/zstd.js';
if (!existsSync(ZSTD_SRC)) {
  console.error('zstd module not found at ' + ZSTD_SRC);
  process.exit(2);
}
const { scanZstdFrames, createZstdFrameDecoder } = await import(pathToFileURL(ZSTD_SRC).href);

const dir = process.argv[2];
if (!dir) { console.error('usage: node read-session-log.mjs <sessionDir>'); process.exit(2); }
const buf = readFileSync(`${dir}/session.jsonl.zstd`);
const scan = scanZstdFrames(buf);
const decoder = createZstdFrameDecoder();
const text = Array.from(decoder.decode(buf, scan.frames), (c) => Buffer.from(c).toString('utf8')).join('');
const events = text.split('\n').filter(Boolean).map((l) => JSON.parse(l));

const counts = {};
for (const e of events) counts[e.type] = (counts[e.type] ?? 0) + 1;
console.log(`frames=${scan.frames.length} tornStart=${scan.tornStart ?? 'none'} events=${events.length}`);
console.log('typeCounts=' + JSON.stringify(counts));

console.log('firstEvent=' + JSON.stringify(events[0]).slice(0, 700));
const last = events[events.length - 1];
console.log(`lastEvent seq=${last.seq} time=${last.time ?? '?'} iso=${last.time ? new Date(last.time).toISOString() : '?'} type=${last.type}`);

let hits = 0;
for (const e of events) {
  const s = JSON.stringify(e);
  if (s.includes('huoshan') || s.includes('"provider"')) {
    hits++;
    console.log(`PROVIDER-HIT seq=${e.seq} time=${e.time ?? '?'} iso=${e.time ? new Date(e.time).toISOString() : '?'} type=${e.type} payload=${s.slice(0, 500)}`);
  }
}
console.log(`providerHits=${hits}`);
