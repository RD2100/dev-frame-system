# Worktree Registry

[English](worktree-registry.md) | 中文

每工作区 git worktree 注册表——一个[能力 seam](../../.agents/notes/proposed/architecture/2026-09-05-worktree-registry.zh.md)，持久登记归属于单个 workspace 的 git worktree。本 seam 的各角色目前住在同一个包里：Service Definition（[`WorktreeRegistry`](../../packages/workflow/worktree-registry)，挂载为 `ctx.worktreeRegistry`）与 Service Provider（`GitWorktreeRegistry`，经 `ctx.subprocess` 在宿主文件系统上执行 git 操作）。Consumer 角色延后：尚无工具、提示词或 UI 面，因此整个 seam 只在宿主侧，不给模型请求增加任何内容。

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)

## 服务

`WorktreeRegistry` 声明四个操作。`create` 经 `ctx.workspaceRegistry` 解析归属 workspace，从 workspace 目录运行 `git worktree add`，并记录观测事实——`fs.realpath` 之后的规范路径与从新 worktree 读回的分支。`list` 以稳定 `(createdAt, id)` 顺序从持久化行作答，绝不 shell out 到 git。`status` 是观测面：目录缺失时报告 `directoryExists: false` 且不调用 git，目录存在时报告实时分支与干净度。`remove` 先运行 `git worktree remove`，git 成功之后才删除登记，所以失败的删除绝不会掩盖真实存在的 worktree。

登记持久化在 `worktree_registry` 存储域（一张以 branded `WorktreeId` 为 key 的 `worktrees` 表）；重启后保留并在下次组合时重新可用。目录操作以归属 workspace 路径为 cwd——Windows 上 worktree 不能以自己为 cwd 删除自己。把行与 git 自身元数据对账（包括产品之外创建的 worktree 与目录已消失的登记）属于延后的 prune 工作；seam 设计与延后接口见 [Agent Note](../../.agents/notes/proposed/architecture/2026-09-05-worktree-registry.zh.md)。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxworktreeregistry--worktreeregistry-abstract-seam"></a>

### `ctx.worktreeRegistry` — `WorktreeRegistry` (abstract seam)

Abstract worktree registry service. Subclass, implement the abstract methods, and load the subclass as a plugin — it registers as `ctx.worktreeRegistry` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior).

Implementations must honor these semantics:

- Operations resolve the owner workspace through `ctx.workspaceRegistry` and fail loud on an unknown `WorkspaceId`; the anchor is never stored unvalidated.
- Records reflect observed facts: canonical paths after the directory exists, branches read back from the worktree, never caller assumptions.
- `list` answers from durable rows only; the registry, not git metadata, is the authority for what this product registered.
- `status` reports a missing directory as an observation (`directoryExists: false`) without invoking git; git failures on a present directory reject.
- `remove` deletes the durable row only after the provider's worktree removal succeeded, so a failed remove never hides an existing worktree.
- `reconcile` compares the rows with `git worktree list` and only reports by default; its actions are opt-in and never delete directories or files.

```ts cordis-catalog
/**
 * Create a linked worktree for one workspace and register it durably.
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered worktree with observed path and branch.
 */
abstract create(request: WorktreeCreateRequest): Promise<Worktree>

/**
 * The workspace's registered worktrees in the stable (createdAt, id) order.
 * @param workspaceId - Owner workspace; unknown ids reject.
 * @returns a fresh ordered array of registered worktrees.
 */
abstract list(workspaceId: WorkspaceId): readonly Worktree[]

/**
 * Observe one registered worktree's live state.
 * @param id - Registered worktree id; unknown ids reject.
 * @returns the observation; optional fields are absent when the recorded
 *   directory no longer exists.
 */
abstract status(id: WorktreeId): Promise<WorktreeStatus>

/**
 * Remove one worktree through git and delete its registration. The row is
 * deleted only after the removal succeeded.
 * @param id - Registered worktree id; unknown ids reject.
 * @param options - Pass `force` to allow removing dirty worktrees.
 * @returns resolution after the worktree is gone and the row deleted.
 */
abstract remove(id: WorktreeId, options?: WorktreeRemoveOptions): Promise<void>

/**
 * Compare this workspace's rows with `git worktree list` and optionally
 * reconcile the difference. Detection always runs; each action is opt-in:
 * `pruneRows` drops stale rows (never directories or files), and
 * `adoptUnregistered` registers git-tracked worktrees this registry holds
 * no row for under any workspace. The repository's main worktree is never
 * reported as unregistered.
 * @param workspaceId - Owner workspace; unknown ids reject.
 * @param options - The opt-in reconcile actions.
 * @returns the observed differences and the applied changes.
 */
abstract reconcile(workspaceId: WorkspaceId, options?: WorktreeReconcileOptions): Promise<WorktreeReconcileReport>
```

Types: [WorkspaceId](workspace.zh.md)

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)
<!-- END GENERATED cordis-surface -->
