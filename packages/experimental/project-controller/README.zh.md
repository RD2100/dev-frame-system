---
description: "配置项目任务准入与仅限 controller 的 Git 集成，使用持久化验证、lead 审查和显式恢复。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-controller

[English](README.md) | 中文

## 概述

跟踪任务从分配、审查、集成到完成的过程，并在工作阻塞或失败时要求明确的恢复计划。限制并发开发任务数，同时区分任务名额与模型请求容量。已注册的根 controller 可以通过 `project_integrate` 集成经过审查的 Worker 提交；工具在快进前检查当前证据与工作树所有权。中断的操作保留意图记录，使 controller 能先检查 Git 实际改动，再决定是否重试。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

本包适用于由一个集成 controller、插件 lead 及已分配的 Worker 在注册工作树上协作的项目。宿主负责项目准入、检查配置的批准与写入者分配。

### 装配与配置

挂载一次 `@deepseek-ai/dsh-experimental-project-controller` 以提供 `ctx.projectController`，并同时挂载 storage-domain 与 session-identity。在完整包名后分别添加 `/consumer` 以提供 `project_integrate`、添加 `/task-consumer` 以提供 `project_task`。另挂载 `/delivery-consumer` 以提供 `project_deliver` 和 `project_review`。三个消费者都使用现有服务，并导出没有默认导出的 Loader 函数插件命名空间。

集成还需要活动会话、DevFrame 会话投影、workspace 与 worktree 注册表，以及持久化验证和审查证据。工具还需要活动 Agent 注册表与工具运行时。[真实 Loader 测试装配](tests/consumer-loader.spec.ts) 提供这些依赖，并在不发起模型请求的情况下执行这两个入口。

| 入口 | 字段 | 默认值 | 含义 |
|---|---|---|---|
| 服务 | `maxActiveTasks` | `2` | 处于 `developing` 的任务数上限，取正整数。 |
| 服务 | `requestBudget` | `1` | 累计模型请求计费预算，取正整数。 |
| 消费者 | `requiredChecksPath` | 必填 | 现有已批准检查配置登记账本的绝对路径。 |
| 消费者 | `gitExecutable` | 必填 | 部署选择的 Git 可执行文件。 |
| 消费者 | `gitTimeoutMs` | 必填 | 每个 Git 子进程的超时毫秒数，取正整数。 |
| 消费者 | `gitMaxOutputBytes` | 必填 | 每个 Git 子进程的输出字节数上限，取正整数。 |

消费者读取配置指定的账本，不批准检查，也不创建替代账本。缺少登记项或内容损坏会阻止准入。宿主的 controller 工具策略必须允许 `project_integrate`；lead 与 Worker 不应获得该工具。

### 规划与启动任务

挂载任务消费者仅暴露 `plan` 和 `start` 两个动作。宿主通过 `startProject()` 开放项目准入，准备当前 Goal 绑定，并在 controller 工具策略中允许 `project_task`。调用要求实际活动的根 controller、属于其当前开放 Goal 的任务，以及由 controller 持有写入锁的注册工作树。

`plan` 接受 `taskId`、`title` 和 `pluginId`，记录已规划任务。`start` 接受 `taskId` 和可选的 `briefing`，从任务与插件绑定推导唯一的活动 Worker。Worker 必须属于该 controller 下插件匹配的 lead。controller、lead 和 Worker 必须在 Goal 的 workspace 内拥有相互独立的注册工作树，并分别持有写入锁。宿主通过 hierarchy/dispatch 装配提供现有 Worker；此工具不创建 Worker。

启动会分配已规划任务，在 `maxActiveTasks` 限制内准入开发，并将可选 briefing 入队。开发准入后重复启动会拒绝，且不会重发 briefing。串行任务写入队列内部以及 briefing 投递前都会重新检查所有权。

失败的调用可能留下已分配或开发中的任务：任务写入和 briefing 投递不是原子操作。恢复前先检查任务板；错误不代表状态没有变化，重复启动也不能为开发中的任务补发缺失的 briefing。

[任务 Loader 测试](tests/task-consumer-loader.spec.ts)覆盖规划、权限拒绝、持久化停止请求后的拒绝、三个排队写入边界的撤权，以及两个真实 Worker 的模型请求重叠。七个用例使用真实本地注册表、存储、派发和工作树；外部模型响应由脚本适配器提供。它们不能证明在线模型完成了项目工作。

