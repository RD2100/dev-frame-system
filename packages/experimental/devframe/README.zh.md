---
description: "协调首个 DSH 原生 DevFrame 项目边界：在清理和持久化完成后才释放单一工作身份与已拥有执行的写入权。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-devframe

[English](README.md) | 中文

## 概述

`dsh-experimental-devframe` 提供 DSH 原生项目控制器使用的少量库契约。调用方可以在派发、证据和完成之间携带同一个工作区、Goal、验收和源代码身份。调用方也可以停止已拥有的 agent、job 和进程句柄，并在清理和最后一次持久化刷新完成前保留写入权。它还把三层 spawn 策略——总控建组长、组长建执行 Agent、执行 Agent 禁建子 Agent——固化为分离的委托请求覆盖值。本包是私有实验性库：不注册 Cordis 插件，也不提供面向模型的工具。

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

当项目控制器已经拥有 DSH 原生会话、Goal、job 和持久化时，从控制器调用本库。本库提供跨模块工作绑定的值类型和一个停止操作；它不会创建项目、挂载 profile 或替代原生状态所有者。

### 停止已拥有的工作

把控制器的实时句柄和所有权回调传给 `stopProject`。函数会关闭接收、请求取消、在给定宽限期内等待、刷新观察到的状态，并且只在所有必需资源结算后调用 `releaseWriter`。

```ts
import { stopProject, type StopProjectOptions } from '@deepseek-ai/dsh-experimental-devframe'

declare const options: StopProjectOptions
const result = await stopProject(options)
```

未解析的进程身份、超时、操作失败或刷新失败都会返回 `needs_attention`，并把写入权释放留给所有者。因此只有成功结果才允许调用方把项目交给另一个写入者。

### 携带一个工作绑定

宿主验证对应值后，使用带 brand 的构造函数。这个绑定就是派发、验证、审查和完成必须接收的同一身份。

```ts
import {
  AcceptanceHash, SourceFingerprint, WorkspaceId,
  type ProjectWorkBinding,
} from '@deepseek-ai/dsh-experimental-devframe'

const binding: ProjectWorkBinding = {
  workspaceId: WorkspaceId('workspace-1'),
  controllerSessionId,
  goalId,
  goalRevision: 1,
  acceptanceHash: AcceptanceHash('approved-config-digest'),
  sourceFingerprint: SourceFingerprint('source-digest'),
}
```

宿主负责验证和持久化。验收值或源代码值发生变化就构成不同绑定，不能复用早先的证据。

### 组装三层 spawn 策略

DevFrame 父 Agent spawn 子 Agent 时，把 `devframeSpawnOverrides(tier)` 展开进委托请求。组长只携带深度预算；执行 Agent 还会失去委托工具，由子 Agent 自己的执行器拒绝（`UNKNOWN_TOOL`），并且持久描述符会在冷恢复时重新应用过滤器。

```ts
import { devframeSpawnOverrides } from '@deepseek-ai/dsh-experimental-devframe'

// { maxDepth: 2, toolFilter: { deny: ['subagent'] } } spread into the
// delegation request; devframeSpawnOverrides('lead') is { maxDepth: 2 }.
const overrides = devframeSpawnOverrides('worker')
const request = { prompt: [], parent: leadAgent, ...overrides }
```

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>

<summary>实现细节——点击展开</summary>

`stopProject` 是有界编排辅助函数。它使用调用方提供的原生 Agent、Goal、Job、subprocess 和 timeout 接缝。它在取消前记录 `stopping`，在排空后记录 `quiesced` 或 `needs_attention`，然后刷新，最后释放写入权。它不会根据丢失的进程内 mutex 或未验证的进程身份推断已经静默。

共享类型把项目绑定、配置确认、生命周期状态和持久化接缝放在一个包中。它不新增 Run 数据库，也不复制原生任务、会话全文或 Goal 状态。

### 完成准入守卫原生 Goal 生命周期

