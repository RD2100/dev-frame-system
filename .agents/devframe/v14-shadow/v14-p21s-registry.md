# V1.4 P21-S markShadow real host invocation — lead registry (L1 Shadow)

- Task: P21-S — wire the real host invocation of `ShadowRouter.markShadow`. Today the designation
  seam exists in `packages/experimental/shadow-router` but only tests and integration probes call it;
  no host composition has a production call site (recorded gap: "No host-composition markShadow
  production call site (the P23/S4 seam)", `docs/working/dsh-controller-v1.2-handoff-2026-09-06.md`).
- Approach (design ruling by L1, read from source): give the host composition a declarative
  designation face on the ShadowRouter service itself — a validated optional config field
  `shadowSessionId`. When configured, the service performs the real `markShadow(agent)` invocation at
  the earliest resolvable point: immediately for an already-live agent (init scan), otherwise on
  `agent/created` for the matching session id. Unconfigured keeps today's fail-closed behavior
  (nothing marked, tools scope-isolated, callers fail `SHADOW_CALLER_FORBIDDEN`). Creation of the
  Shadow session stays host-owned (`ctx.agents.create({ sessionId })`); only the marking becomes
  declarative. This mirrors the pluginization convention "已装插件 = Service + profile patch 行
  config 面" and does not touch project-contracts roles (closed union controller/lead/worker) nor
  any Memory implementation.
- Lead checkout / branch / base: `D:\dsh-devframe-v14-shadow-lead`, `codex/v14-shadow-lead`,
  base `c93b86c43e0a7fa9c5720ea70575241b0c990a22` (verified clean at takeover; untracked
  `controller-write-probe.txt` present in that checkout — left untouched, not mine).
- Isolated-home probes (`C:\Users\25313\.dsh-integration`) and real deployment roots are out of
  scope here; credentials/real Vault absence only blocks the deployment-facing proof, local
  verification continues.

## Registered precise paths (file domain)

L1-owned records (this checkout):

- `.agents/devframe/v14-shadow/v14-p21s-registry.md` (this file)
- `.agents/devframe/v14-shadow/v14-p21s-review.md` (post-review evidence, written after worker lands)

Worker worktree (created by L1, branch `p/v14-shadow-w1` off `c93b86c43e`):

- `D:\dsh-devframe-v14-shadow-w1` — worker cwd; worker owns commits on `p/v14-shadow-w1` only.

Implementation paths (worker):

- `packages/experimental/shadow-router/src/service.ts` — config field + designation wiring.
- `packages/experimental/shadow-router/src/index.ts` — only if a type export must surface.
- `packages/experimental/shadow-router/tests/host-designation.spec.ts` — new targeted spec.
- `packages/experimental/shadow-router/tests/helpers.ts` — only an additive optional boot option;
  existing specs' behavior must not change.
- `packages/experimental/shadow-router/README.md`, `README.zh.md` — Config table + designation face.
- `.agents/notes/implemented/architecture/2026-09-06-shadow-config-designation.md` + `.zh.md` — Agent Note pair.
- `.agents/devframe/integration/cordis.patch.yml` — ONLY the `shadow-router` row block + its comment
  (host config wiring: the row declares `shadowSessionId`; inert until an agent with that id exists).
- `.agents/devframe/v14-shadow/markshadow-host-wiring-evidence.md` — worker evidence (committed).

No-go paths (registered): everything else. Specifically forbidden: `packages/experimental/project-memory/**`,
`packages/experimental/project-contracts/**`, battery snapshots, `docs/config-catalog.md` and every
generated catalog (if a gate demands generated-file changes → STOP and escalate to 主总控 via L1),
historical worktrees, any push/PR/publish, deletion of user files.

## Agent records

### L1 Shadow (this session)

- SessionID: `session-c1668d60-b936-45fd-84bc-77f121241cfe` is the parent (主总控). L1's own session id:
  recorded as the current delegated session (parent id `session-c1668d60-b936-45fd-84bc-77f121241cfe`).
- Provider/model: DeepSeek Harness native — glm-5.3-flash.
- Worktree: `D:\dsh-devframe-v14-shadow-lead` (branch `codex/v14-shadow-lead` @ `c93b86c43e`).
- Nine-state: planned → assigned (worker dispatched).

### L2 Worker (created by L1)

- SessionID: `0b883d36-5612-40ae-8954-f6da2ef17bbe` (continuable subagent; created 2026-09-06)
- Parent ID: L1 Shadow session (above).
- Provider/model: DeepSeek Harness native child — the `subagent` tool schema carries no
  provider/model override parameter, so the lane was not selectable at creation time; recorded
  honestly per the 主控 routing directive (huoshan-2 reserved for the next independent low-conflict
  task, task surface to be reported to 主控 before it starts).
- taskId: `P21-S-markshadow-host-wiring`.
- worktreeId: `D:\dsh-devframe-v14-shadow-w1` / branch `p/v14-shadow-w1` @ base `c93b86c43e`.
- Constraint: worker must NOT create agents; worker commits locally only.
- Nine-state: assigned.

## Hook-skip ledger and substitute verification (per 主控 directive ②)

Environment fact: this host's git is a portable distribution
(`C:\Users\25313\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git`) with no
bundled or PATH-installed `bash`; lefthook's pre-commit `vendor manifest guard` exits 127
(`/usr/bin/env: 'bash': No such file or directory`) and cannot run here. Every affected commit is
recorded below with its skip reason and the substitute verification actually executed. Commits with
hook skips are NEVER reported as "gates passed".

| Commit | Skipped gate | Reason | Substitute verification executed | Real result |
| --- | --- | --- | --- | --- |
| `97a9078112` | vendor manifest guard (pre-commit) | bash absent on host, hook exit 127 | in-hook `whitespace (staged)` passed before the failure; post-commit `git diff --check 97a9078112^..284c485a3c` exit 0; changed-file set is `v14-p21s-registry.md` only (no `vendor/` files, the guard's only subject); byte-level check: file ends with exactly one LF (final bytes `46 10`, no trailing blank line) | PASS (substitute) |
| `284c485a3c` | vendor manifest guard (pre-commit) | same bash absence | same `git diff --check` run covers it (exit 0); same single changed file, byte-level single-LF check passed | PASS (substitute) |

Pairing check for these commits: `.agents/devframe/**` lead records are outside the
translation-pairing manifest scope (`scripts/translation-pairing.manifest.json` covers docs/ and
notes/AGENTS sources); no `.zh.md` pair is required — N/A, not a skip.

This ledger is updated on every future hook skip; each new entry carries its own substitute
verification with real results.

## Four-plane proof plan (source / enabled / composition run / production-ready)

1. Source: package vitest suite + `tsc -b packages/experimental/shadow-router` (worker + L1 re-run).
2. Enabled: config face validated fail-loud (invalid `shadowSessionId` rejects at load) + host row
   declares the field; unconfigured boot stays fail-closed (regression spec).
3. Composition run: real composition boot (agent-loop/session/storage/workspace/bindings/router) —
   designation lands through the real `agent/created` path and the init scan; marked scope exposes
   exactly the four tools; unmarked scope none; dispatcher cross-check; cold restart re-marks via the
   same configured id.
4. Production-ready: NOT claimed by this task. Remaining after merge: a real deployment composition
   with real `authorizedRoots` (blocked by the real data root per prior waves) and real-model e2e.
   Recorded honestly as pending, not failed.
