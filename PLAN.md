# DevFrame 唯一开发计划

状态：v2.3 DSH-native review candidate；重构中的唯一人类开发权威
日期：2026-09-02
适用仓库：`RD2100/dev-frame-system`

Current verdict: **M0 DOCUMENT RESET CANDIDATE / M0 ACCEPTANCE CLOSURE ACTIVE / HUMAN_REQUIRED FOR M0 ACCEPTANCE / M1 NEXT / M2 ENTRY BLOCKED ON EVIDENCE-CONTRACT IMPLEMENTATION / DSH-NATIVE TARGET / CODEXHOST RETIRED**

## Next Action

先完成 M0 的两项剩余验收：对仓库外文档快照执行带 archive-member 路径边界检查的隔离恢复 probe；将当前 Git delta、归档内容、删除路径和迁移后的 fixture 做一次 RootActor reconciliation，使所有相关变化被归因为 `AUTHORIZED_CHANGE` 或 `EVIDENCED_PRE_EXISTING_CHANGE`，并要求 `UNATTRIBUTED_CHANGE = 0`、`UNAUTHORIZED_CHANGE = 0`。不得补造不存在的删除前 worktree baseline，也不得为此在公共仓库创建第二份报告、manifest 或 handoff。

M0 execution precondition：`snapshot_ref/path` 必须由 operator 提供，或通过已授权的 runtime/operator interface 确定性解析；如果无法解析，立即以 `HUMAN_REQUIRED` 停止。不得搜索任意用户目录、猜测可能路径，或根据历史对话重建路径。

恢复 probe 必须保留 operator-local manifest 的稳定 ID 与 SHA-256 直到独立 review 与 RootActor reconciliation 完成。两项证据通过后，由用户决定是否接受 M0。只有 M0 被明确接受，RootActor 才可按照 exact accepted change-set 生命周期处理本地逻辑提交，并激活 M1。M1 只对齐当前 checkout、DSH 登录修复、认证发现、真实 endpoint 和 overlay/source lock。

M2 开始前还必须把四项已定义合同落实到 schema/runtime/负向测试：`GateResolution`、Evidence subject/review-input digest、`RootActor` 权限边界、mixed-origin path 的 exact accepted change-set。M2 先在改造后的 DSH 单会话执行基座上证明单执行器治理闭环，M3 再验证 DSH 多会话、跨会话消息和薄网关合同。

从本次修订起，计划设计冻结到 M2：除执行中发现新的 P0/P1 事实外，不再进行宏观架构扩写；后续优先获得 M0、M1 和 M2 的真实证据。

交给下一位 reviewer 时，重点回答：

1. M0 剩余证据是否足以支持接受，而没有伪造删除前基线；
2. M1 是否能在不依赖历史聊天的情况下定位并验证登录修复；
3. M2 是否已经是最小但完整的治理产品证明；
4. M3 是否让 DSH Core、薄网关、DevFrame 和 Obsidian 各自只有清晰且不重叠的权威边界；
5. 是否仍有自然语言声明被误当成已验证事实或稳定机器接口。

## 1. Authority

本文件是项目唯一的人类开发权威，负责定义：

- 产品目标、边界与用户结果；
- 当前事实、未知项与风险；
- 唯一活动里程碑和有序 backlog；
- Acceptance Delta、HumanGate、退出证据和下一动作；
- 仍然有效的架构与复用决定。

权威顺序：

1. 系统、开发者和当前用户指令；
2. `AGENTS.md` 的最小自动入口；
3. `rules/`、`schemas/`、测试和运行时代码表达的强制约束与实现事实；
4. 本文件选择的产品目标、里程碑和下一动作；
5. 外部资料、记忆、研究报告、模型建议、截图和 Worker 输出。

代码和测试决定“已经实现了什么”；本文件决定“为什么做、下一步做什么、需要什么证据以及何时可接受”。任何外部报告只能提出候选修订，不能自行改变当前 verdict。

`PLAN.md` 是人类计划权威，不是运行时 Task/Run/Evidence/Gate 数据库。程序可以验证本文件存在、唯一、UTF-8、包含必要入口，但不得从自然语言标题、表格位置或措辞推断 canonical runtime state。若未来确有机器读取计划状态的需求，必须通过单独受审 slice 加入版本化、带 schema 和负向测试的最小结构化块；不得暗中把 Markdown prose 当 API。

架构分析 Agent 必须先拆解目标、可选项和潜在假设，再进行证伪式风险分析、开源参照求证、方案取舍和 DSH 落地设计；用户原始构想、外部项目描述和模型建议都只能作为待验证输入。Prompt 负责语义编排建议，不能替代运行时对身份、权限、配额、并发、超时、恢复和证据完整性的硬约束；该 Agent 输出架构方案，不直接写代码。

旧 PRD、MVP、process、HANDOFF、roadmap、Recon Receipt、stage report、reviewer index、release note 和历史研究文档全部退役。它们只可通过 Git 历史或仓库外重构快照恢复，不能重新成为当前依据。

## 2. Product Decision

### 2.1 产品定位

DevFrame 是本地、可审计、可恢复的 AI 开发治理内核。它把用户目标冻结为有边界的 Task 和 Run，组织可替换执行器，收集与精确源码绑定的证据，执行独立审阅和 Gate，并只在证据充分时生成 FinalVerdict。

一句话目标：

> 让 Web AI、Codex、Claude Code、OpenCode、Pi、DSH 和项目原生工具成为可替换执行器，同时让目标、权限、证据、审阅、恢复和最终决定始终由同一套 DevFrame 治理语义掌控。

### 2.2 Core MVP

Core MVP 证明 DevFrame governance，不证明所有 adapter、Host 和领域包。

一个真实软件任务必须经过：

```text
Objective
  → bounded TaskSpec
  → canonical Run
  → one real Executor
  → exact source Diff
  → native build/test/lint
  → EvidenceRevision
  → independent read-only Review
  → revision or GateResolution (not_required / accepted HumanGate)
  → FinalVerdict
  → interruption + restart side-effect reconciliation
```

DSH 多会话扩展、PaperLab、GPT Web、多 Provider、跨项目记忆和复杂自动化用于证明扩展性，不得阻塞 Core MVP。

### 2.3 用户结果

目标用户是长期使用多个 AI 和本地工具完成软件开发或论文研究的个人开发者/研究者。最终日常体验应满足：

1. 打开一个统一工作台并选择项目；
2. 输入目标，不必手工维持几十个终端和会话；
3. 看见 Task、Agent、消息、工具、Diff、证据、预算和待决 Gate；
4. 可逆工作在规则内持续推进；
5. 高风险、不可逆或无法推断的决定才请求人类；
6. 刷新、取消、崩溃或重启后仍能证明和恢复；
7. Worker 成功不会被误写成项目完成；
8. 项目记忆可以辅助，但不能成为第二权威。

### 2.4 不做什么

- 不自研第二套通用编辑器、终端、Diff、会话数据库或 Agent Loop；
- 不把某个模型、Provider、客户端或 Harness 固化成治理语义；
- 不把聊天记录、模型建议、图谱推断或记忆当成事实权威；
- 不为展示效果复制 Task/Run/Evidence/Gate/Verdict 状态；
- 不在没有真实 canary 的情况下宣称外部 Web、Provider、浏览器或论文能力完成；
- 不以无人值守 full-access 代替明确权限和 HumanGate；
- 不在公共仓库堆积执行日志、截图、报告包、临时导出和历史规划文档。

## 3. Target Architecture

### 3.1 DSH 基座上的治理内核

```text
Shadow / Project Controller / Worker
  semantic orchestration through bounded DSH sessions
        │
        ▼
DevFrame governance authority
  Objective / TaskSpec / Run / Context / Policy / Evidence / Review / Gate / Verdict
        │
        ▼
Thin gateway (opaque transport and resource control)
  lifecycle / queue / lease / quota / timeout / dead-letter / recovery metadata
        │ minimal callbacks and event tail
        ▼
Modified DSH Harness
  workspace / session / turn-step / event log / sandbox / tool validation
```

