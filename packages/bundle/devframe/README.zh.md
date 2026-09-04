# `@deepseek-ai/dsh-devframe`

[English](README.md) | 中文

这是 DSH 的轻量 DevFrame Profile 层。运行 `dsh --profile devframe` 时，现有的 `dsh-base` 和 `dsh-web-app` 保持不变，随后挂载一个由 Host 持有的控制器 Session 服务、一个有界的无头任务入口和一个原生 client 投影。它不会替换 DSH 的工作区、Session、聊天、模型选择、工具、持久化、Web 服务器或 API 网关。

本包只是静态 [`cordis.patch.yml`](cordis.patch.yml) 载体。随包提供的 `dsh --profile devframe` CLI 会取得 Profile Host fence，并在 Loader 完成后自动打开稳定的 Global Controller。`--port`、`--host` 等普通 Web 参数仍由 `dsh-web-app` 负责；DevFrame 任务 provider 只有在首个应用参数是 `task` 时才接管。使用一次性的 `task` 命令时，Profile 会切换到无头模式，解析或注册一个原生 Workspace，并通过 Project Controller 执行一到两轮有界 Goal Round：

```bash
DSH_DEVFRAME_EXPERIMENTAL_TASKS=1 dsh --profile devframe task --project <workspace-id-or-path> --objective "run the focused tests" --rounds 1
```

结果是一个不含路径的 JSON 记录，其中只有项目、Goal、Session 和结果标识。命令之外的 Project Controller 仍需显式打开。 [`client 包`](../../client/ui-devframe-control-session/README.md)只接受有界的 `controller/identity` 字段，绝不会选取项目根路径。

## 模型体验

### 总控身份投影与有界 Goal dispatch

#### 模型会看到什么

仅身份打开不会增加模型可见内容。Host 显式调用 `dispatchGlobalGoal` 时，会把原生 Goal Round 提示词以及正常的 AgentLoop 请求／回复事件写入同一个 DSH Session；有界的 `controller/identity` 事件仍只是 Host 与 client 之间的投影约定，不会加入系统提示词或消息。

#### Token 影响

仅身份打开不消耗模型 token。显式有界 dispatch 会消耗配置模型的正常请求 token；本组合包不增加自动 agent loop，也不新建第二套 task／run 日志。

#### KV Cache 影响

仅身份打开不会贡献模型缓存前缀。dispatch 的缓存行为由配置的 provider 决定，本组合包不宣称缓存策略。

## 已知限制与后续工作

- **有界任务入口，还不是自治团队**：CLI 可以通过 Project Controller 显式派发一到两轮 Goal Round；Global→Project 通信、独立 Executor worker、审核循环、预算和无限持续执行仍延期。
- **任务入口仍是实验开关**：权限与审计地基完成前，任务派发默认关闭。只有设置 `DSH_DEVFRAME_EXPERIMENTAL_TASKS=1` 才会启用；否则命令会在发布任务服务、调用 AgentLoop 或写入任务 Session 之前退出。这个 tracer 不是安全总控权限边界。
- **Project 仍需显式打开**：随包启动的 Global Controller 会自动打开；选定工作区后才打开对应的 Project Controller。
- **必须有可用模型配置**：组合后的 Profile 没有可用 provider/model 路由，或模型在每轮预算内没有返回时，任务命令会安全失败。
- **单个受 fence 保护的 DevFrame Host**：Profile fence 允许同一 `$DSH_HOME` 只有一个持久 DevFrame 写入者；第二个 DevFrame Host 会安全失败。非 DevFrame Profile 仍保留 DSH 原生并发行为。
