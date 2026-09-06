# P21-S evidence: markShadow real host invocation wiring (config-declared Shadow designation)

Worktree: `D:\dsh-devframe-v14-shadow-w1` · Branch: `p/v14-shadow-w1` · Base: `c93b86c43e` (docs(devframe): record bext wave closure, build fix merged, next-wave queue)

## Commands run (exact results)

| # | Command | Result |
|---|---|---|
| 1 | `git status` / `git log --oneline -3` / `git branch --show-current` | branch `p/v14-shadow-w1`, HEAD `c93b86c43e`, clean tree |
| 2 | `pnpm install` | exit 0, `Done in 24s using pnpm v11.19.0`; two non-blocking `[WARN] Failed to create bin` lines for `dsh` symlinks pointing at the unbuilt `lib/bin.js` (fresh worktree, no build — unrelated to this task) |
| 3 | `pnpm exec vitest run packages/experimental/shadow-router/tests` (first attempt, `z.string().optional()`) | exit 1, 14 suites failed to load: `TypeError: default.string(...).optional is not a function` — the vendored schemastery has no `.optional()` chainable (see Deviations) |
| 4 | `pnpm exec vitest run packages/experimental/shadow-router/tests` (after fix to bare `z.string()`) | exit 0 — `Test Files 14 passed (14)`, `Tests 32 passed \| 1 skipped (33)`; the 1 skip is the pre-existing POSIX-gated `aliases.spec.ts` skip on Windows |
| 5 | `pnpm exec tsc -b packages/experimental/shadow-router` | exit 0 |
| 6 | `pnpm run verify-translation-pairing --write packages/experimental/shadow-router/README.md` | exit 0, `recorded packages/experimental/shadow-router/README.i18n.yaml` |
| 7 | `pnpm run verify-translation-pairing --write .agents/notes/implemented/architecture/2026-09-06-shadow-config-designation.md` | exit 0, record created |
| 8 | `pnpm run verify-translation-pairing <both anchors>` | exit 0, `2 named pair(s) consistent` |
| 9 | `pnpm run test:docs` (doc-quick aggregate) | exit 0 — `15 passed, 0 failed, 0 skipped in 32.07s` (markdown links, type equivalence, translation pairing, markdown wrap, public repository links, package README model experience, agent note classification/format, archived agent notes, skill invocation metadata, translation prompt, doc budgets, documentation standard tests, package README limitations, doc refs) |
| 10 | `pnpm exec vitest run packages/experimental/shadow-router/tests --coverage --coverage.include='packages/experimental/shadow-router/src/**'` | exit 1 (thresholds applied) — scoped read-out: all uncovered lines are `ids.ts:45,62,79` (brand-factory throw guards), `tools.ts:242-243` (`installShadowTools` rollback catch), and `service.ts:981+` (converge/provision/persist internals). **None fall inside this diff's hunks** (all new src lines sit below service.ts line ~400: schema line, constructor validation, init designation block); `Functions 100% (100/100)`. These residual gaps are pre-existing relative to a scoped run — the CI coverage lane covers them from the full-repo suite. Identical numbers under `--pool=threads` (deterministic, not a fork-merge race). CI owns `test:coverage`; this was a scoped diagnostic only. |
| 11 | `git diff --cached --check` (per commit) | exit 0 every time (whitespace clean) |
| 12 | pre-commit hook attempt (commit 1, without `--no-verify`) | FAILED — verbatim output in the hook-skip ledger below |
| 13 | base-file lint control: `tsx scripts/run-oxlint.ts --config .oxlintrc.staged.json packages/experimental/shadow-router/src/service.ts` with my service.ts change stashed | exit 1 — identical 4 findings at base line numbers (236:34 non-null assertion, 442/918/1017 max-len) |
| 14 | same lint with my changes applied | exit 1 — same 4 findings, lines shifted only (246:34, 471, 947, 1046); zero findings in `tests/host-designation.spec.ts`; **zero new findings introduced by this diff** |

## Commits

| SHA | Subject |
|---|---|
| `eb44be73f6` | feat(shadow-router): perform markShadow from a declared shadowSessionId config |
| `5e86ef6cb3` | docs(shadow-router): document the config-declared Shadow designation |
| this evidence commit | chore(devframe): declare the Shadow designation row and record P21-S evidence (its own SHA cannot appear inside itself; recorded in the L1 report) |

