#!/usr/bin/env node
/**
 * AT1-11 ledger mechanical validator (zero dependencies, pure Node ESM).
 *
 * Reads ../at11-task-ledger.json relative to this file and checks:
 *   (a) every field of every row is a {value, provenance, note?} object whose
 *       provenance sits inside the enum, and every "provenance" key anywhere
 *       in the document stays inside the enum;
 *   (b) any row carrying cumulativeModelReplies carries the sanctioned note
 *       phrase "cumulative, not RPM";
 *   (c) no forbidden token appears in any string in the document — notes are
 *       scanned too, after stripping the sanctioned phrase;
 *   (d) every row carries startBound and endBound (an "unobserved ..." value
 *       counts as present);
 *   (f) the row set equals the expected five task rows.
 *
 * Prints a human-readable summary table and exits 0 (valid) or 1 (invalid).
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const PROVENANCE_ENUM = new Set([
  'git',
  'controller-account-log',
  'worker-report',
  'lead-acceptance-log',
  'unobserved',
]);
const FORBIDDEN = ['rpm', 'rate', 'per-minute', 'speedup', '倍速'];
const SANCTIONED_NOTE_PHRASE = /cumulative,\s*not\s*rpm/gi;
const SANCTIONED_NOTE_TEST = /cumulative,\s*not\s*rpm/i;
const EXPECTED_TASK_IDS = ['W1', 'W2', 'W3', 'L1', 'L2'];
const CELL_WIDTH = 42;

const ledgerPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'at11-task-ledger.json');

const problems = [];
const fail = (message) => problems.push(message);

let doc;
try {
  doc = JSON.parse(readFileSync(ledgerPath, 'utf8'));
} catch (error) {
  console.error(`FAIL: cannot read or parse ${ledgerPath}`);
  console.error(String(error?.message ?? error));
  process.exit(1);
}

/** Visit every string leaf with (text, path, ownerKey). */
function walk(node, visit, path = '', ownerKey = null) {
  if (typeof node === 'string') {
    visit(node, path, ownerKey);
    return;
  }
  if (Array.isArray(node)) {
    node.forEach((item, index) => walk(item, visit, `${path}[${index}]`, ownerKey));
    return;
  }
  if (node !== null && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) {
      walk(value, visit, path ? `${path}.${key}` : key, key);
    }
  }
}

/** (a, whole document) every "provenance" value stays inside the enum. */
function checkProvenanceEnumEverywhere() {
  let ok = true;
  walk(doc, (text, path, ownerKey) => {
    if (ownerKey === 'provenance' && !PROVENANCE_ENUM.has(text)) {
      fail(`(a) provenance out of enum at ${path}: "${text}"`);
      ok = false;
    }
  });
  return ok;
}

function isFieldObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.prototype.hasOwnProperty.call(value, 'value')
    && Object.prototype.hasOwnProperty.call(value, 'provenance');
}

/** (a, rows) every row field is {value, provenance} with provenance in the enum. */
function checkRowFieldShape() {
  const rows = doc.rows;
  if (!Array.isArray(rows) || rows.length === 0) {
    fail('(a) rows missing or empty');
    return false;
  }
  let ok = true;
  rows.forEach((row, index) => {
    if (row === null || typeof row !== 'object' || Array.isArray(row)) {
      fail(`(a) rows[${index}] is not an object`);
      ok = false;
      return;
    }
    for (const [name, field] of Object.entries(row)) {
      if (!isFieldObject(field)) {
        fail(`(a) rows[${index}].${name} is not a {value, provenance} field`);
        ok = false;
        continue;
      }
      if (!PROVENANCE_ENUM.has(field.provenance)) {
        fail(`(a) rows[${index}].${name} provenance out of enum: "${field.provenance}"`);
        ok = false;
      }
    }
  });
  return ok;
}

/** (b) rows carrying cumulativeModelReplies carry the sanctioned note phrase. */
function checkCumulativeNote() {
  const rows = Array.isArray(doc.rows) ? doc.rows : [];
  let ok = true;
  rows.forEach((row, index) => {
    if (row === null || typeof row !== 'object') return;
    if (!Object.prototype.hasOwnProperty.call(row, 'cumulativeModelReplies')) return;
    const note = row.cumulativeModelReplies?.note;
    if (typeof note !== 'string' || !SANCTIONED_NOTE_TEST.test(note)) {
      fail(`(b) rows[${index}].cumulativeModelReplies lacks the sanctioned note phrase`);
      ok = false;
    }
  });
  return ok;
}

/** (c) no forbidden token in any string; notes lose the sanctioned phrase first. */
function checkForbiddenTokens() {
  let ok = true;
  walk(doc, (text, path, ownerKey) => {
    const target = ownerKey === 'note' ? text.replace(SANCTIONED_NOTE_PHRASE, '') : text;
    for (const token of FORBIDDEN) {
      if (target.toLowerCase().includes(token.toLowerCase())) {
        fail(`(c) forbidden token "${token}" in ${path}`);
        ok = false;
      }
    }
  });
  return ok;
}

/** (d) every row carries startBound and endBound field objects. */
function checkBounds() {
  const rows = Array.isArray(doc.rows) ? doc.rows : [];
  let ok = true;
  rows.forEach((row, index) => {
    if (row === null || typeof row !== 'object') return;
    for (const bound of ['startBound', 'endBound']) {
      if (!isFieldObject(row[bound])) {
        fail(`(d) rows[${index}] missing ${bound} field`);
        ok = false;
      }
    }
  });
  return ok;
}

