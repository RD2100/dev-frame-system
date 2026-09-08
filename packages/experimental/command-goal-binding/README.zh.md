---
description: "面向宿主的 /devframe-start、/devframe-resume、/devframe-stop 与 /goal-complete 斜杠命令说明：以真实验证证据启动绑定的 goal，在停止或重启后恢复它，通过可靠性停止链停止项目树，且只有通过已验证完成准入时才完成它。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-command-goal-binding

[English](README.md) | 中文

## 概述

`dsh-experimental-command-goal-binding` 为用户提供 DevFrame goal 绑定流程的启动、恢复、停止与完成动词。`/devframe-start <objective>` 将新 goal 绑定到配置的 worktree 并产出真实验证证据：宿主计算 worktree 的源指纹、注册已批准的必需检查清单、通过控制器启动 goal，并把 role-policy、goal-binding 与 verification 记录落到控制器会话日志，其中每项声明检查都通过真实子进程执行。`/devframe-resume` 在停止或重启后恢复当前绑定的 goal，从会话日志 projection 或绑定存储重建绑定。`/devframe-stop` 通过真实可靠性停止链结束当前 goal：关闭准入、排空项目树的作业与已捕获进程、刷新每个参与会话，且只在链确认静止后才释放 writer。`/goal-complete` 只有通过已验证的完成准入时才会完成当前 goal：源指纹必须能从 worktree 重新推导、已注册的必需检查必须全部通过、授权审查必须通过。每一类可预期的拒绝都以稳定、直接的命令错误返回，指明失败的阶段但不暴露 goal 身份，适配器可以将其作为命令输出渲染。这是一个实验性 wave 包：它为宿主命令面组装准入 seam，并在这些命令之外附带停止链的宿主适配器。

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
| `/devframe-stop` | 启用 `stopChain` 时运行停止链：跨项目树关闭准入、排空拥有的作业与已捕获的后代进程、刷新每个参与会话，且只在链确认静止后才释放 writer；被中断的停止流程在重复停止时收敛 |
| `/goal-complete` | 在配置的 worktree 上通过完成准入完成当前 goal，并记录一条完成回执 |
| `/goal-complete <worktreePath>` | 针对给定 worktree 完成当前 goal，覆盖配置的根路径 |

### 稳定拒绝

可预期的拒绝都是带固定文本的直接命令错误。启动拒绝：缺少 objective、config 缺少 `workspaceRoot`（启动行无法在 objective 之外无歧义地给出 worktree）、以及已有未完成的当前 goal。恢复拒绝：命令名后带意外输入、没有当前 goal、goal 已完成、以及会话日志 projection 与绑定存储中都没有绑定记录。停止拒绝（启用 `stopChain` 时）：命令名后带意外输入、没有当前 goal、没有绑定记录、停止链已在运行中的第二次调用、以及已经 stopped 的绑定。一次未确认的停止——未解决的作业或进程、缺失的活跃 agent 身份、未接线的释放钩子、不可验证的项目树、或缺失的作业注册表——返回稳定的 needs-attention 错误，逐一列出剩余资源（例如 `job:<id>: timeout` 或 `writer:release: operation_failed`），报告 writer 仍被持有，并在项目树无法验证时附加 inventory 附注；该流程保持可重入，重复停止会重新进入 drain 或 release，而不是被拒绝。完成拒绝：没有当前 goal、该 goal 没有完成绑定、没有归属的验证证据、goal 已完成、projection 重放失败已锁存、以及命令行与配置都未给出 worktree 路径。被拒绝的准入会指明其阶段——`source-fingerprint`、`required-checks` 或 `review`——但不暴露 goal id 或 revision。结构性错误（`GoalBindingError`、`SourceFingerprintError`、`RequiredChecksError`、`DevFramePersistenceError`）不会被捕获：它们使分发失败，适配器会报告命令失败。

