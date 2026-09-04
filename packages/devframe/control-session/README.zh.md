# `@deepseek-ai/dsh-devframe-control-session`

[English](README.md) | 中文

DevFrame 的 Host 侧控制器 Session。本包提供 `ctx.devframeControlSessions`，复用 DSH 的 Agent Registry、Session Store、持久化服务、Goal Service 和 Workspace Registry，不新建另一套控制器数据库或运行时。

## 服务 API

- `openGlobal({ profileId, signal? })` 使用固定的非项目 cwd `$DSH_HOME/devframe-control` 打开 `devframe-global:<profileId>`。
- `openProject({ profileId, workspaceId, signal? })` 解析原生 Workspace，使用原生 Session header 中的 Workspace 路径打开 `devframe-controller:<workspaceId>`，再把已持久化的 Session 关联到该 Workspace。
- `dispatchGlobalGoal({ profileId, objective, maxGoalRounds?, signal? })` 通过 Global Controller 的 AgentLoop 运行一轮有界的原生 Goal Round，并在 `ctx.sessions.flush(session)` 成功后返回不含路径的 trace。`maxGoalRounds` 只能为 `1`；组合后的 Host 必须提供已配置的默认模型、AgentLoop、Goal Service 和 goal-round driver。
- `dispatchProjectGoal({ profileId, projectId, projectRoot, objective, maxGoalRounds?, signal? })` 在 Slice 0 中以 `PROJECT_DISPATCH_DISABLED` 失败关闭：Project Controller 会挂载已发布的 coding preset 和项目 File/Shell 工具，但项目写入之前必须具备的 Slice 1A authority 与 Slice 1C policy gates 尚不存在。仅身份的 `openProject` 路径仍可用；完整 dispatch 机制会为后续受门控的 Slice 1 保留。

在单个 Host 进程内，使用相同预期身份重复打开同一 ID 会返回本服务持有的同一个实时 Agent；预期身份冲突时会以 `LIVE_COLLISION` 失败。ID 只接受长度受限的 ASCII 标识字符。公开失败使用稳定的 `ControlSessionError` 代码，绝不回显 profile ID、workspace ID、路径、持久化 payload、提示词或凭据。

## Profile Host fence

本包还导出 `acquireProfileHostFence()`。当组合树包含 `devframe-control-session` 行时，CLI 会在任何配置插件挂载前获取 fence，把不含 token 的 owner 投影提供为 `ctx.profileHostFence`，先完整释放插件树，最后才释放 fence。没有该行的 profile 保持原生 DSH 并发行为。

lease 特意覆盖整个 `$DSH_HOME`，固定存放在 `$DSH_HOME/devframe/host-lease.json`，而不是按 profile id 分锁：同一个 Harness home 下的 DevFrame profile 共用同一 JSONL 持久化权威，不能成为互相独立的 writer。严格的 version 1 记录只包含 `version`、随机 ownership `token`、`pid`、规范化 `hostname` 和 `startedAt`；公开错误不会携带这些值或绝对路径。

创建使用独占 `wx`。已有同机 owner 只有在 `kill(pid, 0)` 返回 `ESRCH` 时才可接管；活跃 PID、`EPERM`、异机记录、畸形数据以及任何无法确定的进程或文件系统结果都会失败关闭。接管和释放都由独占 transition 记录串行化，先验证 owner token，再把 lease 原子重命名为唯一 tombstone，并且只删除该 tombstone。因此，普通 lease 持有进程被强制终止后，同机下次启动可以恢复，同时不会放行两个 writer。

## 身份与持久性

创建操作会先准备一个尚未发布的 Session，在序号 0 追加唯一的 version 1 `controller/identity` 事件并完成持久化，然后才把它恢复进实时 Agent 与 Session 注册表。服务会校验 Agent、Session 与 header 的关系，并且只在 `ctx.sessions.flush(session)` 成功后返回。恢复操作要求相同的角色专用 cwd；已有持久化产物无法恢复时，系统会把它视为无效身份，绝不会借此创建替代权威。

该事件包含 `schemaVersion`、`role`、`sessionId`、`profileId`、规范 `cwd`，Project Controller 还包含 `workspaceId`。这不会新增路径暴露：原生 DSH Session 摘要本来就会把相同的 header cwd 发送到浏览器；有界身份卡不会渲染 cwd。因此 Global Controller 不会再通过 `process.cwd()` 继承 Host 的启动项目；Project Controller 仍只使用已注册 Workspace 的路径。这个仅身份 tracer 不会声称自己使用了 `agentPreset`，因为它并没有真实挂载 preset。

## 执行策略

Global Controller 初始化会安装空工具允许列表和阻止项目／工具执行的 guard。Project Controller 保留现有 DSH 工具注册表，但仅用于身份打开，并且只有在请求的项目 id、根目录与已注册 Workspace 一致后才会打开。Slice 0 的有界 dispatch 只支持 Global Controller：它创建一个原生 Goal，准入一轮 Goal Round，等待 AgentLoop 轮次结束，flush Session，然后只返回安全的标识符和路由元数据。Project 写入 dispatch 以 `PROJECT_DISPATCH_DISABLED` 硬阻断，直到 Slice 1A/1C gates 存在；后续显式 Global 任务会先收尾之前已经停稳的 Goal，再创建自己的 Goal；正在 armed 的活动 Goal 绝不会被并发覆盖。worker 派发、策略升权、重试和后续自治 DevFrame 编排循环仍不在本切片内。

## 模型体验

### 仅身份打开与有界 Goal dispatch

#### 模型看到的内容

仅身份打开不会增加模型可见内容。首条有界 dispatch 会把原生 `goal/change` 事件、Goal Round 提示词以及模型正常的请求／回复事件写入同一个 DSH Session；它不会新建第二套 task／run 日志，也不会在返回的 trace 中暴露路径、提示词或凭据。

#### Token 影响

仅身份打开不消耗模型 token。有界 dispatch 会消耗配置模型请求所需的 token；token 统计和用户可见预算控制尚未纳入本 tracer。

#### KV Cache 影响

仅身份打开不会创建模型缓存前缀。dispatch 的缓存行为由配置的 provider 决定，本切片不宣称缓存策略。

## 已知限制与延期工作

- **中断 transition 需要恢复**：进程若在短暂的接管或释放 transition 记录存在期间被强制终止，后续启动会保持阻断，不会猜测 writer 是否已经准入。Readiness 诊断必须在操作者确认没有 DevFrame Host 运行后要求显式本机恢复。
- **尚无原子 materialize API**：身份创建目前通过公开持久化 `create` 和 `append` 操作完成，再进入实时发布。首次 append 失败后仍保持私有，并可由本服务安全重试；结果不确定或不兼容的产物会被阻断，绝不会被报告为就绪。
- **显式 profile 身份**：调用方必须提供稳定且经过校验的 `profileId`；本包不提供 profile UUID，也不会从 cwd 或 telemetry 身份推导。
- **只有有界 dispatch，且 Slice 0 仅支持 Global**：Global dispatch 只准入一轮 Goal Round，并要求组合中已经挂载 goal-round driver；Project dispatch 以 `PROJECT_DISPATCH_DISABLED` 阻断，直到 Slice 1A/1C gates 存在。worker 派发、控制器间通信、策略、重试、预算和自治的无限迭代仍不属于本包。
- **任务复用是显式的**：Agent 空闲后，新请求可以收尾之前处于 `blocked`、`paused` 或 disarmed 状态的 Goal；如果仍有 armed 的活动 Goal，则返回 `GOALS_UNAVAILABLE`，不会覆盖旧任务。
