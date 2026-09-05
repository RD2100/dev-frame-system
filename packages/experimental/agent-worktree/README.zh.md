---
description: "每 Agent 的 worktree 能力 seam（ctx.agentWorktree），构建在 worktree registry 之上：单一写入者绑定加上面向 Agent 会话的 worktree_create/worktree_status/worktree_remove 三个工具。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-worktree

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-worktree` 是 [worktree registry](../../workflow/worktree-registry/README.zh.md) 之上的每 Agent 层：它让一个 Agent 会话拥有其工作区仓库的第二检出，且只有它能写入和移除。Service Definition（`AgentWorktree`，挂载为 `ctx.agentWorktree`）在注册表的 create/bind/status/remove 之上组合单一写入者协议；同一个包也是 Consumer，暴露 `worktree_create`、`worktree_status`、`worktree_remove` 三个工具。每次调用都授权到调用会话自己的工作区，并绑定到其持久 session id，所以新建的 worktree 从创建那一刻起就是该会话的独占写入目标，直到该会话解绑或移除。本包为实验性私有包：不出现在任何发布 bundle 中，契约可能变化。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

当插件化层级中的 Agent 会话需要带排他承诺的隔离检出时使用本包——把一个任务的改动与工作区隔离、给并行 Agent 一个独立的树。会话从不创建 worktree、或普通的工作区共享检出足够时跳过；工作区场景由 [`tool-worktree`](../../workflow/tool-worktree/README.zh.md) 工具覆盖。

### 何时使用

插件对 `ctx.tools`、`ctx.workspaceRegistry`、`ctx.worktreeRegistry`、`ctx.systemPrompt` 声明硬注入，所以只能挂载在已挂载 worktree registry 的组合里。注册表缺失不是降级模式：插件 fiber 保持 pending、不贡献任何工具，注册表一到达即激活。组合不得把本包与 `tool-worktree` 同装——三个共享工具名会重复注册，第二次加载响亮失败。

### 设置

面向 Agent 会话的最小组合：

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-subprocess-local'
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-worktree-registry'
- name: '@deepseek-ai/dsh-experimental-agent-worktree'
```

本包不接受 Config：每个选择——holder 身份、目标目录、分支——都来自调用会话或模型调用。

### 创建、观察与移除已绑定的 worktree

`worktree_create` 铸出检出并在作答前完成绑定；`worktree_status` 报告实时事实与绑定持有者；`worktree_remove` 对其他持有者拒绝，并在通往 git 的路上先释放调用者自己的绑定：

```text
worktree_create { path: 'wt-task-7', branch: 'agent/task-7' }
// → { id, path, branch } — bound to this session as its single writer
worktree_status { id }
// → { id, directoryExists, branch, clean, locked, lockedByThisSession }
worktree_remove { id }
// → { id, path } — another session's binding refuses; the holder's is released
```

