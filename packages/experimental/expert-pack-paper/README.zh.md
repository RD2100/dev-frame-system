---
description: "expert-team 插件的论文研究数据包：十个中文为主的专家人设、一条含并行评审与修订的十阶段人类关口流水线、交接核查、评审技能与阶段结果 JSON Schema，经核心包的 Config.packs 挂载。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-pack-paper

[English](README.md) | 中文

## 概述

`dsh-experimental-expert-pack-paper` 是 `dsh-experimental-expert-team` 核心包的纯数据包——专家人设、流水线定义、评审技能与 JSON Schema，不含代码。把本目录挂到核心包的 `packs` 配置上，部署就获得论文研究专家团：`topic-scout` 展开研究视角；`literature-reviewer` 产出遵守引用纪律且带 gaps 分析的综述；`idea-selector` 提炼候选研究问题；`method-designer` 把人类选定的问题转为可执行实验设计；`experimenter` 记录可复现的实验结果；`writer` 起草论文；三位评审专家分别检查方法、统计与写作；`writer` 再根据评审报告形成修订计划。综述、选题与修订计划之后各有一个人类关口：专家产物是观察数据，人类批准是信任锚点。产物写入核心包 `artifactsDir` 的运行目录。

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
  - ./packages/experimental/expert-pack-paper
