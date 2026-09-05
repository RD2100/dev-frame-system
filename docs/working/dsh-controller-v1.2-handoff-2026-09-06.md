---
description: Project controller v1.2 handoff snapshot (2026-09-06, second edition): main tree state, dual-plugin four states, in-flight chain, successor first batch, and authorization boundaries.
---

# Project controller handoff — 2026-09-06

English | [中文](dsh-controller-v1.2-handoff-2026-09-06.zh.md)

## Handoff status: preparation in progress (in-flight chain not closed)

This document is the successor controller's **current-state entry point**; the historical ledger (`.agents/devframe/pluginized-round-registry.md`) is consulted on demand. The outgoing controller still holds the sole merge right and the dispatch right until every condition in the "Handoff gate" is met; nobody may declare the handover complete before the successor is activated.

## Voided conclusions (latest user directives govern)

The registry's opening portion contains outdated status and limit statements, now void; the summary:

- No fixed 2/5 concurrency cap: schedule by file owner, conflict risk, and measured API throughput; a same-owner lead may split several workers by concrete file domain (design / independent implementation / test preparation run ahead in parallel; truly dependent wiring lands serially last).
- huoshan-1/2 both routinely take tasks at measured capacity; two provider names do not imply two independent quotas; lane attribution comes only from persisted session JSON.
- The user has authorized: rollback-able development/config/test/technical rulings within the existing project scope, including isolated local small-task acceptance using the existing providers. **Not authorized**: external publishing, push/PR, deleting user files. A specific missing credential (registry auth, DEEPSEEK_API_KEY) or unknown user data root blocks only its own operation; everything else continues.
- The 40-round inspection rule stays unchanged; the 8-minute cadence belongs to external inspection automation, not DSH project configuration; round modifications are no longer discussed.

## Main tree snapshot

| Item | Value |
| --- | --- |
| Snapshot time | 2026-09-06 (second edition, local time zone) |
| HEAD | `ffd9837e7b` (first-edition handoff-doc commit; the registry's last entry is authoritative) |
| Working tree | No changes of mine besides the user's uncommitted items, which stay untouched, uncommitted, unrestored: `AGENTS.md`, `docs/working/devframe-qa-2026-09-04.*`, `stash@{0}` |
| Authoritative gate baseline | build exit 0 (220 artifacts); experimental+extensions sweep 130 files 1256P+1S; agent-hierarchy 40/40; gen-cordis-catalog 0; test:docs 15/15; verify-cordis-config 133; verify-package-invariants 39; the single snapshot-sampling red = known B-family root (see remaining tasks) |

## Dual-plugin four states and shortest evidence paths

Four-state terms: source ready / profile install+enable / runtime verification (composition level) / production ready. Shadow and Memory are both mandatory deliverables. **Only proven faces carry ✅**: install and runtime verification reflect isolated local profile instances and real probes (measured); the production-ready column lists concrete gaps instead of a blanket "deployment decision".

| Plugin | Source | Install+enable (proven) | Runtime verification (proven) | Production ready (concrete gaps) | Shortest evidence path |
| --- | --- | --- | --- | --- | --- |
| Shadow (`packages/experimental/shadow-router`) | ✅ (incl. completeDelivery stopped guard) | ✅ isolated instance (integration profile six-plugin rows; bundle rows+manifest declarations) | ✅ package-level 26P+1S; composition-level markShadow/delivery journey/stop contrast/crash-window full chain (measured double-0 on `.dsh-integration` and on a fresh temp root) | Gaps: no host-composition markShadow production call site (the P23/S4 seam); production authorizedRoots depends on real deployment config (blocked by the real data root); UI state sets | `.agents/devframe/p22/shadow-delivery-flow-evidence.md`, `s6-evidence.md`, registry entries integration-3/4, shadowflow, shadowguard |
| Memory (`packages/experimental/project-memory`) | ✅ | ✅ isolated instance (same profile rows) | ✅ composition-level three-tool face+receipt rehydration agent side+cold recovery (same probe, measured) | Gaps: writeEnabled not enabled on a production instance (config face, local instances authorized); memory three tools not in the role allowlist (config face); the real Vault root depends on production config (blocked by the real data root) | `.agents/devframe/p22/memory-rehydration-evidence.md`, registry entries integration-1/2 |

Composition-level cold-recovery rerun (fresh-temp-root path measured this session): create a new empty temp directory as `DSH_HOME` → run `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-<pkg>` per each plugin's fail-loud prompt (this session's six add calls exited 1 on their install step for missing registry auth, but the plugin rows and profile config landed and the probe resolved every plugin from source; the successor records actual behavior on first run) → `pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write` then `--phase verify`, expecting double 0 → afterwards delete only that temp root. **Never whole-tree delete existing sessions/storages/vault inside a shared home.**

## In-flight chain (the only one at handoff time, evidence verified)

