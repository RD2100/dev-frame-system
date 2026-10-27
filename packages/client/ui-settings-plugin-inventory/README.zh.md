---
description: "dsh Web 客户端设置中的插件清单，以及用户 Skill 与 MCP 管理标签页。"
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-settings-plugin-inventory

[English](README.md) | 中文

## 概述

`dsh-client-ui-settings-plugin-inventory` 向 Web 设置贡献插件清单与管理标签页，并向能力中心贡献独立的技能和连接器页面。**插件列表**在首次被选择时懒调用 `ctx.remote.pluginInventory.list()`，把清单按作用域分成两个可折叠分组。**技能与连接器**读取用户 Skill 与 MCP 客户端，并提供安装、启停、卸载、测试、编辑和移除操作。页面提供「刷新」重新取得管理快照，并标明 profile 或 Agent 预设是配置拥有方。

插件列表保留原有的作用域视图：Agent 预设组在前且默认展开，全局组随后收起；搜索过滤两组，通用失败不会泄露传输细节。技能与连接器标签页在选中会话时报告真实的会话目录；没有当前会话时会说明技能为何不可用，同时仍展示全局连接器状态。

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

打开设置中的「插件」分区并选择**插件列表**标签页，即可查看宿主的插件清单。插件激活期间不会读取 Remote——首次选择该标签页时才挂载组件，并通过 `api-remotes` 懒调用 `ctx.remote.pluginInventory.list()`。能力中心也会把同一管理功能显示为独立的技能和连接器页面。

选择**技能与连接器**即可查看并管理用户能力。当前会话的有效技能通过 `ctx.remote.skills.list()` 读取；用户 Skill 的安装、启停和卸载调用 Host 管理 Remote。MCP 与连接器条目来自宿主插件清单，带有 Loader 阶段和有效启用状态；页面提供添加、编辑、测试、启停和移除。搜索框可过滤任一面板，「刷新」会重新读取四份快照。profile 或 Agent 预设组合行仍由其配置拥有方管理。

### 阅读卡片

每张收起的卡片使用模块短名称作为标题，并以小标签表示启停状态；已启用的条目还会显示彩色根 fiber 状态圆点。展开卡片后会显示声明的条目 id、完整模块标识与状态事实：预设行说明它来自哪个预设、组合存活时的运行状态，以及它携带的禁用条件；被预设提供的全局行说明它由 Agent 预设按会话提供、列出启用它的预设，并提供跳转到预设组的入口。预设名经共享的 `presetDisplayText` 纯函数（`dsh-agent-presets/display`）叠在 [`ui-agent-preset`](../ui-agent-preset/README.zh.md) 的字典上解析：内置预设走当前语言，用户自建预设保留自己的元数据，因此英文界面不会回显预设文件里的中文名。搜索按模块名称与条目 id 过滤两组。

### 预设切换器

切换器与通用设置各行使用同一种「选择胶囊 + 菜单」控件。它列出 roster 的每个预设——默认项带后缀、坏预设带标记——并且只改变列表显示什么：它不写任何设置，选中坏预设时在行的位置展示 discovery 报告的原因。选默认预设或某个会话的预设仍在原处：Agent 预设分区与新会话页。

### 重试失败的读取

读取失败会在标签页内渲染通用失败状态；重试会重新执行懒 `list()` 调用，且不会暴露传输细节。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

插件激活期间不执行 Remote 读取，首次选择时才取得快照。修改操作调用生成的管理 Remote，随后重新读取快照，因此页面不自行维护本地真源。

### 注册

浏览器插件注册 id 为 `all` 与 `skill-connectors` 的本地化 `settings.plugins.tab` 贡献，以及 key 为 `skills` 与 `connectors` 的 `capabilities.center.tab` 贡献。各自的分区拥有导航；两种注册都使用 `ctx.slots.inject()` 和相同的 Host 回调。管理页读取官方 `remote.skills` 与当前会话列表，再用选中的当前会话寻址 Remote。

### 渲染

行 key 按作用域限定（`global:`、`preset:<id>:<index>`），因此同一模块出现在两个作用域时保持各自的展开状态；条目 id 只在行声明了它时作为详情展示，代码不按字符串形状对它分类。预设提供标记在客户端推导：一个全局条目在全局被停用、且至少一个预设行对同一模块标识实际启用时才携带它，因此被所有预设关掉（或仅条件声明）的模块保持单纯的已停用，而不是夸大提供关系。能力标签页从选中会话投影技能元数据，并过滤模块标识中命名为 MCP 或 connector 的清单行；两个投影都保留 profile 或预设作为写入拥有方。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

以下页面覆盖设置分区、Remote 调用与宿主侧投影。

- [ui-settings-plugins](../ui-settings-plugins/README.zh.md)——本标签页注册进的「插件」分区。
- [ui-settings](../ui-settings/README.zh.md)——声明 `settings.plugins.tab` 的领域底座。
- [api-remotes](../../api/remotes/README.zh.md)——`pluginInventory.list()` 背后的 Remote BFF 表面。
- [plugin-inventory](../../host/plugin-inventory/README.zh.md)——本标签页使用的宿主侧 Loader 清单与用户能力管理 Remote。
- [session-controller](../../api/session-controller/README.zh.md)——能力标签页所使用的按会话寻址技能目录。

-----

<a id="model-experience"></a>
## 模型体验

无。该包是浏览器端清单投影，不注册任何面向模型的内容。

#### KV Cache 影响

无；该包既不组装也不发送提供方请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制定义清单视图的新鲜度与触达范围；它们是当前包约束。

- **每个管理页挂载或刷新时读取一份快照**：页面不订阅 Loader 或技能变化，也不会在重连后自动读取；刷新或重新打开页面才会取得新快照。
- **技能按会话寻址**：没有选中的当前会话时，宿主无法回答工作区与预设相关的技能目录；页面会如实说明，而不会猜测另一个会话的结果。
- **profile 与预设组合只读**：标签页管理用户 Skill 文件与 MCP 条目，不修改部署拥有的组合行。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>

**运行时不变式：** 不发布伴生入口。Settings 与能力中心 contribution 使用 Host 拥有的用户 Skill 与 MCP 管理表面。
