---
description: "每工作区 git worktree 注册表（ctx.worktreeRegistry），供选择、挂载或调试工作区仓库受管第二检出的 host 使用。"
kind: "package-reference"
---

# @deepseek-ai/dsh-worktree-registry

[English](README.md) | 中文

## 概述

`dsh-worktree-registry` 给 host 一个持久的、每工作区的 git worktree 注册表：由产品创建、跟踪、并可再次删除的工作区仓库第二检出。有了它，消费方可以为某个 workspace 创建干净或隔离的检出、跨重启列出每个 workspace 名下的检出、观察每个检出是否干净及其所在分支、删除它——删除先经 git 删检出，再删登记，顺序永不颠倒——并把登记与 `git worktree list` 报告的状态对账。本包只在 host 侧：模型、工具与 agent loop 都看不见它，因此不增加任何 token、提示词或请求上下文。它需要 workspace registry、subprocess provider 和存储行一并挂载；组装只需几行配置。

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

当产品需要管理工作区仓库的第二检出时使用本包——workspace 里留有未提交改动时用一个干净树构建、给实验一个隔离树、给后台工作一个并行树。本包登记并跟踪这些检出；它对模型不可见，不增加 token 或请求成本。产品从不创建 worktree 时可跳过；harness 里没有其他东西需要它。

### 何时使用

provider 对 `ctx.workspaceRegistry`、`ctx.subprocess`、`ctx.storageDomain` 声明硬注入，所以它只能挂载在同样挂载 workspace 栈的组合里——web-app bundle 把它挂在 workspace 行旁边。想要 worktree 却没有 workspace 的组合会在激活期失败，而不是悄悄存下无锚点的行。

### 设置

