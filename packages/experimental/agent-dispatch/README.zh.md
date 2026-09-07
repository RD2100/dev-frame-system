# @deepseek-ai/dsh-experimental-agent-dispatch

横跨 agent-hierarchy 引擎的宿主侧派发入口。服务定义向组合层调用方暴露
`ctx.agentDispatch.createChildAgent(parent, request, options)`；引擎
（`@deepseek-ai/dsh-experimental-agent-hierarchy`）拥有子 agent 身份与生命
周期，本适配器自身绝不实现创建。

## 入口契约

- 在引擎调用前以权威注册表行校验请求：已注册的 worktree id、存在的目录、
  path/branch 匹配，以及该 workspace 的锁占有着（`status` 只回报
  `directoryExists/branch/clean`；path 与 `lockedBy` 来自
  `worktreeRegistry.list`）。
- 复用引擎的批准范围契约
  （`config.leadPluginScopes[creator.agentId]`）——适配器不复刻角色
  policy；引擎拒绝原样透传。
- 装配在入口内部完成：preset `composeFrom(parent.ctx)`、由子 session id 持
  有的 `worktreeRegistry.bind` 单写锁，然后是引擎的
  `bindPreparedSession`；可选 `prompt` 仅在引擎发布之后经
  `child.agent.followup` 送达。
- 调用方提供的 `setup` 在装配片之后运行，不得用来供给装配本身。

## 错误面

`AgentDispatchError` 错误码：`DISPATCH_WORKTREE_UNREGISTERED`、
`DISPATCH_WORKTREE_MISMATCH`、`DISPATCH_PARENT_UNBOUND`、
`DISPATCH_HIERARCHY_DENIED`。引擎拒绝（角色、范围、深度、去重）以其自身
类型化错误透传。

`DispatchAgentOptions` 是适配器 options 面：四个引擎
`CreateChildAgentOptions` 字段按键显式透传，外加用于权威行校验的必填
`workspaceId` 与可选 `prompt`。

不发布运行时 invariant 伴随物：适配器承诺的每一项保证（worktree 注册、
path/branch 匹配、锁排他、范围批准）都从它所调用的同一批权威注册表行与引
擎求值推导，拒绝在其调用返回的 `AgentDispatchError` 面上可观察，因此不存
在可能分叉的独立观察。

## 已知限制与待办

- 证据状态：真实 Loader 组合套件证明工具注册与 controller/lead/worker 可见
  性面；真实模型回合证明 service 面与一次真实派发回合（worker 工件）。
  shipped opt-in overlay 已接线——其候选 profile 验证（显式 `--patch`、隔
  离 HOME）是剩余验收步骤。
- 中断创建的恢复复用引擎的 `recoverChildAgent` 语义（typed
  `SessionPersistenceNotFoundError` 按原 id 恢复；损坏与取消不 fallback）；
  适配器只新增持久身份查询，身份复用绝不重投 prompt。