DevFrame 的核心闭环运行在改造后的 DSH Harness 之上，不依赖任何商业闭源 Host。DSH 负责单会话 turn/step、append-only 事件、沙箱和工具调用校验；DevFrame 负责治理对象的 canonical identity 和最终状态；外层薄网关只负责会话生命周期与传输基础设施，不解析业务 payload。

### 3.2 当前交互基线

当前基线继续使用 DSH 工作台与 DevFrame 薄扩展。正式 DSH 上游仍锁定 `dsh-v0.1.1-rc.2`；任何升级必须重新应用并审查 source-only overlay，不能只改版本号。

### 3.3 DSH 二次开发目标

底层基座固定为改造后的 DSH Harness。CodexHost 路线因 Codex 本身不开源而退役，不再作为复用候选、兼容目标、fallback 或架构决策前置条件。

DSH 的职责边界：

- 每个 Agent 角色映射为一个独立 DSH session，并拥有稳定 `session_id`；
- 执行单个 session 的 turn-step 循环、append-only 事件日志、沙箱和工具调用校验；
- 通过最小外部回调暴露生命周期、事件 tail、取消、健康检查和重启信号；
- 不承载 Shadow、项目总控、Worker、评审、辩论、仲裁等业务流程。

DevFrame/薄网关的职责边界：

- `Shadow` 只做全局目标对齐、项目路由、汇总和用户级记忆读取，不直接执行项目业务；
- 项目总控 Agent 负责项目 Objective、TaskSpec、Run、拆解、派发、证据、审查和人类 Gate；
- Worker 只执行具体任务并提交原始产出，不拥有高层接受权；
- 薄网关负责 session 生命周期、消息队列、lease、资源配额、权限标签、超时熔断、死信和崩溃恢复元数据；网关把 payload 当作不透明数据，不解析业务语义；
- Obsidian 负责用户/项目知识文档的持久化，不能成为第二个 Task/Run/Evidence/Gate/Verdict authority。

Prompt 与运行时的边界：Prompt 可以选择任务拆解、是否请求审查、是否辩论以及何时提出仲裁；代码必须硬性保障 session identity、权限、write-set、消息大小/数量、并发 lease、超时、取消、幂等、恢复、死信、禁止自审和证据绑定。不能用“模型会记得流程”替代这些约束。

DSH 二次开发分层：

- DSH plugin：注册 session、暴露受控 spawn/send/inbox/cancel/status 回调，订阅事件并把运行事实投影给 DevFrame；
- DSH Core 最小补丁：只增加稳定 session identity、外部生命周期回调、事件 tail、取消/重启信号和必要的幂等钩子；坚决不加入 Shadow、项目拆解、评审、辩论、仲裁或 Obsidian 业务逻辑；
- 独立薄网关：实现 opaque message queue、lease、配额、超时、熔断、死信和崩溃恢复元数据；不得按 payload 内容理解或编排业务；
- Prompt/知识库规范：描述角色职责、消息 envelope、可信度/时效性和复盘格式；不能替代权限、并发、资源和恢复硬约束。

Obsidian namespace contract：

- `user-memory/` 只允许 Shadow 通过受治理 adapter 写入；项目总控、Worker、Reviewer 和网关只能 bounded read，不能写用户记忆；
- `project/{project-id}/` 按项目隔离，项目产出、评审、辩论和仲裁记录必须带 project/run/session provenance；跨项目读取必须经过显式授权；
- 每条可用于推理的笔记至少带 `source`、`confidence`、`freshness`、`sensitivity`、`owner`、`created_at` 和 `updated_at`；过期或冲突内容只能作为候选，不能自动提升为事实；
- 用户记忆采用 create-only proposal + 人工/Shadow promotion；项目笔记采用版本/CAS 或 append-only 事件避免并发覆盖；网关不直接访问 Vault。

### 3.4 复用与改造假设

以下是待 M1/M3 求证的边界判断，不是 LOC 审计或已接受事实：

| 能力 | 预计可复用 | 当前决定 |
|---|---:|---|
| DSH 现有 session/turn-step、事件、沙箱、工具校验 | 以当前 source/overlay 实测 | 作为唯一底座，先锁版本和补丁来源 |
| DSH CLI/工作台与本地人工测试能力 | 以当前 checkout 实测 | 保留现有能力，优先做薄插件 |
| DevFrame 目标、证据、审阅、Gate、恢复和记忆治理 | 不预设比例 | 必须由 DevFrame 自有语义掌控 |
| 跨 session 通信与薄网关 | 新增合同为主 | 独立于 DSH Core，先做最小可恢复管道 |
| Shadow/项目总控/Worker 的业务编排 | Prompt + DevFrame 边界 | 不下放到 DSH Core 或网关 |

任何 DSH Core 扩大改造、第二套桌面壳或新的多 Harness UI 都不是默认路线；没有可重复的失败证据和 HumanGate，不扩大范围。

## 4. Canonical Governance Model

### 4.1 核心对象

| 对象 | 唯一职责 |
|---|---|
| `ProjectObjective` | 项目长期目标和完成条件 |
| `Milestone` | 有边界的阶段结果、入口和退出 Gate |
| `TaskSpec` | scope、write-set、forbidden-set、风险、验收和预算 |
| `Run` | 一次真实执行的稳定身份、参与者和状态 |
| `MessageEnvelope` | Controller、Agent、Task 和人类之间可追踪通信 |
| `ContextPacket` | 派发时冻结的来源、选择、预算、压缩和 hash |
| `ContextLedger` | ContextPacket 的使用、修订和来源账本 |
| `PolicyDecision` | 工具、文件、网络、凭证和风险权限决定 |
| `EvidenceRevision` | 绑定 base/head、candidate diff digest、verification subject digest、命令和输出的不可混用证据版本 |
| `Review` | 独立、只读、绑定 EvidenceRevision、subject digest 和 review-input digest 的审阅 |
| `HumanGate` | 不可逆、新授权或重大产品决定的人类入口 |
| `GateResolution` | `not_required` 或绑定一个已接受 HumanGate；不得用虚构空 Gate 填充 |
| `FinalVerdict` | 绑定当前证据、accepted Review 和明确 GateResolution 的唯一完成结论 |
| `MemoryProposal` | 可审阅的计划/经验候选，不是事实或任务权威 |
| `RootActor` | Project Controller 下唯一具有 accepted change-set Git 生命周期权限的 privileged participant；不是新治理权威 |

### 4.2 状态语义

状态由三个正交维度组成，不得混成一个互斥 enum：

| 维度 | 值 | 含义 |
|---|---|---|
| `lifecycle_state` | `planned` / `active` / `candidate` / `accepted` / `failed` / `deferred` | 对象或里程碑处于哪个生命周期阶段 |
| `gate_state` | `none` / `blocked` / `human_required` | 是否被证据缺口或人类决定阻塞 |
| `fact_state` | `verified` / `observed` / `unverified` / `unspecified` | 一个事实声明的证据强度 |

因此 M0 可以同时是 `lifecycle_state=candidate`、`gate_state=human_required`，其 acceptance closure 可以是 `active`；DSH source/overlay relationship 若尚未完成锚定，则是 `fact_state=unspecified`。`unspecified` 禁止 Agent 根据上下文猜值，`observed` 也不得自动提升为 `verified`。

`completed`、Worker `success`、测试 exit code 0 和模型自评均不自动等于 `accepted` 或 `final_ready`。

### 4.3 Reviewer 独立性

最低独立性合同：

1. `review.participant_id != author.participant_id`；
2. `review.run_id != author.run_id`；
3. review context 必须只读，不能改源码、EvidenceRevision 或 Gate；
4. Review 必须绑定精确且仍为当前的 EvidenceRevision、`subject_digest` 和 `review_input_digest`；
5. 同一 provider/model 可以参与不同身份的 run，但 provenance 必须保留；
6. Review 输入只包含 TaskSpec、验收条件、exact candidate diff、EvidenceRevision、必要源码上下文、测试输出和已知风险；作者完整聊天、自评和无关历史不默认注入；
7. 高风险 slice 可由 HumanGate 提升为不同模型、不同 provider 或人类审阅。

