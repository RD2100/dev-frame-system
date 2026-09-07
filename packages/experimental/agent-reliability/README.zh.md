---
description: "把防御性停止、准入切断、不确定调用对账与刷写屏障模式产品化的 Cordis 服务。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-reliability

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-reliability` 挂载 `ctx.agentReliability`，把代理工作接缝所需的防御性模式实践化为 Cordis 服务：DevFrame 进程树停止以一次序列化调用呈现——先关准入、只取消已知后代、刷写完成前不释放写者；派发前置步骤（`assertAdmitted`）拒绝一切工作绑定与当前准入身份不匹配的操作，且当代际附有 epoch 截止时，从截止时刻（含）起拒绝一切派发；不确定调用对账先查外部状态、最多重试一次且仅在探测证明效果缺失后重试；刷写屏障在刷写失败时关闭准入并保留写权。准入是默认关闭的进程内状态。

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
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'
import type { GoalBindingIdentity } from '@deepseek-ai/dsh-experimental-devframe/controller'

function startGeneration(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.openAdmission(identity)
}

function beforeDispatch(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.assertAdmitted(identity)
}
```

### 以截止时刻限定准入

打开准入时附上 epoch 毫秒截止时刻即可限定派发代际：前置步骤在每次派发时读取墙钟（`Date.now()`），从 `deadline` 时刻（含）起以 `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` 拒绝。恢复唯显式重开新代际；非有限截止在打开处明确失败，不触碰当前代际。

```ts
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'
import type { GoalBindingIdentity } from '@deepseek-ai/dsh-experimental-devframe/controller'

function startBoundedGeneration(ctx: { agentReliability: AgentReliability }, identity: GoalBindingIdentity) {
  ctx.agentReliability.openAdmission(identity, { deadline: Date.now() + 60_000 })
  // From the deadline (inclusive), assertAdmitted rejects dispatch.
}
```

需要停止在途工作时，把宿主当前代际的 `StopProjectOptions` 作为 `openAdmission(identity, { deadline, stop })` 的 `stop` 字段传入。定时器到期先关闭服务准入，再调用既有 `stopProject`；清理与 flush 确认后才释放写权。`deadlineStopResult` 在触发后提供结果。未确认的资源保留 `needs_attention`。

显式关闭或重开会撤销尚未触发的定时器。停止期间重开抛出 `AGENT_RELIABILITY_STOP_IN_PROGRESS`，防止旧释放回调作用于新代际。服务释放清除定时器并等待已触发的有界停止。定时器不维持 Node 进程存活；在截止前退出的进程不会运行截止清理。宿主从经验证的 Config 提供截止与 grace，以及真实 Agent、job、持久化和 writer 适配；省略 `stop` 时仅执行原有派发前检查。

### 对账一次不确定调用

调用结果未知时，把计划交给对账器：探测先查外部状态，重试最多执行一次、且仅在探测证明效果缺失后执行。

```ts
import type {
  AgentReliability, ReconciliationProbe,
} from '@deepseek-ai/dsh-experimental-agent-reliability'

async function reconcileWorktree<R>(
  ctx: { agentReliability: AgentReliability },
  probeExternalState: () => Promise<ReconciliationProbe>,
  createWorktree: () => Promise<R>,
) {
  return await ctx.agentReliability.reconcileUncertainCall({
    operation: 'create-worktree',
    probe: probeExternalState,
    retry: createWorktree,
  })
}
```

### 给刷写设屏障

失败的刷写会关闭准入并保留写权；绝不在未刷写的日志上释放写者。

```ts
import type { AgentReliability } from '@deepseek-ai/dsh-experimental-agent-reliability'

async function flushBeforeRelease(
  ctx: { agentReliability: AgentReliability },
  flushSessions: () => Promise<void>,
  reportFlushFailure: (failure: unknown) => void,
) {
  const barrier = await ctx.agentReliability.flushBarrier(flushSessions)
  if (!barrier.flushed) reportFlushFailure(barrier.failure)
  return barrier
}
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
- **截止缝在前置步骤强制执行，而非存储态。** `openAdmission` 可附截止，非有限截止在打开处明确失败且不触碰当前代际；从截止时刻（含）起，前置步骤先于身份检查以 `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` 拒绝——截止已过是对窗口的陈述，非对身份的陈述。`admissionState` 仍报告存储的代际决定（`'closed' | 'open'`）；未提供 `stop` 时仅由派发闸门执行截止；提供 `stop` 后定时器显式关闭准入。恢复需在停止结束后显式重开新代际。

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
- **自动停止依赖真实宿主适配** —— 未提供 `cutoff.stop` 的部署只拒绝后续派发。项目验收必须覆盖实际宿主与持久写锁。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
