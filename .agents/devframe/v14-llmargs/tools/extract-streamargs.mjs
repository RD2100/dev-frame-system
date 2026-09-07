// C2b ①② evidence extractor: reconstructs the exact streamed tool-call-delta
// fragment sequence of one session log and the tool/call dispatch output the
// pre-fix assembler produced from it.
//
// Packed storage rows (tool-call-chunks/text-chunks/reasoning-chunks) expand
// through the repo's own decodeStorageRecord — no hand-rolled row parsing; a
// packed row never mixes ids, so the expanded log order reproduces the exact
// stream the assembler consumed.
//
// Usage: node --import tsx/esm extract-streamargs.mjs <sessionDir> <outJsonPath>
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const ZSTD_SRC = 'D:/dsh-devframe/packages/session/session-persistence-jsonl/src/zstd.js';
const { scanZstdFrames, createZstdFrameDecoder } = await import(pathToFileURL(ZSTD_SRC).href);
const { decodeStorageRecord } = await import(
  pathToFileURL('D:/dsh-devframe-v14-llmargs-lead/packages/core/session/src/chunk-rows.ts').href,
);

const dir = process.argv[2];
const outPath = process.argv[3];
if (!dir || !outPath) {
  console.error('usage: node --import tsx/esm extract-streamargs.mjs <sessionDir> <outJsonPath>');
  process.exit(2);
}

const buf = readFileSync(`${dir}/session.jsonl.zstd`);
const scan = scanZstdFrames(buf);
const decoder = createZstdFrameDecoder();
const text = Array.from(decoder.decode(buf, scan.frames), (c) => Buffer.from(c).toString('utf8')).join('');
const records = text.split('\n').filter(Boolean).map((l) => JSON.parse(l));

// Expand packed rows back to session events, in log order.
const events = records.flatMap((record) => decodeStorageRecord(record));

// tool-call-delta stream, in order, grouped by turn/step.
const stream = {};
for (const e of events) {
  if (e.type !== 'assistant/chunk' || e.data?.chunk?.type !== 'tool-call-delta') continue;
  const key = `turn${e.data.turn}-step${e.data.step}`;
  (stream[key] ??= []).push({
    seq: e.seq,
    index: e.data.chunk.index,
    id: e.data.chunk.id,
    ...(Object.hasOwn(e.data.chunk, 'name') ? { name: e.data.chunk.name } : {}),
    argumentsDelta: e.data.chunk.argumentsDelta,
  });
}

// Dispatched calls (post-assembler) per turn/step, in log order.
const dispatched = {};
const results = [];
const rejections = [];
for (const e of events) {
  if (e.type === 'tool/call') {
    const key = `turn${e.data.turn}-step${e.data.step}`;
    (dispatched[key] ??= []).push({ seq: e.seq, callId: e.data.callId, name: e.data.name, arguments: e.data.arguments });
  }
  if (e.type === 'tool/result') {
    // Real row shape: data.message.content[] holds the tool-result; its text
    // sits in content[].content[].text and isError on the tool-result entry.
    const entry = (e.data?.message?.content ?? []).find((c) => c?.type === 'tool-result');
    const text = (entry?.content ?? []).map((c) => (typeof c?.text === 'string' ? c.text : '')).join('');
    const isError = entry?.isError === true;
    results.push({ seq: e.seq, callId: e.data?.message?.source?.callId, isError, excerpt: text.slice(0, 300) });
    if (isError && (text.includes('must be an object') || text.includes('must be object'))) {
      rejections.push({ seq: e.seq, callId: e.data?.message?.source?.callId, excerpt: text.slice(0, 300) });
    }
  }
}

// block-end tool-call blocks per turn/step (what the assembled block looked like).
const blockEnds = {};
for (const e of events) {
  if (e.type !== 'assistant/chunk' || e.data?.chunk?.type !== 'block-end') continue;
  const b = e.data.chunk.block;
  if (b?.type !== 'tool-call') continue;
  const key = `turn${e.data.turn}-step${e.data.step}`;
  (blockEnds[key] ??= []).push({ seq: e.seq, index: e.data.chunk.index, id: b.id, name: b.name, arguments: b.arguments });
}

const summary = {
  frames: scan.frames.length,
  tornStart: scan.tornStart ?? null,
  recordCount: records.length,
  steps: Object.fromEntries(Object.entries(stream).map(([k, v]) => [k, {
    deltaCount: v.length,
    indexes: [...new Set(v.map(d => d.index))],
    ids: [...new Set(v.map(d => d.id))],
  }])),
  rejections,
};
writeFileSync(outPath, `${JSON.stringify({ summary, stream, dispatched, blockEnds, results }, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(summary, null, 2));
