# Agent Note: DevFrame cross-group QA evidence boundaries

Status: proposed

English | [中文](2026-09-04-devframe-cross-group-qa-evidence.zh.md)

## Problem

The DevFrame candidate combines native Team, Goal, session persistence, role policy, and process-stop work from several groups. Local tests can pass while the fixed profile, generated event directory, build outputs, or session snapshot path remains unavailable.

## Proposal

Record QA evidence against one fixed candidate with exact commands, storage mode, model authority, acceptance IDs, and known blockers. Use real Context, JSONL persistence, native Goal, Team tools, and owned subprocesses for cross-group regression. Treat partial acceptance subcases as partial evidence and keep the full case incomplete until every required path has run on the same candidate.

Do not add recorded-session fixtures until a shipped `dsh` profile loads the DevFrame package and the snapshot harness can reconstruct its model-visible inputs. Keep profile, manifest, event-directory, persistence, and runtime implementation fixes with their owning groups.

## Alternatives considered

**Treat focused green tests as acceptance.** This would hide missing cold recovery, profile, event-directory, and delivery evidence behind a passing helper or local composition. The report keeps `slice_green` separate from `qa_accepted`.

**Record a feature snapshot through a temporary profile patch.** This would create artifacts that do not represent a shipped application entrypoint and would expand QA into profile and assembly ownership. The snapshot decision stays deferred until a shipped composition exists.

**Repair every blocker from the QA worktree.** This would overwrite other groups' implementation and persistence decisions and make the evidence object unclear. The report names exact owners and leaves those files untouched.

## Acceptance criteria

The fixed candidate has a reproducible focused regression command, a bilingual evidence report, a reviewer index, and a clear mapping from each partial result to the authoritative acceptance case. The report names all failed or unavailable prerequisites and makes no full delivery or release claim.

## Risks

The focused tests use mock model behavior and disposable storage, so they do not prove provider usefulness, multi-project isolation, live-model behavior, or every restart path. A green snapshot infrastructure smoke only proves the existing corpus structure. Profile, event, persistence, build, and package blockers remain release-relevant until their owning groups close them and QA reruns the fixed candidate.