任一被审阅源码、write-set、verification-set、candidate diff 或 review input digest 改变，Review 立即 stale。负向验证至少覆盖：作者自审被拒绝、review 写入被拒绝、stale revision 被拒绝、没有 accepted review 的 FinalVerdict 被拒绝。

### 4.4 RootActor 权限边界

`RootActor` 是当前 Project Controller 下具有 accepted-slice Git 生命周期权限的 privileged participant，不是新的 Task、Evidence、Review、Gate 或 Verdict authority。

- 可以执行 reconciliation，并在证据、独立 Review 和必要 HumanGate 通过后构造本地 accepted commit；
- 不能接受自己的实现，不能作为同一 change-set 的作者或 reviewer；
- 不能修改 Review、EvidenceRevision 或 Gate resolution；
- 不能自行解决 HumanGate，也不能跳过当前 subject digest；
- 身份、Run、输入、staging 方法和 commit 动作必须进入 provenance；
- `RootActor != Human`，用户仍是 HumanGate 的决定者。

### 4.5 Bootstrap Authority Rule

M0-M1 的 `Reviewer`/`RootActor` 是由 PLAN 与 operator 控制的 procedural bootstrap roles，不代表运行时已经具备对应的强制执行能力。它们只能用于保持 provenance、角色分离、exact accepted change-set 和 HumanGate 纪律，不能把“人工按流程执行过”宣称为 schema/runtime 已经 enforce。

从 M2 entry 起，`GateResolution`、`RootActor` 权限、subject/review-input digest、stale invalidation 和 exact accepted change-set 必须由 schema/runtime 与负向测试共同强制；在此之前缺少机器证据时保持 `blocked`/`human_required`。

## 5. Non-Negotiable Invariants

1. 一个物理 Run 只能有一个 canonical identity 和一个最终治理投影。
2. Worker 不得审阅或接受自己的工作。
3. FinalVerdict 必须绑定当前 EvidenceRevision、accepted Review 和明确 GateResolution；PolicyDecision 要求 HumanGate 时必须绑定已接受 HumanGate，否则必须显式记录 `gate_resolution=not_required`，不得伪造空 Gate。
4. 同一项目同一时刻最多一个 write-capable Run；读取和审阅不得绕过写串行器。
5. 客户端只能显示、请求、提议和显式调用允许动作，不能制造完成状态。
6. Provider/模型身份只属于 provenance，不改变治理语义。
7. 记忆、外部 Web、Research MCP、CodeGraph 和图谱输出默认是不受信任的上下文或证据候选。
8. 不建立第二项目注册表、第二聊天/会话数据库、第二 Task authority 或第二 FinalVerdict。
9. 对用户输入、外部路径、命令、网络目标和凭证执行边界验证；路径逃逸或命令注入是 P0 hard stop。
10. 不读取、复制或输出秘密；真实凭证和用户 Vault 只在明确授权的真实 canary 中使用。
11. 保护进入任务时的脏工作树；禁止 broad restore、stash、reset、clean 和宽泛 stage。
12. Worker 和候选 slice 不得 stage、commit 或设置 `root_accepted`；只有 RootActor 在独立审阅和要求的 HumanGate 后构造 exact accepted change-set。path-level staging 仅在该 path 的全部当前 delta 都属于 accepted slice 时允许；mixed-origin path 必须使用 hunk/blob-level staging，无法安全分离时 hard-stop 给用户。
13. 每个 accepted slice 只允许一个本地逻辑 commit；提交前必须证明 cached diff 与 reviewed accepted diff 等价，满足 `commit_delta == reviewed_accepted_delta`，而不只是路径集合相等。push、PR、merge、release、部署和历史重写另行授权。
14. 客户端、runtime、provider、MCP、review/evidence、多 Agent 或桌面行为在写入前必须完成 Recon 和开源复用评估。
15. 取消、超时、崩溃和重启必须能证明副作用、participant、事件顺序、lease 和恢复边界。
16. 不允许把 `blocked`、`failed`、flaky、skipped 或环境缺失包装成通过。
17. 公共仓库不保存本地 Agent 状态、浏览器 Profile、证据包、报告 dump、真实 Vault、密钥、临时构建或生成归档。
18. 未来 destructive slice 必须在动作前冻结 machine-readable baseline、精确目标和可恢复来源；不得把事后重建写成事前证据。
19. EvidenceRevision 在 dirty/shared worktree 中不得只依赖 HEAD 表示源码身份；必须绑定 candidate diff digest 以及 write-set、verification-set 的 subject digest，FinalVerdict 前 digest 变化会使 Review stale。

## 6. Product Capability Register

P0 的定义是：没有它，就无法完成一个真实、受治理、可恢复、可独立审阅的软件任务。

| ID | 能力域 | Core MVP 结果 | 优先级 |
|---|---|---|---|
| CAP-001 | 工作台 | 复用成熟 workspace/session/chat/file/shell/terminal/diff/permission | P1 |
| CAP-002A | Runtime readiness | 当前环境的健康检查、可解释 degraded/blocked、失败关闭 | P0 |
| CAP-002B | Distribution | 新用户 clean checkout 安装、升级、禁用、回滚和发布体验 | P1 / M7 Gate |
| CAP-003 | Controller 身份 | 稳定 Controller 与 canonical Run identity，刷新重启不换权威 | P0 |
| CAP-004 | 目标主线 | Objective→Milestone→TaskSpec→Run，scope/write-set 可冻结 | P0 |
| CAP-005 | 团队通信 | Roster、Task Board、Mailbox、claim、纠偏和 human inbox | P1 |
| CAP-006 | 执行器 | Core 只需一个真实 executor；多 Harness 兼容后续验证 | P0 |
| CAP-007 | 治理迭代 | 计划→执行→证据→独立审阅→修订/Gate→Verdict | P0 |
| CAP-008 | 上下文 | sealed context、来源、预算、压缩、知识缺口和 hash | P1 |
| CAP-009 | 权限 | PolicyDecision、精确 write-set、网络/凭证门和 HumanGate | P0 |
| CAP-010 | 代码闭环 | 使用项目原生工具完成一个真实代码任务并独立验收 | P0 |
| CAP-011 | PaperLab | 公开材料 canary 后扩展检索、证据、写作和审阅 | P2 |
| CAP-012 | 外部大脑 | GPT Web 有界读取、Context Pack 发送和不受信任回复隔离 | P2 |
| CAP-013 | 项目记忆 | bounded recall、create-only proposal、项目隔离和故障降级 | P1 |
| CAP-014 | 恢复 | interruption→restart→reconcile、幂等、事件与副作用证明 | P0 |
| CAP-015 | 评估学习 | Scorecard、Feedback、Lesson proposal 和人工 promotion | P1 |
| CAP-016 | 多项目 | Global 只路由和聚合，不获得项目写权或 Verdict 权 | P1 |
| CAP-017 | 自动化 | 定时任务、提醒、背压、预算和 no-progress watchdog | P2 |
| CAP-018 | 用户资产 | Skill、Prompt、MCP、规则和 evidence recipe 的受治理导入 | P1 |
| CAP-019 | 图谱投影 | 代码/证据/知识/任务关系只读投影，不反向成为事实 | P1 |
| CAP-020 | 团队/云 | 多租户、同步、市场和远程执行 | P2 |

## 7. Verified Baseline

所有事实必须带时间边界。下表中的 Git 状态是 M0 文档迁移后的当前 capture，不是伪造的删除前 baseline。

### 7.1 当前仓库 capture

| 字段 | 值 |
|---|---|
| captured date | 2026-09-01 |
| HEAD | `fe21e749b3773cb3465b4be584997722d5d19d2f` |
| branch | `codex/rdcode-secret-containment` |
| upstream | `origin/codex/rdcode-secret-containment` |
| ahead / behind | `+37 / -0` |
| porcelain v2 records | 331 |
| tracked change records | 276 |
| untracked records | 55 |
| tree interpretation | dirty / protected / shared history |

这些数字只能用于当前 reconciliation；后续运行若状态变化，必须重新 capture，不能继续引用旧数字。

本次大规模迁移后必须重新运行完整 release gate；旧数字不能证明当前树，任何接受决定都必须基于新的 capture、证据和审查。

