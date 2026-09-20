# Agent Note: 专家团队经层级派发模式的阶段子代理运行

Status: implemented

[English](2026-09-15-expert-team-m3.md) | 中文

## Problem

expert-team 在 pipeline 模式下，运行时直接为每个阶段创建 persona-scoped 会话并通过 `followup()` + `whenIdle()` 驱动一轮。这意味着 controller/lead/worker 的角色差异只存活在数据包的 YAML 声明中——运行时对三个阶段一视同仁地创建会话。M3 的软件开发团需要 controller → lead → worker 的层级关系在运行时可见：lead 阶段应该能够作为派发父节点，worker 阶段应该作为被派发的子节点，这样 hierarchy 守卫才能根据角色差异执行工具策略，并且 host 侧的 hierarchy 绑定表才能追踪父子关系。

## Decision

运行时对 hierarchical 模式的每个阶段会话，在创建之后、投递简报之前，通过 `ctx.agentBindings.bind` 将其绑定进 hierarchy 角色表。绑定 carries 三件事：role（controller / lead / worker）、parentSessionId（派发父节点，仅 worker 有值）、pluginId（`expert-team`）。绑定是 best-effort：环境不挂载 agentBindings 时静默跳过，真实部署永远挂载。

会话的 session header 同步注入 `parentSession` 和 `delegationDepth`（父节点深度 + 1），使得 hierarchy 守卫在执行时能通过 `delegationDepthOf` 读到正确的深度，不超出绝对预算。Worker 阶段在编排器一侧通过 BFS 沿 depends_on 图寻找最近已完成的 lead 或 controller 作为父节点；找不到时静默跳过绑定。

M3 复用 scoped-create 作为派生 seam，而非使用 `agentHierarchy.createChildAgent` 的 dispatch seam：expert-team 阶段没有 registered worktree，dispatch seam 要求工作树绑定；scoped-create + 绑定在运行时角色表的路径更轻，且与 pipeline 模式共享同一条派生链路。

## Alternatives considered

**使用 agentDispatch.createChildAgent 完整派发。** 否决：dispatch seam 要求 registered worktree（工作树绑定 + cwd 匹配 + 独立于父节点），expert-team 的产物是运行目录下的文件而非工作树；引入 worktree 管理不产生对应收益。

**在 setup window 中做角色绑定。** 否决：binding 需要 agent 的 session 已经在 session store 中持久化（`bindPreparedSession` 在 setup 内部调用），但 scoped-create 的 setup window 在 session 持久化之前；事后 `bindAgent` 同样有效且时序更清晰。

**为所有阶段安装 hierarchy 守卫工具限制。** 否决：guard 的 `leadPluginScopes` 按 creator agentId 查表，expert-team 的阶段 session id 在运行时派生（含 runId），部署无法在挂载时预配置；守卫的 deny face 不影响专家 allowlist 的工具集（专家 allowlist 更严格），所以绑定产生角色关系而不产生工具副作用。

## Consequences

买到：层级关系在 host 侧可见——`ctx.agentBindings.list()` 能按 role / parentSessionId 过滤 expert-team 的绑定行；controller → lead → worker 的角色链持久的 session header + binding 双写；worker 阶段的派发父节点通过 depends_on 图自动推导，无需数据包维护额外字段。工具策略不变：专家 allowlist 仍然是 primary restriction，hierarchy 守卫的 deny face 不影响专家 allowlist 覆盖的工具集。成本：绑定后 session header 含 parentSession / delegationDepth，但这两字段对 expert-team 阶段语义无影响；legacy 部署不挂载 agentBindings 时绑定静默跳过，hierarchy 侧不可见但阶段本身不受影响。

## Testing

运行时单元测试通过 bind 的 best-effort 路径验证：不挂载 agentBindings 时绑定静默跳过；worker 阶段 resolveParentAgent 沿 depends_on BFS 找到最近 lead / controller 父节点；绑定后 session header 包含正确的 parentSession + delegationDepth。编排测试新增两条 hierarchical 路径：一是通过真实 Loader 启动 cordis.yml 挂载分层 fixture 包，controller → worker 两阶段跑通、产物落盘、run-state.json 镜像一致；二是挂载 Storage + StorageDomain + AgentBindingRegistry 后验证 binding 行记录——controller 无 parent、worker 的 parentSessionId 指向 controller 的 agentId、pluginId 为 expert-team。REAL 组合规格在 mock 模型适配器驱动下运行 expert_team_list / expert_team_run / expert_team_status / expert_team_approve 四个工具，承担过渡期的模型可见覆盖。
