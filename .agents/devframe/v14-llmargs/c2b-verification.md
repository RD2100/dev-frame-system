# C2b HuoshanStreamArgs — root-cause closure verification

Branch `codex/v14-llmargs`, tree `D:\dsh-devframe-v14-llmargs-lead`. Subject under
test: the streamed tool-call argument assembler as fixed by `02251fac16`
(index-reused fragments dropped with `indexConflicts` diagnosis; id-less/empty-id
deltas no longer erase the recorded id; fragments pass through verbatim). Source
tree frozen throughout; evidence tooling lives under
`.agents/devframe/v14-llmargs/`.

## ① Pre-fix reproduction on the real chain3 fragments — PASS

- Evidence source: chain3 session `87444f2d-771e-4530-9d29-bedc0ce11c3d`
  (huoshan-1/glm-5.3-flash). Extraction (one unpack, rows expanded through
  `decodeStorageRecord`):
  `node --import tsx/esm .agents/devframe/v14-llmargs/tools/extract-streamargs.mjs <sessionDir> <out>` — exit 0.
- Committed distilled evidence: `out/chain3-streamargs-evidence.json` — step-2
  seq 1081-1115 (parallel `cordis_inspect_query`, indexes 2/3), step-3 seq
  2412-2438 (nested-object input, index 4), step-4, plus the 3 real tool-result
  rejections (`"input" must be an object`, seq 2450/2452/4114).
- Spec: `packages/llm/llm/tests/assembler-streamargs-chain3.spec.ts`, first
  block replicates the pre-`02251fac16` aggregation verbatim and asserts the
  corruption: index-multiplexed parallel calls splice into unparseable JSON
  under an overwritten id; sequential index reuse concatenates two calls; a
  trailing id-less delta erases the recorded id.
- Command: `pnpm vitest run packages/llm/llm/tests/assembler-streamargs-chain3.spec.ts`
  — exit 0, 7/7 passed.

## ② Post-fix assembler resolves the same sample — PASS

- Same spec, second block, same recorded fragments through the current
  `BlockAssembler`: owning call kept intact with 17 `indexConflicts` entries for
  the multiplexed case; both recorded calls assemble intact with no conflicts;
  recorded id survives an id-less continuation; the escaped nested-input
  fragments pass through verbatim (`input` stays a string — the fail-loud
  downstream rejection is the tool's correct behavior for that shape).
- Same command as ① — exit 0, 7/7 passed.

## ③ Real complex-parameter probe through huoshan-1 — assembler plane PASS, one out-of-scope residue

- Composition (fix of two failed attempts, see "Probe attempts" below): web
  profile over isolated `DSH_HOME=D:\dsh-udeliver-iso\verify-home`, with
  `apps/cli/config/examples/cordis/cordis.yml` layered FIRST (mounts
  `tool-cordis`; without it the session has no `cordis_inspect_query` at all),
  then `harness/verify-patch.yml` (driver insert, port 3492).
- Mechanical boot via the controller-delivered runner
  (`dsh-probe-runner.mjs` + `llmargs-probe-config.json`, shell:false, explicit
  `DSH_HOME`, windowsHide, 5 min cap): exit 0, elapsed 57.1 s, boot pid 6732
  exited cleanly. Driver evidence
  (`D:\dsh-udeliver-iso\out\verify-driver.jsonl`): agent-created 01:59:52Z,
  task-idle 02:00:39Z, session `d070abea-fae4-46ff-98fe-2a594a98acd3`.
- Task demanded two parallel `cordis_inspect_query` calls in one turn, one with
  a nested object `input`. Session-log verification
  (`tools/verify-c2b-session.mjs`, rows expanded via `decodeStorageRecord`):
  - a) request/header seq 12 + request/context: `huoshan-1/glm-5.3-flash` ✓
  - b) 4 dispatched calls, all with valid-JSON `arguments` ✓; turn-1 step-1
    dispatched the two calls together (seq 168 + 170, distinct callIds) ✓;
    the nested-input `input` arrived as a string ✗ (see residue)
  - c) 3 `must be an object` rejections ✗ (see residue); the no-input
    `listBuiltins` call succeeded with a real builtins catalog ✓
  - d) `turn/end` at seq 819 ✓
- Committed evidence: `out/verify-c2b-session-evidence.json` (header/context
  routes, the step-1 streamed fragment rows seq0=115/133, all 4 dispatched
  calls, the 3 rejection rows, the successful result, turn/end).
- Verifier exit code on this session: 1 (b/c fail as described) — kept verbatim
  in this record; the C2b defect signature is the assembler producing invalid
  JSON, which is absent (4/4 valid).

### Probe attempts (recorded for the failure chain)

1. attempt1 (predecessor, 10:03): boot without the examples/cordis layer —
   session `33d6d352` had no cordis tools; model correctly declined with a text
   answer; extraction came back empty. Composition fault, not a code fault.
2. attempt2 (delegated leaf, 10:48): `DSH_HOME` was lost to a shell quoting
   error in the leaf's wrapper (stderr: path treated as a command); the boot
   still ran with the full composition and produced session `ed32d2d7` in the
   default home — unusable for isolated-home evidence; probe processes closed
   (PIDs 30608/30348 confirmed exited, port 3492 free).
3. attempt3 (scripted runner, 10:59): the run recorded above.

### Residue (out of C2b scope, reported to the controller)

The provider stream itself carries the stringified body: step-1 index-1
fragments (seq0=115) already read `"input","\":\"","{\\\"","service",...` — the
model emitted the nested object as a JSON string upstream of the assembler,
despite the task text forbidding it, and repeated the shape on all three
retries (same shape as chain3 turn-1 step-3). The assembler's contract is
verbatim pass-through (proven by ②), and the inspect tool rejects a
non-object `input` fail-loud. Closing the rejection therefore needs a
model/adapter-side or task-design decision, not an assembler change; no source
modification was made for it.

## Conclusion

- C2b (HuoshanStreamArgs assembler aggregation hazard): **已修** — verified by
  ① (corruption reproduced under pre-fix semantics), ② (same sample resolves
  under current assembler), ③ (real huoshan-1 probe: parallel multi-tool +
  complex nested-parameter streams assemble to valid JSON end-to-end; no
  assembler-produced invalid arguments; provider/turn evidence complete).
- Residual `input must be an object` rejections: **不属于本切片实现缺陷** —
  provider-side emission shape with correct fail-loud handling; evidence chain
  above, referred to the controller.
- Commits: `03a95947f7` (proofs ①② spec + extractor + distilled chain3
  evidence), `a526a83a7c` (extractor on `decodeStorageRecord`, output verified
  byte-identical), plus this record and the ③ artifacts in the following
  commit. Raw regeneration commands are documented above; large raw extraction
  files are not committed.