### 交付与审查工作

交付消费者使用与集成消费者相同的账本和 Git 配置。它还要求 `requiredChecksByTask`（宿主提供的任务到已批准摘要映射），以及每个检查子进程的正整数限制 `checkTimeoutMs` 和 `checkMaxOutputBytes`。每项已登记检查都必须在已分配 Worker 的实际工作树内运行。为 Worker 允许 `project_deliver`，为其独立插件 lead 允许 `project_review`。

Worker 从清洁且已提交的工作树显式调用 `project_deliver`，提供 `taskId`。宿主推导身份与源信息，在不改变原始 Goal 输入绑定的前提下记录任务交付，并运行现有已批准检查。检查通过且源仍然匹配时，任务才从开发推进到审查。检查失败保留结果但不推进任务；失败或中断的尝试要求显式设置 `retryChecks: true` 才会重跑该已批准检查集。

实际父级 lead 调用 `project_review`，提供 `taskId`、`decision` 和 `findings`。通过要求最新交付具有通过的验证，并提交该输出；`changes_required` 在活动任务上限内将任务退回开发。重复相同的已记录审查可以修复失败的任务状态写入，而不新增审查。冲突决定要求新交付，被拒绝的源必须修改后才能再次交付。Worker 空闲不构成交付或批准。

证据与任务写入是独立的持久化操作。消费者在交付、检查和审查间共享同一个会话 journal，使追加队列和持久化失败锁存状态跨调用保留。出错后检查已保留的证据；日志成功不代表任务已推进。集成仍要求最新的精确任务交付、验证、独立审查和未变化的源提交。

### 任务准入与集成

新服务以 `stopped` 状态启动。宿主先调用 `startProject()`，再创建任务并沿 `planned → assigned → developing → reviewing → submitted` 推进。`blocked` 或 `failed` 流转必须携带原因、下一步和唤醒条件；`resume` 清空这些字段并将任务恢复为 `assigned`。

集成工具只接受 `taskId` 与 `action`。它从实际活动 Agent 取得调用方，验证根 controller 绑定及会话目录，再从已分配 Worker 与 controller 的工作树记录解析源路径和目标路径。模型参数不能提供另一调用方、路径、检查结果或合并标记。

准入要求任务已提交、存在当前 Goal 绑定、持久化验证与独立插件 lead 审查相匹配、已批准的必需检查满足要求，且没有失败级任务警告。三级角色的工作树必须相互独立并属于同一 workspace。Worker 与 controller 必须分别持有源工作树和目标工作树的写入锁。系统检查源指纹、确切 Git 提交、工作树清洁状态和快进祖先关系，并在 Git 启动前重新检查证据和所有权。

| 动作 | 行为 |
|---|---|
| `integrate` | 准备新的意图记录，执行一次快进，并在观察到已应用结果后记录 `integrated`。 |
| `reconcile` | 观察保留的意图，不重复执行 Git。`applied` 结果可以补全集成记录；`unchanged` 不推进任务状态；`ambiguous` 需要调查。 |
| `retry` | 仅当清洁目标仍处于原始 HEAD 时，显式重新准入已准备的尝试。当前证据与所有权必须再次通过检查。 |

中断后，重新开放项目准入，并使用原 controller 身份与写入锁进行核对。普通 `integrate` 调用不会替换保留的意图。命令错误或取消均不能证明 Git 没有改变目标。若被忽略的本地文件与即将写入的已跟踪内容冲突，该文件会被保留，合并则失败。

宿主消费者先调用 `requestMainTreeMerge(callerSessionId, taskId, request)`，再将返回的标记直接交给 `integrate(taskId, marker)`。请求携带确切 Git 路径与提交、进程限制、已批准检查配置存储，以及可选的 `retryUnchanged` 和取消信号。标记是一次性对象能力，不是可传递的 JSON。服务的 `reconcileMainTreeIntegration(callerSessionId, taskId, options)` 读取持久化意图。集成不会自动调用 `complete`。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

controller 串行执行任务变更与集成尝试。任务记录、累计请求计费和 Git 意图经 `project_tasks` 域持久化；生命周期状态与标记能力保留在进程内。已应用的 Git 观察结果先于任务变为已集成而持久化，因此任务写入失败后可以在重启时核对恢复。

