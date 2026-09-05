---
description: Project controller v1.2 handoff snapshot (2026-09-06): main tree state, dual-plugin four states, in-flight chain, and remaining-task boundaries.
---

# Project controller handoff — 2026-09-06

English | [中文](dsh-controller-v1.2-handoff-2026-09-06.zh.md)

## Handoff status: preparation in progress

The outgoing controller still holds the sole merge right and the dispatch right until every condition in the "Handoff gate" below is met. After the in-flight chain settles, the outgoing controller updates the final SHA and acceptance result in the "In-flight chain" section, then stops new dispatches and merges; only then does the handover take effect. Nobody may declare the handover complete before the successor is activated.

## Voided conclusions (latest user directives govern)

The opening portion of the registry (`.agents/devframe/pluginized-round-registry.md`) contains outdated status and concurrency-limit statements; the following conclusions are **void**:

- "Concurrency cap of 2/5 chains" — the user has authorized: no fixed parallel cap; schedule by file owner, conflict risk, and measured API capacity; routinely exceed 5.
- Lane assumptions such as "huoshan-1 in backoff / huoshan-2 exclusive" — huoshan-1/2 both routinely take different tasks; lane attribution comes only from persisted session JSON, never from assumption.
- "Routine rulings must wait for user authorization" — the user has authorized: development/test/integration/config/acceptance rulings that align with the main line and are verifiable and rollback-able execute by default. Only W4 real tasks, production deployment decisions, and external publishing still need explicit authorization.
- "40-round inspection rule adjustments / 8-minute cadence as a project parameter" — the 40-round rule stays unchanged; the 8-minute cadence belongs to external inspection automation, not DSH project configuration.

## Main tree snapshot

| Item | Value |
| --- | --- |
| Snapshot time | Around 08:30 on 2026-09-06 (local time zone) |
| HEAD | `c1d9da130e` (before the handoff-doc commit; the registry is authoritative) |
| Working tree | Clean; user's uncommitted files stay untouched |
| Protected items | `AGENTS.md`, `docs/working/devframe-qa-2026-09-04.*`, `stash@{0}` (user recovery snapshot) — never commit, revert, or push them |
| Authoritative gate baseline | build exit 0 (220 artifacts); experimental+extensions sweep 130 files 1256P+1S; agent-hierarchy 40/40; gen-cordis-catalog 0; test:docs 15/15; verify-cordis-config 133; verify-package-invariants 39; the single snapshot-sampling red = known B-family root (below) |

## Dual-plugin four states and shortest evidence paths

Four-state terms: source ready / profile install+enable / runtime verification (composition level) / production ready. Shadow and Memory are both mandatory deliverables; the first three states are achieved, and production-ready is a deployment-decision surface (not a code gap).

| Plugin | Source | Install+enable | Runtime verification | Production ready | Shortest evidence path |
| --- | --- | --- | --- | --- | --- |
| Shadow (`packages/experimental/shadow-router`) | ✅ (incl. completeDelivery stopped guard) | ✅ (bundle rows+manifest declarations) | ✅ (package-level 26P+1S; composition-level markShadow/delivery journey/stop contrast/crash-window full chain) | =deployment decision (real authorized roots+host marking policy) | `.agents/devframe/p22/shadow-delivery-flow-evidence.md`, `s6-evidence.md`, registry entries integration-3/4, shadowflow, shadowguard |
| Memory (`packages/experimental/project-memory`) | ✅ | ✅ (integration profile row) | ✅ (composition-level three-tool face+receipt rehydration agent side+cold recovery) | =deployment decision (writeEnabled+role allowlist) | `.agents/devframe/p22/memory-rehydration-evidence.md`, registry entries integration-1/2 |

Composition-level rerun commands: set `DSH_HOME=C:\Users\25313\.dsh-integration`, clean the whole `sessions/storages/integration-vault` tree, then run `pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write` followed by `--phase verify`; expect double 0.

## In-flight chain (the only one at handoff time)