### 7.2 能力事实

| 区域 | 当前状态 | 证据边界 |
|---|---|---|
| 治理内核 | accepted baseline claim / M2 must re-prove as product | TaskSpec、canonical Run、sealed context、EvidenceRevision、Review、Gate、FinalVerdict 和 provider-neutral adapter 已有实现与测试 |
| 工具链 | accepted baseline claim / M2 real canary required | command/ACP 等可归一化；项目原生 build/test/lint 可通过 manifest 接入 |
| Obsidian 记忆 | accepted locally / Core MVP optional | bounded recall、create-only writeback、client/project isolation、kill switch 和 degraded path 有测试 |
| DSH 薄扩展 | candidate | rc.2、Profile/Host lease、Controller、readiness、Task Board、review/revision、memory、CodeGraph 和 rollback 路径有候选证据 |
| DSH 外部 Agent | candidate | 命令、流、取消和会话投影有候选/组装证据，不替代新的真实 canary |
| CodeGraph | candidate read-only | snapshot、transport、freshness、selection、packet/ledger 有局部验证；自动刷新和写回未授权 |
| PaperLab/Polaris | fixture-only candidate | 只读 source/citation 和 compatibility guard 有测试；真实 endpoint、凭证、全文和写回未通过 |
| GPT Web 外部审阅 | blocked | fixture、direct call 或截图均不等于真实 ChatGPT Web Host roundtrip |
| DSH 登录修复 | candidate / unanchored | 历史上下文称取得过 `auth.openai.com` URL 并验证取消，但当前 checkout 是否包含、来源 SHA 和 changed files 尚未核对 |

### 7.3 M0 当前证据

| 证据 | 结果 |
|---|---|
| retired `docs/` files | 0 |
| retired path scan | 0 hit（PLAN 中用于表达禁令的文字除外） |
| root human planning documents | `PLAN.md`；`AGENTS.md` 仅为自动入口 |
| migrated machine fixture | 30 个 negative-acceptance fixture 已归入 owning package |
| full pytest | `2741 passed, 12 skipped` |
| public snapshot | passed |
| real wheel build/install/smoke | passed in explicit offline verification mode |
| `devframe doctor` | 10/10 |
| `git diff --check` | passed；仅换行转换 warning |

### 7.4 仓库外恢复快照

| 字段 | 值 |
|---|---|
| snapshot id | `dev-frame-system-docs-before-reset-20260901.zip` |
| storage | operator-local；绝对用户路径不得写入公共仓库 |
| format | ZIP |
| bytes | 1,157,124 |
| entries | 233 |
| SHA-256 | `941489AAB9FF249E742D0650643E3A287EF53571D264BE4811D2C450BC34FDDD` |
| CRC test | passed |
| known sentinels | old AGENTS、README、handoff 和 retired docs root are present |
| archive-member path validation | `pending` |
| isolated restore probe | `pending` |
| operator-local manifest ID / SHA-256 | `unspecified` |

Hash、CRC 和条目存在只能证明归档可读，不能替代隔离恢复。快照的本机绝对路径由 operator/runtime 提供，不允许模型从公共 PLAN 推断。

## 8. Current Risk Register

| ID | 优先级 | 状态 | 风险 | 关闭条件 |
|---|---|---|---|---|
| DOC-RESET-001 | P0 | candidate | 文档删除已完成，但未形成最终 accepted reconciliation | 旧路径为 0、测试通过、restore probe、`unattributed=0`、`unauthorized=0`、用户接受 |
| DOC-RESET-002 | P0 | open | 归档 hash/CRC 通过，但尚未证明安全、语义可恢复 | member path/collision/special-file 检查、隔离解压、sentinel/manifest digest 通过 |
| SNAPSHOT-001 | P0 | planned | `snapshot_ref/path` 未解析时若 Agent 搜索任意目录、猜测路径或重建历史，会把未知来源误当作事实 | 只接受 operator 或授权 runtime/operator interface 提供的确定性引用；无法解析立即 `HUMAN_REQUIRED` |
| BASELINE-002 | P0 | planned | M0 后继续在共享 dirty worktree 中执行 M1/M2，无法隔离后续 delta 与历史用户变化 | M0 accepted 后由 RootActor 建立 exact local commit，并从该 commit 创建 isolated clean worktree；原树只读保护 |
| BOOTSTRAP-001 | P1 | planned | M0/M1 证据散落或只存在对话中，后续 Reviewer/RootActor 无法稳定复核 | 单一 operator-local evidence root、stable `evidence_ref`、`manifest_sha256` 和授权读取接口 |
| TREE-001 | P0 | active | 大型脏工作树可能混入无关 hunk；按 path stage 会错误吸收 mixed-origin delta | porcelain v2 capture、exact accepted change-set、cached diff 等价、`unattributed=0` |
| BASELINE-001 | P0 | planned | M1 登录修复仍引用不可寻址历史上下文 | 精确 source type/SHA/worktree/patch、changed files、tests 和当前 HEAD 包含关系 |
| CORE-001 | P0 | planned | 已有组件测试不等于产品治理闭环成立 | M2 一个真实代码 canary 加 interruption→restart→reconcile 路径通过 |
| EVIDENCE-001 | P0 at M2 | blocked | HEAD/base 不能唯一标识 dirty/shared worktree 中被审阅源码 | diff/subject/review-input digest、stale invalidation 和 GateResolution schema/runtime/负向测试通过 |
| REVIEW-001 | P1 | planned | Reviewer 独立性仍可能停留在原则 | participant/run/revision/read-only schema 与负向测试通过 |
| ARCH-001 | P0 at M3 | blocked | DSH Core、薄网关、DevFrame 或 Obsidian 形成第二 Task/Run/Evidence/Gate/Verdict 权威或职责越界 | Ownership Matrix、schema 和恶意 mapping/越权负向测试通过 |
| ARCH-002 | P0 at M3 | blocked | 为追求灵活性把业务流程、评审或仲裁逻辑下放到 DSH Core/网关，导致不可审计或不可替换 | Core/网关边界审计、opaque payload probe 和最小补丁评审通过 |
| SOURCE-001 | P0 at M3 | blocked | DSH rc.2 source、overlay 与当前 checkout 的来源关系未解析，升级可能悄悄改变行为 | source type/base SHA/overlay patch/hash/environment lock 全部冻结 |
| COMPAT-001 | P1 | open | DSH Core/CLI/工作台、插件回调或薄网关协议更新可能破坏 session、消息和恢复 | 固定版本、合同审计、升级/失败/回滚 canary |
| MESSAGE-001 | P0 at M3 | planned | Prompt 自主 spawn、轮询和辩论可能造成无限会话、消息风暴或死循环 | session/message 配额、轮次上限、lease、背压、死信和恢复 canary 通过 |
| OBSIDIAN-001 | P1 at M3 | guarded | 过时、冲突或幻觉笔记被当作事实传播，或多 Agent 并发覆盖用户知识 | 命名空间/权限/版本/冲突检测、可信度时效标签和 create-only 写回通过 |
| AUTH-001 | P1 | human_required | 官方 ChatGPT/Codex 登录需要用户亲自授权 | 用户完成授权，重启/撤销/取消真实路径通过 |
| RELEASE-001 | P1 | blocked | 共享脏树使旧 release evidence 失效 | 当前 accepted tree 重新通过完整 gate、review 和精确 local commit |
| MEMORY-001 | P1 | guarded | 记忆可能泄漏项目/路径/secret 或成为第二计划 | 项目绑定、bounded recall、redaction、create-only、outage fail-open |
| WEB-001 | P2 | blocked | 真实 GPT Web 路径仍缺环境证明 | 真实 Host read→send→return 并保留关联/hash/撤销/错配证据 |
| PAPER-001 | P2 | deferred | fixture-only PaperLab 被误写成生产闭环 | 真实来源、引用、隐私、错误论文和回滚 canary |

## 9. Delivery Roadmap

任何时刻只允许一个 `active` 里程碑，且只能是 write-capable。后续条目是有序 backlog，不授权并行写入。