## Four-plane proof (kept SEPARATE)

### Plane 1 — source (vitest + tsc)

- `pnpm exec vitest run packages/experimental/shadow-router/tests`: exit 0, 14/14 files, 32 passed + 1 pre-existing POSIX-gated skip (aliases.spec.ts on Windows).
- `pnpm exec tsc -b packages/experimental/shadow-router`: exit 0, strict, no new `any`.
- New code lines/branches each covered by the package suite (scoped coverage read-out shows every uncovered line outside the diff hunks; new-branch mapping: config-present/absent → scenarios 1-6 + 27 pre-existing tests; scan-hit/miss → scenarios 2 / 1; `agent/created` listener match/mismatch → shadow vs worker creation; constructor validation `undefined`/`''`/`'   '`/valid → scenarios 4 + 3 + 1; `markShadow` idempotency short-circuit → existing s6-markshadow-scope).

### Plane 2 — enabled (config face)

- Fail-loud validation: `host-designation.spec.ts` boots with `shadowSessionId: ''` and `'   '` → plugin activation rejects with `SHADOW_INVALID_CONFIG` (scenario 4).
- Host row declares the field: `.agents/devframe/integration/cordis.patch.yml` `shadow-router` row now carries `shadowSessionId: session-shadow` (plain string, no `!!js`) under `config:`, with the block comment rewritten to the declarative designation face.
- Unconfigured regression: scenario 3 boots unconfigured — `isShadow` false for a live agent even with the would-be designated id, zero shadow tools in any scope, direct `openProject` rejects `SHADOW_CALLER_FORBIDDEN`, `listBindings()` empty. The 27 pre-existing tests are all unconfigured boots and stay green (zero behavior change when unconfigured).

### Plane 3 — composition run (real composition)

`tests/host-designation.spec.ts` boots the real stack (Context + mountAgentLoopTestDependencies + SessionProjectionRegistry + AgentLoop `{agents: []}` + Storage + StorageJson + StorageDomain json + JsonlSessionPersistence + WorkspaceRegistry + AgentBindingRegistry + ShadowRouter) with the real `ctx.agents.create({ sessionId })` host creation path and the real scoped-tools accessor + real dispatcher (`ctx.tools.execute`):

1. created-after-mount → marked via the real `agent/created` listener; marked scope schemas exactly `SHADOW_TOOL_NAMES`; unmarked scope none; dispatcher cross-check (unmarked `project_status` → `unknown tool "project_status"`, marked → isError false).
2. created-before-mount → marked at init via the scan path.
3. unconfigured → nothing marked, fail-closed service face.
4. invalid config (`''`, `'   '`) → `SHADOW_INVALID_CONFIG` at boot.
5. cold restart over a reused storage root: process 1 marks at creation and opens one real project (`openProject` against a real directory) producing a durable binding row; `ctx.fiber.dispose()`; process 2 restores the row `toEqual` field-for-field while the designation is not restored — until the host recreates `session-shadow`, which re-marks through the real listener. Proves designation is in-memory, rows durable.
6. same-process dispose & recreate: handle dispose removes the marking via the existing `agent/disposed` cleanup; recreating the same id re-marks with the full tool set.

### Plane 4 — production-ready (NOT claimed)

Real-deployment `authorizedRoots` and real-model e2e for the designation row remain **pending, not failed**: they are blocked by the real data root / `DEEPSEEK_API_KEY` credentials, which this worktree does not hold. The composition row is wired but has not been exercised against a live `dsh --profile integration` boot with a real model.

## Hook-skip ledger (lefthook pre-commit, `--no-verify` commits)

Commit 1 hook attempt (without `--no-verify`) failed; verbatim:

```
│  lint (staged) ❯
packages/experimental/shadow-router/src/service.ts:246:34: error typescript(no-non-null-assertion): Forbidden non-null assertion.
packages/experimental/shadow-router/src/service.ts:471:1: error @stylistic(max-len): This line has a length of 163. Maximum allowed is 140.
packages/experimental/shadow-router/src/service.ts:947:1: error @stylistic(max-len): This line has a length of 155. Maximum allowed is 140.
packages/experimental/shadow-router/src/service.ts:1046:1: error @stylistic(max-len): This line has a length of 144. Maximum allowed is 140.
exit status 1
┃  whitespace (staged) ❯
/usr/bin/env: ‘bash’: No such file or directory
┃  vendor manifest guard ❯
exit status 127
summary: (done in 2.94 seconds)
✓ whitespace (staged) (0.06 seconds)
✗ lint (staged) (2.72 seconds)
✗ vendor manifest guard (0.04 seconds)
```

