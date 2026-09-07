# Worktree Registry

[English](worktree-registry.md) | 中文

每工作区 git worktree 注册表——一个[能力 seam](../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.zh.md)，持久登记归属于单个 workspace 的 git worktree。Service Definition（[`WorktreeRegistry`](../../packages/workflow/worktree-registry)，挂载为 `ctx.worktreeRegistry`）与 Service Provider（`GitWorktreeRegistry`，经 `ctx.subprocess` 在宿主文件系统上执行 git 操作）住在同一个包里。Consumer 角色有两个：[`tool-worktree`](../../packages/workflow/tool-worktree) 向 workspace 会话暴露五个 `worktree_*` 工具，并把每次调用都授权到调用会话自己的工作区；实验性的 [`agent-worktree`](agent-worktree.zh.md) seam 把每个新建 worktree 绑定到唯一写入者，服务于 Agent 会话。

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)

## 服务

`WorktreeRegistry` 声明八个操作。`create` 经 `ctx.workspaceRegistry` 解析归属 workspace，从 workspace 目录运行 `git worktree add`，并记录观测事实——`fs.realpath` 之后的规范路径与从新 worktree 读回的分支——在此之前先拒绝 workspace 或其他已登记 worktree 已占用的路径，以及同一 workspace 的其他 worktree 已持有的显式分支。`bind`/`unbind` 维护每个 worktree 至多一个的单一写入者绑定：holder 值不透明，当前 holder 重复绑定是幂等成功，其余任何绑定、非 holder 的解绑、对未绑定 worktree 的解绑都以 `WorktreeLockError` 拒绝。`list` 以稳定 `(createdAt, id)` 顺序从持久化行作答，绝不 shell out 到 git。`status` 是观测面：目录缺失时报告 `directoryExists: false` 且不调用 git，目录存在时报告实时分支与干净度。`remove` 在 worktree 处于绑定状态时拒绝——`force` 绝不覆盖绑定——然后运行 `git worktree remove`，git 成功之后才删除登记，所以失败的删除绝不会掩盖真实存在的 worktree。`reconcile` 把登记行与 `git worktree list` 作差并报告差异——悬空登记与未注册的 worktree——只有显式选择对应动作时才丢弃过时行或采纳外部创建的 worktree；它绝不删除目录或文件，且 `pruneRows` 丢弃过时行时连同其绑定一起丢弃，因为绑定守护的是活着的 checkout，不是消失的目录。

登记持久化在 `worktree_registry` 存储域（version 2；一张以 branded `WorktreeId` 为 key 的 `worktrees` 表，携带成对写入读取的可选 `lockedBy`/`lockedAt` 绑定字段）；重启后保留并在下次组合时重新可用。目录操作以归属 workspace 路径为 cwd——Windows 上 worktree 不能以自己为 cwd 删除自己。模型只能经 [`tool-worktree`](../../packages/workflow/tool-worktree) 的 `worktree_*` 工具与 [`agent-worktree`](agent-worktree.zh.md) 的每 Agent seam 触达这些操作，工具描述自带四类已分类 git 拒绝方言（路径被占用、分支冲突、脏树、路径超长）的重试语义。

## 提交请求与结果

`WorktreeCommitId` 是带品牌的完整 Git 对象 ID。`WorktreeCommitRequest` 通过 `id` 标识已登记的检出，通过 `holder` 标识获授权的写入者，通过 `expectedHead` 指定乐观并发前置条件；`paths` 列出字面相对文件路径，`message` 提供提交消息。`WorktreeCommitResult` 返回新的 `head` 和整个检出的 `clean` 状态。

仅限宿主调用的 `commit` 操作要求消费者授权并使其他写入者停止写入。它保留无关改动、拒绝已有暂存，并要求登记分支和预期 HEAD 匹配。取消或失败可能留下暂存改动或提交；重试前应检查。[包契约](../../packages/workflow/worktree-registry/README.zh.md)负责 hooks、filters 和路径限制。

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
- `bind`/`unbind` maintain one single-writer binding per worktree. The holder value is opaque; equality is the entire contract. Re-binding by the current holder is an idempotent success; any other bind, an unbind by a non-holder, or an unbind of an unbound worktree refuses with a `WorktreeLockError`.
- `remove` refuses while the worktree is bound, whatever options say — the lock is a product-level exclusivity promise, not a dirty-tree guard.
- `remove` deletes the durable row only after the provider's worktree removal succeeded, so a failed remove never hides an existing worktree.
- `reconcile` compares the rows with `git worktree list` and only reports by default; its actions are opt-in and never delete directories or files.

```ts cordis-catalog
/**
 * Create a linked worktree for one workspace and register it durably. The
 * path must not collide with the owner workspace directory or any registered
 * worktree, and an explicitly requested branch must not already be
 * registered to another worktree of the same workspace (git itself refuses
 * a branch that exists in the repository, whatever workspace registered it).
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered worktree with observed path and branch.
 */
abstract create(request: WorktreeCreateRequest): Promise<Worktree>

/**
 * Bind one worktree to a single writer. The holder is opaque to the
 * registry; binding succeeds when the worktree is unbound or already bound
 * to the same holder, and refuses with `WorktreeLockError`
 * (`already-locked`) otherwise.
 * @param id - Registered worktree id; unknown ids reject.
 * @param holder - The single-writer marker taking or holding the binding.
 * @returns the updated worktree with the binding stamped.
 */
abstract bind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>

/**
 * Release a worktree's single-writer binding. Refuses with
 * `WorktreeLockError` (`not-locked`) when the worktree is unbound and
 * (`holder-mismatch`) when `holder` is not the current holder.
 * @param id - Registered worktree id; unknown ids reject.
 * @param holder - The single-writer marker releasing the binding.
 * @returns the updated worktree with the binding cleared.
 */
abstract unbind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>

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
 * Commit selected paths through the host provider while retaining the writer lock.
 * The consumer must authorize the calling writer and stop its other mutations first.
 * Existing staged changes, a changed branch, and a stale HEAD reject before staging.
 * A rejection after staging may leave an index or commit; inspect before retrying.
 * No rollback, reset, history rewrite, or sandbox permission change is performed.
 * @param request - Trusted writer, registered target, expected HEAD and literal paths.
 * @param signal - Cancellation of queued or executing Git operations.
 * @returns The verified new commit and the remaining worktree cleanliness.
 */
abstract commit(request: WorktreeCommitRequest, signal?: AbortSignal): Promise<WorktreeCommitResult>

/**
 * Remove one worktree through git and delete its registration. A bound
 * worktree refuses with `WorktreeLockError` (`already-locked`) until its
 * holder unbinds — `force` never overrides the lock. The row is deleted
 * only after the removal succeeded.
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
