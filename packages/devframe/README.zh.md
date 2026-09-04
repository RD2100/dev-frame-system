# devframe/：控制器 Session 地基

[English](README.md) | 中文

建立在 DSH 原生 Session、Workspace、Agent、Profile 和浏览器界面之上的 DevFrame 扩展。本组把控制器身份留在现有 DSH 运行时中，不拥有第二套工作台或持久化系统。

| 包 | 职责 | ctx 键 |
|---|---|---|
| [`control-session/`](control-session/README.md) | 仅身份的稳定 Global Controller 与 Project Controller Session | `ctx.devframeControlSessions` |

子包 README 负责服务、持久性、隐私、执行和单 Host 进程约定。