证据来自现有 DevFrame 投影与三级绑定注册表。本包不增加 reviewer 角色或第二套证据数据库。标记不能替代执行时准入：更新的审查、验证、警告或所有权记录会使准备阶段的证据失效。

| 文件 | 职责 |
|---|---|
| [`src/controller.ts`](src/controller.ts) | 任务生命周期、串行准入、持久化意图与恢复。 |
| [`src/consumer.ts`](src/consumer.ts) | 集成工具入口、调用方授权与宿主配置。 |
| [`src/task-consumer.ts`](src/task-consumer.ts) | 根 controller 规划、注册 Worker 准入与 briefing 投递。 |
| [`src/delivery-consumer.ts`](src/delivery-consumer.ts) | 显式 Worker 交付、已批准检查与独立 lead 审查。 |
| [`src/integration-evidence.ts`](src/integration-evidence.ts) | 确切任务证据与独立 lead 权限。 |
| [`src/git-integration.ts`](src/git-integration.ts) | 有界 Git 检查、快进与结果观察。 |
| [`src/spec.ts`](src/spec.ts) | 带版本的任务、请求预算与集成意图存储。 |

本包未发布运行时 invariant 伴随物：中断后，Git 推进与任务持久化可能不一致，因此核对操作报告并处理该恢复状态，而不要求两者持续相等。[controller 恢复测试](tests/integration-controller.spec.ts)和 [Loader 测试](tests/consumer-loader.spec.ts)执行这些关系的验证；调用方必须核对结果不明的操作。

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [架构与 profile](../../../docs/architecture.zh.md)：受支持的启动与装配方式。
- [Agent 层级](../agent-hierarchy/README.zh.md)：controller、lead 与 Worker 权限。
- [DevFrame](../devframe/README.zh.md)：Goal 绑定、检查与审查证据。
- [工作树注册表](../../workflow/worktree-registry/README.zh.md)：注册工作树与写入锁。

-----

<a id="model-experience"></a>
## 模型体验

### 项目任务与集成工具

#### 模型看到什么

挂载消费者会暴露带 `taskId` 和 `action` 参数的 `project_integrate`。成功结果包含任务 id、任务状态和集成观察；失败通过工具运行时报告拒绝原因。普通工具调用与结果日志承载这些模型可见值。仅挂载服务不会暴露工具。任务消费者单独暴露 `project_task`：规划需要标题与插件范围，启动接受可选 briefing。结果报告 `taskId`、`state` 和 `briefingQueued`；指令入队不代表 Worker 已完成。

交付消费者还提供 `project_deliver`（任务与可选重试标志）和 `project_review`（任务、显式决定与发现项）。两者返回 `taskId`、`state` 和 `outcome`，通过普通工具调用与结果日志展示；模型不能指定身份、源码路径或检查命令。

#### Token 影响

当工具对 Agent 可见时，工具定义会占用请求 token；每次调用会将参数与结果加入会话历史。本包没有经过测量的固定 token 成本。

#### KV Cache 影响

稳定的工具定义可以保留在可复用的请求前缀中。修改工具可见性或周边工具策略配置可能改变该前缀；调用与结果会扩展会话历史。包测试未测量提供方缓存复用情况。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

选择装配方式和处理中断工作时，需要考虑以下约束。

- 重启后的生命周期为已停止。宿主必须重新开放准入并重新评估恢复出的进行中任务；进程内标记无法跨重启保留。
- 版本 3 存储域拒绝旧布局。不要将其直接激活到现有版本 2 域上，也不要将重置该域当作隐式升级。
- 集成仅支持同一仓库内清洁且独立的工作树与快进更新。它不重置文件、不解决冲突，也不自动重复结果不明的命令。
- 写入锁依赖参与宿主遵守所有权。它们无法阻止绕过注册表的其他文件系统写入者或 Git 命令。
- `maxActiveTasks` 统计开发中任务，而非活动模型请求。请求计费跨重启保留；账号与提供方限制仍由部署负责。
- Loader 与真实 Git 测试验证本地装配。它们不能证明已完成随产品提供的 profile 部署、生产激活或真实模型完成质量验证。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