`GoalBindingController.complete` 是完成的生产调用点：它解析精确绑定、在尝试期间关闭准入，并按固定证据链序求值——先对绑定自身记录的指纹做指纹比对，再对 store 登记的配置做必需检查，最后看授权审查。拒绝以数据返回且原生 Goal 不被触碰，继续工作必须经人类授权的 resume。准入通过后经 `NativeGoalPort` 缝完成原生 Goal——`GoalServicePort` 把每个动词委托给其绑定 Agent 上的活 `ctx.goals` 服务——并把绑定持久化为服务返回的 revision。结构失败，包括不可用指纹、未登记 digest、外来身份和归属另一 Goal 的审查证据，都 fail-loud 抛出，绝不转换为拒绝。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | 停止操作和共享契约的库入口 |
| [`src/controller/goal-binding.ts`](src/controller/goal-binding.ts) | Goal 绑定控制器、完成准入合取与生产原生 Goal 服务端口 |
| [`src/hierarchy/index.ts`](src/hierarchy/index.ts) | 总控 → 组长 → 执行树各档的 spawn 覆盖值 |
| [`src/permissions/events.ts`](src/permissions/events.ts) | 持久化角色和策略身份事件契约 |
| [`src/reliability/stop.ts`](src/reliability/stop.ts) | 接收截止、已拥有取消、有界排空和写入权释放 |
| [`src/required-checks-file-store.ts`](src/required-checks-file-store.ts) | 文件后备必需检查登记存储：digest → 配置 JSON 账本的 durable 边界 |
| [`src/required-checks.ts`](src/required-checks.ts) | 必需检查配置 schema、规范 digest、完成判定与 digest → 配置登记存储 |
| [`src/shared/types.ts`](src/shared/types.ts) | 带 brand 的工作身份和绑定持久化接口 |
| [`src/source-fingerprint.ts`](src/source-fingerprint.ts) | 只读 worktree 指纹引擎与显式 verify 比对面 |
| [`tests/hierarchy-roles.spec.ts`](tests/hierarchy-roles.spec.ts) | 各档 spawn 覆盖值策略覆盖 |
| [`tests/reliability/stop.spec.ts`](tests/reliability/stop.spec.ts) | 单元测试和真实已拥有进程停止覆盖 |
| [`../../experimental/agent-team/tests/devframe-composition.spec.ts`](../agent-team/tests/devframe-composition.spec.ts) | Team、Goal、dispatcher 和 JSONL 的真实组合基线 |

不发布运行时不变量 companion，因为本包不注册 Cordis 插件，也不拥有可由独立观察者检查的运行时关系；事件、投影和生命周期测试直接覆盖库操作。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

- [单项目设计](../../../docs/detailDesign-part1.zh.md)——工作身份、证据、角色和完成前提。
- [可靠性设计](../../../docs/detailDesign-part4.zh.md)——停止、恢复、预算和写入所有权。
- [Team 包](../agent-team/README.zh.md)——原生 roster、mailbox 和任务所有权。

-----

<a id="model-experience"></a>
## 模型体验

### 仅限宿主的项目编排

#### 模型看到的内容

无。本库不注册面向模型的工具、提示词区块或模型请求；`stopProject` 和共享绑定只在宿主侧运行。

#### Token 影响

每次请求不增加模型 token。本包不添加消息、工具 schema 或请求字段。

#### KV Cache 影响

无。宿主侧调用不会改变模型请求前缀。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

- **接收和持久化由调用方拥有**——本库不会发现项目根目录、创建 Goal 或追加自己的会话事件。
- **完成裁定不落日志**——控制器把准入裁定返回给调用方；记录裁定或完成回执、以及组合 `GoalServicePort` 的宿主命令面，仍属延期的宿主组合工作。
- **进程句柄必须经过验证**——缺失或不确定的句柄会保留为 `needs_attention`；辅助函数绝不会按可执行文件名或复用的 PID 杀进程。
- **单进程协调**——这些契约不提供跨进程锁、分布式投递或恶意代码隔离。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

本包是实验性单项目流程的首个共享边界。控制器、权限和生命周期组从各自模块消费这些契约；profile 组合和用户命令仍是独立工作。

</details>
