---
description: "专家团队核心插件：挂载数据包时的响亮失败校验（严格的 expert-md 与 team.yml 验证）、带人工关口的流水线编排、经代理注册表 scoped-create 接缝派生的角色化阶段子代理，以及五个模型工具（list、run、status、approve、consult）。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-team

[English](README.md) | 中文

## 概述

`dsh-experimental-expert-team` 从数据包挂载专家团队：专家角色（`experts/<id>.md`）、流水线定义（`team.yml`）、包内技能与阶段结果 JSON Schema，加载时响亮失败校验，运行时逐阶段编排。一个 Cordis 行提供 `ctx.expertTeam` 并注册五个模型工具（`expert_team_list`、`expert_team_run`、`expert_team_status`、`expert_team_approve`、`consult_expert`）；每个阶段经代理注册表的 scoped-create 接缝派生一个角色化子代理，把产物写成 `<artifactsDir>/<runId>/` 下的文件，并在任何声明的 human-review 关口停车——人类批准是信任锚点，专家输出是观察数据。shipped 的[论文研究数据包](../expert-pack-paper/README.zh.md)是包格式的参考消费者。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 挂载插件

本插件作为普通 `cordis.yml` 行挂载。两个配置字段都必填且无默认值：`packs` 是至少一个团队数据包目录，`artifactsDir` 是运行产物的根（运行写在 `<artifactsDir>/<runId>/` 下；仓库相对路径按进程工作目录解析）。任何校验失败的包——缺失 `team.yml`、畸形专家文件、前向或未知的 `depends_on`、缺失 schema 或技能文件、重复团队 id——都让加载失败，而不是半挂载。

```yaml
- name: '@deepseek-ai/dsh-experimental-expert-team'
  config:
    packs:
      - ./packages/experimental/expert-pack-paper
    artifactsDir: ./research-artifacts
```

### 你会得到什么

该行提供 `ctx.expertTeam`（一个 `TeamOrchestrator`）和 `ctx.tools` 上的五个模型工具。

- `expert_team_list` — 列出每个已挂载团队的阶段、依赖、产物、关口与专家；运行团队或咨询专家前先读它。
- `expert_team_run` — 以自由文本输入（例如研究主题）启动一次流水线运行，并在运行停车时返回：人工关口（`waiting-approval`）、完成或失败。
- `expert_team_status` — 读取一次运行的快照：各阶段状态、产物、尝试次数与已记录的评审。
- `expert_team_approve` — 在停车的关口记录人类决定；批准让流水线推进到下一个停车点，并向阶段会话尽力送达一次接受追问，驳回把产物连同批注退回同一阶段会话作为修订指引。
- `consult_expert` — 在任何运行之外获得一次有界的专家回答：无产物、无运行状态、无阶段副作用。

专家 front matter 的 `tools` 是允许清单，受到双重强制：派生时把子代理可见工具限制在该清单内，执行器守卫再按名拒绝清单之外的一切。包声明了部署未挂载的工具时，运行启动（或咨询）以 `EXPERT_TEAM_TOOL_MISSING` 响亮失败，而不是组合出无法兑现承诺的阶段。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本节解释插件背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)完整覆盖。

### 包契约与响亮失败的挂载

目录（`src/catalog.ts`）每个进程挂载一次配置的包：专家 md front matter 与 `team.yml` 的严格键集解析（`src/expert-md.ts`、`src/team-yml.ts`），以及交叉检查——每个阶段引用的专家存在、`depends_on` 只指向更早阶段（按构造无环）、schema 文件在包内存在、声明的技能带有 `SKILL.md`。任何违规都在加载时抛出携带稳定 `EXPERT_TEAM_*` 代码的 `ExpertTeamError`。

### 阶段结果协议

阶段专家没有写文件工具。它以回复正文作为产物，并在最末尾给出围栏 JSON 结果对象（`artifactPath`、`summary`、可选 `openQuestions`）（`src/result-protocol.ts`）；运行器拆分回复，按声明的产物名和包的 JSON Schema（如声明）校验结果，只在契约通过后原子写入正文，契约失败时对同一会话至多重驱两次，让修订留在上下文中（`src/runtime.ts`）。承载运行事实、上游产物路径、handoff 核查清单与输出契约的简报在 `src/briefing.ts` 组合。

### 关口语义

运行状态以内存为权威，并在每个提交点镜像到 `<artifactsDir>/<runId>/run-state.json`（`src/orchestrate.ts`）。带关口的阶段以 `gate-pending` / `waiting-approval` 停车；并发批准经每次运行的串行门序列化。耗尽结果契约重试的阶段把运行停在它的关口并报告失败——人类无法批准失败阶段（不存在可下传的已接受产物），但带批注的驳回会把它作为引导式修订在同一会话中重新打开。批准之后还会向被关口阶段会话尽力送达一条追问——产物已获通过，附评审批注（如有）——让角色的接受后步骤（例如记忆备注）能在真实一轮中触发；流水线绝不等待这次送达，追问失败只记录日志，不会让运行失败。

### 派生接缝

