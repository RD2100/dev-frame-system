# Agent Worktree

[English](agent-worktree.md) | 中文

每 Agent 的 worktree seam——一个[能力 seam](../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.zh.md)，构建在 [worktree registry](worktree-registry.zh.md) 之上，把每个新建 worktree 绑定到唯一写入者。Service Definition（[`AgentWorktree`](../../packages/experimental/agent-worktree)，挂载为 `ctx.agentWorktree`）在注册表的 create/bind/status/remove 之上组合单一写入者协议；同一个包也是 Consumer 角色：面向模型的 `worktree_create`、`worktree_status`、`worktree_remove` 三个工具，每次调用都授权到调用会话自己的工作区，并绑定到其持久 session id。该包为实验性私有包：不出现在任何发布 bundle 中。

Source: [`packages/experimental/agent-worktree/src/service.ts`](../../packages/experimental/agent-worktree/src/service.ts)

## 服务

`AgentWorktree` 声明三个操作，全部经由 `ctx.worktreeRegistry`。`create` 通过注册表登记 worktree，并在作答之前把它绑定到 `holder`，所以 Agent 会话创建的 worktree 从第一次观测起就是该会话的单一写入目标。`status` 按 workspace 授权——该工作区没有登记行的 id 与未知 id 的报告完全一致——并把绑定事实与实时分支、干净度并列呈现。`remove` 在其他持有者拥有该 worktree 时拒绝，先释放调用者自己的绑定，再以 git 删除的规范路径作答；注册表自身的 git 拒绝（未加 `force` 的脏树、目录已消失）以已分类错误原样传播。

holder 对注册表是不透明的；本 seam 用调用会话的持久 id 铸造它，因此恢复后的 Agent 仍匹配自己的绑定。执行点保留在 worktree 注册表——已绑定的 worktree 在那里拒绝 `remove`，无论调用方如何请求——当目录在产品外消失时，注册表的 `reconcile` 仍是过时行（连同绑定）离开注册表的唯一途径。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentworktree--agentworktree-abstract-seam"></a>

### `ctx.agentWorktree` — `AgentWorktree` (abstract seam)

Abstract per-agent worktree service. Subclass, implement the abstract methods, and construct the subclass inside a plugin — it registers as `ctx.agentWorktree` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior).

Implementations must honor these semantics:

- `create` registers the worktree through `ctx.worktreeRegistry` and binds it to `holder` before answering. The registry's git refusals (occupied path, branch conflict, oversized path) propagate as classified errors; a bind failure after a successful create surfaces loud and leaves the worktree registered and unbound.
- `status` authorizes by workspace: an id this workspace holds no row for is reported exactly like an unknown one, and a bound row from the same workspace is observable by any session of that workspace.
- `remove` refuses while the worktree is bound to another holder; the holder's own binding is released first, and an unbound worktree is removable by any authorized session.

```ts cordis-catalog
/**
 * Create a linked worktree for the workspace and bind it to `holder` as
 * its single writer.
 * @param holder - The opaque single-writer marker taking the binding.
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered, bound worktree with observed path and branch.
 */
abstract create(holder: WorktreeLockHolder, request: AgentWorktreeCreateRequest): Promise<AgentWorktreeView>

/**
 * Observe one workspace-authorized worktree's live state and binding.
 * @param workspaceId - The caller's workspace; ids outside it reject.
 * @param id - Registered worktree id.
 * @returns the observation; the live fields are absent when the recorded
 *   directory no longer exists.
 */
abstract status(workspaceId: WorkspaceId, id: WorktreeId): Promise<AgentWorktreeStatus>

/**
 * Remove one workspace-authorized worktree. A worktree bound to another
 * holder refuses; the caller's own binding is released before the removal.
 * @param holder - The opaque single-writer marker of the caller.
 * @param workspaceId - The caller's workspace; ids outside it reject.
 * @param id - Registered worktree id.
 * @param options - Pass `force` to allow removing dirty worktrees.
 * @returns the canonical directory path of the removed worktree.
 */
abstract remove( holder: WorktreeLockHolder, workspaceId: WorkspaceId, id: WorktreeId, options?: { readonly force?: boolean | undefined }, ): Promise<string>
```

Types: [WorkspaceId](workspace.zh.md) · [WorktreeId](worktree-registry.zh.md) · [WorktreeLockHolder](worktree-registry.zh.md)

Source: [`packages/experimental/agent-worktree/src/service.ts`](../../packages/experimental/agent-worktree/src/service.ts)
<!-- END GENERATED cordis-surface -->
