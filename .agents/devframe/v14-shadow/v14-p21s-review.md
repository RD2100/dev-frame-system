# L1 review record — P21-S markShadow real host invocation (worker p/v14-shadow-w1)

- Reviewer: L1 Shadow lead (this session), reviewing worker branch `p/v14-shadow-w1`
  (worker SessionID `0b883d36-5612-40ae-8954-f6da2ef17bbe`) before integration.
- Verdict: **APPROVED**; integrated into `codex/v14-shadow-lead` as merge `0c0cdaf1e8`
  (--no-ff). Only 主控 merges main; nothing pushed anywhere.

## Independent verification executed by L1 (not restated from the worker report)

| Check | Command | Real result |
| --- | --- | --- |
| Change surface | `git diff --name-status c93b86c43e..p/v14-shadow-w1` | exactly the 10 registered/claimed files; no forbidden paths touched |
| Whitespace | `git diff --check c93b86c43e..p/v14-shadow-w1` | exit 0 |
| Unit + composition suite (re-run) | `pnpm exec vitest run packages/experimental/shadow-router/tests` | 14/14 files, 32 passed + 1 pre-existing POSIX-gated skip |
| Type check (re-run) | `pnpm exec tsc -b packages/experimental/shadow-router` | exit 0 |
| Pairing (re-run) | `pnpm run verify-translation-pairing <README anchor> <note anchor>` | 2 named pair(s) consistent |
| Lint control (base content at real path) | overwrite working file with `c93b86c43e` content → staged-config lint → restore | exit 1, 4 findings at 236:34 / 442 / 918 / 1017 (lengths 163/155/144) |
| Lint (HEAD) | staged-config lint on service.ts + new spec | same 4 rules/lengths at 246:34 / 471 / 947 / 1046 — pure displacement; **0 findings in the new spec** |

Working tree restored clean after the control run (`git status --short` empty).

## Diff review findings

- `service.ts`: design implemented as ruled — optional `shadowSessionId` with contract JSDoc,
  `SHADOW_INVALID_CONFIG` constructor validation (empty/whitespace), `'agents'` added to
  `static inject`, init-time live scan + `agent/created` listener registered through
  `ctx.effect(..., 'shadow-router.shadowDesignation')` only when configured, `SessionId` branding
  applied, `ResolvedConfig` narrowed to keep the optional face. Unconfigured boots register
  nothing (verified by the regression scenario and the 27 untouched pre-existing tests).
- `tests/host-designation.spec.ts`: spec-local real composition without the forced
  `markShadow` (correct isolation from `helpers.ts`, which stays byte-identical); real
  `ctx.agents.create` host path; real scoped-tools accessor and real dispatcher cross-check;
  six scenarios cover created-path, init-scan, unconfigured fail-closed, invalid-config fail-loud
  (both `''` and whitespace), cold restart with a durable binding row restoring field-for-field
  while the in-memory designation re-marks, and dispose/recreate re-marking.
- Archive row (`.agents/devframe/integration/cordis.patch.yml`): only the `shadow-router` block +
  its comment; `shadowSessionId: session-shadow` plain string; fail-closed semantics documented.
- README pair: mirrored bilingual edits; `.i18n.yaml` sidecars re-recorded/created via the official
  `verify-translation-pairing --write` (blessed by L1 as mechanical pairing records — precedent:
  `2026-09-05-worktree-registry.i18n.yaml`).
- Agent Note pair: format matches the house template; alternatives and costs stated honestly.

## Deviation rulings

1. `z.string()` instead of `z.string().optional()` — **accepted**. Vendored schemastery has no
   `.optional()` chainable; bare `z.string()` is the repo's optional-field idiom (L1 independently
   confirmed precedents, e.g. `permission-presets`, `web` provider fields). Runtime semantics match
   the design intent; the optional face lives in the `ShadowRouterConfig` type.
2. Pairing sidecars outside the registered paths — **blessed** as mechanical, gate-required records
   produced only by the official command.
3. Scoped coverage diagnostic instead of CI's `test:coverage` — **accepted** (CI owns the gate;
   every new branch maps to a named scenario per the evidence file).

## Hook-skip ledger (worker commits, verified by L1)

All three worker commits used `--no-verify`: lefthook `whitespace (staged)` passed in-hook, then
`vendor manifest guard` exited 127 (bash absent — same host environment fact recorded in the L1
registry ledger), and `lint (staged)` failed only on the four pre-existing service.ts findings
proven pre-existing by L1's independent control run above. Substitute verification over the whole
range `git diff --check c93b86c43e..p/v14-shadow-w1` exit 0; L1 re-ran the package suite, tsc, and
pairing after merge. NOT claimed as gates passed.

## Four-plane status after integration

1. Source: PROVEN (L1 re-run: 32+1 vitest, tsc 0).
2. Enabled: PROVEN (fail-loud validation scenario; host row declares the field; unconfigured
   fail-closed regression green).
3. Composition run: PROVEN at composition-test level (real composition, real agent/created path,
   real dispatcher, cold restart, dispose/recreate). The `dsh --profile integration` live boot with
   a real model was NOT exercised.
4. Production-ready: NOT claimed — real-deployment `authorizedRoots` + real-model e2e remain
   pending, blocked by the real data root / `DEEPSEEK_API_KEY`.
