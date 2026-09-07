---
description: "插件化 DSH 代理层级的共享类型词汇：角色、任务状态、品牌 ID、绑定与任务记录、创建意图、持久化接缝与稳定错误类型。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-contracts

[English](README.md) | 中文

## 概述

`dsh-experimental-project-contracts` 收纳插件化代理层级的跨插件类型词汇：三种角色（`controller`、`lead`、`worker`）、项目面板的九个任务状态、带品牌的 `PluginId` 与 `TaskId` 标识、持久化的 `AgentBindingRecord` 与 `TaskRecord` 形状、每次创建尝试都携带的 `CreationIntent` 记录、最小化的 `BindingStore` 与 `TaskStore` 持久化接缝、封闭联合类型守卫，以及稳定的 `ProjectContractsError` 类型。本包是只含类型与纯值辅助函数的私有实验库：不注册 Cordis 插件、不持有活状态、不提供模型可见表面。每个同族插件——session-identity、agent-hierarchy、project-controller、agent-evidence、agent-reliability——都从这里导入契约，而不是各自重复声明。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

当某个插件化层级插件需要与其同族插件在角色、任务状态、ID、记录或存储接缝上达成一致时使用本包。它是新层级插件中唯一的跨插件源码依赖；发布包不得依赖它。

### 读写词汇表

从包根导入类型、守卫与工厂。工厂先校验后打品牌；守卫在持久化边界上对不可信值分类。

```ts
import { isTaskState, PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'

const pluginId = PluginId('agent-reliability')
const taskId = TaskId('task-7')
function parseTaskState(rawState: unknown) {
  if (!isTaskState(rawState)) throw new Error('unknown task state')
  return rawState
}
```

### 实现存储接缝

`BindingStore` 与 `TaskStore` 只固定 `read`、`write`、`list`。实现放在其属主插件里——冷恢复用插件自有 storages 目录下的 JSON 存储，测试用内存存储——对缺失记录的 `read` 返回 `undefined` 而不是失败。实现必须校验从磁盘读回的记录，并通过 `ProjectContractsError` 报告失败。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释设计决策并指向实现代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **一份词汇，六个消费方。** 角色、状态、记录与错误只在这里声明一次；同族插件依赖本包，而不依赖彼此的运行时导出。
- **互不相同的品牌字符串。** `TaskId` 的品牌是 `ProjectTaskId`，刻意与实验性 DevFrame 团队任务品牌分开，使两套任务词汇在类型层面无法混用；`agentId` 与 `sessionId` 复用宿主 `SessionId` 品牌，因为本地代理在两个位置携带同一身份。
- **在归属边界上做校验。** ID 工厂拒绝空值、纯空白与带首尾空白的值；封闭联合类型守卫对不可信字符串分类；其余记录校验属于读取持久化字节的存储实现。
- **契约里没有状态机。** `TaskState` 类型记录派发顺序以及 `blocked` 或 `failed` 任务必须携带的恢复三元组，但流转强制是 project-controller 的运行时职责，不是契约关注点。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/types.ts`](src/types.ts) | 角色、任务状态、记录形状、创建意图与存储接缝——纯类型 |
| [`src/ids.ts`](src/ids.ts) | `PluginId` 与 `TaskId` 品牌及其校验工厂 |
| [`src/guards.ts`](src/guards.ts) | 冻结成员元组与封闭联合类型守卫 |
| [`src/errors.ts`](src/errors.ts) | `ProjectContractsError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 重新导出词汇表的包入口 |

### 不变式

不发布运行时 invariant 伴随物：本包不持有活状态，也不在独立观察之间断言任何关系——每个导出都是值类型、纯守卫或工厂、或错误类型，不存在可能分叉的东西。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 契约词汇

#### 模型看到什么

没有任何内容。本包不贡献工具、提示词段落或会话事件——任何 `AgentBindingRecord` 或 `TaskRecord` 值都不会到达模型请求——因此没有请求字段携带其数据。

#### Token 影响

对每次请求的直接 token 影响为零。

#### KV Cache 影响

与实时请求无关：本包不触碰请求前缀，因此不可能使提供方缓存复用失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制界定了契约在何种场景下不适用或需要特别运维关注。它们是当前包约束，不是任务清单。

- **存储接缝不携带记录校验** —— `BindingStore` 与 `TaskStore` 只固定操作；每个实现必须校验从自身持久化介质读回的记录，并通过 `ProjectContractsError` 报告失败。
- **`CreationIntent.pluginScope` 是单值** —— 一次创建尝试最多命名一个插件范围；将要横跨多个范围的子代理需要另一种意图形状，当前无法表达。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
