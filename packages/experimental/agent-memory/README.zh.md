---
description: "面向 DSH Agent 的持久化情节、语义与程序记忆，提供作用域隔离、来源、生命周期、有界上下文组装、遗忘、冲突处理与召回追踪。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-memory

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-memory` 让 Agent 在任务之间携带经过选择的经验。它复用 DSH 现有的 storage-domain 层保存情节、带来源的语义事实、程序候选和召回追踪。召回按显式作用域过滤，对当前 active 记录排序，并且只组装能放进上下文预算的记录。缺少存储后端时插件仍然可以挂载，但会报告 `MEMORY_UNAVAILABLE`，主任务可以继续执行。

## 目录

- [使用本包](#use-this-package)
- [记忆生命周期](#memory-lifecycle)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在已经提供存储栈的组合中挂载服务。没有存储时服务也能加载，并把失败明确返回。

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: /var/lib/dsh/memory
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-experimental-agent-memory'
  config:
    workspaceId: dsh
    contextBudgetBytes: 12000
    autoRetrieve: true
```

服务位于 `ctx.agentMemory`。主要 API 是 `retrieveContext`、`recordEpisode`、`upsertFact`、`registerProcedure`、`forget`、`inspectTrace` 和 `consolidate`。

```ts
const context = await ctx.agentMemory.retrieveContext({
  query: 'database migration',
  scope: { workspaceId: 'dsh', projectId: 'harness' },
  budgetBytes: 4000,
})
```

模型工具为 `memory_retrieve`、`memory_record_episode`、`memory_upsert_fact` 与 `memory_forget`。记忆文本以带追踪 ID 的数据注入，不会授予指令、权限或工具。

<a id="memory-lifecycle"></a>
## 记忆生命周期

语义事实带有来源和权威级别。同一作用域、主体与谓词下，更强来源会替代 active 的弱来源。相同权威的不同结论会把所有竞争事实标记为 `conflicted`；召回会排除冲突、被替代、过期、归档和删除的记录。推断事实默认是 `candidate`；更强来源的事实可用一条 active 记录取代其结论。`memory_forget` 会永久删除一条记录。程序注册默认是 `candidate`，`consolidate` 只从重复情节提出候选，不自动晋升。

每次召回都会写入追踪，记录选中的 ID、分数、注入 ID 与原始查询。作用域比较要求所有给出的作用域部分一致；不同工作区会在服务边界被拒绝。

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节</summary>

本包声明一个 `agent_memory` 存储域，包含 `episodes`、`facts`、`procedures` 与 `traces` 四个按记录存储的表。服务用内存 Map 做同步排序，同时所有修改都通过领域表持久化。`agent/pre-step` 监听器在已接受的请求开始时召回上下文，并追加带来源的用户消息，遵守 DSH 的“模型可见即已记录”规则。

存储打开采用尽力策略。缺少设施或领域打开失败时记录不可用状态；工具返回稳定错误，准备步骤保持普通消息不变，因此存储故障不会停止无关任务。

</details>

<a id="model-experience"></a>
## 模型体验

### 有界记忆召回

#### 模型看到什么

启用后，模型会看到四个记忆工具，并可能在请求开始收到一条带来源、有预算的上下文消息。事实、情节和程序都标明为数据，消息带有追踪 ID 便于诊断。凭据和类似凭据的文本在写入边界被拒绝。

#### Token 影响

工具模式和固定的召回消息会增加少量提示词开销。召回内容由 `contextBudgetBytes` 限制；候选超过预算时返回截断标记。

#### KV Cache 影响

插件配置不变时，工具模式和静态来源标记保持前缀稳定。召回上下文位于正常请求历史之后，只随相关记忆变化。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与延期工作

- 召回使用确定性的词法匹配。Embedding 和向量索引留待实测证明召回需要后加入。
- 未启用从任意模型输出自动提取情节；调用方要记录有界的结构化情节。
- Consolidation 只返回程序候选，不自动晋升。
- 作用域权限由宿主提供的身份表示；需要文件级 ACL 的集成必须在调用服务前验证来源。

<a id="dev-note"></a>
### 开发备注

无。