阶段经 `ctx.agents.create({ sessionId, meta, agentOptions, setup })`——代理注册表的 scoped-create 面——派生，再以 `followup()` 加 `await agent.whenIdle()` 驱动一轮。它有意不是 agent-hierarchy 的派发引擎：流水线阶段需要角色化会话、有界工具面、无工作树、无角色绑定；层级模式才是把关口映射到派发的接缝。经注册表派生让本包保持为既有循环行为之上的普通插件——不新增执行循环。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/types.ts`](src/types.ts) | 专家、阶段与团队定义；运行与阶段状态；稳定 `EXPERT_TEAM_*` 错误码并集 |
| [`src/validate.ts`](src/validate.ts) | 包文件解析器共享的严格值校验器 |
| [`src/expert-md.ts`](src/expert-md.ts) | 单个专家定义文件的严格解析 |
| [`src/team-yml.ts`](src/team-yml.ts) | `team.yml` 解析与包级交叉校验 |
| [`src/catalog.ts`](src/catalog.ts) | 包挂载与不可变的团队/专家查找 |
| [`src/config.ts`](src/config.ts) | 显式配置校验（packs、artifactsDir） |
| [`src/ids.ts`](src/ids.ts) | 不透明 `RunId` 品牌及其铸造/解析 |
| [`src/result-protocol.ts`](src/result-protocol.ts) | 回复拆分、结果契约检查、schema 校验、咨询上限 |
| [`src/briefing.ts`](src/briefing.ts) | 阶段简报、修订追问与咨询消息 |
| [`src/runtime.ts`](src/runtime.ts) | 角色派生的子代理、有界重试循环、咨询 |
| [`src/orchestrate.ts`](src/orchestrate.ts) | 运行、拓扑阶段执行、关口、运行状态镜像 |
| [`src/tools.ts`](src/tools.ts) | 五个模型工具定义 |
| [`src/plugin.ts`](src/plugin.ts) | Loader 接线：配置、目录、服务、工具、使用段落、处置 |

### 不变量

未发布运行时 invariant 伴随物：编排器不持有可跨进程观察的关系需要断言——它的保证（契约通过后才写产物、提交点镜像状态、批准串行化）都在单进程内强制，并由编排行为测试验证。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 专家团队工具与指引

#### 模型看到什么

可见作用域中恰好多出五个工具：`expert_team_list`、`expert_team_run`、`expert_team_status`、`expert_team_approve` 与 `consult_expert`。一个静态使用段落（`expert-team:usage`）进入全局提示层，教导何时列出、运行、以评审者原话批准、以及何时宁可咨询而不跑完整流水线，并说明产物是按路径引用的文件。运行期间，每个阶段子代理的请求携带逐字专家角色、每个声明包技能一个段落、上游产物路径、handoff 核查清单与阶段输出契约（含 schema 文本）——产物内容本身绝不回到提示词，只有路径会。

#### Token 影响

五个工具的模式在可见作用域的每次请求中占用 token，使用段落的固定文本每次请求进入提示词一次。一次运行的成本按阶段到来：每个阶段请求加上它的角色（数 KiB）加技能段落、上游引用与声明的 schema 文本；每个阶段结果和每次关口决定在可复用前缀之后追加一条有界 JSON。

#### KV Cache 影响

挂载的包与工具模式不变时前缀稳定：模式与静态使用段落只声明一次，每阶段内容追加在可复用请求前缀之后。编辑任何包文件会改变后续运行组合的内容，并为受影响请求开启新前缀；挂载或卸载会改变工具清单，破坏受影响代理下一次请求的提供方缓存复用。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制是当前插件约束，不是任务清单。

- **层级模式未编排。** 声明 `mode: hierarchical` 的团队可以挂载和列出，但 `expert_team_run` 以 `EXPERT_TEAM_MODE_UNSUPPORTED` 拒绝；把关口映射到 agent-hierarchy 派发引擎推迟到真实层级包出现需求时。
- **运行不跨进程恢复。** `run-state.json` 为检查而镜像状态，但停车或进行中的运行在重启后丢失；从镜像状态恢复推迟到有部署跨重启运行团队时。
- **记忆记录是委托而非自有。** 到 project-memory 的实体锚定经包的工具允许清单实现：声明了 `memory_append` 的专家可以以研究主题为实体标签记录其产物，未配置记忆时由工具如实报告 `MEMORY_UNAVAILABLE`。编排器自身从不调用记忆；核心自有的按产物记忆写入推迟到有度量需求，且实体标签没有别名登记表，跨运行召回依赖写入模型复用标签。
- **阶段串行执行。** 声明顺序是拓扑序，但执行器从不并行化独立阶段；有度量的延迟需求时才值得改变。
- **关口记录的是决定，不是经验证的人类。** 编排器停车并记录 `expert_team_approve` 收到的内容，但无法验证发言者是人类：批准者是人工评审这一规则只经使用段落的提示词固定，不是能力强制。
- **M1 没有每团队并发上限。** 受信任的驱动会话可以对同一团队并发发起多个 `expert_team_run`。数据包无法递归——声明插件自有工具的包在挂载时失败（`EXPERT_TEAM_TOOL_FORBIDDEN`），阶段专家因此不能批准关口或启动运行——但驱动会话受信任且不受上限约束。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

M1 范围的决策记录见[专家团队 Agent Note](../../../.agents/notes/implemented/feature/2026-09-14-expert-team-m1.zh.md)。

</details>
