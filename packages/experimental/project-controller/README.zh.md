---
description: "拥有项目任务板的 Cordis 服务：带恢复三元组的 TaskState 流转、有界开发中任务预算、项目生命周期，以及仅限 controller 的主树合并门禁。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-controller

[English](README.md) | 中文

## Summary

`dsh-experimental-project-controller` 挂载 `ctx.projectController`，拥有项目任务板的 Cordis 服务。它让任务沿共享 `TaskState` 顺序流转（`planned → assigned → developing → reviewing → submitted → integrated → completed`），为每次 `blocked` 或 `failed` 流转强制要求原因、下一步与唤醒条件，通过经校验的 `maxActiveTasks` 配置（默认 2，与"同账号最多两路模型请求"约束对齐）限定并发 `developing` 任务数，运行 DevFrame 项目生命周期（`admission_open → stop_requested → quiescence_confirmed → stopped`，旁路状态 `needs_attention` 与 `ambiguous`），并设置主树合并门禁：只有绑定为 `controller` 的会话可以铸造合并标记，`integrate` 恰好消耗一次该标记。任务记录经 `project_tasks` 存储域持久化并在启动时原样恢复；生命周期本身是进程内运行态，新进程以 `startProject` 显式开启。

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

在存储栈与 session-identity 注册表旁挂载本服务；它硬注入 `ctx.agentBindings`（合并门禁用其校验角色）与 `ctx.storageDomain`，任一缺失即在激活时失败。

```yaml
- name: '@deepseek-ai/dsh-experimental-project-contracts'
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-project-controller'
  config:
    maxActiveTasks: 2
```

### 派发任务

每次流转返回更新后的记录；非法流转以稳定错误码大声失败，而不是重写状态。

```ts
controller.startProject()
await controller.createTask({ taskId, pluginId, title: 'Wire the gate' })
await controller.assign(taskId, workerSessionId)
await controller.startDevelopment(taskId)
await controller.beginReview(taskId)
await controller.submit(taskId)
const marker = await controller.requestMainTreeMerge(controllerSessionId, taskId)
await controller.integrate(taskId, marker)
await controller.complete(taskId)
```

`blocked` 或 `failed` 流转必须携带完整恢复三元组；`resume` 清空三元组并经 `assigned` 重新进入派发。

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

本节解释设计决策并指向实现代码；可观察行为已在 [Use this package](#use-this-package) 完整覆盖。

### 设计决策

- **双闸合并。** 合并门禁只为绑定为 `controller` 角色的会话铸造一次性、进程内的标记；`integrate` 在状态检查之前校验标记，因此已消耗的标记即使任务已流转也报 `MARKER_INVALID`。
- **预算卡在 developing 边缘。** 并发预算统计 `developing` 状态的记录，并恰好在任务要进入该状态的流转处强制；离开开发（`beginReview`）即释放名额。预算是经校验的配置字段，不是常量。
- **派发与记录分离。** 派发路径流转（`assign`、`startDevelopment`、`beginReview`、`submit`、合并、`resume`、`createTask`）要求 `admission_open`；记录性流转（`block`、`fail`、`complete`）在项目未停止前始终可用，使停止过程仍能记录工作为何结束。
- **原样冷恢复。** 任务板按持久化内容原样返回；进行中的记录需要宿主关注，因为其活动 worker 已随旧进程消亡。合并标记是进程内回执，永不恢复。

### Source map

| File | Role |
|---|---|
| [`src/controller.ts`](src/controller.ts) | `ctx.projectController` 服务：生命周期、任务流转、预算、合并门禁、恢复 |
| [`src/spec.ts`](src/spec.ts) | `project_tasks` 域声明与绑定到共享契约类型的 zod 记录 schema |
| [`src/errors.ts`](src/errors.ts) | `ProjectControllerError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |

### Invariant

不发布运行时 invariant 伴随物：任务板是一张域表的写穿投影并在启动时重建，JSON 后端拒绝同一单元的第二个活动句柄，生命周期是进程内状态且无第二观察者，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## Model Experience

### 项目控制器

#### What the model sees

没有任何内容。本包不注册工具、提示词段落或会话事件——任何 `TaskRecord` 值都不会到达模型请求——因此没有请求字段携带其数据。

#### Token effect

对每次请求的直接 token 影响为零。

#### KV Cache effect

与实时请求无关：本包不触碰请求前缀，因此不可能使提供方缓存复用失效。

## Known Limitations and Deferred Work

这些限制界定了控制器在何种场景下不适用或需要特别运维关注。它们是当前包约束，不是任务清单。

- **生命周期是进程内的** —— 重启丢失 `stop_requested`/`quiescence_confirmed` 并以 `stopped` 启动；宿主显式重新开放准入，并自行重新解读恢复出的进行中记录。
- **合并标记随进程消亡** —— 重启前铸造的标记无法完成 integrate；新进程开放准入后由控制器重新铸造。
- **预算限定任务状态，而非活动模型请求** —— `maxActiveTasks` 限制可处于 `developing` 的任务数；实际模型请求上限仍是部署的账号级约束。

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