provider 接受可选 Config，共五个经过校验的字段——`gitPath`、`timeoutMs`、`maxTimeoutMs`、`graceMs`、`maxOutputBytes`——默认值适配本地 git。最小的 web 层组合：

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-worktree-registry'
```

每次 git 调用都经过挂载的 `ctx.subprocess` provider；base bundle 的 `@deepseek-ai/dsh-subprocess-local` 提供它。行存在 `worktree_registry` 存储域里，跨重启存活。

### 创建与观察 worktree

为 workspace 创建 worktree：给出 workspace id 和目标目录，本包从 workspace 目录运行 `git worktree add`，记录规范路径与 git 实际创建的分支，并返回登记。随时观察它；被产品之外删除的检出报告 `directoryExists: false` 而不是失败：

```text
// Host consumer code, after the composition above is loaded:
const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: '/path/to/wt' })
ctx.worktreeRegistry.list(workspaceId) // that workspace's registrations, stable order
await ctx.worktreeRegistry.status(worktree.id) // { directoryExists, branch, clean }
```

### 删除 worktree

检出不再需要时删除登记：本包先运行 `git worktree remove`，git 成功之后才删持久化行。有改动或未跟踪文件的检出拒绝删除，除非传 `force: true`（对 git 传 `--force`）。删除绝不触碰 workspace 记录或仓库历史。

### 对账登记与 git

登记行与 git 自身的元数据可能漂移：目录在产品之外被删会留下没有检出的行，绕过 git 的删除会让 git 跟踪一条死路径，产品之外创建的 worktree 对注册表一无所知。`reconcile(workspaceId)` 把 workspace 的行与 `git worktree list` 对比并报告差异——`dangling` 行（`directory-missing` 或 `git-unknown`）与 `unregistered` 的 git 跟踪 worktree——默认不做任何修改：

```text
const report = await ctx.worktreeRegistry.reconcile(workspaceId)
// { dangling: [{ id, path, reason }], unregistered: [{ path, branch? }], removedRows: [], adoptedPaths: [] }
```

两个可选动作作用于报告。`pruneRows: true` 删除悬空行（绝不删目录或文件），并在被删行的目录缺失时运行一次 `git worktree prune`，让 git 不再列出死的 admin 条目。`adoptUnregistered: true` 以规范路径与观测到的分支（detached 时为 `HEAD`）登记每个未注册 worktree——仓库主检出与已登记在另一 workspace 名下的 worktree 永不会被采纳或报告。检测是即时的，并与 create/remove 一起在 provider 的操作链上串行。

<a id="failure-kinds-retry-semantics-and-link-shells"></a>

### 失败类别、重试语义与链接壳

provider 能识别的 git 拒绝分为四类；每个错误都是 `WorktreeGitOperationError`，携带调用事实、git 的 stderr 与补救建议：

| Kind | git 拒绝的原因 | 错误携带的补救 |
|---|---|---|
| `path-exists` | 目标目录已存在且非空 | 换一个目标目录，或复用/清理已有目录 |
| `branch-conflict` | 同名分支已存在 | 换分支名，或不带 `-b` 复用已有分支 |
| `dirty-tree` | worktree 有改动或未跟踪文件 | 以 `force: true` 重试删除，或先清理 worktree |
| `path-length` | 路径超出当前 git 配置的路径长度上限 | 换更短路径，或 `git config core.longpaths true` |

重试语义：任何东西都不会自动重试。被拒绝的操作是确定性的——不改变参数的重试会再次失败。失败的尝试绝不留下登记行，也绝不留下 worktree（`remove` 只在 git 成功后才删行），所以修正后的重试从干净状态开始。`path-length` 拒绝时 git 可能在磁盘上留下空的前导目录；注册表既不登记也不删除它们。

链接壳契约（symlink 与 junction）：注册表从不创建 symlink 或 junction。它记录的每个路径都在目录存在之后经 `fs.realpath` 规范化，所以经由 junction 或 symlink 拼写到达的 worktree 以其物理目标登记，同一目录的两种拼写就是同一登记——经由别名创建已有 worktree 的尝试以已登记失败，而不是重复登记。`reconcile` 以同样方式规范化 git 报告的路径再比较，所以存储了链接拼写的 git 元数据仍能匹配到行。Windows 路径比较折叠大小写；git 的正斜杠输出与登记的反斜杠路径视为相等。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释功能背后的设计决策并指向实现它们的代码；可观察行为已完整覆盖在[使用本包](#use-this-package)。

### 设计理念

- **uuid 是锚点，路径是事实。** worktree 路径会被规范化与 git 本身改写，所以行以生成的 `WorktreeId` 为 key，存储创建之后观测到的规范路径。
- **独立的域，不挂 WorkspaceRecord 字段。** worktree 生命周期是 git 机制，不是 workspace 的 session 记账；行存在本包的 `worktree_registry` 域，归属关联是一个 `workspaceId` 字段，在操作时经 `ctx.workspaceRegistry` 校验。
- **观测事实优先于假设。** 存储的分支是从新 worktree 读回的，存储的路径是创建后的 `fs.realpath`，`status` 只报告 git 当下报告的内容。
- **注册表是登记的权威。** `list` 从持久化行作答；git 自身元数据与之相悖时，`reconcile` 报告差异并仅在被要求时修复。
- **对账默认只动登记侧。** 删行绝不删目录或文件，采纳绝不改写 worktree——动作只把产品的记录对齐到已存在的事实上。
- **删除 git 优先。** `git worktree remove` 成功之后才删持久化行，所以失败的删除绝不会掩盖一个真实存在的检出。

### API 行为

seam 拆成抽象的 `WorktreeRegistry` Service Definition 与组合加载的 `GitWorktreeRegistry` provider。逐方法契约在代码里——见 [src/registry.ts](src/registry.ts) 与 [src/git-provider.ts](src/git-provider.ts)。provider 在单条操作链上串行化自身变更；行写入在域的写链上排队。

### 源码地图

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | 包入口：导出、`WorktreeId` 工厂、provider 的 default export |
| [`src/registry.ts`](src/registry.ts) | 抽象 Service Definition 与 `ctx.worktreeRegistry` key |
| [`src/git-provider.ts`](src/git-provider.ts) | 本地 git provider：配置校验、经 `ctx.subprocess` 跑 git、五个操作 |
| [`src/porcelain.ts`](src/porcelain.ts) | `git worktree list --porcelain -z` 解析与对账用的路径比较 |
| [`src/spec.ts`](src/spec.ts) | 域声明：记录 schema 与 `defineDomain` spec |
| [`src/types.ts`](src/types.ts) | 公共词汇：`WorktreeId`、请求、worktree、status 与对账类型 |

### 持久形态

provider 打开 `worktree_registry` 域（version 1）：一张以 `WorktreeId` 为 key 的 `worktrees` 表，带 `workspaceId`、规范 `path`、观测的 `branch` 和 ISO-8601 时间戳。没有 global 状态——list 顺序每次读取时从记录字段推导。

### 生命周期

启动时 provider 打开自己的域并把句柄生命周期绑到它的 fiber。处置时域关闭，服务从 context 卸载，之后的组合从头基于已存储的行启动。没有 bootstrap：新域就是空注册表。

### 失败与恢复

未知 workspace、非 git 的 workspace 目录、已登记路径、git 自身的拒绝，全部带着 git 的 stderr 拒绝；没有任何东西被吞掉。两步删除有一个已知的窗口——git 已删 worktree 但行删除失败——表现为指明两个事实的响亮错误，同时 `status` 报告目录缺失；用 `reconcile` 加 `pruneRows` 可回收悬空行。

### 不变量

不发布运行时不变量伴随件：provider 没有第二缓存（读取直接落到持久化表）、域 schema 在重开时重新校验行、不存在可能发散的独立观测。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

- [Worktree registry Agent Note](../../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.zh.md)——seam 设计：身份、持久化状态归属、会话事件分析与含 reconcile 的 git 命令映射。
- [Worktree 工具 Agent Note](../../../.agents/notes/implemented/feature/2026-09-05-worktree-tools-and-reconcile.zh.md)——consumer 包的授权与 schema 决策。
- [Capability seams](../../../docs/architecture.zh.md)——本包遵循的 Service Definition / Service Provider / Consumer 模型（"能力 seam"一节）。
- [Workflow package map](../README.zh.md)——组内各包及其仓库位置。

-----

<a id="model-experience"></a>
## 模型体验

### Worktree 登记

#### 模型看到什么

没有。`ctx.worktreeRegistry` 只服务 host 侧消费方：本包不注册工具、不注入提示词、不写会话事件，所以任何请求字段都不会携带本包的数据。

#### Token 影响

每个请求的直接 token 为零。

#### KV Cache 影响

与实时请求无关：本包绝不触及请求前缀，因此不会使提供方缓存复用失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制定义了注册表何时不适用或需要特殊运维关注。它们是当前包约束，不是任务积压。

- **还没有消费方**——模型可见的 `worktree_*` 工具与任何 host UI 都是后续工作；已交付组合挂载了 provider，但没有任何东西调用它，所以服务 API 之外没有产品面。
- **对账从不删除树**——删行与采纳登记是仅有的动作；需要物理删除的 worktree 仍走 `remove`（或用户自己动手）。
- **删除需要归属方**——删除 worktree 时归属 workspace 登记必须仍存在；删除 workspace 会卡住其 worktree 行的删除，直到 workspace 重新登记或该行经 reconcile 删除。
- **采纳信任 git 的列表**——被采纳的 worktree 记录观测到的分支；detached HEAD 记为 `HEAD`，注册表不解析 detached HEAD 指向什么。
- **一个删除失败窗口**——git 已删 worktree 而行删除失败时，行保留并报告目录缺失；之后用 `reconcile` 加 `pruneRows` 可回收。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
