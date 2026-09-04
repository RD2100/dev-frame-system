# Agent Note: 每工作区 git worktree 注册表能力 seam

Status: proposed

[English](2026-09-05-worktree-registry.md) | 中文

## 问题

在某个 workspace 里工作的 agent 需要同一仓库的第二份检出：workspace 里留有未提交改动时用一个干净树跑构建、给实验性重构一个隔离树、给后台任务一个并行树。Git 已有机制——链接 worktree——但 harness 没有任何东西 owning 它：

- 每个消费方都得走 shell 能力拼 `git worktree` 命令并手写输出解析。没有任何包登记哪些 worktree 存在、各属于哪个 workspace、哪些可以安全删除，于是状态只存在于调用方的对话里，随会话消失。
- 没有任何东西把 worktree 关联到 `WorkspaceId`。workspace 实体是"用户工作的目录"这个产品锚点；worktree 是 per-workspace 事实，未来的模型可见面需要这条关联才能呈现并约束它们。
- 没有任何东西支持换执行世界。经沙箱或远端 provider 创建的 worktree 必须遵守与本地的同一个注册表契约。

本 note 提出拥有这些事实的最小 seam：一个 per-workspace 的 git worktree 注册表，含 create/list/status/remove、一个本地 git provider，以及这些行的持久化归宿。

## Proposal

新包 `packages/workflow/worktree-registry`（`@deepseek-ai/dsh-worktree-registry`），本切片把 seam 的角色合并在一个包里。它沿用 `dsh-shell` 模板：抽象 Service Definition 声明接口，具体 provider 类实现它，包的 default export 是 Loader 挂载的 provider。

| 角色 | 元素 | 说明 |
| --- | --- | --- |
| Service Definition | `WorktreeRegistry`（抽象类，具名导出） | 声明 create/list/status/remove、记录词汇表和 `ctx.worktreeRegistry` 这个 key。 |
| Service Provider | `GitWorktreeRegistry`（default export） | 经 `ctx.subprocess` 运行 `git`，拥有持久化行。每个 context 一个 provider；二次注册经 cordis 的重复服务规则 fail loud。 |
| Consumer | 本切片没有 | 模型可见的 `worktree_*` 工具和任何 host UI 是下一个变更；上面的服务 API 是它们稳定的地基。按 docs/architecture.md，seam 缺了 consumer 就不完整，所以 consumer 面在这里设计（见下方 git 映射）、作为一个整体延后。 |

### 身份

`WorktreeId = Branded<'WorktreeId'>` 来自 `@deepseek-ai/dsh-brand`，取值为生成的 uuid。路径绝不作 key：worktree 路径会被规范化、被 git 本身改写，引用锚点必须稳定——与 `WorkspaceId` 用 uuid 的理由相同。品牌放在本包，因为铸造和使用它的是本包。

### 持久化状态：独立 KvTable，不挂 WorkspaceRecord

注册表打开自己的存储域 `worktree_registry`（version 1），一张表 `worktrees`，以 `WorktreeId` 为 key。记录携带 `workspaceId`（归属锚点）、`path`（规范路径，来自 `git worktree add` 成功后观测的 `fs.realpath`）、`branch`（create 时观测到的 HEAD，不是调用方的假设）、`createdAt`、`updatedAt`。

这些行刻意不扩展 `WorkspaceRecord`：

- **归属内聚。** worktree 生命周期是 git 与 workflow 机制。workspace 域回答"哪些 session 在这个目录里跑过"；worktree 行回答"这个 workspace 存在哪些第二检出"。问题不同、写入方不同、演进时钟不同。
- **单写入方纪律。** `dsh-workspace` 的记录只有一个写入方——它自己的 registry。把 worktree 行挂上 `WorkspaceRecord`，等于让第二个包拿到另一个能力持久化格式的写入面，或者迫使每次 worktree 变更都绕道 workspace registry。
- **独立的 schema 版本化。** `worktree_registry` 域盖自己的版本戳，worktree 格式变更永远不会 bump workspace 域，反之亦然。