| Commit | Skipped gate | Reason | Substitute verification (real results) |
|---|---|---|---|
| `eb44be73f6` | pre-commit `lint (staged)` | Pre-existing findings in service.ts, proven present at base (control run with the change stashed: identical 4 findings; re-run with the change: same 4, lines shifted only, zero findings in the new spec) — hook-config-vs-CI discrepancy, not introduced by this diff | `git diff --check c93b86c43e..eb44be73f6` exit 0 |
| `eb44be73f6` | pre-commit `vendor manifest guard` | bash absent on this host — `/usr/bin/env: 'bash': No such file or directory`, hook exit 127 (environment fact; inspects vendor/ only, untouched by this diff) | `git diff --check c93b86c43e..eb44be73f6` exit 0 |
| `5e86ef6cb3` | all pre-commit jobs | same environment (bash absent for `vendor manifest guard`); lint/translation-pairing/notices jobs skipped by `--no-verify` | `git diff --check c93b86c43e..5e86ef6cb3` exit 0; `pnpm run verify-translation-pairing` on both touched pairs exit 0 (2 named pairs consistent); `test:docs` translation-pairing job PASS |
| this evidence commit | all pre-commit jobs | same environment | verified post-commit over `c93b86c43e..HEAD`: `git diff --check` exit 0; byte-level trailing-newline check over all 10 changed files — 0 violations (every file ends with exactly one `\n`, no `\n\n` tail); working tree clean |

Substitute verification run for every `--no-verify` commit: `git diff --check <base>..<commit>` exit 0 (no whitespace errors), plus a byte-level trailing-newline check that every changed file ends with exactly one `\n` and no `\n\n` tail (script below).

## Deviations (recorded, deliberate)

1. **Schema idiom**: the L1 design specified `z.string().optional()`; the vendored schemastery (`vendor/schemastery`, v3.18.2) has no `.optional()` chainable on schema instances (chainables are `required/disabled/collapse/hidden/loose/default/link/comment/description/max/min/step`), so the field uses the repo idiom for an optional field — bare `z.string()` — which omits an absent key and validates a present string (precedent: `permission-presets` `name: z.string()`). Runtime semantics are exactly the design intent; the optional face is carried by the `ShadowRouterConfig` type.
2. **Registered-path addition — pairing sidecars**: `packages/experimental/shadow-router/README.i18n.yaml` (re-recorded) and `.agents/notes/implemented/architecture/2026-09-06-shadow-config-designation.i18n.yaml` (created) are outside the registered precise paths but are the mechanical consistency records the `translation-pairing` gate (in `test:docs`) requires for any bilingual edit — the repo's documented procedure for touching a README/note pair. Without them `test:docs` cannot be green. Both updated via the official `verify-translation-pairing --write` command only.
3. **Scoped coverage diagnostic**: run once to validate new-branch coverage; the authoritative per-file 100% gate remains CI-owned `test:coverage` (not run, per task constraints).

## Files changed

- `packages/experimental/shadow-router/src/service.ts` — `shadowSessionId` config field + schema, constructor validation, `agents` inject, init scan + `agent/created` listener (`shadow-router.shadowDesignation`), `ResolvedConfig` type adjusted
- `packages/experimental/shadow-router/tests/host-designation.spec.ts` — NEW, 6 scenarios
- `packages/experimental/shadow-router/README.md` / `README.zh.md` — config table row + declarative designation paragraph + yaml snippet
- `packages/experimental/shadow-router/README.i18n.yaml` — pairing record re-recorded
- `.agents/notes/implemented/architecture/2026-09-06-shadow-config-designation.md` + `.zh.md` + `.i18n.yaml` — NEW Agent Note pair + record
- `.agents/devframe/integration/cordis.patch.yml` — `shadow-router` row block + preceding comment only
- `.agents/devframe/v14-shadow/markshadow-host-wiring-evidence.md` — NEW (this file)
