// Lane-evidence decoder: DSH session.jsonl.zstd is an append stream of
// concatenated zstd frames; sync decompress only returns the first frame.
// Usage: node decode-session.mjs <session.jsonl.zstd> [--grep substr] [--max n]
import { createZstdDecompress } from 'node:zlib';
import { readFileSync } from 'node:fs';

const file = process.argv[2];
const grepIdx = process.argv.indexOf('--grep');
const grepSub = grepIdx > -1 ? process.argv[grepIdx + 1] : null;
const maxIdx = process.argv.indexOf('--max');
const max = maxIdx > -1 ? Number(process.argv[maxIdx + 1]) : 8;

const dec = createZstdDecompress();
const chunks = [];
dec.on('data', (c) => chunks.push(c));
const ended = new Promise((r) => dec.on('end', r));
dec.end(readFileSync(file));
await ended;

const text = Buffer.concat(chunks).toString('utf8');
const lines = text.split('\n').filter(Boolean);
console.log('LINES', lines.length);
const events = lines.map((l) => {
  try { return JSON.parse(l); } catch { return { UNPARSED: l.slice(0, 60) }; }
});
const types = {};
for (const e of events) types[e.type] = (types[e.type] || 0) + 1;
console.log('TYPES', JSON.stringify(types));
console.log('FIRST', JSON.stringify(events[0]).slice(0, 400));
console.log('LAST', JSON.stringify(events[events.length - 1]).slice(0, 600));
if (grepSub) {
  let shown = 0;
  for (let i = 0; i < events.length; i++) {
    const s = JSON.stringify(events[i]);
    if (s.includes(grepSub)) {
      console.log(`MATCH@${i}`, s.slice(0, 700));
      if (++shown >= max) break;
    }
  }
  console.log('MATCHES_SHOWN', shown);
}