代价是没有跨域事务：create 只读 workspace registry，remove 只碰本域和 git。worktree 行是注册状态的权威，git 是 worktree 存在性的权威；没有任何不变量横跨两个介质，所以不欠一个事务。

`workspaceId` 锚点对本包的 schema 是不透明的——"它指向一个真实 workspace"的校验发生在操作里，经 `ctx.workspaceRegistry`（见下），这是最早可解析的时点。

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
}

export interface WorktreeStatus {
  readonly directoryExists: boolean
  readonly branch?: string   // observed now; undefined when the directory is missing
  readonly clean?: boolean   // `git status --porcelain` empty; undefined when missing
}

export abstract class WorktreeRegistry extends Service {
  create(request: WorktreeCreateRequest): Promise<Worktree>
  list(workspaceId: WorkspaceId): readonly Worktree[]
  status(id: WorktreeId): Promise<WorktreeStatus>
  remove(id: WorktreeId, options?: { force?: boolean }): Promise<void>
}
```

每个 provider 必须遵守的语义：

- **create** 经 `ctx.workspaceRegistry` 解析归属 workspace，对未知 `workspaceId` fail loud。先拒绝本注册表已持有的路径，再运行 git；git 自身的拒绝（目录已存在、分支已被检出、不是仓库）作为描述性失败传播。返回的记录反映观测事实——目录存在后经 `fs.realpath` 得到的规范路径、从新 worktree 读回的分支。
- **list** 以同样方式校验 workspace id，返回该 workspace 的行，按 `createdAt` 再按 id 排序。它只读持久化行；不 shell out 到 `git worktree list`，因为本产品登记了什么，权威是注册表而不是 git 元数据。与 git 的对账属于 status 和未来的 prune。
- **status** 是唯一的观测面：目录缺失时报告 `directoryExists: false` 且不调用 git（这是观测，不是失败）；目录存在时报告实时分支与干净度，git 自身报错则 fail loud。
- **remove** 运行 `git worktree remove`（按请求加 `--force`），git 成功之后才删除行，所以失败的 remove 永远不会掩盖一个真实存在的 worktree。目录缺失时 fail loud 并点明 git 元数据已悬空，因为注销它是 prune 的职责而 prune 尚不存在。

注册表变更在 provider 内部的单条操作链上运行，行写入走域的写链，并发操作按 `dsh-workspace` 同样的方式串行化。

### git 命令映射

| Seam 操作 | git 调用 | cwd |
| --- | --- | --- |
| create | `git worktree add [-b <branch>] <path>` | 归属 workspace 路径 |
| list | 无——持久化行就是答案 | — |
| status | `git rev-parse --abbrev-ref HEAD`、`git status --porcelain=v1` | worktree 路径 |
| remove | `git worktree remove [--force] <path>` | worktree 路径（链接 worktree 自己能解析共享仓库） |
| prune | 延后 | — |

`prune` 刻意不进本切片。它对 git 的 worktree 元数据是破坏性的，其注册表一侧需要一个本 seam 不该猜的策略：prune 是否同时删除目录已消失的行、结果如何向未来消费方汇报。它随第一个需要它的 consumer 变更落地。

### 会话事件：本切片没有

本切片没有任何东西进入模型请求——没有工具、没有 prompt 注入、没有模型可见渲染——所以"模型可见⟺已记录"不变量不新增任何 `SessionEventMap` 成员。consumer 工具落地时，其结果是 tool call/result 事件，session log 本来就承载；为此也不欠新事件类型。只有当 worktree 状态必须在工具交互之外可重建时（例如 host UI 卡片在 replay 后从日志渲染），才需要新事件；该决策属于引入那个面的变更。过渡期 host 侧的变更观测走存储域的 `domain/changed`，它是进程内的。

### 配置

provider 的 Config 是带默认值的 schemastery 校验对象，可从 cordis.yml 修改：`gitPath`（默认 `git`）、`timeoutMs`（默认 60000）、`maxTimeoutMs`（默认 600000）、`graceMs`（默认 3000）、`maxOutputBytes`（默认 64000）。校验拒绝非正或非有限值，`graceMs` 超过定时器上限在构造期拒绝——即 pwsh-local 模式。任何随部署变化的值都不硬编码在这些字段之外；git 协议常量（旗标拼写）保持固定。

### 组合

provider 声明 `static inject = ['workspaceRegistry', 'subprocess', 'storageDomain']`：workspace registry 解析归属锚点，subprocess seam 跑 git，storage domain 存行。因为第一个注入，provider 只能挂载在 `dsh-workspace` 也挂载的组合里；本切片把它挂在 web-app bundle 里 workspace 行旁边。想要 worktree 但没有 workspace 的组合无法挂载这个 provider——正确的失败发生在激活期，而不是留下一条无锚点的行。远端或沙箱 provider 在同一个 Definition 后面替换自己的执行世界，注册表契约不变。

## Alternatives considered

- **把行挂上 `WorkspaceRecord`**（扩展 workspace 域，每个 workspace 带一个 worktree 列表）：理由已在"持久化状态"一节否决——跨包写入面、耦合的 schema 版本、以及 `dsh-workspace` 单写入方记录里出现第二个写入方。
- **用 `node:child_process` 直接跑 git**：否决。仓库惯例是所有 spawn 走 `ctx.subprocess`（有界输出收集与 spill、按进程树终止、环境清洗、deadline 融合）；手写等于删掉这些保证并重复它们的测试。`dsh-shell` 与两个 executor 都经 seam spawn。
- **以路径为行的 key**：否决——路径被规范化、大小写、git 本身改写；稳定锚点是 uuid，与 `WorkspaceId` 同一决策。
- **`list` shell out 到 `git worktree list --porcelain`**：本切片否决。那样注册表会报告它从未登记过的事实（产品之外创建的 worktree），而 consumer 面尚未设计如何呈现；持久化行契约保持诚实，prune/对账随能给出策略的 consumer 到来。
- **同一次变更顺带交付模型可见工具**：以范围为由否决。工具带来 schema、呈现、快照覆盖和模型可见契约；并进来会把存储与 seam 决策和 UI 决策耦合。四方法服务是工具消费的稳定地基。
- **每次注册表变更发一个 session 事件**：否决——不存在任何模型可见物，且在没有模型消费方时把 host 侧状态写进每个 session log，等于把 workspace 作用域的事实塞进 session 的所有权。

## Acceptance criteria

- 行为测试覆盖 create（观测到的规范路径与分支）、list 的过滤与排序、status 的干净/脏/目录缺失、remove 带 `force` 与不带、以及 fail-loud 路径：未知 workspace、非 git 的 workspace 目录、重复登记、不带 `force` 删除脏 worktree。
- 处置：dispose provider 的 fiber 关闭存储域，之后的操作 fail loud 而不是悄悄重开。
- 真实 Loader 组合在 `dsh-workspace` 旁边启动 provider，行经 json 存储后端在冷重启后存活。
- `pnpm exec vitest run packages/workflow/worktree-registry` 与 `pnpm run typecheck` 绿；不存在模型可见面，因此不欠快照变更。

## Risks

- **两步 remove。** git 先删 worktree，随后才删行；两步之间存储失败会留下一条目录已消失的行。失败以指明两个事实的响亮错误浮出，status 报告目录缺失——但恢复要等未来的 prune。
- **外部删除。** 用户在产品之外删掉 worktree 目录会把 `remove` 卡住直到 prune 落地；错误信息明确说明这一点。
- **在 worktree 内部执行 remove。** 以目标为 cwd 的 `git worktree remove` 依赖链接 worktree 解析共享仓库；若某个 git 版本拒绝，provider 把 cwd 换成归属 workspace 路径——provider 局部修复，不动 seam。
- **git 输出解析保持最小。** status 只读 `--porcelain=v1` 的空与不空和 `rev-parse --abbrev-ref HEAD`；更丰富的事实（locked、prunable、detached）延后，本切片绝不半解析自己没有建模的 porcelain 输出。