| Item | Value |
| --- | --- |
| Task | `p/fprecompute`: sourceFingerprint recompute engine (AT1-05 variant 5 src wave), design first+ruling request |
| Lead SessionID | `55979618-6bd7-4bc7-badc-8a3b13079158` (L-Foundation) |
| Worker | One-shot foreground subagent dispatched by the lead (SessionID per the lead's session record; the successor asks the lead, never assumes) |
| Worktree / branch / base | `D:\dsh-devframe-p-foundation`, branch `p/fprecompute`, base `526e773b23` |
| Provider | Per persisted session JSON (this session verified L-Foundation's historical routing = huoshan-2; the current worker is unverified — the successor must check the JSON before labeling, never assume) |
| Artifact state | No commits at handoff time; the worktree already holds `packages/experimental/devframe/src/source-fingerprint.ts` and `tests/source-fingerprint.spec.ts` (in progress, files seconds fresh) |
| Recovery point | If the lead's session breaks: resume from the worktree file state (design doc→engine+cases→gates), never redo what is already on disk |
| Acceptance gates | Package vitest+package tsc+`pnpm run build`+verify-export-jsdoc+`git diff --cached --check`+commit --no-verify (src/test/docs as separate commits) |
| Ruling request | Engine inside the StartGoalRequest binding flow or a standalone verify surface — until the outgoing controller rules, only the compute engine and cases land; the comparison face stays untouched |

## Remaining tasks (file domains/dependencies/acceptance/parallelism)

| Task | File domain | Dependency | Acceptance | Parallelizable |
| --- | --- | --- | --- | --- |
| fprecompute comparison face | `devframe/src` (StartGoalRequest/resolveResultBinding neighborhood) | outgoing controller rules on the request | same gates as above+real git fixture cases | no (same chain) |
| required-checks model (product+src) | devframe config surface+evidence comparison face | fprecompute closure (same owner, serial)+design doc first | host build tier+positive/negative cases | no (same owner) |
| P05 residual gaps ②③ | `agent-evidence`/`devframe` | ①④ closed (p05harden `3a18ca5d61`); ②③ design first | same as above | dispatchable to another owner when free of ①④ conflicts |
| P23/S4 production composition wiring | EvidenceReviewerDirectory production impl→project_review | P23 wave start | composition probe extension | awaits P23 |
| AT1-03/AT4 real journeys | agent-reliability/hierarchy tests | model/process-injection wave authorization | package vitest+host build | the process-injection face (AT4-02/03/06) has no model dependency and can dispatch first |
| B-family snapshot red (the only 88F root) | `base/cordis.patch.yml` L252-254+minimal preset L36-38 | product ruling among three options (parameterize/win32 skip/ungate) | test:snapshot lib-mode delta | awaits ruling |
| W4 real tasks+AT1-11 | whole repo | explicit user authorization | per task brief | awaits authorization |
| Deployment decision surface | cordis.yml deployment instances | user deployment wave | composition probe+dump | awaits authorization |

First-batch suggestion: after fprecompute settles and closes → dispatch required-checks design-first on the same owner serially; in parallel, dispatch the AT4 process-injection face design to L-Hierarchy or L-Verify (different owner, zero file conflicts).

## Handoff gate

1. In-flight chain delivers → outgoing controller personally verifies (real commits/artifacts/gates/session JSON) → merges to main → updates the final SHA and acceptance result in the "In-flight chain" section above.
2. The outgoing controller stops all new dispatches and merges (registry gets its final entry).
3. The successor checks: main HEAD, the registry's last entry, and this doc's four-state and in-flight sections — once all three agree, the successor holds sole control.
4. When old child-chain results cannot be received safely across sessions: the outgoing controller closes out first, then hands over, without blocking workers; the successor never rebuilds, interrupts, or re-dispatches in-flight chains.
5. The user's uncommitted files and stash stay untouched through the whole handover; no push, no PR, no publish, no deletion.

## Preserved rules (mandatory for the successor)

Three-layer topology (controller→lead→worker; a worker never creates agents); leads and the controller keep independent worktrees; the controller alone merges to main; no idle spinning; SessionID/Agent/Worktree/task/result persistence; lanes and providers labeled only from persisted JSON; no silent routing, no blind retries of uncertain calls (a single same-command retry covers only transient failures and is disclosed).

## Dev Note

This doc is the 2026-09-06 handoff snapshot, expiring scratch under docs/working; after closing the in-flight chain the successor updates it and archives once the new controller is stable. Provider/SessionID fields not marked "verified" must be re-checked against persisted records before use.
