# v14-b2acp worker w1 report — B-2 pin 侧车变体管线修复

- Worker tree: `D:/dsh-devframe-v14-b2acp-w1`, branch `codex/v14-b2acp-w1`, base `b915db85ee` (clean at start).
- STATUS: **delivered**.

## Dispatch identity receipt（原文声明）

Dispatched with **provider=huoshan-2, model=glm-5.3-flash**. This dispatch declaration is the identity receipt; the serving model cannot be independently introspected from inside the worker.

## Per-commit SHAs

| # | Commit | Message | Exit |
| --- | --- | --- | --- |
| a | `f471f56c5f` | fix(session-snapshot): fs-agnostic sidecar variant write targets, refresh-mode guard ordering, sourceEventSeqs spelling preservation | 0 |
| b | `29d966ebcd` | test(acp): image-compaction win32 pin sidecar variant via cross-corpus symlink | 0 |
| c | (this commit) | chore(devframe): v14-b2acp worker receipts and logs | 0 |

Every commit: `git diff --cached --check` exit 0 recorded before `git commit --no-verify` (pre-commit lefthook vendor guard skipped per lane discipline; win32 exit-127 environment fact). All touched files verified to end with exactly one trailing newline before staging.

## Environment / install receipts

| Step | Command | Exit | Note |
| --- | --- | --- | --- |
| 1 | `pnpm install --frozen-lockfile` | **0** | 281 workspace projects; lockfile up to date. First attempt was a silent no-op (log pipe failure lost output, node_modules absent) — re-ran with working log, exit 0 recorded. |
| 2 | delete `*.tsbuildinfo` outside node_modules + `pnpm run build` (`DSH_EXAMPLE_MODE=lib`) | **0** | First build attempt failed (`Cannot find package 'typescript'`) because node_modules was absent from the no-op install; after real install, build exit 0. |
| 3 | delete `*.tsbuildinfo` + `pnpm run build` (post-fix, G5) | see G5 | |

## G1 — baseline red (pre-fix), real exit code

- Command: `$env:DSH_EXAMPLE_MODE='lib'; pnpm vitest run --config vitest.snapshot.config.ts 'snapshots/acp/acp.snapshot.ts' -t 'image-compaction'`
- Exit: **1**. Log: `logs/g1-baseline-red.log`.
- Signature: `AssertionError: session 4f77f685-97b7-498d-a015-34a087e0bf4b: initial system prompt #1 diverged from image-compaction/system-prompt.expected.md` at `packages/test-support/session-snapshot/src/suite.ts:1581:18`.
- Diff sides verified against the brief: expected = POSIX wording ("Check the [exit code: N] marker on every bash result…"), received = win32 wording ("Non-zero exits are reported as `[exit code: N]` markers… On Windows a killed process…") plus the worktree paragraph. 1 failed | 14 skipped (15). Signature matches the brief exactly; no improvisation needed.

## Implementation (design §一/§二, all in named file domain)