同样的操作也可以经 `ctx.agentWorktree` 以编程方式触达——宿主工具策略可以把一个 worktree 绑定到它创建的会话，而不经过任何模型调用。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本节解释 seam 背后的设计决策并指向实现它们的代码；可观测行为已在[使用本包](#use-this-package)完整覆盖。

### 设计决策

- **执行点保留在注册表。** `AgentWorktree` 增加的是策略，不是第二个执行面：注册表的 `remove` 对任何已绑定 worktree 拒绝、无论调用方如何请求，本 seam 只决定何时先解绑。绕过 `ctx.agentWorktree` 的宿主会撞上同一堵墙。
- **holder 是会话的持久 id。** `WorktreeLockHolder` 对注册表保持不透明；本 seam 用调用会话的持久 id 铸造它，因此恢复后的 Agent 仍匹配自己的绑定，而同一会话里不可能出现新的 Agent 身份。
- **授权镜像会话头。** workspace 来自不可变的会话 `cwd`，绝不来自模型；该工作区没有登记行的 id 与未知 id 的报告完全一致。
- **失败以已分类错误传播。** git 拒绝以注册表的 `WorktreeGitOperationError` 类别到达（路径被占用、分支冲突、脏树、路径超长）；绑定拒绝以注册表的 `WorktreeLockError` 到达。

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | 函数插件：服务挂载、三个工具、使用指引 |
| [`src/service.ts`](src/service.ts) | 抽象 Service Definition 与 `ctx.agentWorktree` key |
| [`src/provider.ts`](src/provider.ts) | 注册表后端 provider：create+bind、按 workspace 授权的 status、先解绑再移除 |
| [`src/authorization.ts`](src/authorization.ts) | 调用方解析：会话 cwd → workspace，会话 id → holder |
| [`src/types.ts`](src/types.ts) | 请求、视图与 status 形状——仅类型 |

### Invariant

不发布运行时 invariant companion：本 seam 自身不持有任何活状态——它做出的每个保证（绑定排他、workspace 授权）都在拥有持久行与移除路径的 worktree registry 处执行并可观测，不存在可能分叉的独立观测。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### System prompt

#### 模型看到什么

本插件注册作用域内的每个父请求都会收到下面的固定指引。

##### Agent worktree 指引

```markdown
The agent worktree tools manage second checkouts (git worktrees) of the calling session's own workspace. worktree_create binds the new worktree to this session as its single writer: other sessions can observe it but cannot remove it, and it survives restarts — always worktree_remove a worktree this session created before finishing, or unbind it explicitly if another session must take it over. Get ids from the creating session or the host before worktree_status or worktree_remove.
```

#### Token 影响

插件激活期间每个请求小的固定指引成本。

#### KV Cache 影响

插件作用域与指引文本不变时前缀稳定。本提示词节的激活或卸载可能使缓存复用失效。

### 工具 schema

#### 模型看到什么

生成的 [`worktree_*` schema](../../../docs/tool-catalog.zh.md#deepseek-aidsh-experimental-agent-worktree) 暴露三个工具。`worktree_create` 接受必填 `path` 字符串与可选 `branch` 字符串；`worktree_status` 接受必填 worktree `id`；`worktree_remove` 接受必填 `id` 加可选 `force` 布尔。注册表侧细节——持久行、subprocess 调用、拒绝分类——不在调用 schema 里。

#### Token 影响

工具可见的每个请求小的固定 schema 成本。

#### KV Cache 影响

定义与可见性不变时前缀稳定。

### 工具结果

#### 模型看到什么

create 返回 `{ id, path, branch }`，渲染文本点明绑定；status 返回 `{ id, directoryExists, branch?, clean?, locked, lockedByThisSession }`，目录消失时实时字段缺省；remove 返回 `{ id, path }`。错误返回 isError 结果，文本说明原因与具体修法——包括拥有被拒绝移除的持有者。

#### Token 影响

三个工具都是单条目结果。

#### KV Cache 影响

每个结果追加在可复用请求前缀之后；本包不引入前缀失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制定义了本 seam 尚不支持什么。它们是当前约束，不是任务积压。

- **每次调用一个工作区**——授权把每个操作锚定到调用会话的工作区；即使目标 workspace 已登记，会话也无法管理其 worktree。
- **没有 list 工具**——id 从创建会话的上下文或宿主到达模型；workspace 级列表工具等到有消费方需要再做。
- **没有 unbind 工具**——会话只能通过移除 worktree 释放绑定；显式交接工具等到层级需要再做。
- **过时绑定阻塞他人**——创建后不移除就抛弃 worktree 的会话使所有其他会话无法移除，直到绑定持有者行动或该行经注册表的 reconcile 丢弃。
- **呈现保持 generic**——每张卡都是 `generic` 卡；专用的 worktree 卡渲染器延期。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

开放方向：层级 worktree 交接所需的显式 unbind/交接工具对；有消费方需要时的 workspace 级 list 工具；session-identity 落地后把 holder 接到 P01 的 `AgentBindingRecord.worktreeId`。

</details>
