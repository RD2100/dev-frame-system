# Agent Note: 每工作区 git worktree 注册表能力 seam

Status: implemented

[English](2026-09-05-worktree-registry.md) | 中文

## 问题

在某个 workspace 里工作的 agent 需要同一仓库的第二份检出：workspace 里留有未提交改动时用一个干净树跑构建、给实验性重构一个隔离树、给后台任务一个并行树。Git 已有机制——链接 worktree——但 harness 没有任何东西 owning 它：

- 每个消费方都得走 shell 能力拼 `git worktree` 命令并手写输出解析。没有任何包登记哪些 worktree 存在、各属于哪个 workspace、哪些可以安全删除，于是状态只存在于调用方的对话里，随会话消失。
- 没有任何东西把 worktree 关联到 `WorkspaceId`。workspace 实体是"用户工作的目录"这个产品锚点；worktree 是 per-workspace 事实，模型可见面需要这条关联才能呈现并约束它们。
- 没有任何东西支持换执行世界。经沙箱或远端 provider 创建的 worktree 必须遵守与本地的同一个注册表契约。

本 note 拥有承载这些事实的 seam：一个 per-workspace 的 git worktree 注册表，含 create/bind/list/status/remove/reconcile、一个本地 git provider、这些行的持久化归宿，以及面向模型的 consumer 包。

## Decision

包 `packages/workflow/worktree-registry`（`@deepseek-ai/dsh-worktree-registry`）承载 Service Definition 与 Service Provider；包 `packages/workflow/tool-worktree`（`@deepseek-ai/dsh-tool-worktree`）是面向 workspace 的 Consumer，持有[工具决策](../feature/2026-09-05-worktree-tools-and-reconcile.zh.md)；实验性包 `packages/experimental/agent-worktree` 是每 Agent 的 Consumer，把每个新建 worktree 绑定到唯一写入者，持有[单一写入者绑定决策](../feature/2026-09-05-per-agent-worktree-single-writer-seam.zh.md)。registry 沿用 `dsh-shell` 模板：抽象 Service Definition 声明接口，具体 provider 类实现它，包的 default export 是 Loader 挂载的 provider。

| 角色 | 元素 | 说明 |
| --- | --- | --- |
| Service Definition | `WorktreeRegistry`（抽象类，具名导出） | 声明 create/bind/list/status/remove/reconcile、记录词汇表和 `ctx.worktreeRegistry` 这个 key。 |
| Service Provider | `GitWorktreeRegistry`（default export） | 经 `ctx.subprocess` 运行 `git`，拥有持久化行。每个 context 一个 provider；二次注册经 cordis 的重复服务规则 fail loud。 |
| Consumer | `tool-worktree` | 面向 workspace 的 `worktree_*` 工具；授权与 schema 决策见[工具与对账 Agent Note](../feature/2026-09-05-worktree-tools-and-reconcile.zh.md)。 |
| Consumer | `agent-worktree`（实验性，私有） | 建立在单一写入者绑定之上的每 Agent `worktree_create`/`worktree_status`/`worktree_remove` 工具；见[绑定 Agent Note](../feature/2026-09-05-per-agent-worktree-single-writer-seam.zh.md)。 |

### 身份

`WorktreeId = Branded<'WorktreeId'>` 来自 `@deepseek-ai/dsh-brand`，取值为生成的 uuid。路径绝不作 key：worktree 路径会被规范化、被 git 本身改写，引用锚点必须稳定——与 `WorkspaceId` 用 uuid 的理由相同。品牌放在本包，因为铸造和使用它的是本包。单一写入者的绑定标记以同样方式加品牌（`WorktreeLockHolder = Branded<'WorktreeLockHolder'>`）；注册表只存储与比较它、从不解释它，所以铸造它始终是调用方的决定。

### 持久化状态：独立 KvTable，不挂 WorkspaceRecord

