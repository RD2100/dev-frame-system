# S6 Real Delivery Flow Acceptance Evidence (shadow-router)

- Task: S6 final wave (real delivery flow + completed settlement acceptance), supervised by L-Shadow, under the DeepSeek Harness pluginization plan (P22 line).
- Worktree: `D:\dsh-devframe-p-shadowflow`, branch `p/shadowflow`, baseline `f06a4703e7` (main HEAD at wave start).
- Scope: acceptance evidence for the full cross-root delivery journey under the package's REAL machinery — real JSON storage on disk, real tool dispatcher, real controller sessions created by `project_open`. Nothing in `packages/experimental/shadow-router/src/` was modified; `.agents/devframe/integration/**`, READMEs, tsconfigs, and existing tests were not touched.

## What was verified

Three new vitest specs (test names carry the literal `S6`), all passing. Every claim below is a literal `expect()` in the spec, numbered by inline `[n]` markers; per-spec counts: 32 + 33 + 29 = **94 assertions**.

### 1. `tests/s6-delivery-flow.spec.ts` — the full delivery journey (1 test, 32 assertions)

Re-run: `pnpm exec vitest run packages/experimental/shadow-router/tests/s6-delivery-flow.spec.ts`

One project travels open → authorize → send → settle → status read-back:

1. `project_open` dispatch (real `ctx.tools.execute`) succeeds.
2. The rendered model face (the tool result's text) is byte-identical to `JSON.stringify` of the dispatcher's canonical value — the rendered JSON is the value.
3. The rendered open value carries `state: "ready"`.
4. The open value carries a workspace id.
5. The open value carries a controller session id.
6. The open value carries a binding revision ≥ 1.
7. `ctx.sessions.get(controllerSessionId)` finds a live session in the real session store.
8. That session's `header.cwd` equals the canonical path from the receipt.
9. Its `header.parentSession` is undefined (the controller is never parented to the Shadow).
10. `ctx.agentBindings.find(controllerSessionId)?.role` is `'controller'`.
11. After `setActiveGoal`, the binding records the run's `activeGoalId`.
12. The binding records the matching `activeAcceptanceHash`.
13. `project_send` dispatch (current revision, same goal/hash) succeeds.
14. The send receipt's status is `received`.
15. The receipt carries a message id.
16. `listDeliveries` holds exactly one row.
17. The row state is `received`.
18. `receivedAt` is defined.
19. `completedAt` is undefined.
20. `completeDelivery` returns state `completed`.
21. The settled record carries `completedAt`.
22. Settlement preserved the original `receivedAt`.
23. The durable row (read back through `listDeliveries`) reads `completed`.
24. The durable row kept `receivedAt` — the two-write history survives settlement.
25. `project_status` dispatch succeeds.
26. The status page lists exactly one project.
27. The entry's workspaceId is the opened workspace.
28. The rendered project state is `ready`.
29. The entry lists exactly one delivery.
30. The rendered delivery's messageId is the settled message.
31. The rendered delivery state is `completed`.
32. The rendered delivery carries `completedAt`.

### 2. `tests/s6-stop-settlement.spec.ts` — stop-path settlement contrast (1 test, 33 assertions)

Re-run: `pnpm exec vitest run packages/experimental/shadow-router/tests/s6-stop-settlement.spec.ts`

Residue path chosen and documented: project A's queued crash-residue row is seeded router-less through the real domain BEFORE the harness boots (`seedHarness` + `seedWorkspaceFact`, a ready binding without a goal, one queued intent `msg-s6-stop-queued-1` / requestId `s6-stop-queued-1`) — the seed pattern of `tests/delivery-limits.spec.ts`. `project_open` then runs through the real dispatcher and converges on the ready row. This is the simplest real path: one harness generation, the residue is a true crash residue (a send whose acceptance never landed), and the open dispatch exercises real convergence.

1–6. A opens through the real dispatcher (converged, ready, residue visible after cold restore); B opens through the real dispatcher (fresh, ready); A and B resolve distinct workspace identities.
7–9. `project_send` to A and to B each succeed with `received` receipts.
10–13. `project_stop` on A through the real dispatcher: receipt `stopping`, exactly 1 cancelled delivery, binding revision bumped.
14–17. The queued residue converged to `cancelled` with `cancelReason: 'project-stopped'` visible; A's accepted row is still `received` with no `completedAt` — the stop preserves accepted input without completing or dropping it.
18–22. Repeating the stop with the SAME request id replays the exact stored receipt (deep equality); a second stop with a NEW request id is a no-op receipt (`stopping`, 0 cancellations).
23. `confirmProjectStopped(A)` (host seam) → binding `stopped`.
24–25. OBSERVED probe (see Fail-loud findings): `completeDelivery` on A's received row on the stopped project SUCCEEDED — the row reads `completed` with `completedAt` defined. No rejection exists in the frozen source.
26–33. B isolation: binding still `ready`; B's controller session still live with its canonical cwd; B's queue untouched (exactly its one accepted row); a NEW `project_send` dispatch to B succeeds (`received`); B's queue grows to two accepted rows; sanity: the successful send carries no failure code.

### 3. `tests/s6-crash-window.spec.ts` — crash-window adjudication (1 test, 29 assertions)

Re-run: `pnpm exec vitest run packages/experimental/shadow-router/tests/s6-crash-window.spec.ts`

Generation 1 opens a real project through the dispatcher, authorizes the goal, and persists one accepted delivery; then `close()` — context disposed, root kept (process death). The queued intent whose acceptance never landed is seeded through the real domain (requestId `s6-crash-queued-1`, messageId `msg-s6-crash-queued-1`). Generation 2 boots a fresh harness over the same root and re-creates the reserved controller session on the SAME id through the real session store (sessions are process-local; the documented host recovery action, same pattern as `tests/s6-cold-restore.spec.ts`).

1–5. Generation 1: open ready, send received, exactly one accepted row.
6–7. Generation 2: binding restored `ready`, keeping generation 1's reserved controller id.
8–9. The seeded intent is `queued` after cold restore, with no `receivedAt`.
10–14. `recoverDeliveries(workspaceId)` converges exactly that one row to `received` with `receivedAt` defined; exactly ONE row exists for the message id (no duplicate); the workspace holds exactly two rows.
15–19. Replay through the real dispatcher (same request id + identical input): same message id, `received`, no row added, and `receivedAt` NOT rewritten (the post-recovery instant is preserved verbatim).
20–23. Conflict (same request id, different text): the dispatch fails loud with `SHADOW_REQUEST_CONFLICT` (asserted via `failureCode`), the failure names the reused request id, and no row is added.
24–29. Generation 1's row survived with state `received`; a same-requestId replay returns the same message id with the rendered `received` JSON, adds no row, and does not rewrite its `receivedAt`.

### Gates as run (from the worktree root)

- `pnpm exec tsc -b packages/experimental/shadow-router` → exit 0, zero errors (the package program covers the frozen src; the specs are not in it).
- `pnpm exec vitest run packages/experimental/shadow-router/tests` → Test Files 13 passed (13); Tests 25 passed | 1 skipped (26). Baseline before this wave: 10 files; 22 passed | 1 skipped (23). The +3 files / +3 passed are this wave's specs; the 1 skipped is the pre-existing POSIX-gated `aliases.spec.ts` case on Windows.
- `pnpm run build` (FULL host build — new acceptance criterion for this wave) → attempt 1 exit 1 with four TS2304 errors in `tests/s6-crash-window.spec.ts`: a missing `JsonValue` type import in THIS wave's own new file (the host typecheck program includes `tests/`; vitest's transform does not typecheck). Fixed in place; retry exit 0 (`build:lib:host`: gen:typert + `tsc -b tsconfig.host.json` + tsdown; `build:lib:client`: runtime bundle, 220 client artifacts recorded). No surface outside shadow-router failed. Built `lib/` output confirmed gitignored (`.gitignore` rule `lib/`); `git status --short` stays clean of build output.

