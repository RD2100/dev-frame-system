---
description: "实验组地图：不进入正式发布的私有原型与内部专用插件，供浏览本组的用户与维护者阅读。"
kind: "package-group"
---

# packages/experimental

[English](README.md) | 中文

## 概述

实验组包含不属于任何正式发布的原型能力：它们运行在真实 harness 上，但约定可能变更，也不提供支持承诺。本组包含 Agent Teams、跨 realm Inspector、代码执行 seam 的 CPython 子进程后端，以及预览部署使用的浏览器 worker 运行时与镜像打包器。用这些包来尝试未发布的能力；它们没有稳定性承诺，已发布产品不得依赖它们。

## 目录

- [包](#packages)
- [相关文档](#related-documentation)
- [开发备注](#dev-note)

-----

<a id="packages"></a>
## 包

| 包 | 职责 | ctx 键 |
|---|---|---|
| [`agent-hierarchy`](agent-hierarchy/README.zh.md) | 插件化层级的三态角色策略、创建入口守卫、插件范围校验与冷恢复 | `ctx.agentHierarchy` |
| [`agent-team-profile`](agent-team-profile/README.zh.md) | Agent Teams 的显式源码 checkout profile 层 | — |
| [`agent-team`](agent-team/README.zh.md) | 具名 teammate，成员之间持久消息与共享任务板 | `ctx.agentTeams` |
| [`agent-team-web-profile`](agent-team-web-profile/README.zh.md) | Agent Teams 的显式源码 checkout Web 层 | — |
| [`agent-worktree`](agent-worktree/README.zh.md) | 构建在 worktree registry 之上的每 Agent worktree seam：单一写入者绑定与三个 `worktree_*` 工具 | `ctx.agentWorktree` |
| [`client-ui-agent-team`](client-ui-agent-team/README.zh.md) | Web Team roster、任务板与 teammate 导航 | — |
| [`code-runtime-python`](code-runtime-python/README.zh.md) | 代码执行 seam 的 CPython 子进程后端 | `ctx.codeRuntime` |
| [`devframe`](devframe/README.zh.md) | 实验性单项目控制器的共享契约 | — |
| [`inspector`](inspector/README.zh.md) | 用于 Host 调试、Client Runtime 检查、网络采集与 Cordis 树的跨 realm CDP hub | `ctx.inspector` |
| [`agent-evidence`](agent-evidence/README.zh.md) | 代理工作的追加式证据台账：任务/Goal 绑定回执、提交回执与验证快照 | `ctx.agentEvidence` |
| [`agent-reliability`](agent-reliability/README.zh.md) | 进程树停止、准入切断、不确定调用对账与刷写屏障，集于一个服务 | `ctx.agentReliability` |
| [`project-contracts`](project-contracts/README.zh.md) | 插件化代理层级的共享类型词汇：角色、任务状态、ID、记录与存储接缝 | — |
| [`project-controller`](project-controller/README.zh.md) | 项目任务板：TaskState 流转、有界开发预算、生命周期与仅限 controller 的合并门禁 | `ctx.projectController` |
| [`project-memory`](project-memory/README.zh.md) | 基于用户选定 Obsidian Vault 子树的有界追加式项目记忆：作用域化搜索/读取/追加工具、会话日志回执、路径包含与如实失败报告 | 库服务，不使用 ctx key |
| [`session-identity`](session-identity/README.zh.md) | 持久代理绑定注册表与准确 cwd 的原生会话创建 | `ctx.agentBindings` |
| [`tool-agent-team`](tool-agent-team/README.zh.md) | 让模型创建、发消息与协调 teammate 的十个工具 | 按作用域注册工具到 `ctx.tools` |
| [`webworker-packer`](webworker-packer/README.zh.md) | 构建浏览器 worker 预览所消费的 gzip 压缩 VFS 镜像 | 库与 CLI，不使用 ctx key |
| [`webworker-runtime`](webworker-runtime/README.zh.md) | 在专用浏览器 worker 中运行 harness 插件树 | 库与 worker 入口，不使用 ctx key |

-----

<a id="related-documentation"></a>
## 相关文档

- [实验包决策](../../.agents/notes/implemented/architecture/2026-08-18-experimental-agent-teams-packages.zh.md)——位置、发布排除与依赖隔离。
- [Agent Teams 子系统](../../docs/subsystems/agent-team.zh.md)——持久 Team 类型与 `ctx.agentTeams` 服务 API。
- [实验子树规则](AGENTS.md)——实验状态放宽了什么、不放宽什么。

-----

<a id="dev-note"></a>
## 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