- `src/expectations.ts`: added `expectationWriteName(manifest, kind, platform)` — mirrors `sessionFixtureFileName`'s fs-agnostic contract (never consults the filesystem; declared host-platform variant ⇒ variant name, else base name), JSDoc with `@param`/`@returns`.
- `src/suite.ts`:
  - Write sites (system-prompt + tool-schemas sidecars) now build the target via `join(snapshotsDir, source.name, expectationWriteName(await manifestOf(source.name), kind, process.platform))` instead of `resolveExpectationPath`. Read/comparison sites keep `resolveExpectationPath` fail-loud untouched.
  - Fixture guard extracted to exported `assertDeclaredVariantFiles(dir, name, manifest, refreshing)`: the exempt name set is derived from `manifest.expectations` via `expectationFileName` (NOT the full `declaredExpectationVariantFiles` list); in refresh mode only declared expectation-sidecar variants that are missing are exempted. Declared session/child-session variants stay fail-loud in every mode; stdout-variant loop untouched in the guard `it`; replay/record fail-loud everywhere.
  - `preserveFixtureVolatiles` gains the `sourceEventSeqs` branch inserted immediately before the `record.type !== 'hook/result'` early return: when both record and existing carry array `sourceEventSeqs` and `decodeSeqRanges` of both (imported from `@deepseek-ai/dsh-session`) are deep-equal (compared via the file's existing `canonicalJson`), the EXISTING spelling is kept; decoded-unequal keeps fresh.
- `src/index.ts`: exports `expectationWriteName` and `assertDeclaredVariantFiles` with JSDoc.
- `snapshots/acp/image-compaction/snapshot.yml`: `expectations.variants.win32: [system-prompt]` block inserted after `toolSchemasSource` (two-space indent style). Per design §二.3, tool-schemas is deliberately NOT declared (no read/write effect; would make the guard demand a file that must not exist) — this follows the design, not a deviation.
- `snapshots/acp/image-compaction/system-prompt.win32.expected.md`: created via `New-Item -ItemType SymbolicLink` with target `../../session/read-image/system-prompt.win32.expected.md` (forward slashes). Staged blob verified at both staging and commit time: `git ls-files -s` → mode `120000`, blob `a0232796e5c4b88ead2f066a251763c5044933d0`, `git cat-file -p` prints exactly `../../session/read-image/system-prompt.win32.expected.md` (no backslash spelling ever landed). Resolves to `session/read-image/system-prompt.win32.expected.md` (blob `af14c15dd4…`, matching the classification's harvest-byte equality evidence).

## Tests (design §三 spec cases)

- E-1 `expectations.spec.ts` "names the expectation write target without requiring the file to exist": win32 host + declared → variant name; kind not declared for host → base; posix declared → posix variant; undeclared platform → base; no declarations → base.
- E-2 `expectations.spec.ts` "fails loud when a declared win32 system-prompt variant is missing on the read path": `resolveExpectationPath` throw preserved (regression coverage; complements the pre-existing tool-schemas/posix missing-variant throw specs, which remain green).
- S-1 `suite.spec.ts`: new package-local fixture root `tests/fixtures/suite-refresh/variant-pin/` (copied from the `pin-turn` pattern; manifest declares both `win32` and `posix` system-prompt variants so the spec is host-agnostic; committed WITHOUT the variant files). A registered refresh-mode suite over a temp copy bootstraps the variant file during the run; write-back spec asserts the written variant equals the committed base sidecar byte-for-byte (base untouched). NEVER touches the real snapshots corpus; no refresh run against `snapshots/acp/image-compaction` was ever executed in this worker.
- S-2 `suite.spec.ts` `assertDeclaredVariantFiles` describes: (1) replay mode + declared-but-missing sidecar variant → throws `declared platform variant must exist`; refresh mode → no throw; (2) declared session fixture variant missing in refresh mode → still throws (session variants not exempt).
- S-3 `suite.spec.ts` `stabilizeRefreshLog`: fresh range `[[12,15]]` + existing expanded `[12,13,14,15]` → write-back keeps expanded; symmetric case (fixture stores ranges) → keeps ranges; decoded-unequal → fresh kept. Packed/other-field behavior covered by pre-existing specs (all still green).

## Per-gate exit codes (all real)

| Gate | Command | Exit | Evidence |
| --- | --- | --- | --- |
| G1 baseline red | focused `-t image-compaction` (lib) | **1** (expected) | `logs/g1-baseline-red.log`; suite.ts:1581 signature |
| G2 package vitest | `pnpm vitest run packages/test-support/session-snapshot` | **0** | **358 passed \| 1 skipped** (baseline 342 passed \| 1 skipped not regressed; +16 from new specs incl. the registered variant-pin refresh suite). Re-run after a final unused-import cleanup with identical counts (`logs/g2-package-final.log`). |
| G3 focused ×2 | same command as G1, post-fix | **0**, **0** | `logs/g3-run1.log`, `logs/g3-run2.log`; 1 passed \| 14 skipped; normalized signatures byte-identical (only wall-clock `Start at`/`Duration` lines differ) |
| G5 rebuild | delete `*.tsbuildinfo` + `pnpm run build` (lib) | first attempt **1** (`TS6133` unused `SnapshotExpectationKind` import — fixed), final **0** | `logs/g5-build.log`; honestly recorded |
| G4 full replay | `pnpm run test:snapshot` (lib) | **1** (expected residual reds) | `logs/g4-full-replay.log` |
| G6 | `git diff --check` / `git diff --cached --check` per commit | **0** / **0** | recorded each staging |
| G7 docs | `pnpm run test:docs` | **0** | 15 gates passed, 0 failed, 0 skipped (`logs/g7-docs.log`), includes the session-snapshot corpus gate over the full corpus |

## G4 failure set (complete, honest)

Tests: 3 failed | 107 passed | 10 skipped (120). Test files: 2 failed | 4 passed (6). Failure names, exactly the briefed known set, zero new names:

1. `replays both-mode-turn through dsh --profile headless` — recording-tree-root embed: fixture embeds `D:\dsh-devframe-p-battery\...` worker paths vs this tree's `D:\dsh-devframe-v14-b2acp-w1\...` (pre-existing, not my domain).
2. `replays ptc-turn through dsh --profile headless` — same mechanism.
3. `replays subagent-continuable through dsh --profile sdk` — GAP-4 functional regression, present because the fix landed on main AFTER base `5e5a706f0a`/`b915db85ee` and merging main is forbidden.

**image-compaction is GREEN in G4** (no `snapshots/acp/acp.snapshot.ts` failure; that file passed).

## File-domain audit (design §四)

`git diff --name-status b915db85ee..HEAD` (commit c excluded; worker records land in commit c under `.agents/devframe/v14-b2acp/worker/**`):

```
M packages/test-support/session-snapshot/src/expectations.ts        (§四: named)
M packages/test-support/session-snapshot/src/index.ts               (§四: named)
M packages/test-support/session-snapshot/src/suite.ts               (§四: named)
M packages/test-support/session-snapshot/tests/expectations.spec.ts (§四: named)
M packages/test-support/session-snapshot/tests/suite.spec.ts        (§四: named)
A packages/test-support/session-snapshot/tests/fixtures/suite-refresh/variant-pin/* (7 files; package-local test fixtures, S-1/S-2 basis — within the named tests files' domain)
M snapshots/acp/image-compaction/snapshot.yml                       (§四: named)
A snapshots/acp/image-compaction/system-prompt.win32.expected.md    (§四: named, symlink 120000)
```

- `snapshots/session/**`: ZERO diff (never touched). `snapshots/sdk/**`, `packages/sdk/**`: ZERO diff. `packages/experimental/{devframe,agent-evidence,command-goal-binding,shadow-router,project-memory}`: ZERO diff. `vendor/**`, `.agents/devframe/v14/next/**`, `apps/web/**`, `scripts/**`: ZERO diff.
- **Base fixtures: zero `M` status anywhere in the history** — the only fixture-name entries in `git diff --name-status base..HEAD` are `A` (new files): the package-local `suite-refresh/variant-pin` fixtures and the new image-compaction win32 variant symlink. No `session.jsonl`, `stdout.expected.jsonl`, `input.json`, `cordis.yml`, `cordis.snapshot.yml`, or pre-existing sidecar was modified in any commit; `git status --porcelain` after G4 (full replay) showed no fixture mutation either.
- Post-commit-c `git status --porcelain`: clean.

## Deviations

None silent. Two declared implementation notes, both within the contract's wording:

1. The guard was extracted into exported `assertDeclaredVariantFiles(dir, name, manifest, refreshing)` instead of an inline loop — required to make S-2 ("非 refresh 模式守卫对 declared-but-missing 红") an assertable real spec; session/child/stdout assertions are behaviorally unchanged (S-2's second case proves session variants stay fail-loud in refresh).
2. S-1's fixture declares variants for BOTH `win32` and `posix` (instead of win32-only) so the spec is host-agnostic on the CI matrix; the refresh bootstrap path exercised is identical to the image-compaction win32-only shape (win32 behavior verified by G3/G4 on this win32 host).
3. No refresh run was executed against `snapshots/acp/image-compaction` (only replay G3 ×2 + G4), so base-fixtures-zero-modification is additionally guaranteed by construction, not just by audit.

## Residual risks

- `both-mode-turn`/`ptc-turn` tree-root-embed reds and `subagent-continuable` GAP-4 red persist by design (pre-existing, out of lane); they mask nothing in the acp corpus — image-compaction is green and the acp snapshot file passes wholesale.
- The cross-corpus write-through-symlink behavior for `tool-schemas` (image-compaction schemaSource `escalation-approved`, byte-identical write) remains unclaimed across suites (`claimSharedSnapshot` is per-suite) — registered in classification §一②, unchanged this wave per design.
- The headless suite's main-sidecar write site (`snapshots/session/headless.snapshot.ts`) still uses `resolveExpectationPath` for writes — design §一.4 explicitly defers it (no in-flight gap; registered as future seam-unification with the corpus gate's `.md/.json` variant-existence gap).
- Install/build on a fresh worktree: `pnpm install --frozen-lockfile` must actually complete before `pnpm run build` (a swallowed log-pipe failure made the first install a silent no-op; worth a lane-standard note).

## Logs index (all under `.agents/devframe/v14-b2acp/worker/logs/`)

`install.log`, `build-1.log`, `g1-baseline-red.log`, `g2-focused-specs.log`, `g2-package.log`, `g2-package-final.log`, `g3-run1.log`, `g3-run2.log`, `g5-build.log`, `g4-full-replay.log`, `g7-docs.log`.