| Item | Value (verified) |
| --- | --- |
| Task | `p/fprecompute`: sourceFingerprint recompute engine (AT1-05 variant 5 src wave), design first+ruling request |
| Lead SessionID | `55979618-6bd7-4bc7-badc-8a3b13079158` (L-Foundation; its parent = controller session `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d`) |
| Worker SessionID | `00e07e03-f59a-49ca-84d6-018655769a55` (one-shot subagent, label "Build fingerprint recompute engine") |
| Parent chain | Worker `00e07e03…` → L-Foundation `55979618…` → controller `session-724834c2…` |
| cwd / worktree / branch | `D:\dsh-devframe-p-foundation` (the workspace declared in the worker's brief), branch `p/fprecompute`, base `526e773b23` |
| Provider / model | **huoshan-2 / glm-5.3-flash** (verified: `modelSelection.lastUsed` in `C:\Users\25313\.dsh\storages\session_projcache\sessions\00e07e03-f59a-49ca-84d6-018655769a55.json`) |
| Artifact state (same JSON todos) | Design doc / engine module / test spec written to disk; gates (package vitest+tsc+build+jsdoc) in progress; three commits+final report pending |
| Recovery point | If the lead's session breaks: resume from the worktree file state and that JSON todos, never redo what is already on disk |
| Acceptance gates | Package vitest+package tsc+`pnpm run build`+verify-export-jsdoc+`git diff --cached --check`+normal commit (repository hooks run) |
| Ruling request | Engine inside the StartGoalRequest binding flow or a standalone verify surface — until the outgoing controller rules, only the compute engine and cases land; the comparison face stays untouched |

## Successor first-batch dispatches (checked against current state, no padding)

Same-owner does not imply serial: judge by concrete file/interface conflict; a same-owner lead may split workers by file domain with dependent wiring landing last.

| Task | Lead | File domain | Dependency | Acceptance | Conflict handling |
| --- | --- | --- | --- | --- | --- |
| P05 follow-ups (required-checks model+comparison-face wiring) | L-Foundation | `devframe/src` (config schema and resolveResultBinding neighborhood), `agent-evidence` (comparison) | fprecompute closure; ruling request approved before wiring | package vitest+tsc+build+jsdoc | design and test prep run parallel to fprecompute (different files); events/schemas wiring lands serially last |
| Windows snapshot platform issue (the only 88F B-family root) | L-Foundation (patch lines)+L-Verify (delta verification) | `base/cordis.patch.yml` L252-254, minimal preset L36-38, snapshot corpus expectation face | platform-parameterization technical ruling (authorized): scenario-level platform expectation config fields, anti-hardcoded-tunables rule | test:snapshot lib-mode delta (A/C families stay 0, B family closes)+dump | patch lines belong to L-Foundation, corpus expectations to L-Verify — different file domains |
| Shadow/Memory local config integration | L-Integration | local (non-shared) profile instance config+writeEnabled/role allowlist local instances | none (the integration file domain is that lead's alone and currently idle) | dump-config+dual-phase probe (fresh temp root)+build | no file overlap with AT4/three-level prep; parallel |
| AT4 fault recovery (AT4-02/03/06 process-injection journeys) | L-Foundation second worker | `packages/experimental/agent-reliability/tests/` (separate file domain) | no model dependency (real process trees); dsh-ci-test-reliability isolation rules enforced | package vitest+tsc+build | different package from P05 (devframe/evidence), zero conflict |
| Real three-level task acceptance preparation | L-Verify | three-level task briefs+acceptance scaffolding (the parts not needing DEEPSEEK_API_KEY) | none; a missing key auto-blocks only the real-run segment | scaffolding offline segments green+brief review | separate profile/e2e file domains from L-Integration's local integration task, or serialize |

## Handoff gate

1. The in-flight chain delivers → the outgoing controller personally verifies (real commits/artifacts/gates/session JSON) → merges to main → updates the final SHA and acceptance result in the "In-flight chain" section above.
2. The outgoing controller stops all new dispatches and merges (registry gets its final entry) and pauses the automatic goal.
3. The successor is created by **external coordination**: an independent top-level Session+independent worktree; the outgoing controller never creates it as a child agent and never edits parent-child records.
4. The successor checks: main HEAD, the registry's last entry, and this doc's four-state/in-flight/first-batch sections — once they agree, the successor holds sole control.
5. When old child-chain results cannot be received safely across sessions: the outgoing controller closes out first, then hands over, without blocking workers; the successor never rebuilds, interrupts, or re-dispatches in-flight chains.
6. The user's uncommitted items and stash stay untouched throughout; no push, no PR, no publish, no deletion of user files.

## Preserved rules (mandatory for the successor)

Three-layer topology (controller→lead→worker; a worker never creates agents); leads and the controller keep independent worktrees; the controller alone merges to main; no idle spinning; SessionID/Agent/Worktree/task/result persistence; lanes and providers labeled only from persisted JSON (two provider names do not imply two independent quotas); no silent routing, no blind retries of uncertain calls (a single same-command retry covers only transient failures and is disclosed).

## Dev Note

This doc is the second edition of the 2026-09-06 handoff snapshot, expiring scratch under docs/working; the successor updates the in-flight section after closing the chain and archives once the new controller is stable. Every Provider/SessionID here is verified against persisted records; new fields follow the same verification discipline.
