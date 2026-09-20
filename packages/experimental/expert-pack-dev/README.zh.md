---
description: "expert-team 插件的软件开发数据包：六个中文为主的专家人设、一条六阶段带人类关口的层级团队（PRD、架构、任务分解、实现、测试、评审）、交接核查清单、验收检查单技能与阶段结果 JSON Schema，经核心包的 Config.packs 挂载。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-pack-dev

[English](README.md) | 中文

## 概述

`dsh-experimental-expert-pack-dev` 是 `dsh-experimental-expert-team` 核心包的纯数据包——专家人设、团队定义、技能与 JSON Schema，不含代码。把本目录挂到核心包的 `packs` 配置上，部署就获得软件开发专家团：`product-manager` 把原始需求整理成带用户故事、功能范围、可测试验收标准与非目标的 PRD；`architect` 把确认后的 PRD 落成模块边界、接口契约、数据结构、带理由的技术选型与风险清单；`tech-lead` 把设计分解成任务 DAG，每个任务带验收标准与依赖关系；`engineer` 以数据包里最宽的工具面（shell、文件写入、todo）在运行目录内实现代码并记录日志；`qa` 从验收标准推导测试计划，产出带复现步骤的缺陷报告；`code-reviewer` 从正确性、可维护性、测试覆盖与安全四个面评审，供人类做最终决定。PRD 之后与评审之后各有一个人类关口：专家产物是观察数据，人类批准是信任锚点。产物写入核心包 `artifactsDir` 的运行目录。

## 目录

