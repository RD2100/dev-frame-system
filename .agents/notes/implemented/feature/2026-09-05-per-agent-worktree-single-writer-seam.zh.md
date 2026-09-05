# Agent Note: 每 Agent 的 worktree 单一写入者绑定与 agent-worktree 消费方

Status: implemented

[English](2026-09-05-per-agent-worktree-single-writer-seam.md) | 中文

## 问题

worktree registry seam 及其面向工作区的工具把 worktree 当作共享基础设施：归属 workspace 的任何会话都能创建、观察、移除任何登记。插件化 Agent 层级对它自己的会话需要相反的承诺——恰好一个写入者拥有的任务检出——而三个缺口使共享面对这个用途不可用：

- 没有任何东西记录所有权。拿到同一个 worktree 的两个 Agent 会话都能写它，任何一方都能在另一方背后移除它。
- 移除与交接赛跑。完成任务 Issue 的会话在同伴仍需要 worktree 时就把它删掉；没有办法把一个 worktree 挡在所有其他人的清理之外。
- 回收会无声地摧毁所有权。带 `pruneRows` 的 `reconcile` 是唯一能退役登记的路径，而没有任何东西说明绑定在那里意味着什么。

## 决策

两块一起落地，因为绑定只有在面向模型的消费方使用它时才有意义：

- **注册表拥有绑定机制**（`packages/workflow/worktree-registry`）：`bind(id, holder)` 与 `unbind(id, holder)` 加入服务面——现在是七个操作——持久记录获得可选的 `lockedBy`/`lockedAt` 字段对（存储域 version 2；按预发布立场旧介质在打开时拒绝）。holder 值是不透明的 branded `WorktreeLockHolder`；相等即全部契约。当前 holder 重复绑定幂等，其他任何绑定以 `already-locked` 拒绝，他人解绑以 `holder-mismatch` 拒绝，对未绑定 worktree 的解绑以 `not-locked` 拒绝，绑定期间 `remove` 拒绝——`force` 绝不覆盖绑定。`pruneRows` 丢弃过时行时连同绑定一起丢弃：绑定守护的是活着的 checkout，不是消失的目录。
- **消费方在创建时即绑定**（`packages/experimental/agent-worktree`，`@deepseek-ai/dsh-experimental-agent-worktree`，私有且实验性）：`ctx.agentWorktree` 上的 `AgentWorktree` Service Definition 组合 create+bind，使 worktree 从第一次观测起就处于绑定状态，暴露按 workspace 授权的 `status`，并提供 `worktree_remove`——对其他持有者拒绝，在 git 运行前先释放调用者自己的绑定。它的 Consumer 角色注册恰好三个工具——`worktree_create`、`worktree_status`、`worktree_remove`——加一段固定指引。注册表缺席时插件 fiber 保持 pending 且不贡献任何东西；注册表到达时激活。与 `tool-worktree` 同装会重复注册共享工具名并响亮失败。

### holder 是会话的持久 id

消费方铸造 `WorktreeLockHolder(String(agent.session.id))`——持久 session id，不是每轮或每进程的值——所以恢复后的 Agent 在重启后仍匹配自己的绑定。注册表从不解释标记；身份选择属于消费方，另一个消费方可以对同一注册表铸造不同的 holder。

### 授权镜像工作区工具

每个操作都从不可变的会话头 cwd 解析调用方 workspace——绝不来自模型提供的 id——且该工作区没有登记行的 id 与未知 id 的报告完全一致。`status` 保持观测性：归属 workspace 的任何会话都可以观察绑定事实，而移除保持 holder 独占。

### 注册表级分支唯一性

`create` 现在拒绝同一 workspace 的另一个 worktree 已持有的显式分支，在 git 运行之前抛出已分类的 `branch-conflict` 类别；git 仍是跨 workspace 的兜底，所以两个不同 workspace 仍可在同名分支上各持 worktree。

## 已考虑的替代方案

- **绑定存进消费方自己的存储**（holder→worktree 行的私有表）：拒绝——排他承诺必须约束所有其他消费方都会触达的注册表 `remove`；消费方侧的表只会是建议性的，并与它指向的行漂移。
- **`force` 覆盖绑定**：拒绝——一个默默打破绑定所做唯一承诺的 force 标志会让绑定沦为摆设；holder 的解绑才是显式、有日志的出路。
- **锁定超时或破锁操作**：拒绝——会过期的定时器重新引入绑定要消除的赛跑；过时 holder 使移除卡住，直到 holder 回来、其他权威以 holder 值解绑、或 reconcile 丢弃已消失的行。
- **面向模型的分离 create 与 bind 工具**：拒绝——两次调用之间未绑定的 worktree 正是这个 seam 要关闭的窗口；消费方组合这对操作，把模型词汇保持在三个工具。
- **在相同名字下复用 `worktree_*` 工具名但换 schema**：不适用——名字是稳定的模型面契约，所以消费方保持它们完全一致，靠响亮的双重注册拒绝把两个消费方挡在同一组合之外。

## 后果

Agent 会话的 worktree 默认独占：create 即绑定，其他会话能观察但不能移除，移除在同一调用里释放持有者自己的绑定，承诺在注册表的持久行中跨重启存活。代价：

- **过时绑定卡住移除。** 创建后不移除就抛弃 worktree 的会话阻塞所有其他会话的移除，直到 holder 行动、或其目录消失后该行经 reconcile 丢弃；没有超时，也没有第三方破锁。
- **绑定是产品承诺。** 它只在注册表的 `remove` 执行；注册表之外运行的 git 命令完全无视它。
- **存储域 version 2 没有迁移。** version 1 写下的介质在打开时拒绝；部署必须重建 worktree 登记或接受拒绝，按预发布立场。
- **实验性包是同名工具的第二个模型面。** 它的工具不出现在任何 bundle，但同装两个消费方的组合在加载时响亮失败，而不是交付含混的工具。

## 验证

- `pnpm exec vitest run packages/workflow/worktree-registry`——绑定生命周期（`tests/agent-lock.spec.ts`）：create→bind→status→reconcile→remove、幂等重绑、每一种解绑拒绝、锁定 `remove` 带/不带 `force` 的拒绝、`pruneRows` 丢弃目录已消失的绑定行、并发同路径 create 恰好一胜、同 workspace 重复分支拒绝且不建目录、跨 workspace 分支同名仍允许。
- `pnpm exec vitest run packages/experimental/agent-worktree`——消费方（`tests/agent-worktree.spec.ts`）：三个工具 schema、create→绑定行、每会话 status 视角、按持有者与工作区的移除拒绝、无注册表时 pending 且注册表挂载后激活的 fiber、以及经插件 fiber 的 HMR 卸载/重装。
- `pnpm run gen-tool-catalog` 用替身注册表目录化三个 schema，与 `tool-worktree` 相同；`pnpm run gen-cordis-catalog` 在[子系统页](../../../../docs/subsystems/agent-worktree.zh.md)覆盖扩展后的注册表与新的 `ctx.agentWorktree` 面。