注册表打开自己的存储域 `worktree_registry`（version 2），一张表 `worktrees`，以 `WorktreeId` 为 key。记录携带 `workspaceId`（归属锚点）、`path`（规范路径，来自 `git worktree add` 成功后观测的 `fs.realpath`）、`branch`（create 时观测到的 HEAD，不是调用方的假设）、`createdAt`、`updatedAt`，以及可选的 `lockedBy`/`lockedAt` 绑定字段对——record schema 要求它们成对出现，绑定作为一个事实整体写入读取。version 2 新增绑定字段对；version 1 盖章的介质按预发布立场在打开时拒绝，绝不在新 schema 下半读。

这些行刻意不扩展 `WorkspaceRecord`：

- **归属内聚。** worktree 生命周期是 git 与 workflow 机制。workspace 域回答"哪些 session 在这个目录里跑过"；worktree 行回答"这个 workspace 存在哪些第二检出"。问题不同、写入方不同、演进时钟不同。
- **单写入方纪律。** `dsh-workspace` 的记录只有一个写入方——它自己的 registry。把 worktree 行挂上 `WorkspaceRecord`，等于让第二个包拿到另一个能力持久化格式的写入面，或者迫使每次 worktree 变更都绕道 workspace registry。
- **独立的 schema 版本化。** `worktree_registry` 域盖自己的版本戳，worktree 格式变更永远不会 bump workspace 域，反之亦然。

代价是没有跨域事务：create 只读 workspace registry，remove 只碰本域和 git。worktree 行是注册状态的权威，git 是 worktree 存在性的权威；reconcile 是两个介质之间显式的"报告并行动"步骤，没有任何不变量悄悄横跨两者。`workspaceId` 锚点对本包的 schema 是不透明的——"它指向一个真实 workspace"的校验发生在操作里，经 `ctx.workspaceRegistry`，这是最早可解析的时点。

### 服务面

```ts
export type WorktreeId = Branded<'WorktreeId'>
export function WorktreeId(id: string): WorktreeId

export interface WorktreeCreateRequest {
  workspaceId: WorkspaceId   // owner anchor; resolved through ctx.workspaceRegistry
  path: string               // target checkout directory, any spelling; created by git
  branch?: string            // new branch name; omitted lets git derive it from the path
}

export interface Worktree {
  readonly id: WorktreeId
  readonly workspaceId: WorkspaceId
  readonly path: string      // canonical
  readonly branch: string    // observed HEAD branch at create time
  readonly createdAt: string
  readonly updatedAt: string
  readonly lockedBy?: WorktreeLockHolder  // present exactly with lockedAt
  readonly lockedAt?: string
}

export interface WorktreeStatus {
  readonly directoryExists: boolean
  readonly branch?: string   // observed now; undefined when the directory is missing
  readonly clean?: boolean   // `git status --porcelain` empty; undefined when missing
}

export interface WorktreeReconcileReport {
  readonly dangling: readonly WorktreeDanglingRegistration[]
  readonly unregistered: readonly WorktreeUnregisteredWorktree[]
  readonly removedRows: readonly WorktreeId[]
  readonly adoptedPaths: readonly string[]
}

export abstract class WorktreeRegistry extends Service {
  create(request: WorktreeCreateRequest): Promise<Worktree>
  bind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>
  unbind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>
  list(workspaceId: WorkspaceId): readonly Worktree[]
  status(id: WorktreeId): Promise<WorktreeStatus>
  remove(id: WorktreeId, options?: { force?: boolean }): Promise<void>
  reconcile(workspaceId: WorkspaceId, options?: WorktreeReconcileOptions): Promise<WorktreeReconcileReport>
}
```

每个 provider 遵守的语义：

