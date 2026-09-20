---
description: 提议的专家团插件与数据包：专家目录、带人工关口的流水线编排，以及论文专家团的分阶段研究工作流。
---

# 详细设计：专家团

[English](detailDesign-expert-team.md) | 中文

## 概述

本文定义专家团（expert team）特性：一个机制层，把多专家工作流运行为在宿主 agent 注册表上派生的人设作用域会话；外加描述专家及其阶段图（phase graph）的团队数据包（pack）。核心插件拥有目录加载、带人工关口的编排与只读宿主状态 Remote；每个团队（论文团、软件开发团）都是一个数据包，由专家 Markdown 文件、skill（技能）目录、`team.yml` 和结果对象 JSON Schema 组成，新增团队零代码。专家产物属于观察所得的上下文，被记录的人工关口决定是信任锚点——与[记忆设计](detailDesign-part3.zh.md)对已确认事实采用的公证处模型同构。当前 checkout 已包含论文团十个阶段、软件开发团六个层级阶段以及 Web 状态入口。

## 目录

- [背景与借鉴机制](#background)
- [需求分析](#requirements)
- [概要设计](#outline)
- [专家格式](#expert)
- [团队定义与校验](#team)
- [编排与关口](#orchestration)
- [模型工具与配置](#tools)
- [团队数据包](#packs)
- [测试策略](#testing)
- [里程碑](#milestones)

<a id="background"></a>

## 背景与借鉴机制

设计参考了六个开源项目，每个项目贡献一项具体机制，下表同时列出本设计明确不取的部分；此外，pack 格式押注行业事实标准：Markdown 人设（persona）加 skills 目录，与 Claude Code 的 subagent 和 skill 同构。

| 项目 | 本设计采纳的内容 | 明确不取的内容 |
| --- | --- | --- |
| [ChatDev](https://github.com/OpenBMB/ChatDev) | 阶段链作为组合单元，以及在指定阶段由人类占据评审位置进入循环。 | 固定的虚拟软件公司类比，以及角色之间的聊天消息传递。 |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | "Code = SOP(Team)"：标准作业程序沉淀在数据中，角色之间传递结构化产物，而不是对话记录。 | 其内置角色集和内部通信底座。 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 人设三元组（role、goal、backstory）、带期望产物与依赖 DAG 的任务，以及 pipeline/hierarchical 两种编排模式。 | 其运行时：由 DSH 的会话派生、skill 与人工决定替代。 |
| [AI-Researcher](https://github.com/HKUDS/AI-Researcher) | 自动化研究工作流的阶段分解（文献综述、选题、方法、实验、写作评审），以及一次运行可从不同输入层级进入。 | 把五阶段顺序当作定律：论文团调整了阶段划分，实验与写作阶段推迟。 |
| [PaperQA2](https://github.com/Future-House/paper-qa) | 引用纪律（综述中每条论断都带可核验引用），以及把撤稿/可靠性检查作为综述要求。 | 其存储引擎与后台索引器；专家使用会话的普通文件与搜索工具。 |
| [STORM](https://github.com/stanford-oval/storm) | 视角先行：先发现研究视角再做文献工作，再用视角控制提问的深度与广度。 | 其提纲生成与写作流水线的具体实现。 |

统领性的架构原则是机制与数据分离。核心插件只提供专家目录和带人工关口的流水线编排；论文团和软件开发团都是纯数据包。其余一切复用 DSH 既有能力而非新造：[agent 注册表](../packages/core/agent/README.zh.md)的作用域创建（scoped-create）接口、system-prompt 小节、工具限制与执行守卫、部署的[默认模型选择](../packages/core/agent-default-model/README.zh.md)、[project-memory](../packages/experimental/project-memory/README.zh.md) 实体锚定，以及会话事件日志。agent loop 不动。

<a id="requirements"></a>

## 需求分析

### 用例

| 编号 | 用例 | 结果 |
| --- | --- | --- |
| `UC1` | 用户以一个研究主题启动一次论文团运行。 | 运行按声明顺序执行各阶段，在第一道人工关口停靠，产物已落盘。 |
| `UC2` | 用户对关口做出决定：批准，或驳回并附批注。 | 批准继续运行；驳回把产物连同评审批注交回被关口阶段的专家修订，修订后的产物重新进入关口。 |
| `UC3` | 用户在流水线之外向单个专家提问。 | `expert_team_run` 接受 `expert` 加 `question`，派生一个携带该专家人设与工具允许列表的单轮会话，返回有界答案；不创建运行，也不产生产物。 |
| `UC4` | 部署挂载一个新的团队数据包。 | 目录仅凭配置即可纳入；核心零改动，无效 pack 在加载时快速失败。 |

### 功能需求

| 编号 | 必要行为 |
| --- | --- |
| `FR1` | 从已挂载 pack 加载全部 `<pack>/experts/<expert-id>.md`；校验 frontmatter 约定；对格式错误的专家、重复的 pack 目录或团队 id 快速失败。 |
| `FR2` | 加载并校验 `team.yml`：阶段 id 唯一、专家引用存在、`depends_on` 只向后引用（按构造即无环）、`entry` 一致、被引用的 schema 文件存在于 pack 内。 |
| `FR3` | 按声明顺序执行一次运行的各阶段；每个阶段派生一个人设作用域会话，简报包含运行请求、上游产物路径、handoff 核查清单和输出契约。 |
| `FR4` | 只有在阶段回复通过其结果契约——围栏 JSON 结果对象，以及声明了 JSON Schema 时的 schema 校验——之后，才把产物写入 `<artifactsDir>/<runId>/`；契约失败在同一个会话上重试至多 2 次，之后该阶段失败。 |
| `FR5` | 设有关口的阶段在产物落盘后停靠，等待人工决定；批准继续流水线，驳回携带批注重驱该阶段；每次决定都记录决定、批注与时间。 |
| `FR6` | 暴露四个模型工具：`expert_team_list`、`expert_team_run`、`expert_team_status`、`expert_team_approve`；咨询是 `expert_team_run` 的一种输入形态。 |
| `FR7` | 在每个提交点把运行状态镜像到 `<artifactsDir>/<runId>/run-state.json`，磁盘文件讲述完整运行故事；模型可见的一切——简报、工具结果、决定——都能从会话日志重建。 |

### 非功能需求

| 编号 | 必要属性 |
| --- | --- |
| `NFR1` | 机制与数据分离：新增团队只是新增 pack 文件；核心包不变。 |
| `NFR2` | 配置错误快速失败：pack 缺陷在挂载时以稳定的 `EXPERT_TEAM_*` 错误码拒绝；半挂载的专家团比缺席更糟。 |
| `NFR3` | 不硬编码可调参数：`packs` 与 `artifactsDir` 是经过校验的 Config 字段；结果契约重试上界 2 与 runId 生成格式是本设计的固定不变量，不是可调参数。 |
| `NFR4` | 信任模型：专家产物属于 `observed`，被记录的人工关口决定是信任锚点；pack 内容是被引用的数据，从不授予工具、权限或权威。 |
| `NFR5` | 模型可见 ⟺ 已记录：简报、工具结果或被记录决定展示给模型的任何内容，都能从会话事件重建。 |
| `NFR6` | 复用既有能力而非改动循环：全部行为经由 agent 注册表、prompt 小节、工具限制、默认模型选择与 project-memory 承载；不引入新执行循环。 |
| `NFR7` | 有界暴露：简报携带上游产物路径与简短描述，不携带产物内容；人设、产物正文、结果摘要与咨询答案都有显式字节上界。 |

### 范围边界

- 当前实现范围内：核心包（目录、流水线与层级编排、关口、四个工具、只读宿主状态 Remote）、论文团十个阶段、软件开发团六个层级阶段，以及常驻 Web 状态卡片。
- 推迟事项：核心层按产物保证的记忆记录、独立 DAG 阶段的并行执行、网站指南投影，以及在新进程中恢复已停靠的运行。
- 范围之外：agent loop 改动；文献索引或向量存储（仅在实测出现检索问题时再议）；一次运行内的跨团队编排；专家阶段使用基于工作树的 `agent_dispatch` 执行；模型代替评审人做关口决定的任何路径。

<a id="outline"></a>

## 概要设计

### 概念模型

| 概念 | 定义 |
| --- | --- |
| Pack | 只读的团队目录：`team.yml`、`experts/*.md`、可选的 `skills/<name>/` 目录（各含一个 `SKILL.md`）、可选的 `schemas/*.json` JSON Schema 文件。 |
| 专家 | 一个专家 Markdown 文件：人设正文加 frontmatter（身份、角色、目标、工具允许列表、可选 skills 与 handoff 检查项）。 |
| 团队 | `team.yml` 声明的一个具名编排：模式、入口阶段与阶段列表。 |
| 阶段 | 一个专家、其 `depends_on` 集合、其输出产物、可选结果 schema，以及可选关口。 |
| 运行 | 一个团队的一次执行，持有宿主铸造的品牌化 `runId`；产物与 `run-state.json` 位于 `<artifactsDir>/<runId>/`。 |
| 产物 | 一个阶段产出的一个文件；由宿主——绝不是专家——在回复通过结果契约之后写入。 |
| 关口 | 阶段上的人工检查点（`human-review`）；运行停靠直至决定被记录——批准继续，驳回携带批注重驱。 |

### 架构与模块布局

```text
pack (data, read-only)                core plugin (mechanism)
+--------------------------+  load   +-------------------------------+
| team.yml                 |-------->| catalog loader + validators   |
| experts/<expert-id>.md   |         | pipeline orchestrator (DAG)   |
| skills/<name>/SKILL.md   |         | expert runtime (sessions)     |
| schemas/<result>.json    |         | four model tools on ctx.tools; read-only status Remote |
+--------------------------+         +-------------------------------+
```

编排器与关口位于编排器模块；运行时负责派生会话并执行结果契约；目录是唯一的 pack 读取方。`packages/experimental/` 下新增两个包：

| 包 | 职责 |
| --- | --- |
| `@deepseek-ai/dsh-experimental-expert-team`（`packages/experimental/expert-team/`） | 目录加载器与校验器、流水线／层级编排器、专家运行时、四个模型工具与只读状态 gateway；Config `{ packs, artifactsDir }`；提供 `ctx.expertTeam` 与 `ctx.expertTeamGateway`。 |
| `@deepseek-ai/dsh-experimental-client-ui-expert-team`（`packages/experimental/client-ui-expert-team/`） | Web Remote 绑定与常驻只读侧栏状态卡片；浏览器专用，不增加模型可见面。 |
| `@deepseek-ai/dsh-experimental-expert-pack-paper`（`packages/experimental/expert-pack-paper/`） | 论文团 pack：专家文件、skill 目录、`team.yml` 与结果对象 JSON Schema；纯数据包，不含运行时代码。 |

### DSH seam 映射

| 关注点 | 既有能力 | 用法 |
| --- | --- | --- |
| 阶段会话 | [Agent 注册表](../packages/core/agent/README.zh.md)作用域创建（`ctx.agents.create`） | 每阶段一个人设作用域会话，命名为 `expert-team-<runId>-<phaseId>`，用 `followup` 加 `whenIdle` 驱动一轮；运行目录即会话的持久 cwd。层级阶段复用该接缝，再通过 `agentBindings` 记录角色／父级绑定；不分配工作树，也不调用 `agent_dispatch`。 |
| 人设与工具允许列表 | prompt 小节 + 工具限制 | 人设正文原样随一条 system-prompt 小节注入；专家的 `tools` 列表既是派生会话的可见性限制，也是执行守卫。 |
| skill | pack skill 文本作为 prompt 小节 | 声明的 pack skill 的 `SKILL.md` 作为独立 prompt 小节注入——加载时解析的 pack 数据，不是注册表 skill 条目。 |
| 模型选择 | [agent-default-model](../packages/core/agent-default-model/README.zh.md) | 阶段与咨询会话以部署的默认模型派生；缺少默认模型在任何会话派生之前快速失败。 |
| 关口决定 | 被记录的评审 | `expert_team_approve` 把评审人的决定——决定、批注、时间戳——记录为运行状态；固定的用法小节要求模型转述人类自己的决定与原话。 |
| 记忆 | [dsh-experimental-project-memory](../packages/experimental/project-memory/README.zh.md) | 哪些专家可以搜索或追加由数据包允许列表决定。shipped 论文包把工具给 `literature-reviewer` 与 `experimenter`，开发包给 `engineer`；记录仍是尽力而为，Vault 不可用时如实跳过。 |
| 运行观测 | `run-index.json` + 宿主 Remote | 编排器把轻量运行元数据镜像到 `<artifactsDir>/run-index.json`；gateway 向 Web 消费方暴露当前进程视图。该文件是审计镜像，不是恢复来源。 |
| 持久性 | `run-state.json` + 会话日志 | 每个提交点原子镜像运行状态（[dsh-atomic-write](../packages/util/atomic-write/README.zh.md)）；模型可见内容是会话事件。 |

<a id="expert"></a>

## 专家格式

一个专家就是一个文件 `<pack>/experts/<expert-id>.md`：定长键的 YAML frontmatter 块加人设正文。frontmatter 键集合是精确的——未知键即拒绝：

| 键 | 约定 |
| --- | --- |
| `id` | kebab-case（`[a-z0-9]` 段以单横线连接，最长 64 字节），且与去掉扩展名的文件名一致。 |
| `team` | kebab-case；必须等于 pack 的 `team.yml` 中的 `team` id。 |
| `name` | 列表与简报中显示的名称；单行，最长 128 字节。 |
| `role` | 一行，说明专家职能；最长 256 字节。 |
| `goal` | 一行，说明产物级目标；最长 512 字节。 |
| `tools` | 非空数组允许列表，列出阶段会话可调用的工具名（最多 32 项）；挂载时证明——未挂载的名称以 `EXPERT_TEAM_TOOL_MISSING` 失败，本插件自己的工具名（`expert_team_*`）以 `EXPERT_TEAM_TOOL_FORBIDDEN` 失败——并在执行时强制。 |
| `skills` | 可选数组；每个条目命名 pack 的 `skills/` 下一个必须提供 `SKILL.md` 的目录（最多 16 项）。 |
| `handoff-checks` | 可选的单行验收字符串数组（最多 16 项，每项 256 字节）；简报把它们交给专家作为产出前逐项核查的清单，未通过的检查让阶段带着说明停下。 |

正文是人设文本，中文为主，非空，最长 16 KiB；解析前 CRLF 归一为 LF。人设是给阶段会话的被引用任务上下文，绝不是对宿主的指令。论文团的一个示例：

```text
---
id: literature-reviewer
team: paper
name: 文献综述专家
role: 带引用纪律与撤稿检查意识的文献综述专家。
goal: 围绕确认的研究视角产出可溯源、含 gaps 分析的综述 survey.md。
tools:
  - read
  - grep
  - glob
  - memory_search
  - memory_append
skills:
  - review-checklist
handoff-checks:
  - perspectives.md 存在且非空，每个视角都有核心问题、研究理由与视角边界。
  - …
---

（中文为主的人设正文：工作方式、综述纪律、引用规则、放弃条件……）
```

<a id="team"></a>

## 团队定义与校验

`<pack>/team.yml`（论文团前 4 个阶段）：

```yaml
team: paper
title: 论文研究专家团
mode: pipeline
entry: perspective-discovery
phases:
  - id: perspective-discovery
    expert: topic-scout
    input: 运行请求给出的研究主题，以及可选的范围约束与既有项目记忆笔记的检索结果
    output:
      artifact: perspectives.md
  - id: literature-review
    expert: literature-reviewer
    depends_on:
      - perspective-discovery
    input: perspectives.md 中列出的研究视角与研究主题
    output:
      artifact: survey.md
      schema: schemas/survey-summary.schema.json
    gate: human-review
  - id: idea-selection
    expert: idea-selector
    depends_on:
      - literature-review
    input: survey.md 及其研究缺口（gaps）分析与开放问题清单
    output:
      artifact: research-questions.md
      schema: schemas/research-questions-summary.schema.json
    gate: human-review
  - id: method-design
    expert: method-designer
    depends_on:
      - idea-selection
    input: 经人类关口选定的研究问题（research-questions.md 中被批准的候选）
    output:
      artifact: method.md
```

顶层键集合精确（`team`、`title`、`mode`、`entry`、`phases`）；每个阶段的必需键是 `id`、`expert`、`output`，可选键是 `depends_on`、`input`、`gate`。

| 键 | 约定 |
| --- | --- |
| `team` | kebab-case，pack 内唯一的团队 id；每个专家的 `team` 字段必须与之匹配，两个 pack 不得挂载同一团队 id。 |
| `title` | `expert_team_list` 展示的可读标题；最长 256 字节。 |
| `mode` | `pipeline` 或 `hierarchical`。 |
| `entry` | 一个未声明 `depends_on` 的阶段 id；运行执行的第一个阶段。 |
| `phases[].id` | 唯一的 kebab-case 阶段 id（最长 64 字节）；每队最多 64 个阶段。 |
| `phases[].expert` | 同一 pack 中存在的专家 id。 |
| `phases[].depends_on` | 可选数组（最多 16 项），只引用更早的阶段 id——列表顺序定义"更早"，因此依赖图按构造无环；向前、自引用或未知引用以 `EXPERT_TEAM_PHASE_CYCLE` 失败。 |
| `phases[].input` | 可选的自由格式描述，说明该阶段消费什么（最长 512 字节）；入口阶段的描述即运行输入。 |
| `phases[].output.artifact` | 写入运行目录的产物文件名；单一路径段，最长 128 字节。 |
| `phases[].output.schema` | 可选，指向 pack 内一个 JSON Schema 文件的相对路径；必须留在 pack 内并指向已存在的文件。 |
| `phases[].gate` | 可选；唯一允许的值是 `human-review`。 |

校验在挂载时快速失败并给出稳定错误码。自包含检查——包括全部工具允许列表——在加载时拒绝；依赖会话的模型检查在最早可解析点、任何会话派生之前拒绝：

| 错误码 | 条件 |
| --- | --- |
| `EXPERT_TEAM_CONFIG_INVALID` | 插件配置校验失败：`packs` 缺失或为空、路径空白、带首尾空白或含控制字符，或运行输入为空。 |
| `EXPERT_TEAM_CATALOG_INVALID` | pack 或其 `team.yml` 缺失、格式错误、重复或自相矛盾：未知或缺失键、`mode` 或 `gate` 非法、阶段 id 重复、字段超限、`entry` 不是无 `depends_on` 的阶段、专家 `team` 不匹配、同一团队 id 被两个 pack 挂载。 |
| `EXPERT_TEAM_EXPERT_INVALID` | 专家文件未通过结构或上界校验：frontmatter 形状、键集合、id 与文件名主干不匹配、字段形状或上界、人设为空或超限。 |
| `EXPERT_TEAM_EXPERT_MISSING` | 阶段或咨询请求引用了 pack 未定义的专家 id。 |
| `EXPERT_TEAM_TEAM_MISSING` | 请求的团队 id 未挂载。 |
| `EXPERT_TEAM_PHASE_CYCLE` | `depends_on` 引用了非更早的阶段 id（向前、自引用或未知）。 |
| `EXPERT_TEAM_SCHEMA_MISSING` | 引用的 schema 路径越出 pack、不存在，或不是文件。 |
| `EXPERT_TEAM_SKILL_MISSING` | 声明的 skill 在 pack 中没有 `SKILL.md`，或文件在委派时已消失。 |
| `EXPERT_TEAM_TOOL_MISSING` | 专家允许列表命名了本部署未挂载的工具。 |
| `EXPERT_TEAM_TOOL_FORBIDDEN` | 专家允许列表命名了本插件自己的工具（`expert_team_*`）。 |
| `EXPERT_TEAM_MODEL_MISSING` | 部署没有提供派生专家会话所需的默认模型选择。 |
| `EXPERT_TEAM_RUN_UNKNOWN` | 请求的 run id 格式非法，或不是本进程的存活运行。 |
| `EXPERT_TEAM_GATE_PENDING` | 没有待决关口，或批准指向一个已失败的阶段。 |
| `EXPERT_TEAM_RESULT_INVALID` | 阶段回复违反结果契约：围栏、JSON、产物名、摘要上界或声明的 schema。 |
| `EXPERT_TEAM_MODE_UNSUPPORTED` | 未来或其他不受支持的团队模式到达运行时；shipped 的 `pipeline` 与 `hierarchical` 都已编排。 |

<a id="orchestration"></a>

## 编排与关口

### 流水线模式

编排器按声明顺序串行执行阶段——`depends_on` 只向后引用的规则使声明顺序即拓扑序——即使 DAG 允许并行也不并行。启动一次运行：要求非空输入，铸造品牌化 `runId`（`run-<紧凑 UTC 时刻>-<8 位十六进制>`，单一路径段），创建 `<artifactsDir>/<runId>/`，并在每个提交点把运行状态镜像到 `run-state.json`。

每个阶段，运行时派生或复用会话 `expert-team-<runId>-<phaseId>`，以运行目录为持久 cwd。system prompt 组合人设小节（frontmatter 事实加原样正文）与每个声明 pack skill 一节；第一条用户消息是阶段简报：运行请求、阶段的 `input` 描述、要阅读的上游产物路径、handoff 核查清单和输出契约。数据包可以为阶段授予文件工具；阶段把产物写成回复正文，并在回复最末尾以一个围栏 `json` 结果块收尾，代码修改只能留在运行目录内，不能替代结果契约。

结果契约固定结果对象 `{ artifactPath, summary, openQuestions? }`：`artifactPath` 必须等于声明的产物名，`summary` 是非空中文摘要且不超过 8 KiB，产物正文不超过 256 KiB。阶段声明了 schema 时，结果对象必须满足它（JSON Schema draft-07；一次性报告全部违例，让一轮修订能全部修复）。违例在同一个会话上携带修订消息重驱；至多重试 2 次后该阶段失败并记录最后的细节。只有通过的回复才被持久化——宿主原子写入产物，恰好一个行尾换行——因此停靠的失败绝不留下半个被接受的产物。

关口流程：

1. 设有关口的阶段在有效产物落盘后停靠为 `gate-pending`；运行状态变为 `waiting-approval`。
2. `expert_team_approve` 在该阶段记录 `{ decision, comment?, at }`。`approved` 把阶段标记完成，并把流水线推进到下一个停靠点；它还向被关口阶段的会话尽力投递一次批准后后续消息（followup），让人设的验收后记忆笔记获得真实一轮——后续消息即发即忘，失败按名记录，推进不等待它。`rejected` 携带批注重驱同一会话——无批注时使用固定的兜底消息——并重新武装关口。
3. 已失败的设关口阶段同样让运行停靠在 `waiting-approval`：人类不能批准已失败的阶段，因为不存在可向下游传递的已接受产物；带批注的驳回把它作为受导引修订重开。
4. 无关口的阶段失败即运行失败（`failed`）。
5. 完成把运行标记 `completed` 并释放其阶段会话；停靠的运行保留会话，让驳回在上下文中修订。

每次运行上的可变区间经每运行链条串行化，并发的 `expert_team_approve` 无法交错状态转换或双重驱动同一会话。运行不在新进程中恢复（M1 范围限制）；`run-state.json` 保证停靠状态可读。每次驳回本身就是一次显式人工决定，因此驳回/修订循环不需要数字上界；结果契约重试上界 2 是本设计的固定不变量，与已批准蓝本一致，不作为 Config 字段。

### 层级模式

软件开发数据包使用层级模式。运行时通过同一个 scoped-create 接缝按声明／拓扑顺序执行阶段，写入 `parentSession` 与 `delegationDepth`，并通过 `agentBindings` 记录每个 controller、lead 或 worker；worker 沿依赖图查找最近完成的 lead 或 controller 作为父级。这建立了持久角色关系，但不分配工作树，也不复用 `agent_dispatch` 完成关口。独立阶段仍按串行执行，角色允许列表仍是主要工具限制。

### 信任模型

专家产物属于 `observed`：是有用上下文，绝不是权威。被记录的人工决定是信任锚点，与记忆设计中"已确认状态要求直接人工来源"的规则同构。执行器强制关口的停靠与批准记录——设关口的阶段停靠到决定被记录为止，没有已接受产物时批准被拒绝——而决定来源（说话的确实是人类）由提示词钉住：固定的全局用法小节教会模型自己的位置：运行停靠时，决定是评审人的，不是模型的——先询问人类，再以他们的决定和他们的原话作为批注调用 `expert_team_approve`，绝不把关口改述为已完成。每次决定都以决定、批注和时间戳记录进运行状态，会话日志承载模型可见的一切，来源可重建；把决定绑定到经人类核实的通道是文档化的 M2 加固路径（能力级批准接缝）。pack 内容（人设、`team.yml`、schema、skill 文本）是被引用的数据；它自己从不注册工具、权限或检查项。

<a id="tools"></a>

## 模型工具与配置

| 工具 | 输入 | 行为与输出 |
| --- | --- | --- |
| `expert_team_list` | 无。 | 列出已挂载 pack：团队 id、标题、模式、入口，每个专家的 `name`/`role`/tools，以及每个阶段的依赖、产物与关口。 |
| `expert_team_run` | 运行使用 `team`、`input`；咨询使用 `expert`、`question`，`team` 可选。 | 启动一次运行并返回第一个停靠点的快照（`waiting-approval`、`completed` 或 `failed`），或在不创建运行的情况下返回一条有界咨询答案（`{ answer, truncated }`）。 |
| `expert_team_status` | `run_id`。 | 运行快照：状态、各阶段状态与尝试次数、产物引用、失败细节、已记录评审。 |
| `expert_team_approve` | `run_id`、`decision`（`approved`/`rejected`）、可选携带评审人原话的 `comment`。 | 在停靠关口记录决定并应用状态转换；驳回时批注成为修订导引。 |

`expert_team_run`、`expert_team_status` 与 `expert_team_approve` 返回同一个冻结运行快照，渲染为规范 JSON——与编排器镜像进 `run-state.json` 的形状相同。运行状态为 `running`、`waiting-approval`、`completed`、`failed`；阶段状态为 `pending`、`running`、`gate-pending`、`done`、`failed`。

配置是经过校验的 Cordis 插件配置，激活时快速失败：

```yaml
packs:
  - ./packages/experimental/expert-pack-paper
artifactsDir: ./research-artifacts
```

| 字段 | 约定 |
| --- | --- |
| `packs` | `string[]`，必需，至少一项；每项是指向已存在 pack 目录的干净路径，加载时校验。 |
| `artifactsDir` | `string`，必需；产物根目录，相对路径按进程工作目录解析。运行写入 `<artifactsDir>/<runId>/`，绝不写到这里之外。 |

插件是名为 `expert-team` 的函数插件（`name`/`inject`/`Config`/`apply`）：校验配置、加载目录（任何 pack 问题都使加载失败）、提供 `ctx.expertTeam`、注册四个工具与静态用法小节，并拥有面向 Web 的只读 `ctx.expertTeamGateway`。释放时移除工具、小节、服务与全部派生会话。`runId` 是品牌化不透明 id，生成格式是不变量；解析模型提供的 id 只做形状检查——格式合法但未知的 id 在查找时以 `EXPERT_TEAM_RUN_UNKNOWN` 失败。

<a id="packs"></a>

## 团队数据包

### 论文团

论文团实现分阶段研究工作流。十个阶段都已声明并挂载：视角发现、文献综述、选题、方法设计、实验执行、写作、三路评审与修订。

| 序号 | 阶段 id | 专家 | depends_on | 产物 | 结果 schema | 关口 | 里程碑 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `perspective-discovery` | `topic-scout` | —（入口） | `perspectives.md` | — | — | M1 |
| 2 | `literature-review` | `literature-reviewer` | `perspective-discovery` | `survey.md` | `survey-summary.schema.json` | `human-review` | M1 |
| 3 | `idea-selection` | `idea-selector` | `literature-review` | `research-questions.md` | `research-questions-summary.schema.json` | `human-review` | M1 |
| 4 | `method-design` | `method-designer` | `idea-selection` | `method.md` | — | — | M1 |
| 5 | `experiments` | `experimenter` | `method-design` | `experiments.md` | `experiments-summary.schema.json` | — | M2 |
| 6 | `writing` | `writer` | `experiments` | `draft.md` | `draft-summary.schema.json` | — | M2 |
| 7 | `review-methodology` | `reviewer-1` | `writing` | `review-methodology.md` | `review-summary.schema.json` | — | M2 |
| 8 | `review-statistics` | `reviewer-2` | `writing` | `review-statistics.md` | `review-summary.schema.json` | — | M2 |
| 9 | `review-writing` | `reviewer-3` | `writing` | `review-writing.md` | `review-summary.schema.json` | — | M2 |
| 10 | `revision` | `writer` | 三份评审；supersedes `writing` | `revision-plan.md` | `revision-plan-summary.schema.json` | `human-review` | M2 |

阶段职责：`topic-scout` 从主题调研出多个研究视角，`perspectives.md` 控制后续提问的深度与广度（STORM）。`literature-reviewer` 检索并阅读文献；每条论断都带引用，`survey.md` 包含 gaps 分析（PaperQA2），关口与人类确认综述方向。`idea-selector` 从 gaps 提炼候选研究问题，各附新颖性论证与风险（AI-Researcher），关口由人类选定课题。`method-designer` 在 `method.md` 中给出实验设计、数据集、基线与评价指标。`experimenter` 记录结果，`writer` 起草论文，三位评审分别独立评估，`revision` 根据全部报告形成修订计划。

`literature-reviewer` 与 `experimenter` 携带 project-memory 工具，以研究主题作为实体锚定，在其工作被接受后记录尽力而为的笔记；project-memory 未配置时工具如实报告 `MEMORY_UNAVAILABLE`，阶段在没有笔记的情况下继续。按产物保证的核心记录仍未实现。

### 软件开发团（M3 概要）

软件开发团已实现为六阶段层级数据包：PM 起草 PRD（关口：人类评审）；架构师将其转为设计文档；技术主管把工作分解为任务 DAG；工程师在运行目录内实现；QA 测试；最终评审以人类验收为关口。controller、lead 与 worker 会话经 `agentBindings` 记录；数据包不使用基于工作树的 `agent_dispatch`，声明产物保留在运行目录内。

<a id="testing"></a>

## 测试策略

证据遵循[测试策略文档](testing.zh.md)：优先真实实现，在发布入口路径上证明行为，并把可选项挡在出厂默认之外。

| 层级 | 覆盖内容 |
| --- | --- |
| REAL-composition | 通过 Loader 以测试专用组合启动（临时目录中的 fixture pack）：四个工具出现，一次运行经由真实派生会话执行各阶段，产物与 `run-state.json` 镜像落在配置的 `artifactsDir` 下，批准／驳回流程端到端运行。仅 mock 模型后端。 |
| 单元 | 每条 `EXPERT_TEAM_*` 校验用例（每个错误码一个无效 pack）、`depends_on` 只向后引用规则、结果契约切分与上界、关口转换（含失败阶段的批准拒绝）、重试上界（重驱止步于 2 次），以及配置校验。 |
| 快照 | 明确推迟：录制场景需要 provider key，目前尚未录制。过渡期的模型可见覆盖由 REAL-composition 规格承担——它以 mock 模型适配器驱动同样四个工具：带关口暂停的运行、批准与驳回流程，以及咨询输入形态。 |

关口语义走真实路径：批准/驳回流程在 REAL-composition 层端到端演练，不对接桩编排器。专家人设质量不做机器测试；快照层录制后只固定稳定的模型可见文本。

<a id="milestones"></a>

## 里程碑

| 里程碑 | 范围 | 主要证据 |
| --- | --- | --- |
| M1 | 核心包（目录、流水线编排、关口、四个工具）与论文 pack 的前四阶段，含 run-state 镜像。记忆记录由数据包工具尽力而为。 | REAL-composition、单元；快照层推迟（录制需要 provider key）。 |
| M2 | 论文 pack 剩余阶段：实验、写作、三路评审与修订；文献综述与实验阶段提供尽力而为的记忆笔记。 | 同上；并行评审与核心自有保证记录仍延期。 |
| M3 | 通过 `agentBindings` 记录 controller／lead／worker 关系的软件开发层级数据包；阶段产物保留在运行目录，不使用基于工作树的派发输出。 | 同上加层级组合证据。 |
| M4 | 加固与发布准备：多 pack 组合证据、跨进程恢复决定、运行历史可观测性，以及只读 Web 状态入口。Token/KV 测量与网站指南投影仍延期。 | 聚焦组合、可观测性与客户端类型证据；快照录制仍需 provider key。 |

## 开发备注

本文把专家团蓝本及其当前实现状态形式化；实现包沿用 [dsh-experimental-project-memory](../packages/experimental/project-memory/README.zh.md) 的结构与约定。记录在案的选择都是刻意的：阶段会话经由 agent 注册表的 scoped-create 接缝派生、pack skill 作为 prompt 小节注入；层级绑定在不使用工作树派发的情况下记录；记忆仍由数据包拥有且尽力而为；结果契约重试上界是固定不变量；运行历史只是审计镜像；停靠的运行不在新进程恢复。所引外部项目是机制来源，不是待 vendor 的代码。
