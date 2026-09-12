---
description: GPT-6 Astra 总规划与 DSH 有边界插件化开发的精简交接文档。
---

# DSH 插件化开发交接文档 — 2026-09-05

[English](dsh-pluginized-development-handoff-2026-09-05.md) | 中文

## Summary

这份工作交接文档给 GPT-6 Astra 一份简短的总规划输入，也给 DSH 一份可执行的实现摘要。它只保留影响所有权、并发、SessionID、工作树、插件边界、恢复和验收的决定；详细契约继续放在有明确所有者的文档中。

## Table of Contents

- [1. 目标](#objective)
- [2. 当前状态](#current-state)
- [3. 硬性规则](#hard-rules)
- [4. 插件工作包](#plugin-work-packages)
- [5. Agent 结构与波次](#agent-topology-and-waves)
- [6. Astra 规划提示词](#astra-planning-prompt)
- [7. DSH 执行提示词](#dsh-execution-prompt)
- [8. 验收与汇报](#acceptance-and-reporting)
- [Further Exploration](#further-exploration)
- [Dev Note](#dev-note)

## 1. 目标 <a id="objective"></a>

GPT-6 Astra 先审查仓库、当前 profile、设计文档、测试、Agent Note 和候选插件发布版本，再写出权威的依赖与执行规划。随后 DSH 创建一等 Session、分配工作树、分发有边界的任务、收集证据，并且只合并经过审查的路径。

最终目标是让 DSH 能够规划、分工、恢复、审查并合并自己的低风险开发工作；一次对话成功或侧边栏出现一行都不算完成。

## 2. 当前状态 <a id="current-state"></a>

- 仓库根目录：`D:\dsh-devframe`。
- 本地观察到的 Web profile 条目：`@dsh-mobile/pairing`、`dsh-codex-sidebar`、`dsh-external-agents`、`dsh-model-switch` 和 `dsh-usage-monitor`。
- 仍需明确验证兼容性的插件：`dsh-llm-codex`、`dsh-llm-providers-ui`、`dsh-llm-opencode-go`、`dsh-llm-ollama`、`dsh-llm-grok`、`dsh-llm-commandcode` 和 `dsh-ponytail`。
- 现有用户改动、Agent Note、测试和未跟踪的 `docs/env*` 文件不属于本文档所有权，必须保持不动。
- [dsh-plugins](https://github.com/NOirBRight/dsh-plugins) 目录可能落后于仓库 README；启用前要核对精确版本、DSH/Cordis 兼容性、权限、凭据、配额和许可证。

## 3. 硬性规则 <a id="hard-rules"></a>

- 总控和插件组长是同一类一等 Agent/Session；二者都有真实持久化 SessionID 和独立工作树。
- 逻辑树最多三层、创建边最多两条：总控 → 组长 → Worker。
- 只有总控能创建组长；组长只能在自己的插件内创建 Worker；Worker 不能创建任何 Agent。
- 每条 Agent/工作树记录都绑定 `agentId`、`sessionId`、`pluginId`、`taskId` 和 `worktreeId`；只有总控能合并到主树。
- 不使用 `idle` 状态：使用 `planned`、`assigned`、`developing`、`reviewing`、`submitted`、`integrated`、`completed`、`blocked` 或 `failed`；blocked/failed 必须写原因和下一步。
- 模型可见事实、路由、分配、结果和恢复状态都必须能从会话日志重建。
- UI 默认折叠树；箭头只改变当前父节点的下一层；点击 SessionID 直接复制完整值，不弹对话框。
- 外部 Provider 使用 `@codex`、`@claude`、`@cursor` 等类型化显式路由；路由不可用时明确失败，不能静默降级。
- 共享契约、生成事件、manifest、profile 和主树提升必须有唯一负责人并进入串行集成步骤。
- 未经授权和证据确认，不得 push、PR、发布、破坏性清理或运行依赖凭据的在线测试。

## 4. 插件工作包 <a id="plugin-work-packages"></a>

每一行都是独立的责任单元；P00 是共享库，P12 是 QA/集成工作流，不是可安装的运行时插件。

| ID | 工作包 | 责任范围 | 依赖 |
| --- | --- | --- | --- |
| P00 | `dsh-project-contracts` | 带品牌 ID、类型化事件、任务/结果消息和插件声明 | DSH core |
| P01 | `dsh-session-identity` | 持久化 SessionID 创建、查找、恢复和展示元数据 | P00 |
| P02 | `dsh-agent-hierarchy` | 总控/组长/Worker 角色、权限和最大深度 | P00–P01 |
| P03 | `dsh-worktree-registry` | 每 Agent 一棵工作树的创建、绑定、锁、检查、停止和恢复 | P00–P01 |
| P04 | `dsh-project-controller` | 项目生命周期、调度、有界并发和合并门禁 | P01–P03 |
| P05 | `dsh-agent-evidence` | Goal/任务绑定、提交回执、验证快照和交接 | P00、P04 |
| P06 | `dsh-agent-reliability` | 限流、重启、不确定调用、日志损坏和进程停止 | P01–P05 |
| P07 | `dsh-agent-tree-ui` | 折叠层级、子节点发现、状态/工作树展示和 ID 直接复制 | P01–P06 |
| P08 | `dsh-agent-router` | 类型化 `@provider` 路由和外部任务持久化元数据 | P00、P09 |
| P09 | `dsh-external-agents` | Codex、Claude Code、Cursor 等 Product Worker 适配器 | P08 |
| P10 | `dsh-llm-codex-astra` | Codex Provider 及 `gpt-6-astra` 动态、静态/缓存目录路径 | P11、Codex OAuth |
| P11 | `dsh-llm-providers-ui` | 共享 Provider 设置命名空间和卡片组合 | Web UI |
| P12 | `dsh-model-switch` | 模型和路由选择接入 | P11、Provider 注册表 |
| P13 | `dsh-codex-sidebar` | 侧边栏和项目/Session 导航接入 | P01、P07 |
| P14 | `dsh-usage-monitor` | 用量、配额、限流和重试状态展示 | P05、Provider 注册表 |
| P15 | `dsh-mobile-pairing` | 手机配对、加密连接和隧道回退 | P01、Web UI |
| P16 | `dsh-llm-opencode-go` | OpenCode Go Provider 安装和能力验证 | P11 |
| P17 | `dsh-llm-ollama` | Ollama Cloud Provider 安装和能力验证 | P11 |
| P18 | `dsh-llm-grok` | Grok Provider 安装和能力验证 | P11 |
| P19 | `dsh-llm-commandcode` | Command Code Provider 安装和能力验证 | P11 |
| P20 | `dsh-ponytail` 验证 | 模式、技能和子 Agent 继承的实验室兼容性检查 | 当前发布版本 |
| P21 | Shadow 和 Memory | 后续跨项目路由和有边界记忆扩展 | P04、P06 |
| P22 | 集成与 QA | 固定候选组装、只读 QA、精确路径提升和发布证据 | 已批准波次产物 |

一个验证组长负责隔离 profile 中的 P16–P20；`dsh-llm-providers-ui` 是四个 Provider 的设置前置条件，不是额外的验证目标。缺少凭据或配额时记录 `SKIP_AUTH` 或 `SKIP_QUOTA`，不能算通过。

不要加入已废弃的 `dsh-composer-picker`、隔离区的 `dsh-llm-assistant`/`dsh-buddy`，也不要在没有单独策略审查时加入 `dsh-llm-cursor`。

## 5. Agent 结构与波次 <a id="agent-topology-and-waves"></a>

| 层级 | Agent | 创建权限 | 责任 |
| --- | --- | --- | --- |
| L0 | 项目总控 | 创建 L1 组长 | 项目 Goal、计划、全局状态和主树合并 |
| L1 | 插件组长 | 在本插件内创建 L2 Worker | 插件范围、工作树集合、审查队列和交接 |
| L2 | 叶子 Worker | 无 | 一项有边界的任务和一棵工作树 |

| 波次 | 范围 | 并发 | 退出条件 |
| --- | --- | --- | --- |
| W0 | P00–P03 和 P06 基础 | 共享事件/manifest 串行，测试隔离 | 身份、权限、工作树所有权和恢复已有测试 |
| W1 | P04–P05 和 P22 组合 | 一份固定候选，总控负责集成 | 组长、证据、停止/恢复和 QA 路径端到端可用 |
| W2 | P07–P15 产品接入 | 每插件一个组长，共享 profile 文件走队列 | UI、显式路由、模型、现有插件和重启行为可见 |
| W3 | P16–P20 五仓库验证 | 一个验证组长，隔离 profile | 每插件标记 verified、blocked 或 skipped 并写原因 |
| W4 | P21 Shadow/Memory 和发布试运行 | W1 验收并有明确方案后开始 | DSH 完成一轮有边界的自开发场景 |

## 6. Astra 规划提示词 <a id="astra-planning-prompt"></a>

只有确认当前 Provider/账号暴露该模型后，才能使用 `gpt-6-astra`。官方指引列出 `low`、`medium`、`high`、`xhigh` 和 `max`；其他 effort 必须先检查 DSH Provider。参见[官方模型指引](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)。

把下面的提示词复制给 GPT-6 Astra：

```text
你是 DSH 项目的首席架构师。请先阅读 docs/working/dsh-pluginized-development-handoff-2026-09-05.md、AGENTS.md、docs/architecture.md、设计/验收文档、当前 profile、package.json、测试和 Agent Notes，再检查候选插件的当前 README、发布版本和兼容性。
请输出一份可执行总规划，按“源码已有、profile 已安装、运行时已验证、生产已接受”区分现状；为每项能力给出插件 ID、责任边界、Service Definition/Provider/Consumer、依赖、事件/持久化影响、负责人、测试、验收和回滚。
必须保留：Controller 与 Lead 是同类一等 Session；二者都有真实 SessionID 和独立 Worktree；Controller 只能创建 Lead，Lead 只能创建本插件 Worker，Worker 不能创建 Agent；最多三层、两条创建边；只有 Controller 合并；无 idle；模型可见事实入日志；树默认折叠；SessionID 点击直接复制；外部 Agent 使用显式 @codex/@claude/@cursor 且不静默降级。
单独规划一个验证 Lead 负责 dsh-llm-opencode-go、dsh-llm-ollama、dsh-llm-grok、dsh-llm-commandcode、dsh-ponytail，使用隔离 profile；认证/配额缺失标记 SKIP_AUTH/SKIP_QUOTA。dsh-llm-providers-ui 是四个 Provider 的设置前置条件，不计入五个验证目标。
输出顺序：现状证据、插件清单、依赖与并发波次、Agent/SessionID/Worktree 创建顺序、验收、风险回滚、交给 DSH 的执行提示词。先规划，不改代码、不创建假 Agent、不创建无限层级、不推送远端。
```

## 7. DSH 执行提示词 <a id="dsh-execution-prompt"></a>

Astra 写完规划后，把规划文档和下面的提示词交给 DSH。DSH 必须先用实际工作区核对规划，再开始实现。

```text
你是 DSH 项目级总控 Agent。请先阅读交接文档、GPT-6 Astra 总规划、实际源码、当前 profile、工作区状态、插件注册和已有 SessionID/Worktree 记录，先写执行清单并列出差异，不要把旧聊天、UI 标签或消息发送成功当成证据。
先建立正确拓扑：一个 L0 项目总控、同类的一等 L1 插件组长、每个组长可创建本插件的 L2 Worker；每个 Session 都必须有真实 SessionID、父 SessionID、独立 Worktree、pluginId、taskId、worktreeId 和持久化状态；最大三层、两条边；Worker 严禁创建 Agent。
按 W0→W4 执行，先完成 SessionID、层级、Worktree、总控、证据和可靠性，再并发低耦合插件。共享契约、事件、manifest、profile 和主树合并指定唯一负责人并串行。
为五个指定仓库创建一个隔离验证 Lead；缺少凭据或 quota 如实标记 SKIP_AUTH/SKIP_QUOTA，不污染生产 profile。
状态只能使用 planned→assigned→developing→reviewing→submitted→integrated→completed，外部等待或失败使用 blocked/failed 并写原因、唤醒条件和下一步，禁止 idle；不确定工具调用先查外部状态，禁止盲目重试。
UI 显示默认折叠的 Controller→Lead→Worker；箭头只切换当前节点的下一层；SessionID 点击直接复制；外部 Agent 使用显式 @codex/@claude/@cursor，路由、目标 SessionID、job、Worktree、结果和错误都入日志。
每轮汇报变更文件、SessionID/Worktree 映射、commit、测试命令和结果、未验证项、风险、回滚和下一动作；只有总控合并到主树，未经用户授权不得 push、PR、发布或删除文件。
```

## 8. 验收与汇报 <a id="acceptance-and-reporting"></a>

基础部分必须证明 SessionID 唯一且持久化、创建/执行/冷恢复权限、最大深度、工作树单一写入者、重复阻止和精确父级记录。

产品流程必须证明项目启动、组长/Worker 创建、有界并发、证据回执、停止/恢复、树折叠、SessionID 直接复制、显式外部路由和重启持久化。

可靠性部分必须分类处理限流、不确定调用、日志损坏、服务重启、进程树停止和未授权重放；跳过的在线 Provider 测试必须保持明确的跳过状态。

使用 `slice_green`、`qa_accepted`、`main_integrated` 和 `release_green` 表示不同里程碑；单个本地测试变绿或 Goal 完成不能替代固定组合候选上的独立 QA。

每个组长汇报：`pluginId`、Agent 名称、SessionID、父 SessionID、工作树 ID/路径、状态、精确改动文件、commit、命令/结果、运行时/profile 证据、已知问题、回滚和下一步。

## Further Exploration

阅读[架构文档](../architecture.zh.md)、[测试与验收文档](../testAndAcceptance.zh.md)和 [DevFrame 编排计划](../agent-orchestration-plan.zh.md)，了解各自的权威契约。

启用 Provider 前，复核 [dsh-llm-codex](https://github.com/NOirBRight/dsh-llm-codex)、[dsh-llm-providers-ui](https://github.com/NOirBRight/dsh-llm-providers-ui) 和 [dsh-plugins](https://github.com/NOirBRight/dsh-plugins)。

## Dev Note

这是一份为 2026-09-05 Astra 总规划准备的非权威工作交接文档。详细架构、验收和 QA 证据保留在各自的所有者文档中；本文有意只保留执行主线。
