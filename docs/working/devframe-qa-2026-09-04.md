---
description: Cross-group QA evidence for the proposed DevFrame slice on 2026-09-04.
---

# DevFrame QA Evidence — 2026-09-04

English | [中文](devframe-qa-2026-09-04.zh.md)

## Decision

This worktree is `slice_green` for the tested native Team, Goal, and DevFrame paths, and is not `qa_accepted`, `main_integrated`, or `release_green`. The candidate still has build, package, event-directory, and shipped-profile snapshot blockers.

The report records evidence from one fixed worktree and does not authorize merging, pushing, publishing, or live-model spending. QA files may be committed locally after review; the parent recovery snapshot remains in `stash@{0}`.

## Evidence snapshot

| Field | Recorded value |
| --- | --- |
| Candidate worktree | `C:\Users\25313\.codex\worktrees\9af0\dsh-devframe` |
| Source baseline | Detached `HEAD` at `4e84901e6471b79ec0338099867ebb4606d12bb5` |
| Candidate input | Parent-provided `stash@{0}` applied without dropping the stash |
| Recorded time | 2026-09-04 16:09–16:17 (Asia/Tokyo) |
| Platform | Windows `win32`, Node `v24.19.0`, pnpm `11.19.0` |
| Storage and model | JSONL session persistence with keyless mock model behavior; no real API key or spend |
| Worktree mutation | Candidate implementation files remain unstaged; QA files are committed locally only; nothing is pushed or deployed |

The candidate input contains changes owned by the integration, permissions, Controller, Reliability, and profile/manifest groups. QA added only the composition regression, the paired handoff repair, this report, and its testing note.

## Executed regression

The focused candidate regression passed 15 test files and 102 tests, including the new [cross-group composition test](../../packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts). It mounts the real Context, JSONL persistence, Goal service, Team service, and Team tools, then checks a task/Goal binding, real dispatcher mutation, exact result identity, and persisted `goal/change` and `team/task` events.

```powershell
pnpm.cmd exec vitest run packages/experimental/devframe/tests packages/experimental/agent-team/tests packages/experimental/tool-agent-team/tests packages/experimental/agent-team-profile/tests
```

The existing [native Team and tool-Team regression](../../packages/experimental/agent-team/tests/team.spec.ts) and the new role, recovery, composition, and controller slices are included in that count. The test runner emitted only the existing `vite-tsconfig-paths` deprecation notice.

`pnpm.cmd run verify-scoped-events` passed and reported that `packages/core/scope/src/scoped-events.generated.ts` is up to date.

The snapshot infrastructure smoke command `pnpm.cmd exec vitest run --config vitest.snapshot.config.ts snapshots/session/headless.snapshot.ts -t "gives every composition and header class exactly one pin"` passed one corpus-structure test with 81 tests skipped. It validates the existing recorded-session corpus only; it is not DevFrame feature evidence.

## Acceptance mapping

The acceptance reference remains authoritative at [Tests and Acceptance](../testAndAcceptance.md). The following entries are partial evidence, not full `AT*` passes.

| Acceptance case | Evidence in this worktree | Result |
| --- | --- | --- |
| `AT1-01` / `R1.1` | [role-denial.spec.ts](../../packages/experimental/tool-agent-team/tests/role-denial.spec.ts) exercises the real dispatcher, inherited tool restrictions, a Team-local mutation, and a later allow listener. | Partial evidence; file/shell/workflow/Goal coverage and the full assembled profile are absent. |
| `AT1-02` / `R1.1` | [cold-role-recovery.spec.ts](../../packages/experimental/agent-team/tests/cold-role-recovery.spec.ts) persists a reviewer descriptor, disposes the child, cold-resumes it, and repeats the restricted tool probe. | Partial evidence; persisted role-policy restoration and missing-role denial are absent. |
| `AT1-09` / `R1.5` | [goal-binding.spec.ts](../../packages/experimental/devframe/tests/goal-binding.spec.ts) checks exact Goal A/B identity; the new composition test adds a real Team task and JSONL event path. | Partial evidence; consecutive native restart, budget consumption, and late-result delivery are absent. |
| `AT1-10` / `R1.6` | Goal-binding tests cover human authorization, create/disarm ordering, persistence failure, and explicit resume identity. | Partial evidence; the complete command journey and result/evidence view are absent. |
| `AT4-03` / `R4.2` | [stop.spec.ts](../../packages/experimental/devframe/tests/reliability/stop.spec.ts) exercises an owned child-process tree. | Partial evidence; project-level writer ownership and the full stop acceptance case remain unverified. |
| Remaining `AT*` cases | No reproducible implementation evidence is present in this worktree for the full filesystem, multi-project, memory, live-model, or version-recovery matrices. | `not_run` or `blocked`; no delivery claim. |

