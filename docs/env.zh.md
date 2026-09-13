# 环境排障

[English](env.md) | 中文

## 概述

本文说明影响本仓库 Windows 环境中 Codex Desktop 创建 worktree 的条件。Codex 会先创建 detached Git worktree，然后在源检出目录中搜索未跟踪且被忽略的 `AGENTS.override.md` 文件。大量被忽略的依赖和构建目录会使搜索变慢，产生数十 MB 的 stderr，并在任务获得 ID 之前失败。恢复路径包括检查 Git 所有权、只清理陈旧的 worktree 元数据、把被忽略的目录暂时放到检出目录之外，并在恢复目录前确认 worktree 服务已完成登记。

## 目录

- [检查 Git 仓库所有权](#check-git-repository-ownership)
- [检查陈旧的 worktree](#inspect-stale-worktrees)
- [降低被忽略目录的发现成本](#reduce-ignored-tree-discovery-cost)
- [确认 Codex 登记完成](#verify-codex-registration)
- [恢复暂存目录](#restore-held-directories)
- [进一步阅读](#further-exploration)
- [开发注记](#dev-note)

-----

<a id="check-git-repository-ownership"></a>
## 检查 Git 仓库所有权

当 Git 报告 `detected dubious ownership` 时运行此检查。该命令只为 DSH 检出目录添加 `safe.directory` 条目，然后确认仓库状态。

```powershell
$repo = 'D:\dsh-devframe'
$repoForGit = 'D:/dsh-devframe'
$safe = @(git config --global --get-all safe.directory 2>$null)
if ($safe -notcontains $repoForGit) {
  git config --global --add safe.directory $repoForGit
}
git -c safe.directory=$repoForGit -C $repo status --short --branch
```

状态输出应包含当前分支，例如 `## main`。这个按路径设置的信任条目可以修复 Git 所有权检查，但不会降低被忽略文件发现扫描的成本。

-----

<a id="inspect-stale-worktrees"></a>
## 检查陈旧的 worktree

即使目录已经不存在，陈旧的 Git worktree 元数据也可能阻止新的分配。先检查已登记的路径并预览清理结果，再只删除缺失 worktree 的记录。

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree list --porcelain
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree prune --dry-run
```

执行清理前检查预览中的每一条路径：

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree prune --verbose
```

不要清理仍包含任务活动 worktree 的路径。清理只会删除陈旧的 Git 管理记录，不会恢复源码改动。

-----

<a id="reduce-ignored-tree-discovery-cost"></a>
## 降低被忽略目录的发现成本

检出完成后，Codex 会运行下面的 Git 操作来查找被忽略的 `AGENTS.override.md` 文件：

```powershell
git -c safe.bareRepository=explicit -c core.hooksPath=NUL -c core.fsmonitor= ls-files --others --ignored --exclude-standard -z -- ':(glob)**/AGENTS.override.md'
```

在本仓库中，各包的 `node_modules` 和 `lib` 目录使该操作遍历了数百个被忽略的目录。设置面板随后可能显示下面的失败特征：

```text
[stderr] git ls-files failed while locating AGENTS.override.md
```

### 恢复

移动被忽略的目录前，先保存已跟踪和未跟踪的源码改动。stash 不包含被忽略的文件，因此还要单独保留检出目录外的暂存目录。

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe stash push --include-untracked -m "devframe recovery snapshot 2026-09-04"
```

把根目录和嵌套的依赖、构建、缓存及 coverage 被忽略目录移动到 `D:\dsh-devframe` 之外的暂存目录。保留每个目录的相对路径，以便恢复时直接还原目录，不合并其内容；绝不要移动 `.git`。

本次恢复使用了以下暂存位置：

```text
D:\dsh-devframe-ignored-hold-20260904
D:\dsh-devframe.node_modules.codex-hold-20260904
D:\dsh-devframe.pnpm-store.codex-hold-20260904
D:\dsh-devframe.coverage.codex-hold-20260904
```

嵌套暂存目录共包含 526 个选中的被忽略目录。这个数字是本次检出的观测值，不是阈值。移动这些目录会加快 worktree 设置，但在恢复前也会使源检出目录暂时缺少依赖和构建产物。

-----

<a id="verify-codex-registration"></a>
## 确认 Codex 登记完成

一次只创建一个任务，并等待 worktree 服务完成登记后再创建下一个任务。Git 条目只能确认检出完成；Codex 日志中的 `ready` 和 `owner-thread-set ownerThreadId=...` 标记才确认任务已经拥有该 worktree。

```powershell
git -c safe.directory=D:/dsh-devframe -C D:/dsh-devframe worktree list --porcelain
```

每个成功任务都会在 `C:\Users\25313\.codex\worktrees\...\dsh-devframe` 下增加一个 detached worktree。后续协调使用最终的 `ownerThreadId` 作为任务 ID；创建仍在等待时返回的 `clientThreadId` 只是临时 ID。Codex 侧边栏可能晚于 worktree 服务刷新，因此应以日志或最终 ID 读取任务为准。

-----

<a id="restore-held-directories"></a>
## 恢复暂存目录

只有在每个任务都有 `owner-thread-set` 记录且没有 worktree 设置扫描运行时，才能恢复暂存目录。确认每个目标路径不存在，再按保留的相对路径反向恢复嵌套目录，并把根目录暂存恢复为 `node_modules`、`.pnpm-store` 和 `coverage`，然后再运行 `pnpm` 或构建。

在每个 worktree 确认预期源码快照前，保留恢复 stash。不要用删除暂存目录代替恢复；暂存目录包含 Git 无法恢复的被忽略文件。

-----

<a id="further-exploration"></a>
## 进一步阅读

- [开发指南](development.zh.md) — 仓库前置条件、日常命令和构建要求。
- [根目录说明](../AGENTS.md) — 仓库范围的 Git、worktree 和验证规则。
- [双语文档](i18n/README.zh.md) — 配对文件和翻译一致性检查。
- [OpenAI Windows 排障](https://help.openai.com/en/articles/11369540) — Codex 官方诊断说明。

-----

<a id="dev-note"></a>
## 开发注记

None.
