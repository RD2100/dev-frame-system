# Agent Note: 绑定到调用会话工作区的模型可见 worktree 工具

Status: implemented

[English](2026-09-05-worktree-tools-and-reconcile.md) | 中文

## 问题

worktree 注册表 seam 以宿主侧服务的形态交付：`ctx.worktreeRegistry` 带 create/list/status/remove、持久行和一个跑 git 的 provider。没有任何东西把它暴露给模型，于是这个 seam 赖以成立的能力——agent 管理自己工作区的第二检出——始终不可达，而且两个宿主侧缺口让朴素的暴露不安全：

- 接受模型提供 workspace id 的工具会让一个会话的 agent 通过猜测 id 创建、检视或删除另一个 workspace 的 worktree；持久 worktree id 是稳定、原则上可猜的引用。
- 正常使用中行与 git 会漂移：用户在产品之外删掉 worktree 目录，或用原生 git 创建一个。registry 的 `remove` 对目录消失的拒绝没有任何恢复路径，产品之外创建的 worktree 对 `list` 不可见。

## Decision

包 `packages/workflow/tool-worktree`（`@deepseek-ai/dsh-tool-worktree`）是 seam 的 Consumer：五个模型可见工具——`worktree_create`、`worktree_list`、`worktree_status`、`worktree_remove`、`worktree_prune`——注册到 `ctx.tools`，并在系统提示词中带一段固定路由引导。该包无配置；每个随部署变化的值都留在 registry 的 Config 里。它构建在 [registry seam](../architecture/2026-09-05-worktree-registry.zh.md) 之上，只消费其操作与持久行，不做重新实现。

### 授权：会话 cwd 是锚点

每个 execute 体都从 `exec.agent` 的会话头 cwd 解析调用者——绝不从模型提供的 id。cwd 经 `fs.realpath` 规范化后与 `ctx.workspaceRegistry` 的注册路径匹配（Windows 上大小写折叠）；没有调用 agent、头部没有 cwd、或目录未注册的调用都会拒绝并说明原因。工具 id 只在调用者的工作区内解析：注册在另一工作区名下的 id 与未知 id 用同一消息报告，错误差异不会泄露其他工作区的登记。相对的 `worktree_create` 目标显式相对授权的工作区目录解析，因此无论宿主进程 cwd 如何，registry 收到的总是绝对路径。

### reconcile 作为漂移恢复路径

seam 新增 `reconcile`，`worktree_prune` 暴露它：默认只报告，`pruneDangling: true` 丢弃过时登记，`adoptUnregistered: true` 登记产品之外创建的 worktree。registry 拥有语义和 `git worktree prune` 调用；工具拥有旗标映射与一份报告渲染，点名悬空登记、未注册 worktree 与已应用动作计数。`worktree_status` 的目录缺失观察与 `worktree_remove` 的目录消失拒绝都把 `worktree_prune` 指为恢复路径。

### 失败方言作为模型可用的重试语义

registry 把模型实际能引发的四类 git 拒绝方言——路径被占用、分支冲突、脏树、路径超长——分类为类型化错误，其文本陈述具体修法。工具自身不做分类；`worktree_create` 的描述点名拒绝类别，模型无需宿主帮助即可用修正后的参数重试。

### 呈现与记录

待定调用渲染从调用参数取题的 `generic` 卡；结果保持普通 generic 卡，在有助于恢复的地方加逐条渲染文本。结果走普通的工具 call/result 会话事件——不欠任何新 `SessionEventMap` 成员。组合把 consumer 挂载到 base bundle 的 agent 面；web-app bundle 在启用 registry 的旁边保持 consumer 禁用。

## Alternatives considered

- **workspace id 作为工具参数**（由模型传要管理哪个 workspace）：否决——"这次调用可以碰哪些 worktree"的锚点是会话实际运行所在的目录；模型提供的 id 会让任何会话管理任何 workspace，把授权从边界降格为礼貌性检查。
- **每工具配置字段**（工具名、引导开关、id 校验严格度）：否决——consumer 自身没有随部署变化的选择；registry 的 Config 拥有超时与输出上限，引导文本与任何工具描述一样属于工具契约。
- **reconcile 旗标塞进 `worktree_remove`**（一个丢弃消失行的 `--prune` 变体）：否决——remove 的契约是"经 git 删除一个 worktree"；把它悄悄变成注册表清理，混淆了单个 worktree 的生命周期与整个 workspace 的登记集合，而且 reconcile 的只报告默认将失去面。
- **status 与 prune 的专用卡渲染器**：暂缓——带逐条文本的 generic 卡已承载恢复所需信息；Web 卡管线之后可以从同样的原始事件派生更丰富的 worktree 卡。
- **每次 reconcile 采纳发一个会话事件**：否决——采纳成为持久注册表状态，可经后续工具调用观察；日志已承载执行它的那次工具交互。

## Consequences

seam 完整了：模型创建、观察、删除并对账自己工作区的 worktree，而且即使猜测稳定 id 也触不到另一工作区的登记。过去永远卡死 `remove` 的漂移现在有了显式的、模型可调用的恢复。代价：

- **cwd 锚点是严格的。** 头部 cwd 已移动、或从未附加到已注册工作区的会话完全无法使用这些工具，哪怕是工作区范围的读取。
- **采纳是无条件的。** `adoptUnregistered` 信任 `git worktree list`；一个无关仓库的链接检出可以在没有确认步骤的情况下被采纳到对账 workspace 名下。
- **引导段落消耗 token。** 插件注册范围内的每个请求都携带固定路由引导；文本陈述授权范围与 prune 恢复，让模型重试保持廉价。

## Verification

- `pnpm exec vitest run packages/workflow/tool-worktree` 覆盖授权拒绝（无 agent、无 cwd、未注册目录、外来 id 与未知 id 不可区分）、相对/绝对目标解析、registry 运行前的空参数拒绝、带与不带 `force` 的 remove、prune 旗标映射与渲染文本（`packages/workflow/tool-worktree/tests/tool-worktree.spec.ts`）。
- registry 侧的 reconcile 与失败分类覆盖在 `packages/workflow/worktree-registry/tests/`，由 [seam Agent Note](../architecture/2026-09-05-worktree-registry.zh.md) 报告。
- `pnpm run gen-tool-catalog` 保持生成的 `worktree_*` schema 新鲜；catalog 条目挂载替身 registry，因为 schema 不依赖 provider。