/** (f) the row set equals the expected five task rows. */
function checkRowSet() {
  const rows = Array.isArray(doc.rows) ? doc.rows : [];
  const ids = rows.map((row) => (row && typeof row === 'object' && typeof row.taskId?.value === 'string' ? row.taskId.value : null));
  const missing = EXPECTED_TASK_IDS.filter((id) => !ids.includes(id));
  const extra = ids.filter((id) => id === null || !EXPECTED_TASK_IDS.includes(id));
  if (missing.length > 0) fail(`(f) missing rows: ${missing.join(', ')}`);
  if (extra.length > 0) fail(`(f) unexpected row ids: ${extra.join(', ')}`);
  return missing.length === 0 && extra.length === 0;
}

// --- summary output ---------------------------------------------------------

/** Escape non-ASCII so the console table survives any codepage. */
const ascii = (text) => String(text).replace(/[^\x20-\x7E]/g, (ch) => `\\u${ch.codePointAt(0).toString(16).padStart(4, '0')}`);

function cell(value, width = CELL_WIDTH) {
  let text = typeof value === 'string' ? value : JSON.stringify(value) ?? 'null';
  text = ascii(text);
  return text.length <= width ? text.padEnd(width) : `${text.slice(0, width - 3)}...`;
}

const fieldValue = (row, name) => (row && typeof row === 'object' ? row[name]?.value : undefined);

function statCell(row) {
  const files = fieldValue(row, 'filesTouched');
  const ins = fieldValue(row, 'insertions');
  const del = fieldValue(row, 'deletions');
  if (typeof files === 'number') return `${files} (+${ins}/-${del})`;
  return Object.keys(files ?? {})
    .map((hash) => `${hash}:${files[hash]}(+${ins?.[hash]}/-${del?.[hash]})`)
    .join(' ');
}

function rowLine(row) {
  const commit = Array.isArray(fieldValue(row, 'outputCommit'))
    ? fieldValue(row, 'outputCommit').join('+')
    : String(fieldValue(row, 'outputCommit'));
  const time = fieldValue(row, 'outputCommitTime');
  const timeText = typeof time === 'string' ? time : Object.values(time ?? {}).join(' / ');
  return [
    cell(fieldValue(row, 'taskId'), 4),
    cell(fieldValue(row, 'executorSession'), 12),
    cell(fieldValue(row, 'route'), 24),
    cell(`${commit} @ ${timeText}`, 56),
    cell(statCell(row), 44),
    cell(String(fieldValue(row, 'cumulativeModelReplies')), 11),
    cell(String(fieldValue(row, 'startBound')), 46),
    cell(String(fieldValue(row, 'endBound')), 46),
  ].join(' | ');
}

function commitLine(entry) {
  const stat = entry.filesChanged === undefined
    ? ''
    : `  files=${entry.filesChanged.value} (+${entry.insertions.value}/-${entry.deletions.value})`;
  return `${entry.hash.value}  ${entry.committedAt.value}  merge=${entry.isMerge.value ? 'yes' : 'no '}  parents=${entry.parents.value.length}${stat}  [${entry.line.value}]`;
}

console.log('AT1-11 ledger validation');
console.log(`ledger: ${ledgerPath}`);
console.log(`rows: ${Array.isArray(doc.rows) ? doc.rows.length : 0}`);
console.log('');
console.log('columns: taskId | session | route | commit@time | files (+ins/-del) | replies | startBound | endBound');
console.log('(long cells truncated; non-ASCII escaped; full text in the ledger JSON)');
console.log('');
for (const row of Array.isArray(doc.rows) ? doc.rows : []) console.log(rowLine(row));
console.log('');
console.log(`commits on ${doc.meta?.branch?.value ?? 'branch'}:`);
for (const entry of (doc.commits ?? []).filter((c) => String(c.line?.value ?? '').includes('codex/'))) {
  console.log(`  ${commitLine(entry)}`);
}
console.log('commits on main:');
for (const entry of (doc.commits ?? []).filter((c) => String(c.line?.value ?? '').startsWith('main'))) {
  console.log(`  ${commitLine(entry)}`);
}
console.log('');
console.log(`unobserved gaps recorded: ${(doc.unobservedGaps ?? []).length}`);
for (const gap of doc.unobservedGaps ?? []) console.log(`  - ${cell(gap.gap?.value, 90)}`);
console.log('');

const results = [
  ['(a) row field shape + provenance enum', checkRowFieldShape()],
  ['(a) provenance enum everywhere in the document', checkProvenanceEnumEverywhere()],
  ['(b) cumulativeModelReplies carries the sanctioned note', checkCumulativeNote()],
  ['(c) no forbidden token in any ledger string', checkForbiddenTokens()],
  ['(d) startBound/endBound present on every row', checkBounds()],
  ['(f) row set equals W1/W2/W3/L1/L2', checkRowSet()],
];
console.log('checks:');
for (const [label, ok] of results) console.log(`  ${label} ${'.'.repeat(Math.max(2, 52 - label.length))} ${ok ? 'PASS' : 'FAIL'}`);
console.log('');
if (problems.length > 0) {
  console.log('problems:');
  for (const problem of problems) console.log(`  - ${problem}`);
  console.log('');
}
console.log(`VALIDATION: ${problems.length === 0 ? 'PASS' : `FAIL (${problems.length} problem(s))`}`);
process.exit(problems.length === 0 ? 0 : 1);
