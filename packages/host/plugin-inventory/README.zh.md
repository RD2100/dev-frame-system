---
description: "面向 web GUI 宿主客户端的 Loader 清单，以及用户 Skill 与 MCP 管理 Remote。"
kind: "package-reference"
---

# @deepseek-ai/dsh-host-plugin-inventory

[English](README.md) | 中文

## 概述

客户端与设置页可以调用 `pluginInventory/list` 查看清单，调用 `listSkills`、`installSkill`、`setSkillEnabled`、`removeSkill` 管理用户 Skill，调用 `listMcp`、`createMcp`、`updateMcp`、`setMcpEnabled`、`testMcpEntry`、`removeMcp` 管理 MCP。Loader 清单仍是调用当下的投影；用户 Skill 存放在 `$DSH_HOME/skills`，MCP 配置持久化到 `$DSH_HOME/storages/mcp-servers.json`。Client 包通过显式的 [`api-remotes`](../../api/remotes/README.zh.md) 组合消费这个 Remote，而不导入 Host 实现。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步探索](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

当客户端或设置页需要展示宿主当前组合了什么——哪些插件已加载、已启用、是否存活，以及每个 Agent 预设会给会话什么——时调用 `pluginInventory/list`。Remote 是唯一入口：该服务仅供 Remote 使用，刻意不声明同进程 Cordis `Context` merge。

### 快照包含什么

每一行是一个非组 Loader 条目：其条目 id、精确模块标识、有效启用状态（含被禁用的祖先组）与当前根 Fiber 阶段。`pending` 表示条目等待加载，`loading` 表示正在读取，`active` 表示正在运行，`failed` 表示其 fiber 被拒绝，`unloading` 表示正在拆除；`null` 表示完全不存在存活的根 Fiber。结构性的 group 行会被跳过。

### 每个预设的组合

组合了 roster 时，`agentPresets` 按 roster 顺序携带每个预设一组：其 id、随部署内置还是用户自建（`trust`，客户端据此本地化内置预设名）、发布的显示名、未指名预设的会话是否组合它，以及压平后的插件行——条目 id（文件行未声明时为 null）、模块标识、有效启用状态、行自带的 `!!js` disabled 表达式（如有），以及组合存活时的根 Fiber 阶段。已有会话组合过的预设由其最新 standing 世代作答——即使其文件事后损坏也是如此，因为挂载才是这些会话实际运行的组合；开机以来从未被组合的预设由其组合文件作答，disabled 门用 Loader 上下文求值，且读取从不挂载预设。`conditional` 表示宿主无法求值的门；无人组合的坏预设保留在列表中，携带原因且没有行。没有 roster 时该字段缺席。

### 清单与管理

清单用于展示与诊断；管理方法只作用于用户自己的 Skill 与 MCP 条目，profile 和预设组合行仍为只读。Skill 内容通过 Remote 写入 `SKILL.md`，MCP 投影不会返回密钥。MCP 编辑只替换表单展示的字段，同时保留已存的 `args`、`cwd`、`env`、`headers` 与重试设置等传输选项。MCP 存储属于 DSH home 的本地状态，在宿主文件系统支持时使用私有文件与目录权限写入。由于服务每次调用都读取 Loader，答案反映当前组合，而不是缓存视图。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

### 设计理念

网关让 Loader 作为清单与实时 MCP 状态的权威。用户 Skill 文件在受控根目录边界内校验，并用规范的调用字段重写；MCP 写入通过临时文件原子改名并串行化，启动时在提供 MCP 读取或修改前恢复持久条目。Agent 预设 roster 仍由每次调用的 `ctx.get('agentPresets')` 可选解析。

### 阶段映射

Fiber 状态映射到公共阶段词汇，其中 `disposed` 折叠为 `null`——fiber 已消失的条目没有可报告的存活根。因此阶段从不区分为什么没有存活根：条目可能从未启动，也可能其 fiber 已被释放。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | `PluginInventoryGateway`：`pluginInventory` Remote 服务与 Loader 投影 |
| [`src/types.ts`](src/types.ts) | 公共 payload 类型：`PluginInventoryEntry`、`PluginInventorySnapshot`、`PluginFiberPhase` |
| — | 不发布运行时不变式伴生入口；每个快照都投影 Loader 持有的状态。 |

Typert 生成由 `./typert` 与 `./remote` 导出的 Host 和 Client Remote 产物。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

当清单约定不够用时阅读以下内容：先看 Remote 如何到达客户端，再看它所投影的 Loader 与渲染它的界面。

- [Remote 组合](../../api/remotes/README.zh.md)——客户端如何在不导入 Host 实现的情况下消费 `pluginInventory/list`。
- [Cordis 插件 loader](../../../vendor/loader/README.md)——本包所投影条目的那个 Loader。
- [插件清单设置界面](../../client/ui-settings-plugin-inventory/README.zh.md)——渲染该清单的浏览器侧投影。

-----

<a id="model-experience"></a>
## 模型体验

无。这个 Host 管理面不注册面向模型的内容。

#### KV Cache 影响

无；该包既不组装也不发送提供方请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制说明一个点时刻清单无法告诉客户端什么。它们是当前包约束，不是任务积压。

- **仅表示调用当下**——结果不包含持久的失败历史或订阅；只要不存在存活的根 Fiber，就会报告 `null`，而不区分其原因。
- **profile 与预设行仍只读**——管理范围限定为用户 Skill 文件与本服务创建的 MCP 条目。
- **预设仅随 roster 出现**——未装 `dsh-agent-presets` 的部署只提供 Loader 条目；`agentPresets` 字段缺席而非为空。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
