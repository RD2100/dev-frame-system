---
description: "把防御性停止、准入切断、不确定调用对账与刷写屏障模式产品化的 Cordis 服务。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-reliability

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-reliability` 挂载 `ctx.agentReliability`，把代理工作接缝所需的防御性模式实践化为 Cordis 服务：DevFrame 进程树停止以一次序列化调用呈现——先关准入、只取消已知后代、刷写完成前不释放写者；派发前置步骤（`assertAdmitted`）拒绝一切工作绑定与当前准入身份不匹配的操作；不确定调用对账先查外部状态、最多重试一次且仅在探测证明效果缺失后重试；刷写屏障在刷写失败时关闭准入并保留写权。准入是默认关闭的进程内状态。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在插件集任意位置挂载本服务；它零注入、只持有进程内准入状态，永不阻塞激活。

```yaml
- name: '@deepseek-ai/dsh-experimental-agent-reliability'
```

### 接线派发前置步骤

派发代际开始时为恰一个工作绑定身份打开准入，并把 `assertAdmitted` 设为每次派发的第一步；不匹配或过期的绑定在任何模型/工具工作开始前即被拒绝。

```ts
ctx.agentReliability.openAdmission({ controllerSessionId, goalId })
// inside the dispatch path, before any work:
ctx.agentReliability.assertAdmitted(identity)
```

### 对账一次不确定调用

调用结果未知时，把计划交给对账器：探测先查外部状态，重试最多执行一次、且仅在探测证明效果缺失后执行。

```ts
const outcome = await ctx.agentReliability.reconcileUncertainCall({
  operation: 'create-worktree',
  probe: async () => await probeExternalState(operationId),
  retry: async () => await createWorktree(request),
})
```

### 给刷写设屏障

失败的刷写会关闭准入并保留写权；绝不在未刷写的日志上释放写者。

```ts
const barrier = await ctx.agentReliability.flushBarrier(flushSessions)
if (!barrier.flushed) reportFlushFailure(barrier.failure)
```

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释设计决策并指向实现代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **产品化，而非复制。** 进程树停止就是 DevFrame reliability 模块的 `stopProject`，经服务原样转发——停止契约（先准入、记录持久观察、先静默后刷写、日志干净才释放写者）只有一个实现、一个测试归属。
- **默认关闭的准入。** 新进程准入从关闭开始，只为一个显式身份打开；前置步骤以不同的稳定错误码区分"关闭"与"身份不匹配"，派发接线得以分辨"从未准入"与"错误代际"。
- **探测拥有重试决定权。** `reconcileUncertainCall` 构造上不存在盲目重试路径：重试最多调用一次，且仅在探测返回 `absent` 之后。`confirmed` 仅凭探测即可结算；`still_uncertain` 返回未解决且不重发——未 resolve 的调用由调用方决定含义。
- **刷写屏障保留写者。** 失败的刷写立即关闭准入并报告 `writerRetained: true`；释放写权是宿主的动作，本接缝使"在未刷写日志上释放"无法发生。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/service.ts`](src/service.ts) | `ctx.agentReliability` 服务：前置步骤、对账器、刷写屏障、停止转发 |
| [`src/errors.ts`](src/errors.ts) | `AgentReliabilityError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口、默认导出与停止契约转发导出 |

### 不变式

不发布运行时 invariant 伴随物：准入是一对无持久投影的进程内字段，对账器在调用之间不持状态，刷写屏障的效果（准入关闭、写者保留）经由产生它们的同一服务实例即可观察，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 代理可靠性服务

#### 模型看到什么

没有任何内容。本包不注册工具、提示词段落或会话事件——任何 `ReconciledOutcome`、`FlushBarrierResult` 或 `StopResult` 值都不会到达模型请求——因此没有请求字段携带其数据。

#### Token 影响

对每次请求的直接 token 影响为零。

#### KV Cache 影响

与实时请求无关：本包不触碰请求前缀，因此不可能使提供方缓存复用失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制界定了本服务在何种场景下不适用或需要特别运维关注。它们是当前包约束，不是任务清单。

- **准入是进程内且默认关闭的** —— 重启丢失已准入身份，宿主显式重新打开准入前所有前置步骤都会拒绝。
- **对账器信任其探测** —— `absent` 与 `confirmed` 的答案只与调用方提供的外部状态检查同等可靠；服务无法核实探测检查的是对的资源。
- **停止原样转发 DevFrame 契约** —— 未解决身份、写者保留与重启对账遵循 DevFrame 停止语义；本服务不添加自己的持久停止状态。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