- **create** 经 `ctx.workspaceRegistry` 解析归属 workspace，对未知 `workspaceId` fail loud。先拒绝本注册表已持有的路径，拒绝同一 workspace 的另一个 worktree 已持有的显式分支（已分类的 `branch-conflict` 类别，在 git 运行之前抛出），再运行 git；git 的拒绝被分类为四类类型化失败（路径被占用、分支冲突、脏树、路径超长），错误文本自带修复指引。返回的记录反映观测事实——目录存在后经 `fs.realpath` 得到的规范路径、从新 worktree 读回的分支。
- **bind/unbind** 维护单一写入者绑定：`bind` 对当前持有者幂等，其余任何绑定以 `already-locked` 拒绝；`unbind` 在未绑定时以 `not-locked` 拒绝，其他持有者请求时以 `holder-mismatch` 拒绝。两者都返回新记录，拒绝都是 `WorktreeLockError`——产品决策，绝不是 git stderr。
- **list** 以同样方式校验 workspace id，返回该 workspace 的行，按 `createdAt` 再按 id 排序。它只读持久化行；不 shell out 到 `git worktree list`，因为本产品登记了什么，权威是注册表而不是 git 元数据。与 git 的对账是 reconcile 的职责。
- **status** 是观测面：目录缺失时报告 `directoryExists: false` 且不调用 git（这是观测，不是失败）；目录存在时报告实时分支与干净度，git 自身报错则 fail loud。
- **remove** 在 worktree 处于绑定状态时拒绝——`force` 绝不覆盖绑定——然后运行 `git worktree remove`（按请求加 `--force`），git 成功之后才删除行，所以失败的 remove 永远不会掩盖一个真实存在的 worktree。目录缺失时 fail loud，并指明 reconcile 的 `pruneRows` 动作是这条过时行的恢复路径。
- **reconcile** 把行与 `git worktree list --porcelain -z` 作差，默认只报告。`pruneRows` 丢弃过时行（目录已消失的行、或 git 已不再跟踪的行）并连同其绑定一起丢弃——绑定守护的是活着的 checkout，不是消失的目录——并在真的丢了 directory-missing 行时运行一次 `git worktree prune`，绝不删除 worktree 文件；`adoptUnregistered` 把任何 workspace 都没有登记行的 git 跟踪 worktree 登记进来，记录 git 观测到的分支（detached 时为 `HEAD`）。仓库主 worktree 与对账 workspace 自己的路径绝不会被报为未注册。

注册表变更在 provider 内部的单条操作链上运行，行写入走域的写链，并发操作按 `dsh-workspace` 同样的方式串行化。

### git 命令映射

| Seam 操作 | git 调用 | cwd |
| --- | --- | --- |
| create | `git worktree add [-b <branch>] <path>` | 归属 workspace 路径 |
| list | 无——持久化行就是答案 | — |
| status | `git rev-parse --abbrev-ref HEAD`、`git status --porcelain=v1` | worktree 路径 |
| remove | `git worktree remove [--force] <path>` | worktree 路径（链接 worktree 自己能解析共享仓库） |
| reconcile | `git worktree list --porcelain -z`、`git worktree prune`（仅 directory-missing 行）、`git rev-parse --abbrev-ref HEAD`（采纳时） | 归属 workspace 路径；采纳的条目用其自身路径读分支 |

`git worktree prune` 只作为显式选择的 `pruneRows`（且真的丢了 directory-missing 行）的一部分运行，它只清理 git 自己的过时元数据——注册表绝不删除 worktree 目录或文件。

### 会话事件：没有

本 seam 进入模型请求的只有 session log 本来就承载的普通工具 call/result 事件，所以 `SessionEventMap` 不新增成员。工具的结果与错误就是工具事件；worktree 状态从这些交互与持久行即可重建。只有当 worktree 状态必须在工具交互之外可重建时（例如 host UI 卡片在 replay 后从日志渲染），才需要新事件；该决策属于引入那个面的变更。

### 配置

provider 的 Config 是带默认值的 schemastery 校验对象，可从 cordis.yml 修改：`gitPath`（默认 `git`）、`timeoutMs`（默认 60000）、`maxTimeoutMs`（默认 600000）、`graceMs`（默认 3000）、`maxOutputBytes`（默认 64000）。校验拒绝非正或非有限值，`graceMs` 超过定时器上限在构造期拒绝——即 pwsh-local 模式。任何随部署变化的值都不硬编码在这些字段之外；git 协议常量（旗标拼写）保持固定。porcelain 清单超出 `maxOutputBytes` 时 fail loud，绝不产出截断的对账结果。

### 组合

provider 声明 `static inject = ['workspaceRegistry', 'subprocess', 'storageDomain']`：workspace registry 解析归属锚点，subprocess seam 跑 git，storage domain 存行。因为第一个注入，provider 只能挂载在 `dsh-workspace` 也挂载的组合里；base bundle 把它挂在 agent 面，web-app bundle 把它挂在 workspace 行旁边并禁用 consumer。想要 worktree 但没有 workspace 的组合无法挂载这个 provider——正确的失败发生在激活期，而不是留下一条无锚点的行。远端或沙箱 provider 在同一个 Definition 后面替换自己的执行世界，注册表契约不变。