| Milestone | 状态 | 用户可见结果 | 退出证据 |
|---|---|---|---|
| M0 文档体系归零 | candidate / human_required | 只有一个开发计划入口，没有历史文档竞争方向 | safe restore、unattributed/unauthorized=0、测试、独立 review、RootActor reconciliation、用户接受 |
| M1 运行基线对齐 | planned | 当前 checkout、DSH 登录修复、endpoint 和 overlay/source lock 说法一致 | 精确 source anchor、diff、锁/hash、auth discovery URL/cancel probe、无凭证泄露 |
| M2 Core Governance Canary | planned / entry blocked | 一个真实代码任务从 Objective 到不可伪造 FinalVerdict，并能解释 interruption/restart 副作用 | evidence contracts、单 executor、真实 diff/build/test、独立 review、revision/GateResolution、cold recovery |
| M3 DSH 多会话合同 Recon（M3-A） | planned / pre-gate | 冻结 DSH source、session lifecycle、插件/网关合同与非破坏性探针结果 | source/environment lock、合同和 probe evidence 完整；不扩展 DSH Core patch |
| M4 DSH 架构 HumanGate | planned / blocks M3-B/C/D | 人类确认 DSH Core 最小补丁、插件与网关的最终职责边界 | 产品、技术、安全、维护和回滚报告；明确批准，不批准则保持 DSH 单会话 |
| M5 DSH 最小多 Agent 实现（M3-B/C/D） | planned | Shadow、项目总控和 Worker 能以独立 session 协作，评审/辩论/仲裁可控运行 | transport ack/retry/dedup、lease/quota/recovery、项目隔离和真实 multi-session canary 全部通过 |
| M6 扩展与日常稳定化 | planned | 连续代码任务稳定；按需验证 Memory、PaperLab、GPT Web | 3 个代码任务；扩展能力各自独立 canary，不反向阻塞 Core |
| M7 发布收口 | planned | 新用户从干净 checkout 安装、验证、禁用和回滚 | 目标平台 gate、公共快照、独立 review、精确 local commit；发布另行批准 |

## 10. M0 Acceptance Closure

### 10.1 Acceptance Delta

| 字段 | 冻结值 |
|---|---|
| source | 2026-09-01 用户要求“全部删除，重新重构，摆脱历史包袱” |
| must appear | 根目录唯一 `PLAN.md`；一个 Current verdict；一个 Next Action；架构、基线、风险、路线图、验收和 HumanGate |
| must disappear | 旧 docs 体系、PRD/MVP/process/HANDOFF、Recon/stage/release/history 文档、旧 README/交接入口和旧路径依赖 |
| interaction | 新 Agent 只需自动入口→`PLAN.md` 即可找到唯一活动里程碑；运行时不从 prose 制造 canonical state |
| proof | 文件枚举、旧路径 scan、validator、测试、公共快照、恢复 probe、Git reconciliation、独立 review 或明确 human_required |

### 10.2 已完成

- 旧人类文档文件已经逐路径删除；
- `AGENTS.md` 已缩为唯一计划指针；
- 机器消费的 rule/schema/policy/prompt/template/fixture 保留为包内代码资产；
- 30 个仍有运行价值的负向 fixture 已迁入 owning package；
- 旧路径消费者、Bootstrap、运行时、CLI、validator 和测试已迁移；
- 全量 pytest、公开快照、真实 wheel smoke 和 diff check 已通过；
- 仓库外 ZIP 的 SHA-256、CRC、条目和关键 sentinel 已核对。

### 10.3 剩余验收

1. 从 operator 提供的精确 snapshot path 读取，不让模型拼接或猜测用户路径；
2. 验证 resolved snapshot 与预期 snapshot id/hash 一致；
3. 解压前逐一验证 archive member：拒绝绝对路径、drive/UNC escape、NUL、normalization 后的 `..` escape、restore-root 外 resolved path、未授权 symlink/special file、重复 canonical path，以及 case-insensitive 文件系统上的 case-fold collision；
4. 任何 member path escape 或 collision 都是 P0 hard stop，不进行部分解压；
5. 解压到经过边界检查的 repo 外临时目录；
6. 校验关键旧文档 sentinel 和预期内容，生成排序后的 operator-local manifest、稳定 evidence ID 与 SHA-256；该引用至少保留到独立 review 与 RootActor reconciliation 结束；
7. 将 ZIP entries、Git 删除、fixture MOVE 目标和当前 diff 分类为 `AUTHORIZED_CHANGE`、`EVIDENCED_PRE_EXISTING_CHANGE`、`UNATTRIBUTED_CHANGE`；已知违反 write-set 的变化另记为 `UNAUTHORIZED_CHANGE`；
8. 要求 `UNATTRIBUTED_CHANGE = 0` 且 `UNAUTHORIZED_CHANGE = 0`；无法归因项交给用户，不自动归类；
9. 清理临时恢复目标，不改当前 repo；operator-local manifest 引用按证据保留策略管理；
10. RootActor 复核实际 diff、manifest digest 与验证证据；
11. 用户决定接受或退回 M0。

不能补造“删除前 porcelain snapshot”。缺失的事前证据必须保持缺失，并由 ZIP/Git/当前事实做诚实的 post-action reconciliation。`UNATTRIBUTED_CHANGE = 0` 只表示所有当前相关 delta 都有可审阅来源解释，不表示已经观察到不存在的 pre-action worktree 精确内容。

### 10.4 M0 Exit Action — Clean Execution Baseline

这不是新的产品 milestone，而是 M0 被用户明确接受后的必要执行动作：

1. 由 `RootActor` 按 exact accepted change-set 构造一个本地逻辑提交，并保留 commit SHA、accepted paths、cached/commit delta reconciliation 证据；
2. 将当前原始 dirty/shared worktree 保留为受保护的 source state，不把它改造成“干净树”；
3. 不对原始 worktree 执行 `reset`、`clean`、`stash`、删除或覆盖用户变化；
4. 从 accepted commit 创建边界明确的 isolated clean worktree，记录其 path/ref、commit SHA 和 source identity 到 operator-local evidence；
5. M1/M2 默认只在该 isolated worktree 中执行；回到原始 worktree 必须重新经过 HumanGate；
6. isolated worktree 创建、权限或路径边界检查失败时立即 `HUMAN_REQUIRED`，不能通过修改原始 worktree“修复”。

### 10.5 验收命令

最终命令以当前 runtime 为准，至少包括：

```powershell
rg --files docs
rg -n "docs/status/HANDOFF.md|docs/PRD.md|docs/MVP.md|status-document-inventory.md|reviewer-index.md"
python -m pytest packages/control-plane/tests/test_docs_drift_validator.py -q
python -m pytest packages/control-plane/tests/test_obsidian_project_plan.py packages/control-plane/tests/test_conversation_intake.py -q
pwsh -NoProfile -File scripts/verify-public-snapshot.ps1
git diff --check
git status --porcelain=v2 -z --branch
git status --porcelain=v2 --branch
```

其中 `-z` 输出用于机器证据，非 `-z` 输出只供人阅读。期望：旧人类文档/旧路径为 0；允许的机器资产有 owning package；safe restore 达到 archive identity、structural integrity、safe extractability 和 semantic recoverability；`unattributed=0`、`unauthorized=0`；所有命令记录 exit code、关键输出和 `passed/failed/blocked`。

## 11. Milestone Contracts

### 11.1 M1 — Baseline Reconciliation

M1 只允许以下范围：

```text
current checkout
DSH login fix
actual endpoint
source/overlay lock
credential-safe auth discovery probe
```

进入 M1 时先冻结：

```yaml
m1_login_fix:
  source_type: unspecified
  source_sha: unspecified
  source_worktree: unspecified
  base_sha: unspecified
  source_patch_sha256: unspecified
  preimage_digest: unspecified
  postimage_digest: unspecified
  changed_files: unspecified
  tests: unspecified
  current_head_contains_fix: unverified
  auth_probe:
    phase_a_discovery:
      expected_url_host: auth.openai.com
      credential_submission: false
      account_authorization: false
      declared_side_effects: unspecified
      result: unverified
    phase_b_completion:
      human_gate: required
      result: unspecified
  cancel: unverified

dsh_source_lock:
  upstream_version: 0.1.1-rc.2
  package_lock_resolved_integrity: unspecified
  overlay_base_digest: unspecified
  overlay_patch_digest: unspecified
  post_overlay_source_digest: unspecified
```

