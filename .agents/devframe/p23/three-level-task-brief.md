# 真实三级任务 brief

> **新交付物**（p23 四件套之一；配套 journey-manifest.json / run-offline-acceptance.ps1 / offline-acceptance-evidence.md）。
>
> **锚点取证（实测）**——在 worktree `D:\dsh-devframe-p-3level`、分支 `p/3level`、提交 `fc34223e28bd017339eb3a48164c88321433d630`、工作树干净（`git status --porcelain` 0 行）、p23 四文件尚未落盘时执行：
>
> | 命令 | 实测命中 | 退出码 | 命中文件 |
> |---|---|---|---|
> | `git grep -l "三级任务"` | **1** | 0 | docs/working/dsh-controller-v1.2-handoff-2026-09-06.zh.md |
> | `git grep -li "three-level"` | **4** | 0 | .agents/notes/implemented/simplification/2026-07-29-shared-base-config-overlays.md；docs/working/dsh-controller-v1.2-handoff-2026-09-06.md；packages/client/ui-directory-picker-browse/tests/directory-browser.client.spec.tsx；packages/session/session-telemetry-otel/src/index.ts |
>
> **与派单预期的偏差（fail-loud，不虚构）**：派单方预期"两条 grep 零命中"，实测在基线 `fc34223e28` 上非零命中（1 与 4）。本 brief 不改写实测值；该偏差已列入缺口清单，交组长/总控复核。`git grep` 命中时退出码为 0，未命中时为 1——退出码一律如实记录。
>
> **基线**：`fc34223e28`（分支 `p/3level`，已用 `git rev-parse HEAD` 核验）。建树后执行 `pnpm install --frozen-lockfile`（本任务树依赖已装好，不改锁文件）。

本 brief 描述"总控→组长→Worker"三层链路的一次真实三级任务旅程，及其离线验收脚手架（manifest + runner + 证据文档）。

## 旅程五段

每段字段：执行者 / 输入 / 动作 / 证据要求（命令+退出码+文件路径）/ 持久化点（SessionID、Worktree 路径、分支、提交 SHA、门禁计数，写明落账本 registry 还是证据文档）。

### ①派单（总控→组长）

- 执行者：总控（派单方）→ 组长（接单方）。
- 输入：任务目标、钉死的基线 SHA、worktree/分支规划、文件域。
- 动作：总控创建独立 worktree 与分支（基线钉死 `fc34223e28`），向组长下发任务书；任务书必须含 worktree 路径、分支名、基线 SHA、文件域、禁触清单、验收标准。
- 证据要求：任务书文件路径；`git rev-parse HEAD`（预期退出码 0，输出等于基线 `fc34223e28`）；锚点 grep 命令原文+退出码+命中计数记入派单记录文件。
- 持久化点：SessionID、Worktree 路径、分支 → **落账本（registry）**；commitSha 此段记基线 SHA（尚无新提交）→ **落账本**；门禁计数与锚点计数 → **落证据文档**。

### ②Worker 执行

- 执行者：Worker（三层最末级，**不得创建任何 Agent**）。
- 输入：组长转发的任务书（含文件域、禁触清单、验收标准）。
- 动作：只在 worktree 分支新增授权文件；不碰禁触清单与主树；跑自查证据命令。
- 证据要求：自查命令原文+退出码（本任务：两条锚点 `git grep` 的实测命中与退出码、`run-offline-acceptance.ps1` 退出码 0），连同时间戳写入证据文档 `.agents/devframe/p23/offline-acceptance-evidence.md`。
- 持久化点：SessionID、Worktree 路径、分支 → **落账本**；提交 SHA、门禁计数 → **账本+证据文档双落**。

### ③组长验收

- 执行者：组长（亲验，不转包、不创建 Agent）。
- 输入：Worker 结算（变更文件清单、提交 SHA、证据命令与退出码）。
- 动作：复跑关键命令（两条锚点 grep、runner）；`git show --stat <SHA>` 核对变更文件清单与提交 SHA；与 Worker 结算不一致即打回。
- 证据要求：复跑命令原文+退出码逐条记录；核对结论与变更文件清单写入验收记录文件。
- 持久化点：验收 SessionID、Worktree 路径、分支 → **落账本**；提交 SHA、门禁计数核对值 → **账本+证据文档双落**。

### ④总控合并

- 执行者：总控（**唯一有权合并主树的角色**）。
- 输入：组长验收通过记录（含分支名与提交 SHA）。
- 动作：合并前核对分支基线仍为 `fc34223e28`（`git merge-base` / `git log` 核对）与门禁计数；把 worktree 分支合入主树；不 push、不开 PR。
- 证据要求：基线核对命令原文+退出码；合并提交 SHA；核对结论写入合并记录文件。
- 持久化点：合并 SessionID、主树路径、主树分支 → **落账本**；合并提交 SHA、门禁计数 → **账本+证据文档双落**。

### ⑤账本登记

- 执行者：总控登记（或组长代登、总控复核）。
- 输入：①—④段全部持久化字段与缺口清单。
- 动作：写 registry 条目：日期 / 链路 / SessionID / worktree / 分支 / 提交 SHA / 门禁计数 / 缺口。
- 证据要求：registry 文件路径；逐字段核对条目齐全，缺什么如实记"缺口"，不虚构。
- 持久化点：本段即**落账本（registry 条目本身）**；登记自查命令与退出码 → **落证据文档**。

## 铁律

1. Worker 无子 Agent：任何 Worker 不得创建任何 Agent（subagent、子会话、嵌套派发均禁）。
2. 只有总控合并主树；组长与 Worker 只在 worktree 分支提交。
3. 禁 push、禁 PR、禁发布。
4. 基线钉死（`fc34223e28`）+ 冻结安装（`pnpm install --frozen-lockfile`，不改锁文件）。
5. 禁触：用户未提交改动、`stash@{0}`、跨域目录；主树 `D:\dsh-devframe` 只读。
6. fail-loud：429 限额按退避处理不盲重试；缺口不虚构（缺什么报什么，如锚点零命中预期不成立即照实记录）；退出码如实记录（含 git grep 未命中时的退出码 1）。

## 真实模型运行段

**缺 DEEPSEEK_API_KEY 阻塞该段**。本应执行 `pnpm dsh --profile headless "真实任务"` 走三层派发（总控→组长→Worker 真实链路），并留 SessionID/退出码证据；无 key 不跑、不虚构结果。离线验收段（manifest + runner + 证据文档）不受该阻塞影响，照常执行并留证。
