# Agent Note: Candidate full-chain dispatch acceptance design

Status: proposed

[English](2026-09-07-candidate-full-chain-acceptance-design.md) | 中文

## Problem

候选派发旅程的每条缝都各有套件证明——派发引擎及其 `agent_dispatch` consumer（单元 + 真实 Loader 组合 spec）、持久任务 ack（日志折叠 + 重启证明）、lead 指派落盘波（冷恢复折叠）、审查门（`AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` 拒绝矩阵）、DevFrame 证据日志、project-controller 任务机（`planned → assigned → developing → reviewing → submitted → integrated`）。没有任何套件证明的是**一次真实候选部署上的完整旅程**：一个 controller 会话派发一个 lead，lead 派发**两个相互独立的 Worker 任务、各占独立 worktree、真实并发**，每个 Worker 经真实 required checks 交付，lead 独立审查，任务 submit，controller 经 controller 专属合并门 integrate，受控重启后每条持久事实重推导成立。V1.2 点名的缺口：没有正式运行消费者，产品无法自主闭环。该消费者已派 A2（agent_dispatch → `assigned`/`developing` → Worker 交付+真实 checks → `reviewing` → 独立 lead `recordReview` → `submit` → 既有 `integrate`，复用 `AgentEvidenceJournal`，禁止预制造 `passed`/`submitted` 记录，不重写 controller/Git gate）。本 note 设计将验收该消费者交付的**测试与证据面**；本身不实现。

两个约束塑形本设计。其一，`c-verify-evidence.md` §8 记录的验收范围边界：opt-in overlay 只走显式候选命令，永不涉及默认 3080 bundle，scaffold `composeEntries` 场景永不冒充 shipped-overlay 验证。其二，工作清单的三层证据纪律：只有实际响应层可证 provider；预置或自报状态证明不了任何事。

## Proposal

### 部署面

全链经 harness 已验证的候选命令启动（`apps/cli/tests/cordis-example-overlay.e2e.ts`）：真实源 CLI、显式根级 `--patch`、隔离 harness home——example overlay（钉 3081 webserver + tool-cordis）加私有 DevFrame profile 层（`packages/experimental/devframe-profile/cordis.patch.yml`，六行层级栈）。第三个**闭环 overlay**（测试夹具 yml，绝非默认改动）收口 shipped overlay 有意留空的配置：

- **替换** `agent-hierarchy` 行整份 config（patch 语义）：controller 与 lead 保持 shipped 继承面加 `agent_dispatch`；**worker `inheritedTools` = 最小可行动集**——平台 shell（经平台缝取 `pwsh`/`bash`）加 `read`、`write`、`edit`、`glob`、`grep`。够完成文件交付任务；无派发工具（restrict 下本就不可见）、无 web/goal/worktree 工具。
- 预分配 lead 身份：controller 派发 lead 时点名 `childId: 'candidate-fullchain-lead'`，同 overlay 设 `leadPluginScopes: { 'candidate-fullchain-lead': ['candidate-fullchain'] }`——每次 Worker 派发必须点名的批准范围。
- 插入/patch **project-controller 行**（owner：A2 consumer 携模型面动作；overlay 只保证服务挂载且 `requestBudget: 4`、`maxActiveTasks: 2`——并发窗依赖的机器中性默认值）。
- 注册**批准的 required-checks 清单**（file store），证据请求携带其 digest；checks 保持机器中性（任务 worktree 内 `git diff --check` + 工件存在性探针），真实子进程执行面处处可跑。

### 模型面：wire 级回放，零真实凭据

模型回合（controller、lead、两 Worker）**在 wire 边界脚本化**：harness 起一个本地回放服务器，说 provider wire 协议；隔离 home 的 provider 路由指向它。其余全部真实——CLI 进程、组合、worktree 与 git、日志、任务机、锁、重启。验收因此确定、免凭据、可 CI，且模型可见⟺可记录天然满足（回放回合产生普通会话事件）。之后一轮**授权真实模型回合**（一次总控通知=一轮，凭据仅经 refs 提取进进程环境）用真实 provider 重放同场景，作为运行层证据；其交叉核对约束 wire 形状漂移。

### 场景与证据窗

