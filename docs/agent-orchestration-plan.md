---
description: Controller-owned orchestration plan, feature registry, and agent registry for the DevFrame single-project pilot.
---

# DevFrame Agent Orchestration Plan

English | [中文](agent-orchestration-plan.zh.md)

## Summary

DSH-Project-Controller is the single controller session for this development round: it plans, creates, dispatches, supervises, and integrates every agent. Its host-generated session id is `session-9f2fb633-25a9-4464-8c9b-c257b0c1ab4f`, read from `DSH_SESSION_ID`. Only the controller creates agents, merges feature branches into `main`, and updates this registry; feature owners and their sub-agents report to the controller, and cross-feature interface questions route through it.

User decisions recorded on 2026-09-05: delivery follows the "Controlled single-project pilot" row of the [acceptance delivery table](testAndAcceptance.md#delivery), split into features F01–F07 below; every feature owns a dedicated git worktree, with all seven created up front and their owners activated on a staggered schedule of at most two concurrent owners (the model provider's account-level request-rate limit prevents seven concurrent turns; evidence in the change log). [Shadow routing](detailDesign-part2.md) and [Obsidian memory](detailDesign-part3.md) stay deferred candidate extensions. This round pushes nothing, deploys nothing, and uses no credentials.

## Current state assessment

The previous parallel round (G1–G5, registry in [.agents/devframe-groups.md](../.agents/devframe-groups.md)) landed infrastructure: the SessionID row menu, the worktree registry seam, goal completion receipts, a goal-round-driver teardown fix, and the composition-smoke package. All groups merged and closed out at commit `94820fbabc` on `main`.

| Focus area | State | Gap owned by this round |
| --- | --- | --- |
| SessionID / session persistence | Done (G1 plus the native log) | Receipt presentation leftovers fold into F02 |
| Agent creation / recovery / sub-agents | Base done (subagent capability, spike evidence) | Cold-resume role guard installation — F01 |
| Agent Team | Partial (experimental roster, board, mailbox) | Role policy for controller/worker/reviewer — F01, F05 |
| Worktree productization | Partial (G2 registry seam) | Model-facing tool consumer and prune reconciliation — F06 |
| Plugin mechanism | Done (Cordis profiles and bundles) | Final DevFrame profile assembly — F05 |
| Project-level controller | Not started (library contracts only in `dsh-experimental-devframe`) | Project tools, `/project` journey, admission, completion — F02, F03 |
| Shadow | Designed only | Deferred by the design gate; not in this round |
| Task status / logs / events | Partial (contracts exist in the devframe package) | Projection wiring and status presentation — F02, F05 |
| Tests / docs / release | Infrastructure done | Bind every selected AT case to a real test — F07 |
| Windows compatibility | Constraints recorded | Real process-tree stop and recovery acceptance — F04 |

## Feature registry

Behavioral detail lives in the design references linked per feature; this section owns scope boundaries, inputs and outputs, dependencies, and acceptance anchors. All seven features develop in parallel in separate worktrees; dependencies below mark integration order, not start order.

| ID | Feature | Scope (repository paths) | Depends on | Acceptance anchors |
| --- | --- | --- | --- | --- |
| F01 | Role policy and permission enforcement | `packages/experimental/devframe/src/permissions/**`, `packages/experimental/devframe/tests/permissions.spec.ts` | — | [AT1-01, AT1-02](testAndAcceptance.md#part1) |
| F02 | Project tools and evidence chain | `packages/experimental/devframe/src/controller/**`, new `src/project/**`, `src/events.ts`, `src/projection.ts`, `src/session-journal.ts`, matching tests; additive receipt reference in `packages/goal` | F01 | [AT1-03–AT1-06](testAndAcceptance.md#part1) |
| F03 | `/project` human command journey | New `devframe/src/commands/**` and tests (planned) | F01, F02, F04 | [AT1-10](testAndAcceptance.md#part1) |
| F04 | Reliability early subset | `packages/experimental/devframe/src/reliability/**`, `packages/experimental/devframe/tests/reliability/**` | F01, F02 (integration only; library work starts immediately) | [AT4-01–AT4-05, AT4-06 deadline, AT4-07 flush](testAndAcceptance.md#part4) |
| F05 | Profile assembly and status presentation | DevFrame template rows in `packages/boot/app-boot/src/profile.ts`, `apps/cli/src/profile-boot.ts`, experimental client team status surface | F01–F03 (scaffolding starts immediately) | [AT1-07, AT1-08](testAndAcceptance.md#part1) |
| F06 | Worktree tool consumer and prune reconciliation | `packages/workflow/worktree-registry/**` plus the consumer package it adds | — | Real git subprocess tests; `verify-cordis-catalog` |
| F07 | Integration, acceptance wiring, and docs | `packages/test-support/composition-smoke/**`, `docs/**`, `.agents/devframe/**`; never this file | All | Every selected AT id bound to a real test; `test:docs` green |

### F01 — Role policy and permission enforcement

Implements `R1.1` of the [single-project design](detailDesign-part1.md#roles). Input: the host-owned role enum (controller, worker, reviewer) and the persisted role and policy event contract in `src/permissions/events.ts`. Output: a role-policy lookup plus a `tools.guard()` installer that restores roles from persistence on cold resume and denies unknown identities, missing policy, and model-supplied roles before any dispatched tool executes, including scope-local Team tools; a later pre-execute allow cannot override a guard denial. `tools.restrict()` limits inherited tool faces per role. Non-goals: no agent-loop changes, no project tools, no UI, no commands. Adds a `SessionEventMap` member only if persistence requires it; the TypeScript and Python SDK projection duty then applies in the same change.

### F02 — Project tools and evidence chain

Implements `R1.2` and `R1.3`. Input: F01 role admission, native goal receipts (G3), the approved check definitions, and source snapshots that fingerprint tracked and untracked input bytes. Output: the session-scoped `project_verify`, `project_review`, and `project_complete` tools with their `goalId` and `acceptanceHash` binding validation, `verificationId` and `snapshotId` evidence records, and compare-and-set completion against the current `GoalRef`; the G3 leftover receipt reference from a devframe goal binding is additive work in `packages/goal`. Data: plugin-owned persisted event records replayable before admission; no separate acceptance database. Non-goals: no `/project` commands, no budgets, no profile assembly.

### F03 — `/project` human command journey

Implements `R1.6`. Input: the F02 tool services, the F04 stop and resume semantics, and the native Goal creation order — close admission, create and synchronously disarm the Goal, persist the approved work binding and budget, then explicitly resume under the same human start authorization. Output: the human-only `/project configure`, `confirm`, `start`, `stop`, `resume`, `result`, and `abandon` command adapters with preview validation, stale-preview rejection, and quiescence requirements. Non-goals: no modal UI, no new desktop application, no model-mediated approval; raw `/goal` mutation commands stay omitted from the composed profile.

### F04 — Reliability early subset

Implements the early [reliability](detailDesign-part4.md) subset named by the delivery table. Input: the existing `stopProject` library, the native jobs, subprocess, and timeout seams, and `agent/pre-step` admission. Output: writer-ownership lease and admission cutoff wiring, pre-step admission checks that reject closed or mismatched work bindings while delegating admissible work, and budget accounting for attempts, concurrency, and the wall-clock deadline as validated Cordis plugin config. Non-goals: no distributed locking, no full AT4-06–AT4-08 matrix, no hostile-code isolation. Library-level work starts immediately; integration with F01 and F02 lands after those features merge.

### F05 — Profile assembly and status presentation

Implements `R1.4`. Input: the F01–F03 surfaces, native presets, and the experimental team profile as composition reference. Output: the DevFrame profile template with role-restricted child composition, omitted raw Goal mutation commands, and the required user presentation of task, role, check and review status, and blocking reason in the existing UI. Non-goals: no large UI rework beyond documented extension points. Scaffolding starts immediately; final composition lands after F01–F03 merge.

### F06 — Worktree tool consumer and prune reconciliation

Productizes the G2 registry seam. Input: `ctx.worktreeRegistry`, branded `WorktreeId`, and the design slot left by the G2 proposed note. Output: a model-facing worktree tool consumer with guarded create, list, status, and remove operations, plus prune reconciliation between registered worktrees and git state. Non-goals: it does not take over controller orchestration, which uses plain git worktrees; no second session-identity system. Fully parallel; no dependency on F01–F05.

### F07 — Integration, acceptance wiring, and docs

Cross-cutting close-out. Input: every feature's delivered surfaces and the [acceptance checklist](../.agents/devframe/acceptance-checklist.md). Output: composition-smoke cases for the new surfaces, an `AT*`-id-to-real-test binding record, bilingual documentation sync, and the final integration report. Non-goals: implements no feature behavior; never edits this file, which the controller owns.

## Agent hierarchy and registry

The controller session owns one level of feature owners; sub-agents (implementation, test, docs, review) are created by the controller on an owner's request and report to the controller. No agent other than the controller creates agents, and no agent contacts another agent directly.

Identifier policy: `agentId` values are the durable ids returned by the host subagent tool; `SessionID` values are host-generated only. The controller session id in the summary is read from `DSH_SESSION_ID`. The subagent tool does not return a session id for children, so their `SessionID` column stays `unavailable` until the runtime exposes one; no value is invented. `WorktreeID` is the real git worktree path plus branch, created by the controller before the owner starts.

| Agent | agentId | SessionID | Worktree (branch) | Status | Last activity | Commits |
| --- | --- | --- | --- | --- | --- | --- |
| DSH-F01-RolePolicy-Owner | cbb87195-4eea-4eaf-aff3-438f55b7785f | unavailable | `D:\dsh-devframe-f01` (`feature/f01-role-policy`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F02-ProjectTools-Owner | eafba7de-c57a-4bb9-b652-e7dac528b960 | unavailable | `D:\dsh-devframe-f02` (`feature/f02-project-tools`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F03-ProjectCommands-Owner | 672d8085-e3bd-4a2f-ade5-36e0f6a399ea | unavailable | `D:\dsh-devframe-f03` (`feature/f03-project-commands`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F04-Reliability-Owner | 6a89b5ff-bf0c-487a-bde2-2c0846bf5742 | unavailable | `D:\dsh-devframe-f04` (`feature/f04-reliability`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F05-ProfileAssembly-Owner | f5e1ff2c-c0cc-49ee-81a5-8f939f8c53e4 | unavailable | `D:\dsh-devframe-f05` (`feature/f05-profile-assembly`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F06-WorktreeTool-Owner | b95b5bf6-63c3-4f5b-91a6-8a37fd25cff9 | unavailable | `D:\dsh-devframe-f06` (`feature/f06-worktree-tool`) | assigned | created and dispatched 2026-09-05 | — |
| DSH-F07-Integration-Owner | 571d0c3f-6497-479d-8e72-a52bc098811d | unavailable | `D:\dsh-devframe-f07` (`feature/f07-integration-qa`) | assigned | created and dispatched 2026-09-05 | — |

The live registry is the `main` copy of this file; worktree copies are point-in-time snapshots for owner onboarding.

## Status model and supervision

Each agent is in exactly one state: `planned`, `assigned`, `developing`, `reviewing`, `submitted`, `integrated`, `blocked`, or `failed`. Long idle is not a resting state. The controller checks each agent's last activity, current state, task, real identifiers, commits, test results, and blockers, and records the check in this file's change log.

When an agent stalls, the controller reads its last output and worktree, and classifies the outcome as committed and finished, failed, or abnormally stopped. A recoverable agent receives a recovery message naming the last safe position. An unrecoverable agent is replaced by a controller-created successor with new real identifiers that inherits the task, the commit history, and the context summary; completed code is never overwritten. An agent blocked by the same concrete condition for three consecutive controller rounds is recorded as `blocked` with that condition and a successor or a user decision is prepared.

## Development and merge order

Development: all seven worktrees and owners exist up front, but owner activation is staggered — at most two owners run at a time, in merge-order priority — because the model provider enforces an account-level request-rate limit that terminated seven concurrent turns (429 evidence in the change log). Shared files inside `packages/experimental/devframe` — `src/index.ts`, `src/shared/types.ts`, `package.json`, `README.md`, and tsconfig aggregates — accept additive-only edits from their owners; the controller resolves any conflict at merge.

Merge: the controller merges into `main` in the order F01 → F02 → F04 → F03 → F05 → F06, then closes out with F07. Each merge runs that feature's targeted commands from the table below, plus `pnpm run test:docs` whenever docs, READMEs, or `.agents/` content changed. The final close-out runs typecheck, build, composition-smoke, the targeted matrix, and records the integration report. Only the controller merges; owners never touch `main`.

| Feature | Targeted commands |
| --- | --- |
| F01 | `pnpm exec vitest run packages/experimental/devframe packages/experimental/agent-team packages/core/tools/tests/scoped.spec.ts` |
| F02 | `pnpm exec vitest run packages/experimental/devframe packages/goal` |
| F03 | `pnpm exec vitest run packages/experimental/devframe` |
| F04 | `pnpm exec vitest run packages/experimental/devframe packages/goal packages/guard packages/subagent` |
| F05 | `pnpm exec vitest run packages/experimental/devframe packages/test-support/composition-smoke`; `pnpm run test:docs` |
| F06 | `pnpm exec vitest run packages/workflow/worktree-registry`; `pnpm run verify-cordis-catalog`; `pnpm run test:docs` |
| F07 | `pnpm run test:docs`; `pnpm exec vitest run packages/test-support/composition-smoke` |

## Risks, blockers, and recovery

| Risk | Handling |
| --- | --- |
| Five owners share `packages/experimental/devframe` | Subdirectory partition per feature; additive-only shared files; controller resolves conflicts at merge |
| New `SessionEventMap` members (F02, F03) | TypeScript and Python SDK projections update in the same change; snapshot suites are CI signals and are recorded, not run locally |
| Documentation gates on new or updated docs | Bilingual triplet plus `pnpm run verify-translation-pairing --write` before commit |
| Known Windows red suites in full runs | Owners run targeted commands only; the full suite stays a CI signal with the recorded baseline (16238 passed, 10 known-red) |
| Disk usage of seven worktrees | Monitored by the controller; the prior round's `g1`–`g5` worktrees are recorded as safe to delete if space is needed |
| `pnpm install` overlap across worktrees | The store lock serializes installs; owners verify `node_modules` before running tests |
| Agent stalls or silent failure | Checkpoint, recovery message, or successor agent per the supervision section; three blocked rounds force `blocked` status |

## Environment constraints

Windows host with `pnpm`, `pwsh`, Node 24.19, and git 2.53 only; no npm, no bash. `pnpm run test:snapshot` and `pnpm run test:web` are CI signals with POSIX fixtures — never run, fix, or refreshed locally. The vitest Windows exclusion table applies automatically. Commits use `git commit --no-verify` after targeted manual gates, including `git diff --cached --check` and zero vendor staging. The untracked `docs/env.md`, `docs/env.zh.md`, and `docs/env.i18n.yaml` are user files and are never committed. `stash@{0}` and the prior `g1`–`g5` worktrees are preserved. Nothing is pushed to any remote without explicit user authorization.

## Registry change log

- 2026-09-05: plan written; F01–F07 registered as `planned`; worktrees and owners pending creation.
- 2026-09-05: plan committed as `2be4a074c2`; seven worktrees created at that commit; all seven owners created with host-returned agent ids and dispatched with full task assignments; dependency installs running in the background.
- 2026-09-05: F04–F07 stopped abnormally before any edit landed (worktrees verified clean at the baseline); the controller delivered recovery messages resuming each assignment; F01–F03 kept running; dependency installs completed for f01–f06 with f07 finishing.
- 2026-09-05: all seven owners stopped abnormally with no worktree edits, so no work was lost. Session-log evidence shows `429 AccountRateLimitExceeded` with retry exhaustion — the provider's account-level rate limit under seven concurrent turns. The controller amended execution to staggered activation of at most two owners at a time (F01 and F06 first); installs for all seven worktrees completed. Shell recursion into `node_modules` also pinned as forbidden (pnpm junction cycles); owners use scoped glob patterns or `git ls-files` instead.
