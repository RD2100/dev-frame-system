---
description: "面向希望通过已验证完成准入完成 goal 的宿主的 /goal-complete 斜杠命令说明，提供稳定拒绝与持久完成回执。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-command-goal-binding

[English](README.md) | 中文

## 概述

`dsh-experimental-command-goal-binding` 为用户提供 `/goal-complete` 命令，只有通过已验证的完成准入时才会完成当前 goal：源指纹必须能从 worktree 重新推导、已注册的必需检查必须全部通过、授权审查必须通过。命令通过真实命令注册表分发，读取本包注册的 devframe projection，并在成功时记录一条持久完成回执。每一类可预期的拒绝都以稳定、直接的命令错误返回，指明失败的阶段但不暴露 goal 身份，适配器可以将其作为命令输出渲染。这是一个实验性 wave 包：它为宿主命令面组装准入 seam，除命令本身外不提供任何宿主面。

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

在 agent 携带受约束 goal 的组合中挂载本插件，为操作者提供一条只在准入证据链成立时完成 goal 的人类命令。

### 选择时机

当部署要求"完成"意味着"已验证准入放行"——源树与绑定的快照完全一致、每项必需检查都已执行并通过、授权审查已通过——并且希望这道闸门出现在人类命令上而非模型自由裁量时，选择它。只通过面向模型的 goal 工具完成 goal 的宿主不需要它。本包是实验性的，注册的是私有组合服务，因此其面应视为 wave 范围而非公共约定。

### 命令参考

| 输入 | 结果 |
|---|---|
| `/goal-complete` | 在配置的 worktree 上通过完成准入完成当前 goal，并记录一条完成回执 |
| `/goal-complete <worktreePath>` | 针对给定 worktree 完成当前 goal，覆盖配置的根路径 |

### 稳定拒绝

可预期的拒绝都是带固定文本的直接命令错误：没有当前 goal、该 goal 没有完成绑定、没有归属的验证证据、goal 已完成、projection 重放失败已锁存、以及命令行与配置都未给出 worktree 路径。被拒绝的准入会指明其阶段——`source-fingerprint`、`required-checks` 或 `review`——但不暴露 goal id 或 revision。结构性错误（`GoalBindingError`、`SourceFingerprintError`、`RequiredChecksError`）不会被捕获：它们使分发失败，适配器会报告命令失败。

### 最小配置

命令注入命令注册表、goal 服务与会话 projection 注册表；自定义应用挂载它们的所有者与此插件：

```yaml
- id: commands
  name: '@deepseek-ai/dsh-commands'
- id: goal
  name: '@deepseek-ai/dsh-goal'
- id: session-projection
  name: '@deepseek-ai/dsh-session-projection'
- id: command-goal-binding
  name: '@deepseek-ai/dsh-experimental-command-goal-binding'
  config:
    workspaceId: ws-team-alpha
```

| 字段 | 默认值 | 含义 |
|---|---|---|
| `workspaceId` | 必填 | 归属于本组合绑定与证据的 workspace 身份 |
| `workspaceRoot` | 无 | 命令行省略路径时使用的 worktree |

空 `workspaceId` 或相对 `workspaceRoot` 会让插件激活大声失败。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释命令如何解析证据并分发准入；可观察约定已在[使用本包](#use-this-package)中说明。

### 设计

- **读取本包拥有的 projection。** 激活时注册 devframe projection 单元，处理器为调用会话读取其状态：归属到当前 goal 的最新验证证据，加上最新审查记录。审查证据不按 goal 预过滤——其归属由准入结构性强制，遇到外来审查时以 fail-closed 方式失败。
- **分发前先 fail closed。** 处理器在到达准入之前，会因缺失绑定、缺失证据或已锁存的 projection 重放失败而拒绝，并显式解析 worktree 路径，使缺失根路径成为数据错误而非结构性失败。
- **回执只在准入之后。** 获得准入的完成会通过准入的 compare-and-set 推进原生 goal，并通过 goal 服务记录一条 `completion-admission` 证据条目；拒绝则保持 goal phase、绑定与准入状态不变。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | 插件入口：name、注入列表、config 模式、apply |
| [`src/composition.ts`](src/composition.ts) | 组合服务：绑定启动通道、准入读取、完成处理器 |
| [`src/command.ts`](src/command.ts) | 命令语法、拒绝渲染、回执证据 |
| [`src/config.ts`](src/config.ts) | config 模式与校验 |
| — | 不发布运行时不变式伴生入口；准入语义由 devframe 包拥有并测试，命令行为由包内测试覆盖。 |

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

该命令是准入 seam 之上的薄宿主面；需要了解它组合的各项约定时阅读以下页面。

- [DevFrame 宿主工作会话 seam](../devframe/README.zh.md)——本命令读取并分发的 projection、指纹、必需检查与审查。
- [命令服务](../../interaction/commands/README.zh.md)——命令注册、分发的注册表边界。
- [goal 服务](../../goal/goal/README.zh.md)——准入所完成的原生 goal 生命周期与回执所依附的状态。
- [宿主命令面 Agent Note](../../../.agents/notes/implemented/architecture/2026-09-06-command-goal-binding-host-command-surface.zh.md)——组合与归属决策。

-----

<a id="model-experience"></a>
## 模型体验

### 用户 `/goal-complete` 控制

#### 模型看到的内容

斜杠输入、准入分发以及直接的成功／错误输出都不会进入模型请求。获得准入的完成会记录一条携带 `completion-admission` 证据条目的 `goal/change` 回执，本包注册的 projection 会向宿主面暴露已完成的绑定与审查状态；后续续行提示词只能通过这些被拥有的通道观察到已完成的 goal。

#### Token 影响

分发命令、接收结果与记录回执都不会增加模型 token。后续 Goal Round 提示词只会通过已启用驱动器组装的普通请求历史看到完成后的 phase。

#### KV Cache 影响

命令发现、准入裁决与回执落盘都不会影响缓存。后续续行提示词遵循驱动器的普通请求历史。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制说明命令何时不合适或需要特别注意。它们是当前包约束，不是任务积压。

- **仅有内存存储**——绑定与必需检查注册都保存在进程内存中；重启后检查注册即丢失，命令会以结构性错误 fail closed，而不是完成完成。
- **启动与恢复通道仅在测试可见**——本 wave 只交付完成命令；启动、解除武装与恢复绑定的宿主面仍然延期。
- **证据生产者延期**——一次完成需要先存在 `devframe/verification` 与 `devframe/review` 记录；不生产它们的宿主总会收到稳定的无证据错误。
- **审查归属是结构性的**——命令直接取最新审查记录而不按 goal 预过滤；外来的最新审查会以结构性 `GoalBindingError` 呈现，这正是 fail-closed 方向。
- **模型完成路径绕过本 seam**——直接完成 goal 的面向模型 goal 工具不会运行本准入；该命令只约束人类完成动词。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

本包是 v14 宿主命令面实验 wave。开放且未决：启动与恢复通道的宿主面、生产证据生产者与持久存储；内存存储是组合默认值，不是持久化承诺。

</details>
