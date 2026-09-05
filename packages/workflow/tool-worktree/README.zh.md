---
description: "面向模型的 worktree 工具：作用于调用会话自己工作区的 create、list、status、remove 与 prune（reconcile），供选择或配置 worktree 消费者的用户与维护者阅读。"
kind: "package-reference"
---

# @deepseek-ai/dsh-tool-worktree

[English](README.md) | 中文

## 概述

`dsh-tool-worktree` 基于 `ctx.worktreeRegistry` 向模型提供五个 `worktree_*` 工具：create、list、status、remove 与 prune（reconcile）。每个工具都绑定到调用会话自己的工作区——工作区来自不可变的会话头 cwd，绝不来自模型提供的 id——因此模型只能管理它所在目录的第二检出。registry 包拥有 git 机制、持久行与拒绝分类；本插件拥有 schema、授权门与面向模型的呈现。结果走普通的工具 call/result 会话事件，因此不欠任何新会话事件。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与暂缓事项](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

五个工具是 worktree seam 唯一的模型可见面。运行在已注册工作区内的会话可以为构建、实验或并行任务创建干净的检出、观察它们、删除它们，并把注册表与 git 实际报告的状态对账。目录不是已注册工作区的会话会从每个工具收到同样的授权拒绝。

### 这些工具

| 工具 | 用途 | 关键行为 |
|---|---|---|
| `worktree_create` | 添加关联 worktree 并持久登记 | `path` 必填；绝对路径照用，相对路径相对工作区目录解析。`branch` 命名一个**新**分支。 |
| `worktree_list` | 列出本工作区的登记 | 只答持久行；产品之外创建的 worktree 在被采纳前不可见。 |
| `worktree_status` | 按 id 观察一个 worktree | 目录缺失报告 `directoryExists: false`——是观察，不是错误。 |
| `worktree_remove` | 经 git 删除一个 worktree | 脏树拒绝删除，除非 `force: true`；git 成功之后才删除登记。 |
| `worktree_prune` | 把登记行与 `git worktree list` 对账 | 默认只报告；`pruneDangling: true` 丢弃过时行，`adoptUnregistered: true` 登记外部创建的 worktree。 |

### 授权

每次调用都从 `exec.agent` 的会话头 cwd 解析调用者，经规范化后与 `ctx.workspaceRegistry` 中的注册工作区匹配。没有调用 agent 的调用、头部没有 cwd 的调用、或目录不是已注册工作区的调用都会拒绝并说明原因。注册在另一工作区名下的 worktree id 与未知 id 的报告完全一致——两种情况的拒绝消息都是 `is not registered for this workspace`，模型无法通过错误差异探测其他工作区的登记。

### 拒绝与重试语义

registry 把 git 的四类拒绝方言——路径被占用、分支冲突、脏树、路径超长——分类，类型化错误文本自带具体修法，模型无需宿主帮助即可用修正后的参数重试。分类表与每类重试语义见 [worktree-registry README](../worktree-registry/README.zh.md#failure-kinds-retry-semantics-and-link-shells)；`worktree_create` 的拒绝在原因中标注类别（`path-exists`、`branch-conflict`、`path-length`）。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内幕——点击展开</summary>

本节解释授权门与呈现；可观察行为已完整覆盖于[使用本包](#use-this-package)。

### 设计概念

本插件是薄消费者：不声明配置，注册引导段落，添加五个工具——其 execute 体只做参数校验并委派给 `ctx.worktreeRegistry`（调用者解析用 `ctx.workspaceRegistry`）。git 机制、持久行与拒绝分类是 registry 包的契约，不是这里的重新实现。

### 授权顺序

每个 execute 体先运行 `resolveCaller`：拒绝缺失的 agent 或 cwd，用 `fs.realpath` 规范化头部 cwd，再与注册工作区路径匹配（Windows 上大小写折叠）。然后工具才经 `authorizedWorktree` 解析 id——对调用者工作区没有登记行的 id 会被拒绝。参数校验（`path`、`id` 非空）发生在任何 registry 调用之前。

### 呈现意图

待定调用是一张从调用参数取题的 `generic` 卡（例如 `worktree: create '<path>'`），结果保持普通 generic 卡。status 与 prune 结果附加渲染提示：目录缺失指向 `worktree_prune`，prune 报告列出悬空登记与未注册 worktree 及已应用动作的计数。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | 插件入口：引导段落、五个工具 schema、呈现、对 registry 的委派 |
| [`src/authorization.ts`](src/authorization.ts) | 从会话头解析调用者与工作区授权的 id 校验 |
| — | 不发布运行时 invariant 伴随面；本消费者不拥有独立事件流或可发散的观察——registry 校验自己的操作，工具结果走普通的 call/result 事件。 |

</details>

-----

<a id="further-exploration"></a>
## 进一步阅读

当工具级契约不够时阅读这些页面。

- [Worktree 注册表子系统](../../../docs/subsystems/worktree-registry.zh.md)——工具背后的 seam 契约。
- [Worktree registry 包](../worktree-registry/README.zh.md)——操作、持久行、拒绝分类与对账报告。
- [生成的工具目录](../../../docs/tool-catalog.zh.md#deepseek-aidsh-tool-worktree)——模型收到的准确 schema。
- [Worktree 工具 Agent Note](../../../.agents/notes/implemented/feature/2026-09-05-worktree-tools-and-reconcile.zh.md)——授权设计及其决策。

-----

<a id="model-experience"></a>
## 模型体验

### 系统提示词

#### 模型看到什么

本插件注册范围内的每个父请求都会收到下面这段固定路由引导。

##### Worktree 引导

```markdown
The worktree_* tools manage second checkouts (git worktrees) of the calling session's own workspace: they authorize against the session's working directory and cannot touch another workspace's registrations. Get ids with worktree_list before worktree_status or worktree_remove; create with worktree_create for clean builds, experiments, or parallel tasks. A worktree whose directory was deleted outside the product is recovered with worktree_prune (pruneDangling: true), and outside-created checkouts become manageable after worktree_prune (adoptUnregistered: true).
```

#### Token 影响

插件激活期间每个请求的固定小额引导开销。

#### KV Cache 影响

插件范围与引导文本不变时前缀稳定。激活或处置可能使该提示词段落的复用失效。

### 工具 schema

#### 模型看到什么

[生成的 `worktree_*` schema](../../../docs/tool-catalog.zh.md#deepseek-aidsh-tool-worktree) 暴露五个工具。`worktree_create` 接收必填 `path` 字符串与可选 `branch` 字符串；`worktree_list` 不接收参数；`worktree_status` 与 `worktree_remove` 接收必填 worktree `id`（remove 另有可选 `force` 布尔值）；`worktree_prune` 接收两个可选动作布尔值。提供方侧细节——持久行、subprocess 调用、拒绝分类——不出现在调用 schema 中。

#### Token 影响

工具可见的每个请求的固定小额 schema 开销。

#### KV Cache 影响

定义与可见性不变时前缀稳定。

### 工具结果

#### 模型看到什么

create 返回 `{ id, path, branch }`；list 返回本工作区的登记（id、规范路径、分支、创建时间）；status 返回 `{ id, directoryExists, branch?, clean? }`，目录消失时可选字段缺席；remove 与 prune 返回已应用的结局与逐条渲染文本。错误返回 isError 结果，其文本说明原因与具体修法。

#### Token 影响

list 与 prune 与工作区的 worktree 数量成正比；其余工具是单项结果。

#### KV Cache 影响

每个结果追加在可复用请求前缀之后；本包不造成前缀失效。

## 已知限制与暂缓事项

<a id="known-limitations-and-deferred-work"></a>


这些限制定义工具尚不支持的能力。它们是当前约束，不是任务清单。

- **每次调用一个工作区**——授权把每个工具锚定到调用会话的工作区；即使另一工作区已注册，模型也不能管理它的 worktree。
- **没有 move、rename 或换分支工具**——按原样暴露 registry 的 create/remove 词汇；变更既有 worktree 的位置或分支属于暂缓。
- **采纳信任 git 的清单**——`adoptUnregistered` 会登记 `git worktree list` 报告的、已知行之外的一切，不经人工确认。
- **呈现保持 generic**——所有卡片都是 `generic` 卡；专用 worktree 卡渲染器属于暂缓。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

本开发备注是维护者的工作上下文：尚未决定的开放方向。它明确不具权威性——已交付的行为、限制与已接受的理据以上方各节、包代码与所链 Agent Note 为准。

开放方向：status 与 prune 的专用卡渲染器；move/换分支操作对；以及若部署想将删除与观察分开鉴权，可加按工具的权限钩子。

</details>
