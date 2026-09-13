# Environment troubleshooting

English | [中文](env.zh.md)

## Summary

This reference explains the Windows conditions that affect Codex Desktop worktree creation in this repository. Codex creates a detached Git worktree and then searches the source checkout for untracked ignored `AGENTS.override.md` files. Large ignored dependency and build trees can make that search slow, emit tens of megabytes of stderr, and fail before the task receives its ID. The recovery path checks Git ownership, prunes only stale worktree metadata, temporarily holds ignored trees outside the checkout, and verifies worktree-service registration before restoration.

## Table of Contents

- [Check Git repository ownership](#check-git-repository-ownership)
- [Inspect stale worktrees](#inspect-stale-worktrees)
- [Reduce ignored-tree discovery cost](#reduce-ignored-tree-discovery-cost)
- [Verify Codex registration](#verify-codex-registration)
- [Restore held directories](#restore-held-directories)
- [Further Exploration](#further-exploration)
- [Dev Note](#dev-note)

-----

<a id="check-git-repository-ownership"></a>
## Check Git repository ownership

Run this check when Git reports `detected dubious ownership`. The command adds a `safe.directory` entry only for the DSH checkout and then verifies the repository status.

```powershell
$repo = 'D:\dsh-devframe'
$repoForGit = 'D:/dsh-devframe'
$safe = @(git config --global --get-all safe.directory 2>$null)
if ($safe -notcontains $repoForGit) {
  git config --global --add safe.directory $repoForGit
}
git -c safe.directory=$repoForGit -C $repo status --short --branch
```

The status output should contain the current branch, such as `## main`. This path-specific trust entry fixes Git ownership checks; it does not reduce the ignored-file discovery scan.

-----

<a id="inspect-stale-worktrees"></a>
## Inspect stale worktrees

Stale Git worktree metadata can block a new allocation even when its directory no longer exists. Inspect registered paths and preview pruning before removing only records for missing worktrees.

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree list --porcelain
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree prune --dry-run
```

Review every path from the dry run before executing the cleanup:

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree prune --verbose
```

Do not prune a path that still contains a task's live worktree. Pruning removes stale Git administration records; it does not recover source changes.

-----

<a id="reduce-ignored-tree-discovery-cost"></a>
## Reduce ignored-tree discovery cost

After checkout, Codex runs the following Git operation to locate ignored `AGENTS.override.md` files:

```powershell
git -c safe.bareRepository=explicit -c core.hooksPath=NUL -c core.fsmonitor= ls-files --others --ignored --exclude-standard -z -- ':(glob)**/AGENTS.override.md'
```

In this repository, package-level `node_modules` and `lib` directories made the operation traverse hundreds of ignored directories. The setup panel can then show this failure signature:

```text
[stderr] git ls-files failed while locating AGENTS.override.md
```

### Recovery

Save tracked and untracked source changes before moving ignored trees. The stash does not include ignored files, so keep the external hold directory as a separate recovery point.

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe stash push --include-untracked -m "devframe recovery snapshot 2026-09-04"
```

Move the root and nested ignored dependency, build, cache, and coverage directories to a hold directory outside `D:\dsh-devframe`. Preserve each directory's relative path so the trees can be restored without merging their contents, and never move `.git`.

The recovery used these hold locations:

```text
D:\dsh-devframe-ignored-hold-20260904
D:\dsh-devframe.node_modules.codex-hold-20260904
D:\dsh-devframe.pnpm-store.codex-hold-20260904
D:\dsh-devframe.coverage.codex-hold-20260904
```

The nested hold contained 526 selected ignored directories. That number is an observation for this checkout, not a threshold. Moving these directories makes worktree setup fast, but it also removes dependencies and build output from the source checkout until restoration.

-----

<a id="verify-codex-registration"></a>
## Verify Codex registration

Create one task at a time and wait for the worktree service to finish registration before starting the next task. A Git entry confirms checkout, while the Codex log markers `ready` and `owner-thread-set ownerThreadId=...` confirm that the task owns the worktree.

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree list --porcelain
```

Each successful task adds a detached worktree under `C:\Users\25313\.codex\worktrees\...\dsh-devframe`. Use the final `ownerThreadId` as the task ID for follow-up coordination; the `clientThreadId` returned while creation is pending is provisional. The Codex sidebar can refresh after the worktree service has already completed, so verify the log or read the task by its final ID.

-----

<a id="restore-held-directories"></a>
## Restore held directories

Restore the held directories only after every task has an `owner-thread-set` record and no worktree setup scan is running. Check that each destination is absent, reverse the preserved relative paths for nested directories, and restore the root holds to `node_modules`, `.pnpm-store`, and `coverage` before running `pnpm` or a build.

Keep the recovery stash until every worktree has confirmed the expected source snapshot. Do not delete a hold directory as a substitute for restoration; the hold contains ignored files that Git cannot recover.

-----

<a id="further-exploration"></a>
## Further Exploration

- [Development guide](development.md) — repository prerequisites, daily commands, and build expectations.
- [Root instructions](../AGENTS.md) — repository-wide Git, worktree, and verification rules.
- [Bilingual documentation](i18n/README.md) — pairing files and the translation consistency check.
- [OpenAI Windows troubleshooting](https://help.openai.com/en/articles/11369540) — official Codex diagnostics guidance.

-----

<a id="dev-note"></a>
## Dev Note

None.
