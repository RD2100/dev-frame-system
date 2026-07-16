# Git Rules -- RD2100 Agent Runtime v2

> Domain: git safety
> Phase 0-5: P0/P1 active; P2-P4 within approved task scope

---

## RULE git-001: No Force Push to Main/Master

- **Priority**: P0 (Hard Stop)
- **Trigger**: `git push --force` or `git push -f` to main or master
- **Scope**: All phases
- **Rule**: Never force-push to the main/master branch. This is an irreversible destructive action that can destroy team work.
- **Verification**: If push is needed, verify target branch is not main/master before pushing.
- **Conflict Handling**: No exceptions. If force-push to main appears necessary, stop and escalate to human.

---

## RULE git-002: No Destructive Commands Without Approval

- **Priority**: P0 (Hard Stop)
- **Trigger**: `git reset`, `git clean`, `git restore`, `git checkout -- <path>`, `git stash`, `git branch -D`, or history-rewriting commands
- **Scope**: All phases
- **Rule**: Destructive git commands that discard or hide work require explicit human approval. State what would be lost or moved and why the operation is necessary. The automated logical-slice lifecycle must never use these commands to obtain a clean worktree.
- **Verification**: Git reflog shows no unapproved destructive operations.
- **Conflict Handling**: If a destructive command is in a batch plan, flag it, do not execute without separate confirmation.

---

## RULE git-003: No Skip Hooks

- **Priority**: P1 (Scope Control)
- **Trigger**: `git commit --no-verify`, `git push --no-verify`, `--no-gpg-sign`
- **Scope**: All phases
- **Rule**: Do not skip git hooks unless the user explicitly requests it. If a hook fails, investigate and fix the underlying issue rather than bypassing the hook.
- **Verification**: Git log shows no `--no-verify` flags without documented approval.
- **Conflict Handling**: If a hook is broken and blocking legitimate work, report the hook failure, get approval to bypass, and create a task to fix the hook.

---

## RULE git-004: Clean Commits

- **Priority**: P2 (Evidence)
- **Trigger**: Creating a commit
- **Scope**: All phases
- **Rule**: Each commit should be a logical unit of change. Do not mix unrelated changes in one commit. Do not commit secrets, large binaries, or generated files without explicit approval. Commit messages should explain why, not what.
- **Verification**: `git diff --stat` shows focused changes; `git log --oneline` messages are meaningful.
- **Conflict Handling**: If a change naturally spans multiple concerns, document in the commit body.

---

## RULE git-005: Never Amend Published Commits

- **Priority**: P1 (Scope Control)
- **Trigger**: `git commit --amend` on a commit that has been pushed
- **Scope**: All phases
- **Rule**: Never amend a commit that has been pushed to a shared branch. Amending published history causes divergence and lost work for teammates.
- **Verification**: Before amending, check `git status` and `git log --oneline origin/<branch>..HEAD`.
- **Conflict Handling**: If a published commit must be changed, use `git revert` (for undo) or create a new commit (for fixes).

---

## RULE git-006: Root-Accepted Local Commit Lifecycle

- **Priority**: P1 (Scope Control)
- **Trigger**: Any write-capable slice, staging attempt, or local commit
- **Scope**: All phases, all agents, including dirty worktrees
- **Rule**: A coding worker may edit, test, and return an ExecutionReport, but it must not stage files, create commits, or set `root_accepted`. Only the root coordinator may set `root_accepted`, after an independent reviewer passes the actual diff and all required evidence passes. Worker success, exit code, or self-report is never acceptance.
- **Required Lifecycle**: Preserve the captured baseline manifest and per-path hashes. For each `root_accepted` slice, the root coordinator stages only the accepted path set with path-specific commands, verifies `git diff --cached --name-only` and the cached content exactly match the accepted slice, then creates exactly one local logical commit before starting the next slice.
- **Rejected States**: Failed, blocked, rejected, unreviewed, or otherwise non-`root_accepted` slices must not be committed.
- **Dirty-Worktree Safety**: Do not use `git add -A`, `git add .`, `git commit -a`, broad restore or checkout, stash, reset, or clean as part of the slice lifecycle. Unrelated baseline paths and any pre-existing staged content must remain unchanged. A destructive recovery operation is outside this lifecycle and requires its own explicit human approval under git-002.
- **External-Effect Gate**: Push, pull request creation, merge, release, history rewrite, hook registration, and global Git or agent configuration require an explicit human gate. Force-push to `main` or `master` remains forbidden under git-001.
- **Verification**: The root acceptance record identifies the reviewer verdict, evidence, accepted paths, and baseline. The staged path set and cached diff match that record exactly, the resulting commit contains exactly those paths, and protected baseline hashes outside the slice are unchanged.
- **Conflict Handling**: On any mismatch, stop without committing, leave unrelated work untouched, and return the slice for review or human resolution. Do not repair the mismatch with broad Git state mutations.
