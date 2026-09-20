---
description: "专家团队核心插件：挂载数据包时的响亮失败校验（严格的 expert-md 与 team.yml 验证）、带人工关口的流水线编排、经代理注册表 scoped-create 接缝派生的角色化阶段子代理、四个模型工具与只读 Web 状态 Remote。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-expert-team

[English](README.md) | 中文

## 概述

`dsh-experimental-expert-team` 从数据包挂载专家团队：专家角色（`experts/<id>.md`）、流水线定义（`team.yml`）、包内技能与阶段结果 JSON Schema，加载时响亮失败校验，运行时逐阶段编排。一个 Cordis 行提供 `ctx.expertTeam`，注册四个模型工具（`expert_team_list`、`expert_team_run`、`expert_team_status`、`expert_team_approve`），并为 Web 状态面板暴露只读宿主 Remote；`expert_team_run` 还接受有界的单专家咨询形态。每个阶段经代理注册表的 scoped-create 接缝派生一个角色化子代理，把声明的产物写成 `<artifactsDir>/<runId>/` 下的文件，并在任何声明的 human-review 关口停车——人类批准是信任锚点，专家输出是观察数据。shipped 的[论文研究数据包](../expert-pack-paper/README.zh.md)是包格式的参考消费者。

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

该行提供 `ctx.expertTeam`（一个 `TeamOrchestrator`）、提供状态与执行 Remote（`view`、`startRun`、`consult`、`approve`、`getRun`）的 `ctx.expertTeamGateway`，以及 `ctx.tools` 上的四个模型工具。

- `expert_team_list` — 列出每个已挂载团队的阶段、依赖、产物、关口与专家；运行团队或咨询专家前先读它。
- `expert_team_run` — 以自由文本输入（例如研究主题）启动一次流水线运行，并在运行停车时返回：人工关口（`waiting-approval`）、完成或失败。同一工具也接受 `expert` 加 `question`，在运行之外进行一次有界咨询；不会注册单独的咨询工具。
- `expert_team_status` — 读取一次运行的快照：各阶段状态、产物、尝试次数与已记录的评审。
- `expert_team_approve` — 在停车的关口记录人类决定；批准让流水线推进到下一个停车点，并向阶段会话尽力送达一次接受追问，驳回把产物连同批注退回同一阶段会话作为修订指引。

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

运行时要求阶段以回复正文作为产物，并在最末尾给出围栏 JSON 结果对象（`artifactPath`、`summary`、可选 `openQuestions`）（`src/result-protocol.ts`）；运行器拆分回复，按声明的产物名和包的 JSON Schema（如声明）校验结果，只在契约通过后原子写入正文，契约失败时对同一会话至多重驱两次，让修订留在上下文中（`src/runtime.ts`）。数据包可以向阶段授予 `write`/`edit` 工具以便在运行目录内修改代码，但这些工具不能替代声明的产物契约。承载运行事实、上游产物路径、handoff 核查清单与输出契约的简报在 `src/briefing.ts` 组合。

### 关口语义

运行状态以内存为权威，并在每个提交点镜像到 `<artifactsDir>/<runId>/run-state.json`（`src/orchestrate.ts`）。带关口的阶段以 `gate-pending` / `waiting-approval` 停车；并发批准经每次运行的串行门序列化。耗尽结果契约重试的阶段把运行停在它的关口并报告失败——人类无法批准失败阶段（不存在可下传的已接受产物），但带批注的驳回会把它作为引导式修订在同一会话中重新打开。批准之后还会向被关口阶段会话尽力送达一条追问——产物已获通过，附评审批注（如有）——让角色的接受后步骤（例如记忆备注）能在真实一轮中触发；流水线绝不等待这次送达，追问失败只记录日志，不会让运行失败。

### 派生接缝

阶段经 `ctx.agents.create({ sessionId, meta, agentOptions, setup })`——代理注册表的 scoped-create 面——派生，再以 `followup()` 加 `await agent.whenIdle()` 驱动一轮。流水线阶段使用有界工具面且不分配工作树的角色化会话。层级阶段复用同一接缝，并通过可选的 session-identity 注册表记录 controller／lead／worker 的父级绑定；它们不调用 `agent_dispatch`。经注册表派生让本包保持为既有循环行为之上的普通插件——不新增执行循环。

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
| [`src/tools.ts`](src/tools.ts) | 四个模型工具定义，含 `expert_team_run` 上的咨询模式 |
| [`src/gateway.ts`](src/gateway.ts) | Web 状态快照的只读宿主 Remote 拥有者 |
| [`src/client.ts`](src/client.ts) | Web 快照共享类型 |
| [`src/plugin.ts`](src/plugin.ts) | Loader 接线：配置、目录、服务、工具、使用段落、处置 |

### 不变量

未发布运行时 invariant 伴随物：编排器不持有可跨进程观察的关系需要断言——它的保证（契约通过后才写产物、提交点镜像状态、批准串行化）都在单进程内强制，并由编排行为测试验证。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 专家团队工具与指引

#### 模型看到什么