- [使用本包](#use-this-package)
- [理解数据包](#understand-the-pack)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 挂载数据包

核心包 `@deepseek-ai/dsh-experimental-expert-team` 拥有模型工具、编排、关口与校验；本包只贡献数据。把一个 `packs` 条目指向本目录——仓库相对路径、绝对路径或安装后的包目录：

```yaml
# the expert-team core row in cordis.yml; the field contract is owned by the core package
packs:
  - ./packages/experimental/expert-pack-dev
artifactsDir: ./dev-artifacts
```

核心包在加载时对 `team.yml` 与专家文件显式失败地校验：阶段 id 唯一、专家引用存在、`depends_on` 无环且只指向更早阶段、entry 一致、被引用的 schema 文件存在，以及专家工具允许列表非空、只命名已挂载的工具、绝不命名插件自身的工具。校验失败的数据包绝不半挂载。

### 流水线

| 阶段 | 专家 | 依赖 | 产物 | 关口 |
|---|---|---|---|---|
| `prd` | `product-manager` | —（entry） | `prd.md` | `human-review` |
| `architecture` | `architect` | `prd` | `design.md` | — |
| `task-breakdown` | `tech-lead` | `architecture` | `tasks.md` | — |
| `implementation` | `engineer` | `task-breakdown` | `implementation.md` | — |
| `testing` | `qa` | `implementation` | `test-results.md` | — |
| `review` | `code-reviewer` | `testing` | `review.md` | `human-review` |

关口驳回时，产物带评审批注回流到所属专家修订。每位下游专家在接受上游材料前先核对各自 frontmatter 里的交接检查项：`architect` 核查 PRD 的验收标准可独立判定，`tech-lead` 核查设计契约完整到可以分解，`engineer` 核查任务边界与依赖已完成，`qa` 核查每个任务都有验收标准，`code-reviewer` 核查测试报告有证据支撑。六个阶段都返回经各自 [`schemas/`](schemas/) 下 schema 校验的结构化结果对象；实现阶段声明的产物是 `implementation.md`，工程师用文件工具写出的代码落在运行目录内该产物的旁边。

### 技能、工具与记忆

[验收检查单技能](skills/acceptance-checklist/SKILL.md)是编写与核查验收标准的纪律：`product-manager` 在关口前用它自查，`architect` 在 PRD 交接时应用它，`tech-lead` 对每个任务的验收标准应用它。工具面按角色区分：六位专家共享 `read`、`grep`、`glob` 与 `memory_search`；`engineer` 额外携带 `pwsh`、`write`、`edit`、`read_image`、`todo_write` 与 `memory_append`，`qa` 额外携带 `pwsh`。部署缺少其中任何工具时，运行在最早可解析的点上以 `EXPERT_TEAM_TOOL_MISSING` 响亮失败（允许列表在任何东西被创建之前先证明已挂载）；而已挂载但未配置 vault 时，记忆工具报告 `MEMORY_UNAVAILABLE`，阶段在无记忆笔记的情况下继续并如实报告。记忆锚定沿用 project-memory 的实体设计：工程师为每份实现日志追加一条有界笔记，以项目或模块名作为实体标签。

-----

<a id="understand-the-pack"></a>
## 理解数据包

<details>
<summary>数据包内部——点击展开</summary>

数据包是目录契约，不是库：核心包的目录加载器在加载时读取这些文件，每个阶段在运行时用它们组装自己的 subagent 请求。

| 路径 | 职责 |
|---|---|
| [`team.yml`](team.yml) | 团队：团队 id 与标题、`hierarchical` 模式、entry 阶段，以及六个阶段的依赖、输入、产物、schema 引用与关口 |
| [`experts/product-manager.md`](experts/product-manager.md) | PRD 人设：用户故事、范围、可测试的验收标准、非目标 |
| [`experts/architect.md`](experts/architect.md) | 设计人设：模块边界、接口契约、数据结构、技术选型、风险 |
| [`experts/tech-lead.md`](experts/tech-lead.md) | 任务分解人设：带验收标准与依赖关系的任务 DAG |
| [`experts/engineer.md`](experts/engineer.md) | 实现人设：数据包里最宽的工具面（`pwsh`、`write`、`edit`、`todo_write`）；把代码写进运行目录 |
| [`experts/qa.md`](experts/qa.md) | 测试人设：从验收标准推导测试计划，带复现步骤的缺陷报告 |
| [`experts/code-reviewer.md`](experts/code-reviewer.md) | 评审人设：正确性、可维护性、测试覆盖、安全 |
| [`schemas/prd-summary.schema.json`](schemas/prd-summary.schema.json) | prd 阶段结果对象的 draft-07 校验 |
| [`schemas/design-summary.schema.json`](schemas/design-summary.schema.json) | architecture 阶段结果对象的 draft-07 校验 |
| [`schemas/tasks-summary.schema.json`](schemas/tasks-summary.schema.json) | task-breakdown 阶段结果对象的 draft-07 校验 |
| [`schemas/implementation-summary.schema.json`](schemas/implementation-summary.schema.json) | implementation 阶段结果对象的 draft-07 校验 |
| [`schemas/test-results-summary.schema.json`](schemas/test-results-summary.schema.json) | testing 阶段结果对象的 draft-07 校验 |
| [`schemas/review-summary.schema.json`](schemas/review-summary.schema.json) | code-review 阶段结果对象的 draft-07 校验 |
| [`skills/acceptance-checklist/SKILL.md`](skills/acceptance-checklist/SKILL.md) | 验收检查单技能，与 Claude Code 技能同构 |
| [`skills/acceptance-checklist/references/checklist.md`](skills/acceptance-checklist/references/checklist.md) | 技能应用的检查条目 |

专家文件是 YAML frontmatter 加中文为主的人设正文。frontmatter 键（`id`、`team`、`name`、`role`、`goal`、`tools`，可选 `skills` 与 `handoff-checks`）是加载时契约，`tools` 允许列表约束阶段 subagent 可调用的工具。每个阶段结果 schema 都校验共同的 `{ artifactPath, summary, openQuestions? }` 形态及本阶段的专属约束；各 schema 保持独立，因此目录加载器可以校验数据包内每个被引用的文件。

### 不变量

未发布运行时 invariant 伴随物：本包是经核心目录加载器消费的数据——响亮失败的保证活在加载器的挂载时校验与运行时结果检查里，而不是包内可观察关系。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 伴随 subagent 请求的专家人设

#### 模型看到什么

本包自身不注册任何工具、提示词段落或会话事件；核心包的四个工具——`expert_team_list`、`expert_team_run`、`expert_team_status` 与 `expert_team_approve`——是唯一的模型可见新增，归核心包拥有。`expert_team_run` 还接受 `expert` 加 `question`，在运行之外进行有界咨询。运行期间，每个阶段的 subagent 请求逐字携带该阶段专家的人设正文（中文为主）、上游产物引用与本阶段结果 schema；frontmatter 的 `tools` 允许列表约束 subagent 可调用的工具。engineer 与 qa 的允许列表包含 `pwsh`，这两个阶段的会话以运行目录为工作目录执行 shell 命令。

#### Token 影响

无运行时为零。运行期间，每个阶段请求加入其人设（几 KiB）、上游产物引用与本阶段结果 schema；每个阶段结果与工程师被接受的记忆笔记在可复用前缀之后追加一条有界 JSON。

#### KV Cache 影响

数据包文件静态，阶段内人设与 schema 位于稳定的请求前缀中，产物内容追加在其后。编辑任何数据包文件都会改变后续运行组装的内容，并为受影响的请求开启新前缀；跨会话的不同运行之间没有可复用内容。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制是数据包的当前约束，不是任务清单。

- **层级执行使用 scoped-create，而不是 agent-dispatch。** 六个阶段经核心包的 scoped-create 接缝按声明／拓扑顺序执行。挂载 `session-identity` 时，controller、lead 与 worker 会话会带父级绑定与派发深度记录；expert-team 运行时不分配工作树，也不调用 `agent_dispatch` 工具。相互独立的阶段仍按串行执行。
- **本包只有数据。** 编排、关口批准、schema 校验与记忆写入都归 expert-team 核心包拥有；数据包无法单独运行，其执行证据在核心包针对本包的目录测试里。
- **工具面要求已挂载的工具。** `engineer` 与 `qa` 命名 `pwsh`，engineer 还命名 `read_image`、`todo_write` 与 `memory_append`：缺少这些工具的部署以 `EXPERT_TEAM_TOOL_MISSING` 响亮失败，而已挂载但未配置 vault 时退化为 `MEMORY_UNAVAILABLE` 无笔记并如实报告；按产物保证的记忆写入归核心包。
- **中文为主的人设。** 人设正文用中文约束模型行为，而 schema 描述是英文；想要英文为主人设的部署必须派生本数据包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

核心包的阶段简报描述实际产物契约，并要求阶段不要调用允许列表之外的工具。engineer 的允许列表包含 `write`/`edit`，因此实现代码可以在运行目录内修改；运行时仍会在阶段接受前校验回复契约，并从该契约持久化 `implementation.md`。

</details>