M1 退出前必须预注册一个真实、可回滚、非演示性的 M2 Core canary；不能以 README、fixture 或空合同作为替代：

```yaml
m2_canary:
  status: unregistered
  objective: required_before_m1_exit
  target_package: required_before_m1_exit
  target_behavior: required_before_m1_exit
  candidate_issue_or_gap: required_before_m1_exit
  allowed_write_set: required_before_m1_exit
  forbidden_set: required_before_m1_exit
  expected_source_change: required_before_m1_exit
  deterministic_verification_commands: required_before_m1_exit
  rollback: required_before_m1_exit
  known_preexisting_failures: required_before_m1_exit
```

`status=unregistered` 或任一字段仍为 `required_before_m1_exit` 时，M1 不能退出。canary 必须冻结一个真实软件问题、明确目标包和预期源码变化，并说明已知预存失败；不得为了满足验收临时制造问题。

候选来源必须通过 Git history、worktree、patch 和实际 diff 解析。聊天里的“较新任务工作区”不是合法 anchor。若修复只有 dirty worktree，先形成受边界保护的 patch/evidence，不凭记忆重写。

M1 不做 DSH 多会话重构、PaperLab、GPT Web、UI redesign、memory redesign 或新的 multi-agent abstraction；只对齐当前 DSH checkout、登录修复和 source/overlay 事实。

退出条件：

- 新 Agent 能用确定命令定位修复来源、基点、changed files 和 tests；
- 当前 HEAD 是否包含修复有机器证据；
- DSH rc.2 version、resolved integrity、overlay base/patch/post-image digest 与当前树一致；
- Auth Discovery Phase A 生成/观察官方 `auth.openai.com` URL，不提交凭证、不授权账户；若该过程写 PKCE/session/Profile 状态，副作用必须进入 write-set；
- Auth Completion Phase B 只有用户通过 HumanGate 后才可执行，不是 M1 自动验收前提；
- cancel/restart 路径通过；
- 没有输出 token、cookie、Vault 路径或用户秘密；
- M1 diff 中没有顺带重构；
- `m2_canary` 的 objective、target package/behavior、candidate issue、allowed/forbidden write-set、expected source change、deterministic verification、rollback 和 known pre-existing failures 均已填实并可被独立 Reviewer 复核。

### 11.2 M2 — Core Governance Canary

M2 的目标是证明 DevFrame 核心产品可以稳定运行在 DSH 单会话执行基座上，并不依赖尚未验证的多会话扩展。

M2 entry blocked，直到以下合同已经进入 schema/runtime 和负向测试，而不只存在于 PLAN：

```yaml
evidence_revision:
  base_commit: required
  head_commit: required
  diff_sha256: required
  subject_digest: required
  commands: required
  outputs: required

review:
  evidence_revision_id: required
  subject_digest: required
  review_input_digest: required
  participant_id: required
  run_id: required
  capability: read_only

final_verdict:
  evidence_revision_id: required
  accepted_review_id: required
  gate_resolution:
    state: not_required | accepted
    gate_id: null | HumanGateId

accepted_commit_invariant:
  patch_format: git-binary-full-index
  reviewed_diff_sha256: required
  cached_diff_sha256: required
  commit_delta_equals_reviewed_accepted_delta: true
```

同时预注册 canary 选择，不以 README、空 fixture 或纯说明修改冒充真实产品证明：

```yaml
m2_canary_selection:
  real_user_value: true
  source_change_required: true
  deterministic_native_verification: true
  network_required: false
  credentials_required: false
  reversible: true
  write_set_small: true
  known_preexisting_failure: false
```

冻结的真实、低风险、可回滚软件任务必须包含：

1. 用户 Objective 和明确完成条件；
2. 精确 TaskSpec、write-set、forbidden-set 和预算；
3. 一个 canonical Run 和一个真实 executor；
4. 对真实源码产生非空、可审阅 diff；
5. 使用项目原生 build/test/lint；
6. EvidenceRevision 绑定 base/head、candidate diff SHA-256、write-set/verification-set subject digest、命令、exit code 和关键输出；
7. 不同 participant/run 的只读 reviewer，绑定可重放的 review-input digest；
8. reviewer 发现 P0/P1 时进入 revision，不得直接 accepted；
9. 需要新权限或不可逆动作时进入 HumanGate；
10. FinalVerdict 只能引用当前 EvidenceRevision、accepted review 和合法 GateResolution；
11. 一个组合恢复 canary：真实 write-capable Run 启动→执行中 interruption/cancel→controller/runtime restart→副作用 reconciliation→无重复写→确定性 resume 或 safe terminate；
12. 最终 reconciliation 证明没有 write-set 外变更，并且 cached/commit delta 等于 reviewed accepted delta。

不为触发 revision 故意让 Worker 写错。真实 canary 可以一次通过；`review requests changes → new EvidenceRevision → old Review stale → new Review required` 由确定性 contract test 证明。

Core MVP 退出 Gate：

```text
real task passed
native verification passed
independent review passed
subject/review-input/stale/self-review negative tests passed
interruption + restart reconciliation passed
unattributed changed paths = 0
unauthorized changed paths = 0
cached/commit delta == reviewed accepted delta
FinalVerdict references exact accepted EvidenceRevision, Review and GateResolution
```

PaperLab、GPT Web、DSH 多会话扩展、多 Provider 和跨项目记忆均不在 M2 write-set。

### 11.3 M3 — DSH Multi-Session & Thin Gateway Contract

#### Acceptance Delta

| 字段 | 冻结值 |
|---|---|
| source | 用户明确废弃 CodexHost，后续改造目标固定为改造后的 DSH Harness |
| must appear | 多个独立 DSH session 可受控创建、通信、取消、恢复；Shadow、项目总控、Worker 的边界可验证 |
| must disappear | 对闭源商业 Host 的兼容依赖；把业务流程下放到 DSH Core/网关；第二 Task/Run/Evidence/Gate/Verdict authority |
| interaction | `spawn_session`、`send_message`、inbox 拉取、ack/retry、取消、超时、死信、重启恢复和项目隔离 |
| proof | DSH source/overlay lock、最小 Core patch、插件合同、opaque gateway probe、配额/恢复/负向 canary |

#### Ordered slices and HumanGate sequencing

M3 是能力总合同，但不允许作为一批不可拆分的写入任务执行：

- `M3-A`：DSH source lock 与稳定 session lifecycle；只做 Recon、合同冻结和 non-destructive probes，可在 M4 前执行；
- `M3-B`：opaque message transport，以及 ack/retry/dedup；只有 M4 HumanGate 通过后可实现；
- `M3-C`：lease/quota/timeout/dead-letter/recovery；只有 M4 HumanGate 通过后可实现；
- `M3-D`：project/session isolation 与组合 multi-session canary；只有 M3-B/C 通过后可实现。

每个 slice 必须有独立 Acceptance Delta、allowed write-set、forbidden-set、focused/negative tests、EvidenceRevision 和独立 Review；前一个 slice 未被接受，后一个 slice 不得开始。`M3-A` 不能修改 DSH Core；任何超出 Recon、合同和非破坏性探针的 Core patch 都必须先经过 M4 HumanGate。M3 整体只有在 `M3-D` 通过后才可视为完成。

#### DSH source-lock entry gate

进入 `M3-A` 前必须冻结；`M3-B/C/D` 还必须等待 M4 HumanGate：

```yaml
dsh_source_lock:
  source_type: required
  upstream_or_local_origin: required
  release_label: dsh-v0.1.1-rc.2
  base_sha: required
  overlay_manifest_sha256: required
  overlay_patch_sha256: required
  post_overlay_source_sha256: required
  patch_scope: minimal-core-callbacks-only
  source_relationship: required

environment_lock:
  os_build: required
  dsh_version: 0.1.1-rc.2
  dsh_build_or_commit: required
  python_version: required
  node_version: required
  package_lock_sha256: required
  overlay_runtime_config_sha256: required
```