## Seams used

Model-facing dispatches (through the real tool runtime `ctx.tools.execute`; the caller is the host-designated Shadow agent from the harness):

| Tool | Specs |
|---|---|
| `project_open` | 1, 2, 3 |
| `project_send` | 1, 2, 3 |
| `project_status` | 1 |
| `project_stop` | 2 |

Host-only seams (called as the host on `ctx.shadowRouter`; never model-facing):

| Seam | Specs |
|---|---|
| `setActiveGoal(workspaceId, goalId, acceptanceHash)` | 1, 2, 3 |
| `completeDelivery(workspaceId, messageId)` | 1, 2 |
| `confirmProjectStopped(workspaceId)` | 2 |
| `recoverDeliveries(workspaceId)` | 3 |
| Queries `findBinding` / `listDeliveries` | 1, 2, 3 |

- `completeDelivery` EXISTS: `src/service.ts` line 738 (`async completeDelivery(workspaceId: WorkspaceId, messageId: ShadowMessageId): Promise<ShadowDeliveryRecord>`); its guard set is delivery-membership (line ~741) and the `received` state (lines ~744–749). Existence confirmed — only its stopped-project semantics differ from the mission's expectation (below).
- No API was invented and none was simulated: every step of every journey runs through a seam that exists in the frozen src.
- Zero-mock statement: real JSON storage on disk (`dsh-storage` + `dsh-storage-json` + `dsh-storage-domain` over one temp root; the JSON backend's one-live-handle rule was honored by sequencing the generations), the real tool dispatcher (`ctx.tools.execute` with real `ToolCallId` and caller signal), real controller sessions created by `project_open` through the real session store, the real workspace registry, and the real session-identity binding registry. The ONLY seeded rows are the crash-window residues (specs 2 and 3), written through the REAL `shadow_router` domain (schema-validated tables) — no in-memory simulation anywhere.

## Boundaries

- Host compositions own: marking the Shadow (`markShadow` — the harness performs the host's designation), authorizing open runs (`setActiveGoal`), settling completions (`completeDelivery`), confirming stops (`confirmProjectStopped`), and converging interrupted rows on restart (`recoverDeliveries`, plus re-creating process-local controller sessions on the reserved ids).
- The package persists and receipts but never wakes a model: every dispatched call is a routing read/write; `project_status` never mutates durable state, never appends session events, and never schedules follow-ups; a `received` receipt is reported verbatim and never read as completion; forwarding received input into the controller's session log stays host-side (a bare mount receives nothing model-visible).

## S6 four-state row (final)

- 源码就绪: 达成 — frozen src at `f06a4703e7` compiles clean (`tsc -b` exit 0); every seam the journey needs exists as documented (`openProject`/`sendToProject`/`stopProject`/`projectStatus` plus `setActiveGoal`/`completeDelivery`/`confirmProjectStopped`/`recoverDeliveries`); no API was missing and none was invented.
- 安装+启用: 达成（包级） — the real harness composition mounts the full stack and `markShadow` installs exactly the four project tools into the Shadow scope; this wave drives all four through the real dispatcher (scope-level installation evidence: the earlier S6 wave's `s6-markshadow-scope.spec.ts`). Composition-level enablement (`cordis.patch.yml`) remains L-Integration's surface, unverified here.
- 运行时验证: 达成（本波范围） — delivery journey, stop contrast, and crash-window adjudication verified over real JSON storage with real sessions and the real dispatcher (3 new specs, 94 numbered assertions, all green; package total 25 passed + 1 skipped). 未验证: composition-level integration, recorded-session fixtures, cross-platform runs.
- 生产可用: 不声称 — the fail-loud finding below (`completeDelivery` lacks a stopped-project guard) needs a design ruling by L-Shadow; composition-level integration, recorded-session fixtures, and cross-platform verification remain open before any production claim.

## Fail-loud findings

1. **`completeDelivery` does not reject settlements against a stopped project.** The wave mission expected "a stopped project cannot settle … expect a rejection with a stable code". Checked against the frozen source before running and confirmed empirically on the first run (spec 2 assertions [24]–[25]): after `project_stop` (receipt `stopping`, residue cancelled) and `confirmProjectStopped` (binding `stopped`), `completeDelivery(workspaceId, receivedMessageId)` SUCCEEDS and the row settles to `completed` with `completedAt` defined. There is no stable rejection code to record because no rejection is thrown: the guard set at `src/service.ts` lines 740–749 checks only delivery-membership and the `received` state, never the binding state (contrast `sendToProject`, which gates admission on the binding). Root semantics: a stop preserves accepted input as `received` (stop cancels only `queued` rows, lines 618–622), so the host-only settlement seam remains reachable on a stopped binding. Recorded fail-loud per the wave contract; not simulated, not worked around — the spec records the observed outcome with explicit `OBSERVED` labels. Whether stopping must block settlement is a design decision above this wave's authority (src semantics are frozen).
2. None otherwise — every other expected seam behaved exactly as documented, and the build's first-attempt failure was this wave's own missing type import (fixed; recorded under Gates).