## Alternatives considered

- **把行挂上 `WorkspaceRecord`**（扩展 workspace 域，每个 workspace 带一个 worktree 列表）：理由已在"持久化状态"一节否决——跨包写入面、耦合的 schema 版本、以及 `dsh-workspace` 单写入方记录里出现第二个写入方。
- **用 `node:child_process` 直接跑 git**：否决。仓库惯例是所有 spawn 走 `ctx.subprocess`（有界输出收集与 spill、按进程树终止、环境清洗、deadline 融合）；手写等于删掉这些保证并重复它们的测试。`dsh-shell` 与两个 executor 都经 seam spawn。
- **以路径为行的 key**：否决——路径被规范化、大小写、git 本身改写；稳定锚点是 uuid，与 `WorkspaceId` 同一决策。
- **`list` shell out 到 `git worktree list --porcelain`**：否决。持久化行契约保持诚实——注册表只报告它登记过的事实——与 git 的差值放在专门的 reconcile 操作里，对产品之外创建的 worktree 的报告与处置策略在那里陈述，而不是漏进 list 的答案。
- **seam 与模型可见工具同一次变更交付**：以范围为由否决。工具带来 schema、呈现和模型可见契约；并进来会把存储与 seam 决策和 consumer 决策耦合。seam 先落地，consumer 以 [`tool-worktree`](../feature/2026-09-05-worktree-tools-and-reconcile.zh.md) 为名落在稳定地基上。
- **每次注册表变更发一个 session 事件**：否决——模型只经工具交互看到注册表状态，而 session log 本来就承载这些；在没有模型消费方时把 host 侧状态写进每个 session log，等于把 workspace 作用域的事实塞进 session 的所有权。
- **remove 里悄悄顺带 prune**（目录已消失时自动丢行）：否决。注册表状态的移除保持显式且只在 reconcile 里选择，出人意料的目录消失先被报告，然后才被遗忘。

## Consequences

seam 给 harness 带来一个持久、以 workspace 为锚、跨重启存活的 worktree 词汇：注册表是"本产品登记了什么"的权威，git 是"磁盘上存在什么"的权威。模型经 `worktree_*` 工具触达它，且不新增任何会话事件类型。代价：

- **两步 remove。** git 先删 worktree，随后才删行；两步之间存储失败会留下一条目录已消失的行。失败以指明两个事实的响亮错误浮出，status 报告目录缺失，reconcile 的 `pruneRows` 是恢复路径。
- **采纳信任 git 的清单。** `adoptUnregistered` 会登记 `git worktree list` 报告的、已知行之外的一切，不经人工确认；一个无关仓库的链接检出可能被采纳到对账 workspace 名下。
- **reconcile 绝不删树。** 悬空登记会被丢弃，但未注册 worktree 背后的目录只会被采纳或报告；真实检出的大批量清理仍是 host 的决定。
- **git 输出解析保持最小。** reconcile 只把 `-z` porcelain 清单解析为路径/分支对，采纳只读 `rev-parse --abbrev-ref HEAD`；更丰富的事实（locked、超出目录存在的 prunable 原因）没有建模，解析器绝不半解释自己不保留的字段。

## Verification

- `pnpm exec vitest run packages/workflow/worktree-registry` 在内存后端上用真实 git 子进程覆盖 create/bind/list/status/remove、绑定生命周期及其拒绝类别、reconcile 的一致/检出/丢弃/采纳矩阵、四类 git 失败方言对捕获 stderr 的分类、以及 win32 上的 Windows 长路径拒绝（`packages/workflow/worktree-registry/tests/`）。
- 处置：dispose provider 的 fiber 关闭存储域，之后的操作 fail loud 而不是悄悄重开（`loader-composition.spec.ts`）；行经 json 存储后端在冷重启后存活。
- `pnpm run gen-cordis-catalog` 保持七个抽象方法的生成 Cordis API 页面新鲜。