`base_sha`、overlay digest、environment lock 或 source relationship 任一缺失，M3 保持 blocked；不能只改版本号而不重新审查 source-only overlay。

#### Ownership Matrix

持久化能力不等于治理权威。DSH 只拥有单 session 内部执行事实，薄网关只拥有传输运行事实，DevFrame 只拥有项目治理事实，Obsidian 只拥有笔记内容事实。

| 数据 | Source of record | class | 允许内容 | 明确禁止 |
|---|---|---|---|---|
| ProjectObjective / Milestone / TaskSpec | DevFrame | AUTHORITATIVE | 目标、范围和验收 | DSH/网关复制并修改状态 |
| Run / EvidenceRevision / Review / Gate / FinalVerdict | DevFrame | AUTHORITATIVE | canonical 生命周期与证据 | 第二份接受状态 |
| DSH session identity / turn-step / tool event | DSH | AUTHORITATIVE | session 内部事件和执行结果 | 项目治理状态 |
| session lease / queue / quota / timeout / dead-letter | 薄网关 | AUTHORITATIVE | 传输和资源运行元数据 | 解析或改写业务 payload |
| message payload | 发送方/接收方 DSH event log | REFERENCE | 不透明的 MessageEnvelope | 网关依据内容路由业务流程 |
| Shadow user-memory notes | Obsidian `user-memory/` | AUTHORITATIVE | 用户记忆和偏好原文 | 非 Shadow 直接写入、运行时状态副本 |
| project notes / artifacts | Obsidian `project/{project-id}/` 或项目工作树 | REFERENCE | 项目知识和产出 | 取代 DevFrame canonical state |
| display/read projection | DSH plugin / client | EPHEMERAL_PROJECTION | digest-bound 查询结果 | 生成 accepted 状态 |
| credentials | credential owner | FORBIDDEN | opaque reference only | token、cookie、Vault secret |

必须提供 schema 和恶意 mapping 负向测试，拒绝跨项目 `session_id`、伪造 `run/evidence/finalVerdict`、凭证字段、重复消息和越权写入。

#### Prompt vs runtime boundary

- Prompt 可以决定任务拆解、是否请求审查、是否展开辩论、何时提出仲裁以及复盘内容；
- DSH Core 必须硬性保障 session identity、turn 生命周期、工具权限、沙箱和 append-only 事件；
- 薄网关必须硬性保障 session 数量、消息大小/数量、总预算、并发 lease、超时、取消、ack/retry、幂等、死信和崩溃恢复；
- DevFrame 必须硬性保障 write-set、禁止自审、Evidence digest、HumanGate 和 FinalVerdict 绑定；
- 到达轮次/资源阈值时，系统可以发出 `human_required`、暂停或安全终止，但不能依赖 Agent 自己记得停下。

#### Multi-session canary

1. Shadow 为两个隔离项目创建项目总控 session；每个项目总控再创建受配额限制的 Worker session；
2. 所有 session 获得唯一、不可复用且可追溯的 `session_id`，记录 parent、project、participant 和 policy；
3. `send_message`/inbox 支持顺序、ack、幂等重试和明确的 at-least-once/去重语义；
4. 未知目标、重复消息、过大 payload、超额 spawn、消息风暴、超时和死信均失败关闭；
5. 网关在不理解 payload 业务含义的情况下完成投递、限流和恢复；opaque payload probe 必须通过；
6. 在消息写入前后、ack 前后和 session 崩溃点执行 restart/reconcile，不能重复产生不可逆副作用；
7. 评审、辩论和仲裁使用 Prompt/Agent 语义试运行，但轮次上限、资源预算和人工升级由运行时硬约束；
8. 多项目并行时，user-memory、project namespace、消息和证据不能串线。

#### Go / No-Go

`GO` 必须同时满足：

- 产品 reviewer 通过 DSH Acceptance Delta；
- 技术 reviewer 无 P0/P1；
- DSH Core patch 仅包含必要外部回调，不含 Shadow/评审/仲裁业务逻辑；
- 网关 payload 保持 opaque，schema、权限、配额、恢复和负向测试通过；
- DSH source/environment lock、Ownership Matrix、真实多 session canary 和回滚通过；
- 用户记忆与项目知识隔离，未授权写回不可达。

否则 `NO-GO`：保持 DSH 单会话能力，只交付已验证的插件/adapter contract，不因多 Agent 演示效果扩大 Core 或网关职责。

#### Pre-registered performance budget

以下阈值必须在看到 candidate 结果前由基线 probe 和用户体验目标冻结：

```yaml
performance_budget:
  baseline_timestamp: unspecified
  threshold_timestamp: unspecified
  cold_start_p95_ms: unspecified
  first_message_added_latency_delta_p95_ms: unspecified
  cancel_ack_p95_ms: unspecified
  idle_rss_delta_mb: unspecified
  resume_success_target: unspecified

measurement_protocol:
  host_hardware: unspecified
  os_build: unspecified
  dsh_build: required
  dsh_source: required
  gateway_source: required
  provider_model: unspecified
  sample_count: unspecified
  warmup_count: unspecified
  cold_start_definition: unspecified
  first_message_start_event: unspecified
  cancel_ack_event: unspecified
  direct_dsh_session_baseline: required
```

阈值 timestamp、sample count 和测量事件定义必须早于 candidate measurement timestamp；不得测完后重新解释“可接受”。消息首延迟使用 `gateway-mediated DSH path - same DSH direct session baseline` 的相对增量，避免把 Provider 网络抖动误算为网关开销。

## 12. Execution Protocol

每个非平凡 slice 必须按以下顺序：

1. 读 Current verdict、Next Action、唯一活动里程碑和风险；
2. 核验 repo root、HEAD、branch/upstream 和 CodeGraph 状态；
3. 对未来 destructive slice 在动作前冻结 porcelain v2、tracked/untracked inventory、目标清单和恢复来源；
4. 对成熟能力完成 Recon 和开源复用判断；
5. 冻结一份小 Acceptance Delta；
6. 定义 write-set、forbidden-set、rollback、hard stop 和验证命令；
7. 先构造能暴露问题的 RED 或真实 probe；
8. 做满足目标的最小实现，不重构相邻代码；
9. focused 验证后再按风险运行 affected/broad gate；
10. 产品审阅先于技术 P0–P3 审阅；
11. 由 RootActor 对真实 diff、subject digest、测试、生成物、风险和用户结果做 reconciliation；
12. 只有全部通过才更新本文件的状态和 Next Action；
13. 若形成 accepted slice，RootActor 构造 exact accepted change-set；仅在 path 全部 delta 都已接受时按 path stage，mixed-origin path 使用 hunk/blob-level staging 或 hard-stop；核对 cached diff 与 reviewed diff 等价后创建一个本地逻辑 commit；
14. 任何远程、发布、部署、登录或全局配置动作另行请求。

执行顺序硬约束：M0 的 `snapshot_ref/path` 无法由 operator 或授权 runtime/operator interface 确定性解析时立即 `HUMAN_REQUIRED`；M0 明确接受后先执行 10.4 的 clean execution baseline，再进入 M1。M1 退出前冻结真实 M2 canary；M2 完成前不进入 DSH 多会话实现。DSH 路线按 `M3-A Recon/contracts → M4 HumanGate → M3-B/C/D implementation` 顺序推进，任何 slice 未完成独立 Review、EvidenceRevision 和 accepted reconciliation，不得开始后续 slice。

### 12.1 Baseline 与恢复纪律

- 面向脚本的状态使用 `git status --porcelain=v2 -z --branch`；非 `-z` 版本只用于人类阅读，不作为唯一机器证据；
- tracked/untracked inventory 应使用 NUL-safe 或等价的路径安全格式；
- binary patch 必须由 Git 直接写出，不能经过可能改编码/换行的文本 pipeline；
- reviewed accepted diff 与 cached diff 必须使用同一 write-set、同一 base 和 `--binary --full-index` 语义生成，比较 SHA-256；只比较文件路径或 diff 摘要不构成等价证明；
- 精确 accepted-slice Git gate 必须证明实际 cached/commit delta 与已审阅变更等价；
- baseline/evidence 可进入 operator-local 结构化存储，并用 stable ID/SHA-256 从 PLAN 或 Run 引用，但不能形成公共仓库第二计划权威；
- 任何事后重建必须标记 `post-action reconciliation`，不得冒充事前 snapshot；
- 临时恢复目录必须先验证 resolved path 在 repo 和用户数据目录之外；解压前还必须验证每个 archive member 的 path、type、duplicate 和 case-fold collision，再执行恢复或清理。

