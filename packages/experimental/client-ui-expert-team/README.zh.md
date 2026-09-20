---
description: "专家中心 Web 入口：提供可搜索目录、新会话召唤操作、当前进程运行记录，以及预留的技能和连接器入口。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-expert-team

[English](README.md) | 中文

## 概述

`dsh-experimental-client-ui-expert-team` 是[专家团队核心](../expert-team/README.zh.md)的常驻 Web 入口。它挂载生成的 `ctx.remote.expertTeam` 命名空间，并向侧栏的 `sidebar.footer.action` 座位注册触发器。触发器打开包含“专家”“技能”“连接器”三个入口的专家中心。“专家”页把宿主快照中的已挂载专家投影为可搜索、可按团队筛选、可按名称排序的卡片，并提供详情、召唤与当前进程运行记录操作；召唤会在新的空白对话中预选专家并填入可编辑提示。详情视图区分「启动流水线」与「召唤专家（咨询模式）」两个直接执行按钮，分别调用 `startRun` 与 `consult` Remote 方法，绕过草稿预填路径；等待审批的运行行可展开读取关口问题并记录通过/驳回决定。其他两个入口会明确说明数据源尚未接入。正式发布排除本包，只能从源码 checkout 使用。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与推迟事项](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装到 DevFrame Web profile

[DevFrame profile 层](../devframe-profile/README.zh.md)已经挂载带论文与开发数据包的宿主核心以及本浏览器入口。手动组合时，在宿主挂载 `@deepseek-ai/dsh-experimental-expert-team`，在 Web 侧挂载本包；本包根入口在 headless 组合中为空操作，Web loader 会按 `dsh.client` 清单选择它的 `/client` 导出。

### 你会得到什么

- 常驻侧栏触发器；当运行处于 `running` 或 `waiting-approval` 时显示活动数量。
- 已挂载团队中的完整专家目录，可按名称、角色、id 或团队搜索，并按团队筛选、按综合或名称排序。
- 卡片和详情操作会打开正常的新会话流程、选中专家并填入可编辑提示；只有用户提交后提示才会发送。
- 选中专家后的详情视图，展示所属团队、运行模式、绑定阶段、关口与声明工具；未选中详情时，卡片网格会使用可用宽度。
- 技能与连接器入口会显示明确的“尚未接入”说明，不展示无效控件或伪造目录。
- 最近运行区域展示当前进程最近六条记录，并提供显式刷新与关闭操作。Remote 读取失败会显示错误，而不会被替换成伪造状态。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

浏览器入口（`src/client/index.ts`）挂载生成的专家团队 Remote contribution，并交给 [`mountExpertTeamUi`](src/client/mount.ts)。挂载过程注册英文与中文的 `expert-team` 字典，注入侧栏条目（id `expert-team`，order 20），并注入会话级 `conversation.input.left` 专家标签。卡片读取 `ctx.remote.expertTeam.view()` 后把召唤选择交给 `ExpertSelectionController`；控制器调用 `uiWorkspace.startSession()`，等待空白会话到达，再通过 `ctx.conversation.input` 写入预填提示。宿主 gateway 额外暴露 `startRun`、`consult`、`approve` 与 `getRun`：详情视图直接启动流水线或咨询单个专家，等待审批的运行行通过 `getRun` 拉取完整快照、通过 `approve` 记录带可选批注的人类决定。客户端把返回的专家展平用于搜索、筛选、排序、详情和示例问题渲染；过期读取、选择状态与产品文案分别由对应的客户端界面负责。

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口与生成的 Remote 绑定 |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote 挂载、区域注册与侧栏贡献生命周期 |
| [`src/client/ExpertTeamCard.tsx`](src/client/ExpertTeamCard.tsx) | 常驻触发器、目录、详情操作与示例问题 |
| [`src/client/ExpertSelectionChip.tsx`](src/client/ExpertSelectionChip.tsx) | 空白会话输入框中的专家选择标签 |
| [`src/client/selection.ts`](src/client/selection.ts) | 新会话交接与预填草稿协调 |
| [`src/client/locales.ts`](src/client/locales.ts) | `expert-team` 区域命名空间及中英文字典 |
| [`src/index.ts`](src/index.ts) | profile 组合使用的空操作宿主入口 |
| — | 不发布运行时 invariant 伴生；卡片是宿主 Remote 快照的纯消费者。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [专家团队核心](../expert-team/README.zh.md)——数据包加载、编排、关口与宿主 Remote 的拥有者。
- [DevFrame profile](../devframe-profile/README.zh.md)——同时挂载宿主与浏览器行的源码 checkout Web 组合。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

### 专家团队专家中心

#### 模型看到什么

专家中心本身只运行在浏览器中，不注册工具或提示词段落。召唤操作会在空白会话中填入普通的、用户可见的草稿文字并显示专家标签；如果用户提交该草稿，正常 Conversation 路径会发送它，已挂载的 `expert_team_run` 工具仍是模型可见的编排面。

#### Token 影响

召唤不会自动产生请求；用户提交的预填提示会像普通用户提示一样计入文本 token。

#### KV Cache 影响

本入口不贡献工具或 schema 内容；缓存影响只来自用户提交的提示文本，遵循正常 Conversation 行为。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **交接对话，不直接编排**——召唤操作只预填新会话，不调用运行或批准变更；启动运行与批准人工关口仍属于模型/宿主操作。
- **不会自动提交提示**——召唤后用户可以编辑提示或移除专家标签；没有可用工作区时，选择会暂存到能够打开空白会话为止。
- **只展示已挂载目录**——“专家”页只包含宿主 Remote 返回的团队与专家；“技能”和“连接器”已有可见入口，但对应 Remote 数据源尚未接入。
- **仅有当前进程历史**——宿主 Remote 投影编排器当前内存中的运行索引。`run-index.json` 仍是检查镜像，不是跨进程恢复来源。
- **刷新是显式的**——卡片在挂载、打开或点击刷新时读取；不订阅每次运行状态变化。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
