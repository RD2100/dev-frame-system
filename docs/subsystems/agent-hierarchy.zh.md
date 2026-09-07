# 代理层级策略

[English](agent-hierarchy.md) | 中文

代理层级子系统是插件化 agent（智能体）层级的策略服务：把角色策略统一为 `controller` / `lead` / `worker` 三个状态，在根工具注册表上安装一个覆盖所有 agent 创建入口的单调 pre-execute 守卫，对照宿主批准集合校验 lead 被委托的插件作用域，并强制执行绝对委托深度预算 2——作为委托 seam 自带 `SubagentDepthError` 之外的第二条独立拒绝路径。[包 README](../../packages/experimental/agent-hierarchy/README.zh.md) 负责挂载配置与模型体验。

## 服务面

`ctx.agentHierarchy` 是策略服务。核心操作：

- 守卫自动覆盖面向模型的工具执行；拒绝原因会点名绑定角色、`missing role`、插件作用域或深度预算，且工具体绝不运行。
- `roleOf` — 从活跃绑定注册表解析 agent 的绑定角色。
- `evaluateCreation` — 每个非工具创建入口（宿主服务、SDK 桥接）都必须在子级存在之前以创建者的绑定记录和 P00 `CreationIntent` 调用它。
- `createChildAgent` — 通过工厂 setup 校验并创建子 Agent，在发布前持久化身份。`CreateChildAgentRequest` 携带必需的任务、插件范围和已注册工作树；`CreateChildAgentOptions` 携带宿主 setup、路由选项、取消信号及可选的已分配 SessionID。`CreatedChildAgent` 返回活跃 Agent 和持久绑定，不发送提示词。Agent 生命周期由服务拥有。

- `recoverChildAgent` — 恢复保留身份；持久日志不存在时按原 SessionID 重新发布。日志损坏和 setup 失败不会回退到创建；恢复不投递提示词。
- 配置在构造时校验一次：每角色 `roleToolPolicies`（各角色保留其 `inheritedTools` 列表点名的全局工具）与每 lead `leadPluginScopes`。

## 约定要点

加载期失败在 `AgentHierarchyError` 上携带稳定的 `HIERARCHY_*` 代码（`HIERARCHY_INVALID_CONFIG`、`HIERARCHY_ROLE_UNKNOWN`）；守卫拒绝是普通的理由字符串，按 fail closed 执行，任何 post-execute 监听器都不能推翻。固定拒绝面叠加在配置之上：lead 失去 Team spawn/任务控制工具，worker 失去每一个能创建 agent 的工具，而 `send_message` 被有意保留为 worker 获得授权的汇报路径。深度预算是固定的安全不变量，不是配置字段；depth-2 会话的任何委托都会被拒绝，无论其绑定角色如何。本服务自己没有存储域：角色在每次执行时从 `ctx.agentBindings` 实时解析，因此激活后写入或恢复的绑定立即生效，每 agent 的限制只是惰性安装、随 dispose 解除的投影。

## 子系统边界

它读取的注册表记录在[会话身份绑定](session-identity.zh.md)。委托 seam（[subagent](subagent.zh.md)）保留 `SubagentDepthError` 这第一条拒绝路径；本守卫是第二条独立路径。lead 失去的 Team spawn 与任务控制工具属于 [agent 团队](agent-team.zh.md)，被守卫的工具注册表是 [tools](tools.zh.md) 子系统。未绑定会话继续执行非受控工具。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagenthierarchy--agenthierarchy"></a>

### `ctx.agentHierarchy` — `AgentHierarchy`

The pluginized-hierarchy role and creation policy service. Hard-injects `ctx.agentBindings` (the role authority), `ctx.tools` (the guard and restriction surface), and `ctx.agents` (the exact-identity check the P01 cold-recovery caveat requires) and fails at activation when any is absent.

```ts cordis-catalog
/**
 * Resolve the hierarchy role of one exact live agent.
 * @param agent - Candidate agent identity.
 * @returns The bound role, or `undefined` when the identity is stale or unbound.
 */
roleOf(agent: Agent): AgentRole | undefined

/**
 * Evaluate a programmatic creation intent against the creator's binding
 * and this host's approved plugin scopes. Tool executions reach the same
 * policy through the installed guard; every non-tool creation entry must
 * call this before the child exists.
 * @param creator - The durable binding of the creating session.
 * @param intent - The recorded creation attempt.
 * @returns The verdict with a denial reason when refused.
 */
evaluateCreation(creator: AgentBindingRecord, intent: CreationIntent): CreationDecision
```

Types: [Agent](core.zh.md)

Source: [`packages/experimental/agent-hierarchy/src/service.ts`](../../packages/experimental/agent-hierarchy/src/service.ts)
<!-- END GENERATED cordis-surface -->