Per the acceptance reference, a partial subcase cannot promote a whole case to `passed`, and a blocked required case prevents the corresponding delivery claim.

## Snapshot decision

The repository's recorded-session snapshot lane starts through shipped `dsh` profiles. The existing `team-snapshot.patch.yml` enables native `agent-team` and `tool-agent-team`, but does not load the DevFrame package, role policy, or Goal-binding controller. No committed DevFrame snapshot scenario exists under `snapshots/`.

QA therefore did not create JSONL, prompt, schema, or protocol snapshot artifacts. Adding one requires profile, manifest, and overall assembly changes outside this group's scope; the current integration tests are the correct regression evidence until that shipped composition exists.

## Blocking checks

| Check | Result | Blocking fact |
| --- | --- | --- |
| `pnpm.cmd run test:docs` before this repair | Failed 2 of 15 gates | The Chinese-only handoff lacked its bilingual pair and had adjacent metadata lines parsed as one wrapped paragraph. |
| `pnpm.cmd run build:lib:host` | Failed | `packages/experimental/devframe/tests/reliability/stop.spec.ts:73,83,89,90` mocks omit required `SubprocessOutcome.exitCode`. |
| `pnpm.cmd run hygiene` | Failed 6 of 15 gates | The candidate DevFrame package `files` allowlist violates constraints; its README lacks the omitted-invariant reason; repository build outputs and `vendor/loader/lib/index.js` are absent; an existing ACP profile has invalid root metadata. |
| `pnpm.cmd run typecheck` | Failed before compilation | The repository script invokes `npm`, which is not available in this PowerShell command environment. |
| DevFrame feature snapshot | Not run | No shipped profile scenario loads the DevFrame package, so recording would change profile/manifest scope. |

The build and hygiene failures point to candidate or repository prerequisites owned outside QA; this group did not change those implementation, event, persistence, package, or profile files.

## Required follow-up

1. Fix the reliability test mock to provide the current `SubprocessOutcome` fields, then rerun `build:lib:host`.
1. Correct the DevFrame package `files` list and add the required README explanation for its omitted invariant companion.
1. Resolve the authoritative event-directory and cold-recovery role-restoration blockers, then add a shipped profile composition before recording a DevFrame session snapshot.
1. Produce the required peer build outputs, repair the ACP Loader metadata, and rerun the failed hygiene gates.
1. Rerun this exact QA command on the same candidate after those changes; update the acceptance table only with evidence from that run.

## Reviewer Index

- Changed QA test: `packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts`.
- Changed documentation: `docs/working/handoff-2026-09-03.md`, `docs/working/handoff-2026-09-03.zh.md`, this paired report, and the paired testing note at `.agents/notes/proposed/testing/2026-09-04-devframe-cross-group-qa-evidence.md`.
- Critical paths reviewed: Team task tool dispatch, native Goal create/disarm/resume, JSONL event inspection, role-denial recovery, and owned-process stopping.
- Generated artifacts: no committed snapshot JSONL, prompt, schema, protocol, or build output was added.
- Review focus: keep the partial statuses, blocker ownership, exact test scope, and no-snapshot decision intact when other groups repair the candidate.

## Dev Note

This is a working evidence report for the detached candidate at the recorded baseline and is not an acceptance approval. The existing candidate changes remain unstaged and are not claimed as QA-owned implementation.