可见作用域中恰好多出四个工具：`expert_team_list`、`expert_team_run`、`expert_team_status` 与 `expert_team_approve`。`expert_team_run` 有两种输入形态：`team` 加 `input` 驱动流水线，`expert` 加 `question` 在运行之外发起一次有界咨询。一个静态使用段落（`expert-team:usage`）进入全局提示层，教导何时列出、运行、以评审者原话批准、以及何时使用咨询形态而不跑完整流水线，并说明产物是按路径引用的文件。运行期间，每个阶段子代理的请求携带逐字专家角色、每个声明包技能一个段落、上游产物路径、handoff 核查清单与阶段输出契约（含 schema 文本）——产物内容本身绝不回到提示词，只有路径会。

#### Token 影响

四个工具的模式在可见作用域的每次请求中占用 token，使用段落的固定文本每次请求进入提示词一次。一次运行的成本按阶段到来：每个阶段请求加上它的角色（数 KiB）加技能段落、上游引用与声明的 schema 文本；每个阶段结果和每次关口决定在可复用前缀之后追加一条有界 JSON。

#### KV Cache 影响

挂载的包与工具模式不变时前缀稳定：模式与静态使用段落只声明一次，每阶段内容追加在可复用请求前缀之后。编辑任何包文件会改变后续运行组合的内容，并为受影响请求开启新前缀；挂载或卸载会改变工具清单，破坏受影响代理下一次请求的提供方缓存复用。

### 运行历史

#### 模型看到什么

模型可以通过 `expert_team_status` 检查正在运行的运行；更完整的内存索引也可由宿主通过 `listRuns()` 访问。索引在每个提交点镜像到 `<artifactsDir>/run-index.json`，但启动时不会加载，因此停车或已完成运行不会在新进程中变成模型事实。

#### Token 影响

状态响应只增加 `expert_team_status` 返回的有界 JSON；宿主专用的索引和文件镜像不占用模型 token。

#### KV Cache 影响

插件保持挂载时状态模式的前缀稳定；写入或镜像运行元数据不会改变提供方请求前缀。

### 多包组合

#### 模型看到什么

多个团队包（paper、dev 或自定义）可以通过 `packs` 配置数组同时挂载。它们唯一的团队 id 会出现在 `expert_team_list` 中，所选 id 决定 `expert_team_run` 启动流水线还是层级运行；包自有的技能与阶段契约会抵达对应的阶段代理。

#### Token 影响

每个挂载的包都可以向列表结果增加团队与专家元数据，并向使用它的阶段请求增加角色与技能段落；成本受挂载包内容的大小约束。

#### KV Cache 影响

共享工具模式保持稳定，但改变挂载的包列表或任意包文件会改变编录或阶段提示词内容，使受影响请求的前缀缓存失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制是当前插件约束，不是任务清单。

- **运行不跨进程恢复。** 运行状态以内存为权威，并在每个提交点镜像到 `<artifactsDir>/<runId>/run-state.json`；停车或进行中的运行在重启后丢失。跨进程恢复路径已显式拒绝——未实现存储接缝，`run-state.json` 是镜像而非恢复点。进程重启终止进行中的运行；产物文件和 `run-state.json` 保留用于审计。
- **记忆记录是委托而非自有。** 到 project-memory 的实体锚定经包的工具允许清单实现：声明了 `memory_append` 的专家可以以研究主题为实体标签记录其产物，未配置记忆时由工具如实报告 `MEMORY_UNAVAILABLE`。编排器自身从不调用记忆；核心自有的按产物记忆写入推迟到有度量需求，且实体标签没有别名登记表，跨运行召回依赖写入模型复用标签。
- **阶段串行执行。** 声明顺序是拓扑序，但执行器从不并行化独立阶段；有度量的延迟需求时才值得改变。
- **关口记录的是决定，不是经验证的人类。** 编排器停车并记录 `expert_team_approve` 收到的内容，但无法验证发言者是人类：批准者是人工评审这一规则只经使用段落的提示词固定，不是能力强制。
- **没有每团队并发上限。** 受信任的驱动会话可以对同一团队并发发起多个 `expert_team_run`。数据包无法递归——声明插件自有工具的包在挂载时失败（`EXPERT_TEAM_TOOL_FORBIDDEN`），阶段专家因此不能批准关口或启动运行——但驱动会话受信任且不受上限约束。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

M1 范围的决策记录见[专家团队 Agent Note](../../../.agents/notes/implemented/feature/2026-09-14-expert-team-m1.zh.md)。M3 层级模式与 M4 加固决策记录在 [2026-09-15-expert-team-m3.zh.md](../../../.agents/notes/implemented/feature/2026-09-15-expert-team-m3.zh.md) 和 [2026-09-15-expert-team-m4.zh.md](../../../.agents/notes/implemented/feature/2026-09-15-expert-team-m4.zh.md)；跨进程恢复拒绝记录在 [2026-09-15-expert-team-no-cross-process-resume.zh.md](../../../.agents/notes/implemented/feature/2026-09-15-expert-team-no-cross-process-resume.zh.md)。

</details>