每步列出断言读取的可观察面（会话日志事件、域表、文件产物）：

1. **启动**：3081 readiness 行；`pluginInventory/list` 显示两个 patch 全部行 active（既有 harness 面）。
2. **Controller 回合**：创建 worktree ×2（独立分支）、`agent_dispatch` 派发预分配 lead。证据：workspace 下注册的 worktree 行；持久 agent binding（role `lead`、parent=controller）；`devframe-lead-role-landing` 追加的 **`devframe/role-policy` 落盘事件**（冷恢复折叠重推同一 lead 指派）；`agent/created` 发布。
3. **Lead 回合**：`agent_dispatch` ×2——两个独立 `taskId`、两个 worktree、`pluginId: 'candidate-fullchain'`。证据：两个子会话（记录 parent/role/task/plugin）；**各 worktree 单写锁由其子持有**；briefing 严格后于发布排队；ack `briefed` → `claimed`。
4. **并发窗**（V1.2 点名的证明）：两 Worker 的认领回合真实重叠。证据取自日志，绝不取自 sleep：设每 Worker 认领时刻 `c_i`、终态 `turn/end` 时刻 `t_i`，断言 `max(c_A, c_B) < min(t_A, t_B)`。佐证面：`project_tasks` 同时显示两任务 `developing`（`maxActiveTasks: 2` 恰容此态）；请求预算全局达 ≥ 2 笔 charged 且扣费持久串行（两笔收据、无丢失更新）。
5. **Worker 交付 + 真实 checks**：每 Worker 回合在自己 worktree 内完成文件工件；consumer 以 `AgentEvidenceJournal.recordVerification` 支撑 `developing → reviewing`——批准清单的**真实子进程执行**，结果以一条 `devframe/verification` 事件追加（status passed、记录已执行 checks）。证据：各 worktree 内工件字节；verification 事件绑定正确 `GoalResultBinding`/`snapshotId`；派发 ack 读得 `terminal` + `completed: true` + `durable: true`。
6. **独立 lead 审查**：`recordReview` 追加一条 `devframe/review`（decision pass）——审查门经投影目录对已落盘 lead 权威交叉授权，无任何角色自报字段。证据：review 事件 `reviewerSessionId` = lead 会话；折叠后每被审任务恰一条 review。
7. **Submit → integrate**：consumer 走 `reviewing → submitted`；controller（且仅 controller——binding 查找拒绝他人）经 `requestMainTreeMerge` 铸合并 marker，`integrate` 消费之：任务 `integrated`。证据：`project_tasks` 行状态；已消费 marker 重放 → `PROJECT_CONTROLLER_MARKER_INVALID`；lead 铸 marker 尝试 → controller 专属拒绝。
8. **受控重启**：步 6 之后（integrate 之前）在编排静止点 SIGTERM CLI 并以同命令/同 home 重启。证据：`project_tasks` 逐字恢复；DevFrame 投影自恢复日志折叠出同一结论（落盘 lead 指派、verification、review 全在，与重启前折叠零差异）；`taskAck` 自子日志重推导仍读 `terminal/completed/durable`；worktree 锁恢复或干净重绑。integrate 在重启后的进程内完成。

### 门禁与失败断言

每个具名拒绝恰断言一次、带稳定码，证明门禁非「未被触发」：`DISPATCH_WORKTREE_UNREGISTERED`（外来 worktree id）、`DISPATCH_HIERARCHY_DENIED`（lead 派发越批准范围）、worker 对 `agent_dispatch` 不可见（工具缺席，非仅被拒）、policy 前落盘（fail-loud）、Worker 会话审查 → `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` 且零事件追加、伪造或重放 marker → `PROJECT_CONTROLLER_MARKER_INVALID`、非法迁移（如 `assigned` 态 `submit`）→ `PROJECT_CONTROLLER_ILLEGAL_TRANSITION`、降级 ack 面（无 flush barrier 参与即 `durable: false` + `degraded: true`）以专属探针钉死。

### 真实 vs 预置判据

