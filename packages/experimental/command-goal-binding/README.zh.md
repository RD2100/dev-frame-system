---
description: "面向宿主的 /devframe-start、/devframe-resume 与 /goal-complete 斜杠命令说明：以真实验证证据启动绑定的 goal，在停止或重启后恢复它，且只有通过已验证完成准入时才完成它。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-command-goal-binding

[English](README.md) | 中文

## 概述

`dsh-experimental-command-goal-binding` 为用户提供 DevFrame goal 绑定流程的启动、恢复与完成动词。`/devframe-start <objective>` 将新 goal 绑定到配置的 worktree 并产出真实验证证据：宿主计算 worktree 的源指纹、注册已批准的必需检查清单、通过控制器启动 goal，并把 role-policy、goal-binding 与 verification 记录落到控制器会话日志，其中每项声明检查都通过真实子进程执行。`/devframe-resume` 在停止或重启后恢复当前绑定的 goal，从会话日志 projection 或绑定存储重建绑定。`/goal-complete` 只有通过已验证的完成准入时才会完成当前 goal：源指纹必须能从 worktree 重新推导、已注册的必需检查必须全部通过、授权审查必须通过。每一类可预期的拒绝都以稳定、直接的命令错误返回，指明失败的阶段但不暴露 goal 身份，适配器可以将其作为命令输出渲染。这是一个实验性 wave 包：它为宿主命令面组装准入 seam，除这些命令本身外不提供任何宿主面。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步探索](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在 agent 携带受约束 goal 的组合中挂载本插件，为操作者提供以真实证据启动 goal、跨重启恢复 goal、且只在准入证据链成立时完成 goal 的人类命令。

### 选择时机

当部署要求 goal 工作全程受宿主审计时选择它：目标与必需检查通过部署 config 批准，启动真实执行它们并如实记录结果，完成意味着"已验证准入放行"——源树与绑定的快照完全一致、每项必需检查都已执行并通过、授权审查已通过。只通过面向模型的 goal 工具启动与完成 goal 的宿主不需要它。本包是实验性的，注册的是私有组合服务，因此其面应视为 wave 范围而非公共约定。

### 命令参考

| 输入 | 结果 |
|---|---|
| `/devframe-start <objective>` | 针对配置的 worktree 启动新绑定的 goal：把 role-policy、goal-binding 与 verification 记录落到控制器会话日志，并报告真实执行的检查数与验证状态 |
| `/devframe-resume` | 在停止或重启后恢复并续跑当前绑定的 goal，从会话日志 projection 或绑定存储重建绑定 |
| `/goal-complete` | 在配置的 worktree 上通过完成准入完成当前 goal，并记录一条完成回执 |
| `/goal-complete <worktreePath>` | 针对给定 worktree 完成当前 goal，覆盖配置的根路径 |

### 稳定拒绝

可预期的拒绝都是带固定文本的直接命令错误。启动拒绝：缺少 objective、config 缺少 `workspaceRoot`（启动行无法在 objective 之外无歧义地给出 worktree）、以及已有未完成的当前 goal。恢复拒绝：命令名后带意外输入、没有当前 goal、goal 已完成、以及会话日志 projection 与绑定存储中都没有绑定记录。完成拒绝：没有当前 goal、该 goal 没有完成绑定、没有归属的验证证据、goal 已完成、projection 重放失败已锁存、以及命令行与配置都未给出 worktree 路径。被拒绝的准入会指明其阶段——`source-fingerprint`、`required-checks` 或 `review`——但不暴露 goal id 或 revision。结构性错误（`GoalBindingError`、`SourceFingerprintError`、`RequiredChecksError`、`DevFramePersistenceError`）不会被捕获：它们使分发失败，适配器会报告命令失败。

评级为 fail 的任务告警也会报告修复准入。同一告警重试会复用持久化回执，重启后仍然如此；项目负评消耗同一 Goal 的额度。`repairLimit` 默认为 2。人类授权的 resume 不会重置这项记账，该 Goal 的所有消费方必须使用一致的上限。参见 [DevFrame 修复契约](../devframe/README.zh.md#bound-correction-rounds)。

### 最小配置

本插件注入命令注册表、goal 服务、会话存储与会话 projection 注册表；自定义应用挂载它们的所有者与此插件。启动通道从 config 读取已批准的工作参数：

```yaml
- id: commands
  name: '@deepseek-ai/dsh-commands'
- id: goal
  name: '@deepseek-ai/dsh-goal'
- id: session
  name: '@deepseek-ai/dsh-session'
- id: session-projection
  name: '@deepseek-ai/dsh-session-projection'
- id: command-goal-binding
  name: '@deepseek-ai/dsh-experimental-command-goal-binding'
  config:
    workspaceId: ws-team-alpha
    workspaceRoot: D:/worktrees/team-alpha
    taskIds: [task-alpha]
    maxAttempts: 3
    checks:
      version: 1
      checks:
        - checkId: unit-tests
          executable: pnpm
          arguments: [exec, vitest, run, packages/a]
          cwd: D:/worktrees/team-alpha
```

| 字段 | 默认值 | 含义 |
|---|---|---|
| `workspaceId` | 必填 | 归属于本组合绑定与证据的 workspace 身份 |
| `workspaceRoot` | 无 | `/devframe-start` 绑定的 worktree，也是 `/goal-complete` 在命令行省略路径时的回退 |
| `checks` | 必填 | `/devframe-start` 注册并真实执行的人工批准必需检查清单；每项 `cwd` 必须是绝对路径 |
| `taskIds` | 必填 | 每个启动绑定携带的非空、不重复的原生任务 id |
| `maxAttempts` | 必填 | 冻结进每个启动绑定的最大计费尝试次数 |
| `maxGoalRounds` | 无 | 固定在每个 start 绑定中的可选续跑轮次上限 |
| `repairLimit` | `2` | Goal 共用的正整数修复上限；必须与项目交付消费方一致 |

空 `workspaceId`、相对 `workspaceRoot`、相对检查 `cwd`、空或重复的 `taskIds`、非正数的 `maxAttempts`/`maxGoalRounds` 都会使插件激活明确失败。`repairLimit` 必须为正安全整数。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释各命令如何解析证据并分发准入；可观察约定已在[使用本包](#use-this-package)中说明。

### 设计

- **读取本包拥有的 projection。** 激活时注册 devframe projection 单元，各处理器为调用会话读取其状态：归属到当前 goal 的最新验证证据，加上最新审查记录。审查证据不按 goal 预过滤——其归属由准入结构性强制，遇到外来审查时以 fail-closed 方式失败。
- **每个启动事实都由宿主采集。** `/devframe-start` 计算 worktree 的真实源指纹、从指纹派生快照 id、把批准的 objective 与检查清单哈希为验收摘要，并在命令适配器内铸造人类授权；模型输入永不写证据，四态检查结果如实落账。
- **角色权威由日志派生。** 审查者目录从会话 devframe projection 折叠出的 role-policy 快照解析某个会话的角色——不依赖宿主内存另册——因此审查门的权威就是会话日志自身的记录，未指派的角色一律 fail-closed。
- **日志实例共享会话持久化。** 组合日志和证据日志都通过 `ctx.sessions.flush` 刷新。使用同一活跃会话的所有日志共享追加队列和失败锁；一次结果不确定的刷新会阻止它们之后的写入。
- **分发前先 fail closed。** 各处理器在到达准入之前，会因缺失 goal、缺失绑定、缺失证据或已锁存的 projection 重放失败而拒绝，并显式解析 worktree 路径，使缺失根路径成为数据错误而非结构性失败。
- **回执只在准入之后。** 获得准入的完成会通过准入的 compare-and-set 推进原生 goal，并通过 goal 服务记录一条 `completion-admission` 证据条目；拒绝则保持 goal phase、绑定与准入状态不变。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | 插件入口：name、注入列表、config 模式、apply |
| [`src/composition.ts`](src/composition.ts) | 组合服务：启动/恢复通道、绑定启动通道、准入读取、完成处理器 |
| [`src/command.ts`](src/command.ts) | 命令语法、数据错误文本、拒绝渲染、回执证据 |
| [`src/host-evidence.ts`](src/host-evidence.ts) | flush 闭包、projection 派生审查者目录、role-policy/goal-binding 落账 helper、验收摘要 |
| [`src/config.ts`](src/config.ts) | config 模式与校验 |
| — | 不发布运行时不变式伴生入口；准入语义由 devframe 包拥有并测试，命令行为由包内测试覆盖。 |

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

这些命令是准入 seam 之上的薄宿主面；需要了解它们组合的各项约定时阅读以下页面。

- [DevFrame 宿主工作会话 seam](../devframe/README.zh.md)——这些命令读取并分发的 projection、指纹、必需检查与审查。
- [命令服务](../../interaction/commands/README.zh.md)——命令注册、分发的注册表边界。
- [goal 服务](../../goal/goal/README.zh.md)——准入所完成的原生 goal 生命周期与回执所依附的状态。
- [宿主命令面 Agent Note](../../../.agents/notes/implemented/architecture/2026-09-06-command-goal-binding-host-command-surface.zh.md)——组合与归属决策。

-----

<a id="model-experience"></a>
## 模型体验

### 用户启动、恢复与完成控制

#### 模型看到的内容

斜杠输入、宿主的证据采集以及直接的成功／错误输出都不会进入模型请求。`/devframe-start` 与 `/devframe-resume` 会把 `devframe/role-policy`、`devframe/goal-binding` 与 `devframe/verification` 记录追加到控制器会话日志——这是一份从不进入模型请求的宿主侧持久记录。获得准入的完成会记录一条携带 `completion-admission` 证据条目的 `goal/change` 回执，本包注册的 projection 会向宿主面暴露绑定、证据与审查状态；后续续行提示词只能通过这些被拥有的通道观察到 goal phase。

#### Token 影响

分发命令、采集证据与记录回执都不会增加模型 token。后续 Goal Round 提示词只会通过已启用驱动器组装的普通请求历史看到 goal phase。

#### KV Cache 影响

命令发现、证据采集、准入裁决与回执落盘都不会影响缓存。后续续行提示词遵循驱动器的普通请求历史。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制说明这些命令何时不合适或需要特别注意。它们是当前包约束，不是任务积压。

- **审查生产路径不在本 wave**——`/devframe-start` 只落 verification 证据、不伪造任何审查决定；它之后 `/goal-complete` 如实报告缺失审查记录（稳定的无审查错误），而不是完成。
- **启动存在部分失败窗口**——若原生 goal 与存储绑定建立后 journal 落账失败，`/devframe-start` 以 fail-closed 抛出且不回滚它们；`/devframe-resume` 是恢复路径（存储里有而日志里没有的绑定会被重新落账）。
- **每个会话只有一个活跃写者**——共享日志队列协调同一进程内的一个活跃会话；它不提供跨进程比较交换，也不保护多个独立恢复的写者。
- **绑定与必需检查存储仍是内存参考实现**——重启后存储为空；`/devframe-resume` 从会话日志 projection 重建绑定，已批准清单注册随下一次 `/devframe-start` 回来。持久存储集成归 GoalStore wave 的既有注入点。
- **role policy 只指派 controller 角色**——没有任何审查者被授权，在审查生产 wave 落地审查者指派之前，任何审查提交都会被 fail-closed 拒绝。
- **审查归属是结构性的**——`/goal-complete` 直接取最新审查记录而不按 goal 预过滤；外来的最新审查会以结构性 `GoalBindingError` 呈现，这正是 fail-closed 方向。
- **模型完成路径绕过本 seam**——直接完成 goal 的面向模型 goal 工具不会运行本准入；这些命令只约束人类动词。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

内存存储是组合默认值，不代表持久化承诺。审查生成和持久化存储选型仍由宿主组合负责。

</details>