artifactsDir: ./research-artifacts
```

核心包在加载时对 `team.yml` 与专家文件显式失败地校验：阶段 id 唯一、专家引用存在、`depends_on` 无环且只指向更早阶段、entry 一致、被引用的 schema 文件存在，以及专家工具允许列表只命名已挂载的工具。校验失败的数据包绝不半挂载。

### 流水线

| 阶段 | 专家 | 依赖 | 产物 | 关口 |
|---|---|---|---|---|
| `perspective-discovery` | `topic-scout` | —（entry） | `perspectives.md` | — |
| `literature-review` | `literature-reviewer` | `perspective-discovery` | `survey.md` | `human-review` |
| `idea-selection` | `idea-selector` | `literature-review` | `research-questions.md` | `human-review` |
| `method-design` | `method-designer` | `idea-selection` | `method.md` | — |
| `experiments` | `experimenter` | `method-design` | `experiments.md` | — |
| `writing` | `writer` | `experiments` | `draft.md` | — |
| `review-methodology` | `reviewer-1` | `writing` | `review-methodology.md` | — |
| `review-statistics` | `reviewer-2` | `writing` | `review-statistics.md` | — |
| `review-writing` | `reviewer-3` | `writing` | `review-writing.md` | — |
| `revision` | `writer` | 三份评审意见 | `revision-plan.md` | `human-review` |

关口驳回时，产物带评审批注回流到所属专家修订；各阶段专家在接受上游产物前核对自己的交接检查。八个阶段返回经 [`schemas/`](schemas/) 下对应 schema 校验的结构化结果对象；`perspective-discovery` 与 `method-design` 是两个无 schema 阶段。三位评审都独立依赖 `draft.md`，`revision` 消费三份报告后进入最后一个人类关口。

### 技能与记忆

[审稿检查单技能](skills/review-checklist/SKILL.md)及各评审者技能是专家在核查上游产物或自查交付时加载的结构化纪律。记忆锚定沿用 project-memory 的实体设计：`literature-reviewer` 在综述获接受后追加一条有界笔记，`experimenter` 在实验完成后追加一条可复现性笔记，二者都以研究主题作为实体标签。这仍是尽力而为：未挂载 memory 插件时，本包挂载以 `EXPERT_TEAM_TOOL_MISSING` 响亮失败；已挂载但未配置 vault 时，记忆工具报告 `MEMORY_UNAVAILABLE`，阶段无记忆笔记继续。

-----

<a id="understand-the-pack"></a>
## 理解数据包

<details>
<summary>数据包内部——点击展开</summary>

数据包是目录契约，不是库：核心包的目录加载器在加载时读取这些文件，每个阶段在运行时用它们组装自己的 subagent 请求。

| 路径 | 职责 |
|---|---|
| [`team.yml`](team.yml) | 流水线：团队 id 与标题、模式、entry 阶段，以及十个阶段的依赖、输入、产物、schema 引用、supersedes 链与关口 |
| [`experts/topic-scout.md`](experts/topic-scout.md) | 视角发现人设（借鉴 STORM） |
| [`experts/literature-reviewer.md`](experts/literature-reviewer.md) | 引用纪律的综述人设（借鉴 PaperQA2）；携带 `memory_append` |
| [`experts/idea-selector.md`](experts/idea-selector.md) | 选题人设（借鉴 AI-Researcher） |
| [`experts/method-designer.md`](experts/method-designer.md) | 实验设计人设 |
| [`experts/experimenter.md`](experts/experimenter.md) | 可复现实验人设，携带 `memory_append` |
| [`experts/writer.md`](experts/writer.md) | 以证据约束论文起草与修订的人设 |
| [`experts/reviewer-1.md`](experts/reviewer-1.md) | 方法评审人设 |
| [`experts/reviewer-2.md`](experts/reviewer-2.md) | 统计评审人设 |
| [`experts/reviewer-3.md`](experts/reviewer-3.md) | 写作与论断评审人设 |
| [`schemas/survey-summary.schema.json`](schemas/survey-summary.schema.json) | 文献综述阶段结果对象的 draft-07 校验 |
| [`schemas/research-questions-summary.schema.json`](schemas/research-questions-summary.schema.json) | 选题阶段结果对象的 draft-07 校验 |
| [`schemas/experiments-summary.schema.json`](schemas/experiments-summary.schema.json) | experiments 阶段结果对象的 draft-07 校验 |
| [`schemas/draft-summary.schema.json`](schemas/draft-summary.schema.json) | writing 阶段结果对象的 draft-07 校验 |
| [`schemas/review-summary.schema.json`](schemas/review-summary.schema.json) | 各 review 阶段结果对象的 draft-07 校验 |
| [`schemas/revision-plan-summary.schema.json`](schemas/revision-plan-summary.schema.json) | revision 阶段结果对象的 draft-07 校验 |
| [`skills/review-checklist/SKILL.md`](skills/review-checklist/SKILL.md) | 审稿检查单技能，与 Claude Code 技能同构 |
| [`skills/review-checklist/references/checklist.md`](skills/review-checklist/references/checklist.md) | 技能应用的检查条目 |

专家文件是 YAML frontmatter 加中文为主的人设正文。frontmatter 键（`id`、`team`、`name`、`role`、`goal`、`tools`，可选 `skills` 与 `handoff-checks`）是加载时契约，`tools` 允许列表约束阶段 subagent 可调用的工具。结果对象 schema 校验 `{ artifactPath, summary, citations?, openQuestions? }`：综述 schema 要求 citations（把引用纪律变成机器可查），选题 schema 要求 openQuestions（人类关口必须权衡的事项）；两个 schema 都内联了共享的 citation 形状，各自保持独立可用。

### 不变量

未发布运行时 invariant 伴随物：本包是经核心目录加载器消费的数据——响亮失败的保证活在加载器的挂载时校验与运行时结果检查里，而不是包内可观察关系。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 伴随 subagent 请求的专家人设

#### 模型看到什么

本包自身不注册任何工具、提示词段落或会话事件；核心包的四个工具——`expert_team_list`、`expert_team_run`、`expert_team_status` 与 `expert_team_approve`——是唯一的模型可见新增，归核心包拥有。`expert_team_run` 还接受 `expert` 加 `question`，在运行之外进行有界咨询。运行期间，每个阶段的 subagent 请求逐字携带该阶段专家的人设正文（中文为主）、上游产物引用与其结果 schema（如有）；frontmatter 的 `tools` 允许列表约束 subagent 可调用的工具。

#### Token 影响

无运行时为零。运行期间，每个阶段请求加入其人设（几 KiB）、上游产物引用与声明的结果 schema；每个阶段结果与每条被接受的记忆笔记在可复用前缀之后追加一条有界 JSON。

#### KV Cache 影响

数据包文件静态，阶段内人设与 schema 位于稳定的请求前缀中，产物内容追加在其后。编辑任何数据包文件都会改变后续运行组装的内容，并为受影响的请求开启新前缀；跨会话的不同运行之间没有可复用内容。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制是数据包的当前约束，不是任务清单。

- **本包只有数据。** 编排、关口批准、schema 校验与记忆写入都归 expert-team 核心包拥有；数据包无法单独运行，其执行证据在核心包针对本包的目录测试里。
- **声明的 DAG 仍按串行执行。** 三个评审阶段在数据契约中相互独立，但核心当前按声明顺序执行全部阶段，而不是并行执行；并行评审属于未来的性能优化。
- **引用纪律由提示词强制。** 综述 schema 要求 citations 条目，但无法核实文献真实存在或论断与文献相符；综述专家背后的文献索引延期。
- **记忆写入是尽力而为。** `literature-reviewer` 与 `experimenter` 携带记忆工具：未挂载 memory 插件时本包挂载以 `EXPERT_TEAM_TOOL_MISSING` 失败，而已挂载但未配置 vault 时退化为 `MEMORY_UNAVAILABLE` 无笔记并如实报告；按产物保证的记忆写入归核心包。
- **中文为主的人设。** 人设正文用中文约束模型行为，而 schema 描述是英文；想要英文为主人设的部署必须派生本数据包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