| 面 | 真实（由何证明） | 脚本化（允许） | 禁止 |
| --- | --- | --- | --- |
| 进程与组合 | 真实 CLI 子进程、真实 Loader 启动 | — | scaffold `composeEntries` 替身 |
| 模型回合 | 其产生的会话事件 | wire 回放响应 | 无实际响应层即宣称 provider 身份 |
| Worktree 与锁 | 真实 git worktree、registry 行、单写绑定 | — | mock 锁状态 |
| 证据与状态机 | 真实日志、真实子进程 checks、真实 `project_tasks` 表 | — | 预制造 `passed`/`submitted`/`integrated` 记录 |
| 并发 | 日志导出的墙钟窗 + 预算扣费 | — | sleep 排序的伪串行 |
| 重启 | 真实 SIGTERM + 重启、恢复折叠 | — | 内存续跑宣称 |
| 运行层回合 | 一次授权真实 provider 回合 | — | 把回放跑当 provider 证据 |

SDK 预置 lead/worker 会话（scaffold 身份、进程内脚本回合）仍是其所属套件的有效单元证据，但**不得**顶替步 2–8；候选链的子会话必须经真实派发入口创建并携带持久 binding。

## Alternatives considered

- **纯真实模型全链。** 每回合由真实 provider 驱动。不作为主门：不确定、耗凭据、不可 CI；仅保留为一轮授权运行回合，唯一职责是交叉核对 wire 形状。
- **进程内 scaffold 场景（§8 风格）。** 复用 web 车道夹具机制。拒绝：边界明确禁止以 scaffold 验证 shipped overlay——`composeEntries` 从不加载 example bundle，且预置挂载的子会话会冒充派发子会话。
- **无脚本响应的提示驱动工具链**（让真实模型自行决定每次工具调用）。即便授权轮也拒绝：验收需要精确的工具调用序（两次派发、一次审查、一次铸 marker）可复现；真实轮可变其措辞，但场景经 briefing 提示钉住其工具调用。
- **测试进程直调状态机服务**，绕开模型面 consumer。拒绝：那会绕过本证据面为其验收而存在的对象；测试只走 wire 面（HTTP RPC + 回放模型回合），与真实客户端同路。

## Acceptance criteria

单一 vitest 运行——从启动到重启——exit 0 即设计被接受实施：全部 patch 行挂载；两 Worker 重叠窗由日志时间戳满足；两条 verification 事件携带真实已执行 check 结果；lead 审查获授权并入折叠；两任务经 marker 消费达 `integrated`；重启后折叠在持久事实上逐字节同一；每个具名拒绝以稳定码断言；降级 ack 探针钉死。真实 provider 轮另行 exit 0，其实际响应层按工作清单三层格式记录。运行全程不预制造任何终态，措辞永不宣称默认 3080 激活。

候选组合必须通过正式 host 构造入口复用已有 approved-checks store、完成所有权守卫、集成回执与真实停止适配器。冷 Loader 必须在模型回合前注册公开命令；命令 RPC 通过 Agent wire resolver 恢复原 Controller。重启用例检查冷 stop 不计费模型请求，公开 resume 放行一次原生 goal-round 请求，无需额外用户 prompt，也不重复绑定。此回放证据不代表真实 provider 已完成闭环。

## Risks

- **新夹具面**：wire 级回放服务器尚不存在（web 车道为进程内回放）；这是唯一真正的新建件，其协议覆盖须匹配真实 provider 流式形状——由授权真实轮交叉核对兜底。
- **重叠窗脆弱**：高负载宿主上墙钟窗可能收窄。窗口源自持久日志时间戳（绝不 sleep），且场景把第二次派发排进首 Worker 的长回合内，窗口足够宽；残留抖动由 CI 重跑策略处理。
- **重启点选择**：回合中途 SIGTERM 可能触发 flush-barrier 降级面、搅浑重启 diff。场景在脚本化静止点（回合之间）重启；降级面由专属探针覆盖而非 happy path。
- **词汇漂移**：consumer owner（A2）落地前可能更名动作或状态；本设计只钉 `project-contracts`/`project-controller` 的 `TaskState` 并集与稳定错误码，实施时须对照已落地 consumer 复核每个具名面。
- **所有权边界**：本 note 只提议测试/证据面。运行消费者（A2）、controller/Git gate（V1.2）、shipped overlay 唯一写入权（总控）各归其主；闭环 overlay 是测试夹具，不得泄漏进任何 shipped 默认。