评级为 fail 的任务告警也会报告修复准入。同一告警重试会复用持久化回执，重启后仍然如此；项目负评消耗同一 Goal 的额度。`repairLimit` 默认为 2。人类授权的 resume 不会重置这项记账，该 Goal 的所有消费方必须使用一致的上限。参见 [DevFrame 修复契约](../devframe/README.zh.md#bound-correction-rounds)。

### 最小配置

插件注入命令注册表、Goal 服务、会话存储和会话投影注册表；自定义应用挂载这些组件及本插件。启动流程从配置读取已批准的工作参数。首次启动前先创建账本父目录（本例为 `D:/dsh-state`）；账本放在源码工作树之外，并在部署重启后复用同一路径：

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
    requiredChecksPath: D:/dsh-state/required-checks.json
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
| `requiredChecksPath` | 必填 | 持久化已批准检查账本的非空绝对路径，不得有首尾空白；父目录必须已存在 |
| `checks` | 必填 | `/devframe-start` 注册并真实执行的人工批准必需检查清单；每项 `cwd` 必须是绝对路径 |
| `taskIds` | 必填 | 每个启动绑定携带的非空、不重复的原生任务 id |
| `maxAttempts` | 必填 | 冻结进每个启动绑定的最大计费尝试次数 |
| `maxGoalRounds` | 无 | 固定在每个 start 绑定中的可选续跑轮次上限 |
| `repairLimit` | `2` | Goal 共用的正整数修复上限；必须与项目交付消费方一致 |
| `stopChain` | `false` | 在 `/devframe-stop` 后运行真实可靠性停止链；`false` 保持仅词表面 |
| `stopGraceMs` | `2000` | 链给予 drain、会话刷新与终态记账的正有限宽限期 |

空 `workspaceId`、相对 `workspaceRoot`、缺失、空或相对 `requiredChecksPath`、相对检查 `cwd`、空或重复的 `taskIds`、非正数的 `maxAttempts`/`maxGoalRounds`、或非正有限的 `stopGraceMs` 都会使插件激活明确失败。`repairLimit` 必须为正安全整数。

挂载的插件按规范摘要持久化已批准的检查配置。首次启动可以创建尚不存在的账本文件，但父目录必须已经存在。重启后完成操作从同一账本解析历史摘要；账本缺失、摘要缺失或登记损坏都会失败，不会拿当前部署的检查清单替代。在对应证据仍被使用时保留旧登记。

交付和集成消费方可以读取同一账本。部署必须指定单一写者并串行保存：整文件替换不提供并发写者合并或跨进程锁。将账本放在参与指纹计算的工作树之外，能避免登记写入改变源码证据。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释各命令如何解析证据并分发准入；可观察约定已在[使用本包](#use-this-package)中说明。

### 设计

- **读取本包拥有的 projection。** 激活时注册 devframe projection 单元，各处理器为调用会话读取其状态：归属到当前 goal 的最新验证证据，加上最新审查记录。审查证据不按 goal 预过滤——其归属由准入结构性强制，遇到外来审查时以 fail-closed 方式失败。
- **每个启动事实都由宿主采集。** `/devframe-start` 计算工作树的[实际源码指纹](../devframe/README.zh.md#fingerprint-source-contents)，使用完整状态哈希派生 `snapshot-v2-<headCommit>-<stateHash>`，并将已批准的目标和检查清单哈希为验收摘要。命令适配器提供人类授权；模型输入不写入证据，四态检查结果如实记录。
- **角色权威由日志派生。** 审查者目录从会话 devframe projection 折叠出的 role-policy 快照解析某个会话的角色——不依赖宿主内存另册——因此审查门的权威就是会话日志自身的记录，未指派的角色一律 fail-closed。
- **日志实例共享会话持久化。** 组合日志和证据日志都通过 `ctx.sessions.flush` 刷新。使用同一活跃会话的所有日志共享追加队列和失败锁；一次结果不确定的刷新会阻止它们之后的写入。
- **分发前先 fail closed。** 各处理器在到达准入之前，会因缺失 goal、缺失绑定、缺失证据或已锁存的 projection 重放失败而拒绝，并显式解析 worktree 路径，使缺失根路径成为数据错误而非结构性失败。
- **回执只在准入之后。** 获得准入的完成会通过准入的 compare-and-set 推进原生 goal，并通过 goal 服务记录一条 `completion-admission` 证据条目；拒绝则保持 goal phase、绑定与准入状态不变。
- **停止链是可选项且由宿主接线。** 项目树面与 writer 释放是组合服务上的注入点——不是 config：宿主捕获并做 owner 验证项目树（接收根加上每个 dispatch 血缘后代，通过活跃 agent 注册表上的会话 `parentSession` 链解析）并拥有释放。当 fiber 携带 agent、workspace 与 worktree 注册表时，apply 面挂载真实适配器：基于 `ctx.agents` 按血缘解析的活跃树——独立 worktree 上的 worker 属于树内，无关项目的会话绝不属于——以及 owner 检查的 worktree writer 释放；缺少这些注册表的 fiber 保持 fail-closed 的未接线链。不挂载任何进程 inventory：在真实捕获喂源接管后代进程之前，宿主无法证明的 inventory 会把空数组读成静止，因此链对缺失的面 fail-closed。链在树 inventory 缺失或为空、作业注册表缺失、释放钩子未接线时同样 fail-closed——缺失绝不等于安静。
- **writer 只在链确认后释放。** 确认静止的记录是持久的释放前前置；stopped 终态记录、存储条目与检查点只在该次释放真实成功之后落盘。异步的注册表释放在停止宽限界限内被 await，悬挂或被拒绝的释放都以 `needs_attention` 呈现且 writer 保持持有——警告绝不冒充释放，注册表未证明清空之前绝不落 `stopped`。
- **被中断的停止流程在重复停止时收敛。** 日志停在 `stop_requested`（drain 期间崩溃）时，恢复会基于宿主当前 inventory 重新进入 drain；日志停在 `quiescence_confirmed` 时重新进入释放。持久的注册表行是跨重启的释放真相，重复停止对照它收敛。缺失的活跃身份以 `needs_attention` 呈现且 writer 保持持有——绝不静默绕过，也绝不重启被中断的 goal 工作。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | 插件入口：name、注入列表、config 模式、apply |
| [`src/composition.ts`](src/composition.ts) | 组合服务：启动/恢复/停止通道、绑定启动通道、准入读取、完成处理器、停止链 drain 与恢复 |
| [`src/command.ts`](src/command.ts) | 命令语法、数据错误文本、拒绝渲染、回执证据 |
| [`src/host-evidence.ts`](src/host-evidence.ts) | flush 闭包、projection 派生审查者目录、role-policy/goal-binding 落账 helper、验收摘要 |
| [`src/config.ts`](src/config.ts) | config 模式与校验 |
| [`src/host-stop.ts`](src/host-stop.ts) | 真实宿主停止适配器：dispatch 血缘项目树、owner 检查的 worktree writer 释放 |
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
- [停止链组合 Agent Note](../../../.agents/notes/implemented/architecture/2026-09-08-command-goal-binding-stop-chain-composition.zh.md)——树 fail-closed、确认后释放、有界记账与恢复决策。
- [宿主停止适配器 Agent Note](../../../.agents/notes/implemented/architecture/2026-09-08-command-goal-binding-host-stop-adapters.zh.md)——apply 面默认接线、cwd 身份边界与同步释放的收敛。

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
- **绑定从会话日志恢复**——组合默认的绑定存储仍在内存中；`/devframe-resume` 从投影重建它。挂载的插件使用 `requiredChecksPath` 指向的文件后备必需检查存储；程序化组合保留显式存储注入点。
- **role policy 只指派 controller 角色**——没有任何审查者被授权，在审查生产 wave 落地审查者指派之前，任何审查提交都会被 fail-closed 拒绝。
- **审查归属是结构性的**——`/goal-complete` 直接取最新审查记录而不按 goal 预过滤；外来的最新审查会以结构性 `GoalBindingError` 呈现，这正是 fail-closed 方向。
- **模型完成路径绕过本 seam**——直接完成 goal 的面向模型 goal 工具不会运行本准入；这些命令只约束人类动词。
- **停止链只 drain，绝不重启**——恢复会基于宿主当前 inventory 重跑 drain，并对缺失的活跃身份 fail-closed；它不恢复也不重启被中断的 goal 工作，writer 在某次运行确认树静止前保持持有。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

审查生成和绑定存储选型仍由宿主组合负责。停止链的树捕获与 writer 释放同样由宿主负责；两者缺任一时组合都会拒绝释放。

</details>
