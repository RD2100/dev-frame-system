# 会话身份绑定

[English](session-identity.md) | 中文

会话身份子系统为插件化 agent（智能体）层级中的每个 agent 保留一条持久绑定记录：为宿主自行创建的 agent 以准确的 `cwd` 与血缘头元数据创建原生 Session，绑定由其他入口（spawn、fork、Team spawn、SDK）已创建的 agent，并在启动时冷恢复全部绑定。[包 README](../../packages/experimental/session-identity/README.zh.md) 负责挂载配置与模型体验；本页记录注册表的服务面与约定。

## 服务面

`ctx.agentBindings` 是插件化层级的持久绑定注册表。核心操作：

- `createBoundSession` — 以准确的 `cwd`、`parentSession`、`delegationDepth` 头元数据创建原生 Session，然后把完整记录——宿主 Session id、父会话与工作树——在一次持久写入中写入。
- `bind` — 登记由其他入口创建的 agent；完全相同的重绑是幂等的，冲突的重绑大声失败。
- `find`、`byRole`、`list` — 从进程内索引作答，冷进程无须回放会话即可看到全部绑定。

## 约定要点

每次失败都在 `SessionIdentityError` 上携带稳定的 `SESSION_IDENTITY_*` 代码：未知 agent、未知父会话、已绑定、无效请求或持久化失败。记录以 JSON 文档保存在组合 storages 根目录下的 [存储域](storage.zh.md) `session_identity` 中；查询从 write-through 索引作答，启动时由域表重建索引，因此域表保持为唯一持久权威。绑定记录是没有移除操作的持久事实——没有 unbind——且任何记录值都不会到达模型请求，因此不新增会话事件，两个 SDK 投影都不受影响。

## 子系统边界

注册表硬注入 `ctx.sessions` 与 `ctx.storageDomain`，任一缺失即在激活时失败。[代理层级策略](agent-hierarchy.zh.md) 在每次执行时从这些绑定实时解析角色；[Shadow 项目路由](shadow-router.zh.md) 与[项目任务控制器](project-controller.zh.md) 依据它们校验角色与身份。共享的 `AgentBindingRecord` 类型属于 [project-contracts 包](../../packages/experimental/project-contracts/README.zh.md)。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentbindings--agentbindingregistry"></a>

### `ctx.agentBindings` — `AgentBindingRegistry`

The agent binding registry: durable hierarchy identity per agent.

```ts cordis-catalog
/**
 * Create one native Session with exact cwd and lineage metadata and write
 * its binding record — host Session id, parent session, and worktree — in
 * one durable write. A session whose binding write fails stays live and
 * unbound; the caller owns its disposal.
 * @param request - Creation identity: cwd, role, optional parent/depth/task/plugin/worktree.
 * @returns the live session and the durable binding record.
 */
async createBoundSession(request: CreateBoundSessionRequest): Promise<BoundSession>

/**
 * Bind one agent an existing entry point already created. An identical
 * rebind is idempotent; a different binding for the same agent fails loud.
 * @param request - Binding identity: live agent id, role, and optional fields.
 * @returns the durable binding record.
 */
async bind(request: BindAgentRequest): Promise<AgentBindingRecord>

/**
 * Read one agent's binding from the restored index.
 * @param agentId - Live Agent registry identity selecting the record.
 * @returns the binding, or `undefined` when the agent has none.
 */
find(agentId: SessionId): AgentBindingRecord | undefined

/**
 * Read every binding carrying one role.
 * @param role - Hierarchy role to filter by.
 * @returns the matching records in stable (createdAt, agentId) order.
 */
byRole(role: AgentRole): readonly AgentBindingRecord[]

/**
 * Read every binding in stable (createdAt, agentId) order.
 * @returns all restored or written records.
 */
list(): readonly AgentBindingRecord[]
```

Types: [SessionId](core.zh.md)

Source: [`packages/experimental/session-identity/src/registry.ts`](../../packages/experimental/session-identity/src/registry.ts)
<!-- END GENERATED cordis-surface -->