### 12.2 Bootstrap Evidence Storage

在 M2 runtime evidence contract 完整实现并重新验证之前，M0/M1 bootstrap evidence 统一落在一个 operator-local evidence root，不写入公共仓库，也不创建第二份 PLAN：

```text
<operator-local-evidence-root>/<run-id>/
  manifest.json
  commands.jsonl
  source-status.bin
  candidate.patch
  evidence.json
  review.json
  reconciliation.json
```

PLAN 只记录稳定的 `evidence_ref` 与 `manifest_sha256`，不记录绝对路径、token、cookie、Vault 路径或其他秘密。后续 Reviewer/RootActor 必须能通过已授权的 operator/runtime interface 按 stable reference 重新读取；无法解析或 digest 不匹配就保持 `HUMAN_REQUIRED`，不得从历史对话或任意用户目录猜测。

### 12.3 证据要求

每个 batch 报告：

- 目标和冻结边界；
- 修改文件与关键代码路径；
- 运行命令、exit code、时间和关键输出；
- EvidenceRevision 对应的 base/HEAD、diff SHA-256、subject digest 和 review-input digest；
- 生成物精确路径或受隐私保护的 operator-local reference；
- P0/P1/P2/P3 findings；
- `passed/failed/blocked/human_required` verdict；
- 已知缺口和建议复查焦点。

P0/P1 修复必须至少有一个真实生产路径测试或 probe。逻辑碎片测试只有在生产路径无法安全运行且明确记录 blocker 时才可作为补充。

## 13. Human Gates

以下动作必须得到当前用户明确批准：

- 接受或退回 M0，以及任何无法由恢复证据覆盖的删除；
- 生产部署、迁移、真实数据写入或真实 Vault 批量访问；
- 登录、凭证、付费、账户权限和第三方写权限；
- 全局 Skill、hook、MCP、Agent 或系统配置安装；
- push、PR、merge、release、历史重写和跨主机 handoff；
- 启用未被 DSH PolicyDecision/HumanGate 包裹的 unattended 或等价 full-access 执行；
- 扩大 DSH Core 补丁范围，或把业务流程下放到 DSH Core/薄网关；
- mixed-origin path 无法安全构造 exact accepted change-set 时的 staging/commit 决定；
- 降低测试、删除仍保护当前行为的断言或忽略 P0/P1；
- 对 `unspecified` 性能阈值、source relationship 或登录来源做产品性猜测。

## 14. Deferred Backlog

以下工作不能抢占 M0–M4：

- PaperLab 生产端点、真实全文、Writer 和自动修订；
- GPT Web 真正的双向 MCP roundtrip；
- 跨项目长期记忆 promotion；
- 自动 CodeGraph 刷新、写回和可编辑知识画布；
- 多机器 Agent、云同步、多租户和团队权限；
- 插件/Skill 市场、计费和 Sites；
- 复杂自动模型故障转移和成本优化；
- T3/RD-Code 自定义客户端复活；
- 新浏览器 runtime、第二桌面壳或第二任务数据库。

## 15. Documentation Policy

1. 只有根目录 `PLAN.md` 可以描述当前开发路线、Current verdict、Next Action、未关闭风险、里程碑状态和产品性 go/no-go。
2. `AGENTS.md` 只保留自动入口和不可省略约束，不复制本计划。
3. M0–M6 不再创建 PRD、MVP、process、HANDOFF、roadmap、Recon Receipt、reviewer index、status inventory、release note 或阶段报告 Markdown；当前 `docs/` 零文件 validator 保持有效。
4. 新产品决定直接修改本文件对应章节；历史只在 Decision Log 保留一行，详细差异由 Git 负责。
5. Evidence、Run、Review 和 FinalVerdict 进入运行时结构化存储，不进入公共文档。
6. 机器消费的 rule/schema/policy/contract/prompt/template/fixture 必须归属于具体 package，并通过测试；它们不调度项目，也不能覆盖本文件。
7. 外部研究只把已采纳结论、版本、风险和 go/no-go 写入本文件，不复制报告或建立研究文档库。
8. 本文件不记录真实 token、用户 Vault、绝对用户路径或本机秘密；operator-local evidence 用稳定 ID/hash 引用。
9. 本文件应保持可从头阅读；历史增长时覆盖旧状态、压缩 Decision Log，不追加无限流水账。
10. M7 若产品进入已接受发布阶段，可经 HumanGate 创建面向已接受版本的 README、安装、CLI/API、安全和故障排查 reference；这些用户文档不得包含 roadmap、Current verdict、Next Action、未接受能力或独立状态机，冲突时 PLAN 与 runtime contract 为权威。届时必须在同一 accepted slice 中精确调整 `docs/` validator，不能提前放宽。

## 16. Decision Log

| 日期 | 决定 | 状态 |
|---|---|---|
| 2026-09-01 | v2.1 采用三轴状态、GateResolution、Evidence subject/review-input digest 和 RootActor 权限合同 | defined / implementation required before M2 |
| 2026-09-01 | dirty-tree Git 生命周期从 accepted paths 升级为 exact accepted change-set；mixed-origin path 禁止整文件 stage | P0 boundary |
| 2026-09-01 | M0 以 `unattributed=0`/`unauthorized=0` 诚实收口，并增加 ZIP member 安全与 operator-local manifest digest | active |
| 2026-09-01 | 原 M3 兼容性路线要求 source/environment lock、原生差分和可重放性能测量 | superseded |
| 2026-09-01 | 唯一开发权威不永久禁止用户文档；仅 M7 accepted release 可创建非权威 reference | deferred HumanGate |
| 2026-09-01 | 外部批改的战略部分采纳：Core Governance Canary 提前到 DSH 多会话扩展之前 | accepted plan change |
| 2026-09-01 | M0 已执行，不补造事前 preflight；只补隔离恢复与诚实的 post-action reconciliation | active |
| 2026-09-01 | 外部 Host 版本、tag 和 audited SHA 的兼容性路线不再作为项目入口 | superseded |
| 2026-09-01 | Reviewer 独立性升级为 participant/run/read-only/revision 合同和负向测试要求 | planned verification |
| 2026-09-01 | Core MVP P0 收敛为单执行器真实软件治理闭环；PaperLab/GPT Web/多 Host 降为扩展验证 | accepted plan change |
| 2026-09-01 | 删除旧文档体系，以根 `PLAN.md` 作为唯一开发权威；机器消费文本归代码资产 | candidate / human_required |
| 2026-09-01 | DSH 是唯一底层改造目标；Shadow/总控/Worker 通过 DSH session 扩展实现 | conditional-adopt |
| 2026-09-02 | v2.3 采纳执行性修订：snapshot hard stop、M0 clean baseline、bootstrap authority、M2 真实 canary 预注册、M3-A/M4/M3-B/C/D 顺序和单一 operator-local evidence root；设计冻结到 M2 | accepted plan change |
| 2026-09-02 | CodexHost 路线正式废弃，原因是 Codex 本身不开源；不再作为候选、兼容目标或 fallback | accepted direction |
| 2026-08-31 | DSH/Codex 登录兼容缺陷据历史上下文已修复，但来源和当前 checkout 仍未对齐 | candidate / unanchored |
| 2026-08-30 | DSH 继续锁定 rc.2 和 source-only overlay；升级不得只改 lock | accepted boundary |
| 2026-08-29 | CodeGraph 和项目记忆只能作为显式、有界、不受信任的上下文来源 | accepted boundary |
| 2026-07-20 | Obsidian 是用户拥有的可见载体，不是第二 Task/Run/Evidence/Gate authority | accepted boundary |
