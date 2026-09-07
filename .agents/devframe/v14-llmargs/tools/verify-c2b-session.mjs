// C2b ③ session-log verifier: one unpack, rows expanded uniformly through the
// repo's own decodeStorageRecord (no hand-rolled chunk-format parsing), then
// the a-d checks:
//   a) request/header + request/context name provider huoshan-1 / glm-5.3-flash
//   b) dispatched cordis_inspect_query calls: >=2 with distinct callIds, every
//      `arguments` parses as JSON, and any `input` key is an object, not a string
//   c) no tool/result rejection mentioning "must be an object"
//   d) a turn/end event exists
// Usage: node --import tsx/esm verify-c2b-session.mjs <sessionDir>
// Exit 0 = all checks pass, 1 = any check fails, 2 = usage/IO error.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const ZSTD_SRC = 'D:/dsh-devframe/packages/session/session-persistence-jsonl/src/zstd.js';
const { scanZstdFrames, createZstdFrameDecoder } = await import(pathToFileURL(ZSTD_SRC).href);
const { decodeStorageRecord } = await import(
  pathToFileURL('D:/dsh-devframe-v14-llmargs-lead/packages/core/session/src/chunk-rows.ts').href,
);

const dir = process.argv[2];
if (!dir) {
  console.error('usage: node --import tsx/esm verify-c2b-session.mjs <sessionDir>');
  process.exit(2);
}

const buf = readFileSync(`${dir}/session.jsonl.zstd`);
const scan = scanZstdFrames(buf);
const decoder = createZstdFrameDecoder();
const text = Array.from(decoder.decode(buf, scan.frames), (c) => Buffer.from(c).toString('utf8')).join('');
const events = text.split('\n').filter(Boolean).flatMap((line) => decodeStorageRecord(JSON.parse(line)));

const resultText = (e) => {
  const entry = (e.data?.message?.content ?? []).find((c) => c?.type === 'tool-result');
  return (entry?.content ?? []).map((c) => (typeof c?.text === 'string' ? c.text : '')).join('');
};

const failures = [];
const headers = events.filter((e) => e.type === 'request/header');
const contexts = events.filter((e) => e.type === 'request/context');
const provider = headers[0]?.data?.header?.config?.provider;
const model = headers[0]?.data?.header?.config?.model;
if (provider !== 'huoshan-1' || model !== 'glm-5.3-flash') {
  failures.push(`a: request/header provider=${String(provider)} model=${String(model)}`);
}
const contextRoute = contexts.map((e) => `${e.data?.provider}/${e.data?.model}`).join(',');
if (!contexts.some((e) => e.data?.provider === 'huoshan-1' && e.data?.model === 'glm-5.3-flash')) {
  failures.push(`a: request/context routes=${contextRoute}`);
}

const calls = events.filter((e) => e.type === 'tool/call' && e.data?.name === 'cordis_inspect_query');
const callIds = new Set(calls.map((e) => e.data.callId));
if (calls.length < 2 || callIds.size !== calls.length) {
  failures.push(`b: parallel calls=${calls.length} distinctCallIds=${callIds.size}`);
}
const callSummary = [];
for (const e of calls) {
  let parsed;
  try {
    parsed = JSON.parse(e.data.arguments);
  } catch (error) {
    failures.push(`b: seq ${e.seq} callId ${e.data.callId} arguments not JSON: ${String(error).slice(0, 120)}`);
    callSummary.push({ seq: e.seq, callId: e.data.callId, validJson: false });
    continue;
  }
  const input = parsed?.input;
  const inputIsObject = input === undefined || (typeof input === 'object' && input !== null && !Array.isArray(input));
  if (!inputIsObject) failures.push(`b: seq ${e.seq} callId ${e.data.callId} input is ${typeof input}, not an object`);
  callSummary.push({ seq: e.seq, callId: e.data.callId, validJson: true, inputIsObject, method: parsed?.method });
}

const rejections = events
  .filter((e) => e.type === 'tool/result' && resultText(e).includes('must be an object'))
  .map((e) => ({ seq: e.seq, callId: e.data?.message?.source?.callId }));
if (rejections.length > 0) failures.push(`c: ${rejections.length} "must be an object" rejections`);

const turnEnds = events.filter((e) => e.type === 'turn/end');
if (turnEnds.length === 0) failures.push('d: no turn/end event');

const verdict = failures.length === 0 ? 'PASS' : 'FAIL';
console.log(JSON.stringify({
  verdict,
  frames: scan.frames.length,
  tornStart: scan.tornStart ?? null,
  eventCount: events.length,
  providerModel: `${provider}/${model}`,
  contextRoutes: contextRoute,
  calls: callSummary,
  rejections,
  turnEnds: turnEnds.map((e) => e.seq),
  failures,
}, null, 2));
process.exit(verdict === 'PASS' ? 0 : 1);
