---
description: S4 语义缺口设计切片——五基础插件（session-identity/agent-hierarchy/project-controller/agent-evidence/agent-reliability）的模型可见工具/命令面设计提案（p/accept 工作树）。
---

# S4 工具面设计提案：五基础插件的模型可见工具/命令面

- 状态：设计提案（未实现；本文不改任何 src，不标记任何 AT 用例为已通过，全部 `AT*` 维持 `not_run`）。
- 输入来源：[gaps.md](gaps.md) S4 条目（五包均为纯服务，"controller 任务板命令、evidence 回执入口等会话级工具"待产品波次，S4 归 P04/P05 原组长）；[详细设计第 1 部分](../../../docs/detailDesign-part1.zh.md)（`project_verify`/`project_review`/`project_complete` 与 `/project` 人工命令旅程的设计权威）；[第 2 部分](../../../docs/detailDesign-part2.zh.md)（Shadow 四工具，P21-S 专属，本文仅做冲突规避）；[第 3 部分](../../../docs/detailDesign-part3.zh.md)（memory 三工具，P21-M 专属，明确排除）；[验收矩阵](../../../docs/testAndAcceptance.zh.md#part1) AT1-01..11；[插件化登记表](../pluginized-round-registry.md) §6b P22 矩阵（AT→责任插件既有绑定）。
- 基线：`p/accept` @ `1b5289e9b3`；五包服务面按源码逐包核实（registry.ts / service.ts / controller.ts / ledger.ts / reliability service.ts）。
- 口径：模型面 = 一切到达模型请求的内容（`ctx.tools` 会话级工具、guard 拒绝文本、系统提示节），受"模型可见 ⟺ 会话日志可重建"约束；宿主面 = 仅人/宿主可达的面（`ctx.commands` 命令注册表、pre-step 接线、生命周期调用）。判定沿用 gaps.md：语义缺口归原组长定稿，不代改。

## 1. 范围与排除

范围内：session-identity（P01）、agent-hierarchy（P02）、project-controller（P04）、agent-evidence（P05）、agent-reliability（P06）五包的模型可见工具/命令面设计，以及承载它们的集成切片归属。

明确排除（另有归属，本文只登记命名保留与依赖方向）：

- Shadow（P21-S，L-Shadow）：`project_open`/`project_send`/`project_status`/`project_stop` 四工具、跨根投递持久化（received ≠ completed）、Shadow 模型面白名单。
- Memory（P21-M，L-Memory）：`memory_search`/`memory_read`/`memory_append`、Vault 文件面、回执落日志接缝（gaps.md S3）。
- agent-reliability stop 对账身份跨重启的 host 持久化语义（gaps.md S5）——归 P06 原组长，本文 §4.5 只引用。
- 原生 Team 工具族、`worktree_*` 工具族、基础工具族：不新增、不改名、不重复设计。
- AT1-07 的 profile 组装与成员上限、AT1-11 效用试用：P22 矩阵既有归属（profile/L-Foundation、W4），不进本切片。

## 2. 命名空间冲突检查

对照 [tool-catalog](../../../docs/tool-catalog.zh.md)（全部现存工具节）、`tool-agent-team` 注册面（`spawn_teammate`、`team_task_*`、`followup_task`、`send_message`、`wait_agent`、`interrupt_agent`、`list_agents`）、`dsh-tool-worktree`（`worktree_create/list/status/remove/prune` 五工具）、P21-S/P21-M 保留名、命令注册表现状（现存注册命令：`goal`、`compact`、`feedback`、plan-mode、session-log-export、permission-presets 族）逐名核对：

| 候选名 | 判定 | 依据 |
| --- | --- | --- |
| `project_verify` / `project_review` / `project_complete` | 空闲 ✅ | detailDesign-part1 拟名；tool-catalog 无；P21-S/P21-M 不占用 |
| `project_task_list` / `project_task_get` / `project_task_move` | 空闲 ✅ | 与 `team_task_*` 仅前缀平行、名称不相交；两板并存关系见 §4.3 |
| `project_evidence_get` | 空闲 ✅ | 无任何既有/保留占用 |
| `project:identity`（系统提示节名，非工具） | 空闲 ✅ | 先例：tool-agent-team 的 `team:policy` 节 |
| 命令注册名 `project`（显示为 `/project`） | 空闲 ✅ | 现存命令名无 `project`；作用域限定受管理 profile 项目根会话 |
| `worktree_*` 全族 | 禁用 ⛔ | 已被 `dsh-tool-worktree`（agent-worktree 面）占用；本设计绝不新增 `worktree_*` 名称，worktree 绑定只作为只读字段出现在绑定/身份记录里 |
| `project_open` / `project_send` / `project_status` / `project_stop` | 禁用 ⛔ | P21-S 保留 |
| `memory_search` / `memory_read` / `memory_append` | 禁用 ⛔ | P21-M 保留 |
| `team_*`、`spawn_teammate`、`followup_task`、`send_message`、基础工具名 | 禁用 ⛔ | tool-agent-team 与基础面已占用 |

`project_` 前缀共用约定：part1（会话级工具）与 part2（Shadow 路由）共用 `project_` 前缀、动词集不相交。保留动词表登记如下，后续任何新 `project_*` 候选名必须先对照：`open`/`send`/`status`/`stop` → P21-S；`verify`/`review`/`complete`/`task_*`/`evidence_*` → 本切片（P04/P05 语义）。

## 3. 模型面/宿主面总边界（五包共用规则）

1. **调用者身份一律宿主解析**：工具体内经 `exec.agent` → `ctx.agentBindings.find()` 取真实绑定；模型参数不收角色/身份字段；模型自报角色拒绝（AT1-01）。
2. **角色控制两层**：P02 `tools.guard()` 单调拒绝是安全权威（覆盖全部派发工具含 scope-local，后置 pre-execute 放行不能推翻）；工具体内角色校验是第一道。`restrict()`-only 不合格（AT1-01 明文）。被禁用工具的 schema 可见但执行必拒——隐藏 schema 需改注册位置，本设计不改。
3. **工作归属三查**：每次会话级调用携带 `goalId`+`acceptanceHash`，宿主对照 P06 `assertAdmitted` 准入与 P05 绑定回执；异步工作前先钉住 `taskIds`；陈旧工作返回 `stale_work`，不得成为新 Goal 的证据（part1；AT1-09）。
4. **模型不可写原始证据**：P05 三轨迹没有模型可达的 record 工具；提交/验证事实由宿主从真实进程与 git 观测采集后落账（AT1-05：伪造成功必须在真实路径被拒）。
5. **模型可见 ⟺ 已记录**：工具结果与拒绝本身是可重建的工具事件；新增模型可见输入需要会话事件；如需新增 `SessionEventMap` 成员，同一变更内履行 TypeScript 与 Python SDK 投影义务。
6. **注册即 effect**：工具经 `ctx.tools.register`、守卫经 `ctx.tools.guard`、命令经 `ctx.commands.register`，`register()` 返回 disposer；处置后不留陈旧守卫/限制（AT1-02）。
7. **无硬编码调参**：角色工具面、修复上限、`maxActiveTasks` 等部署可变项全部走已验证 Config 字段（P02 config.ts、P04 controller.ts 已如此，工具面沿用）。

## 4. 逐包提案

### 4.1 P01 session-identity（AgentBindingRegistry）

- 现状：`createBoundSession`/`bind`/`find`/`byRole`/`list`，`session_identity` 域冷恢复，纯服务。
- 模型面提案：**不新增工具**。身份/角色经 `project:identity` 系统提示节投给模型：宿主纯函数渲染，内容取自绑定记录（role、parentSessionId、taskId、pluginId、delegationDepth、worktree 只读字段），会话期静态。理由：身份是创建期固定的宿主事实而非每轮查询；`team:policy` 节是仓库既定先例；节渲染同样满足模型可见 ⟺ 可重建。
- 已评估并否决的备选：`identity_whoami` 读取工具——只回静态事实却新增一个可被探针的调用面，收益为零；否决。
- 宿主面：`createBoundSession`/`bind` 保持宿主专用（合规创建顺序唯一入口），永不注册为工具或命令；绑定写操作不经模型参数，是 AT1-07"递归 spawn 不可用"的前提之一。
- 验收锚：AT1-01（支撑：角色来自宿主绑定，模型无自述入口，自报即拒）。
- Owner：实现归 S4 新切片（§6）；语义复核归 P01 原组长（L-Foundation 已结算，承担评审义务）。

### 4.2 P02 agent-hierarchy（AgentHierarchy）

- 现状：guard + restrict 已就绪（controller/lead/worker 三态角色表、创建面全覆盖单调守卫、深度预算 2 双保险、冷恢复重装、缺角色拒绝）；五个 Config 字段（`roleToolPolicies`/`delegationToolNames`/`teamToolNames`/`otherCreationToolNames`/`leadPluginScopes`）已是配置面。
- 模型面提案：**不新增工具**；模型面 = guard 拒绝词表契约——每类拒绝携带 code 与具体修法（先例：tool-worktree 类型化拒绝文本），枚举五类：未知身份 / 缺失策略 / 模型自报角色 / 深度预算耗尽 / lead 的 pluginScope 未批准（fail-closed）。拒绝文本随工具拒绝事件落日志、可重建。
- 宿主面：guard 安装/冷恢复/dispose 生命周期已实现；S4 只补两件事——拒绝词表文案契约定稿、recorded-session 场景补课（P02 交付时登记的遗留至 P22 项：keyless 场景覆盖调用/拒绝/冷恢复变体）。
- 验收锚：AT1-01、AT1-02（主：真实 dispatcher 探针 + 冷恢复重装 + 缺角色拒绝 + dispose 无陈旧守卫）；AT1-07（支撑：递归 spawn 不可用）。
- Owner：P02 原组长定稿拒绝语义；实现落点在 S4 新切片包内时由切片编码。

### 4.3 P04 project-controller（ProjectController）

- 现状：九态任务板（`planned→assigned→developing→reviewing→submitted→integrated→completed`，`blocked`/`failed` 强制三元组）+ 生命周期准入/停止/静默 + 一次性合并门禁（controller-only marker）+ `maxActiveTasks` 并发预算；纯服务。
- 模型面提案（会话级工具，注册于项目根会话作用域；worker/reviewer 可见性与可用性由 P02 角色面裁剪）：

| 工具 | 调用者 | 输入（`goalId`+`acceptanceHash` 之外） | 宿主职责与输出 | 验收锚 |
| --- | --- | --- | --- | --- |
| `project_verify` | 活动写入者 | `checkIds[]` | 校验派发关联 + 写入所有权 → 运行已配置检查（记录真实可执行文件/参数/工作目录/退出码/有界日志引用）→ P05 落 verification 快照 → 返回 `verificationId`/`snapshotId`/逐项结果；拒绝：未知检查、错误项目、无写入所有权、`stale_work` | AT1-03、AT1-04 主；AT1-05 支撑 |
| `project_review` | 审查者 | `snapshotId`、`decision`（`pass`\|`changes_required`）、有界 `findings[]` | 校验审查者绑定 + 快照现行（宿主重算，`HEAD` 相等不掩盖未跟踪改动、必需检查不可静默削弱）→ 返回审查引用（审查者身份、策略版本、快照）；拒绝：未知快照、开发者冒充 | AT1-05、AT1-06 主 |
| `project_complete` | 控制器 | `snapshotId` | 校验必需 tasks/checks/独立审查同元组 + 无活动写入者 → 取当前 `GoalRef` 比较并交换完成；拒绝：Goal 已变（不对另一 Goal 静默重试）、证据缺失 → `needs_attention` | AT1-06 主；AT1-09 支撑 |
| `project_task_list` | 控制器/审查者 | 可选 state 过滤、有界分页 | 返回九态板记录（`blocked`/`failed` 带三元组），稳定序 | AT1-09 支撑（A/B 板隔离可观察）；AT1-04 支撑 |
| `project_task_get` | 控制器/审查者 | `taskId` | 单记录 + 该任务证据引用（指向 P05 台账） | AT1-06 支撑 |
| `project_task_move` | 控制器 | `taskId`、`action`（封闭枚举 `assign`\|`start`\|`review`\|`submit`\|`merge`\|`complete`\|`block`\|`fail`\|`resume`）、动作字段（`assigneeSessionId` / blocked 三元组） | 逐动作映射 controller 服务方法；`action=merge` 由宿主 `requestMainTreeMerge`+`integrate` 同操作完成，marker 是宿主内部单次令牌、不过模型边界；拒绝：非法迁移、并发预算耗尽、admission 关闭 | AT1-04 主（单写入者租约语义的板面）；AT1-08 支撑（修复次数内 `resume` 交回）；AT1-09 |

- 边界强调：task completed ≠ Goal complete ≠ 项目验收通过（part1 完成语义）。`project_complete` 是唯一 Goal 级完成入口；`project_task_move` 的 `complete` 只动板面记录。
- 与原生 Team 板关系：`team_task_*` 行状态仍由原生任务行负责（part1 taskIds 关联规则）；`project_tasks` 板是控制器生命周期门禁面；两板经宿主拥有的会话事件关联，互不代写。
- 命令面提案（宿主/人工专用）：命令注册名 `project`，子命令旅程对齐 part1 用户操作表——`/project configure <JSON>`（预览 `allowedPaths`/`checks`/`snapshotExcludes`/生效限制）、`/project confirm <previewId>`（批准准确当前预览，陈旧预览拒绝）、`/project start <objective>`（创建并关联原生 Goal 后开放接收；重复启动不替换未完成 Goal）、`/project stop`（关闭接收等停稳）、`/project resume`（验证身份、保留预算）、`/project result`（差异/工作身份/真实检查输出/审查问题/下一允许动作）、`/project abandon`（完全停稳后记录人工决定并清除原生 Goal，保留历史、不宣称完成）。受管理 profile 不挂载原始 `/goal` 修改命令；模型文本或貌似斜杠命令的文本不能充当人工确认。
- 验收锚（命令面）：AT1-10 主；AT1-09 支撑（A 后 B 的启动与预算保留经 `start`/`resume` 可观察）。
- Owner：工具面实现归 S4 新切片；`/project` 命令面归 P04 原组长（P22 矩阵既定"命令面归 P04"）；verify/review/complete 与任务板迁移语义定稿归 P04 原组长评审。

### 4.4 P05 agent-evidence（AgentEvidenceLedger）

- 现状：三轨迹 append-only 台账（bindings/submissions/verifications），冷恢复，只存溯源不持判定。
- 模型面提案：**写入零工具**（本切片关键边界）。`recordTaskGoalBinding`/`recordSubmission`/`recordVerification` 不暴露给模型——提交与验证事实由宿主采集（git 观测、真实进程退出码）后落账；模型唯一的提交动作是 `project_task_move` 的 `action=submit`，宿主核对 commit/`changedPaths`/`inputDigest` 后才落 submission 回执。理由：模型可写台账 = AT1-05 防线自拆。
- 读取面：`project_evidence_get`（控制器/审查者）：输入 `taskId` 或 `controllerSessionId`+`goalId` → 三轨迹有界视图（回执 id、时间序、引用），含"证据引用可解析"所需全部 id。`project_verify`/`project_review`/`project_complete` 的响应内嵌证据引用（§4.3）。
- 已评估并否决的备选：向模型暴露 `evidence_record` 类写入工具——直接违反第 3 节规则 4 与 AT1-05；否决且不再议。
- 验收锚：AT1-06 主（证据引用可解析、重复完成无害、不建独立验收数据库——读取面直接消费台账）；AT1-05、AT1-09 支撑（伪造拒绝可观察、A/B 绑定分立可见）。
- Owner：读取面与"模型零写"边界归 P05 原组长评审（gaps.md S4 既列 P05）；实现归 S4 新切片。

### 4.5 P06 agent-reliability（AgentReliability）

- 现状：admission fail-closed（进程内，fresh process 必须显式开放）、`assertAdmitted` pre-step、`reconcileUncertainCall`（探针先行、至多一次重试、无盲目重试路径）、`flushBarrier`（失败关闸留写权）、`stopProject`（进程树停止）。
- 模型面提案：**零新增工具**。模型面 = pre-step/工具拒绝的结构化词表：`AGENT_RELIABILITY_ADMISSION_CLOSED`（admission closed；等待宿主 resume，不盲目重试）与 `AGENT_RELIABILITY_IDENTITY_MISMATCH`（有界说明，不含项目内容/机密）。没有 `openAdmission`/`stopProject`/`reconcileUncertainCall` 的任何模型入口——停止、恢复、对账全部宿主串行。
- 宿主面：`openAdmission` 只从 `/project start`/`/project resume` 人工授权路径调用（AT1-10：模型文本不能授权）；`closeAdmission` 接 `requestStop` 与 flush 失败；`flushBarrier` 挂持久化路径；`stopProject` 由宿主在停止流程串行调用，unresolved 身份经 `/project result` 呈现（跨重启保留语义 = gaps.md S5，归 P06 原组长，本文只引用）。
- 验收锚：AT1-04、AT1-10 支撑（准入拒绝可见且授权不可由模型授予）；主锚 AT4-01/04/06（P22 矩阵既定归 P06，本文不改写）。
- Owner：P06 原组长（拒绝词表与命令接线语义）；编码落 S4 新切片包内时由切片承担。

## 5. 汇总表

| # | 面 | 名称 | 调用者/触发 | Owner | 验收锚 |
| --- | --- | --- | --- | --- | --- |
| 1 | 模型工具 | `project_verify` | 活动写入者 | S4 切片实现，P04/P05 组长评审 | AT1-03/04 主，AT1-05 支撑 |
| 2 | 模型工具 | `project_review` | 审查者 | 同上 | AT1-05/06 主 |
| 3 | 模型工具 | `project_complete` | 控制器 | 同上 | AT1-06 主，AT1-09 支撑 |
| 4 | 模型工具 | `project_task_list` | 控制器/审查者 | 同上 | AT1-09/04 支撑 |
| 5 | 模型工具 | `project_task_get` | 控制器/审查者 | 同上 | AT1-06 支撑 |
| 6 | 模型工具 | `project_task_move` | 控制器 | 同上 | AT1-04 主，AT1-08/09 支撑 |
| 7 | 模型工具 | `project_evidence_get` | 控制器/审查者 | S4 切片实现，P05 组长评审 | AT1-06 主，AT1-05/09 支撑 |
| 8 | 模型提示节 | `project:identity` | 宿主渲染 | S4 切片实现，P01 组长评审 | AT1-01 支撑 |
| 9 | guard 拒绝词表 | 五类拒绝 code+修法 | 宿主守卫 | P02 组长定稿 | AT1-01/02 主，AT1-07 支撑 |
| 10 | pre-step 拒绝词表 | admission/identity 两类 | 宿主 pre-step | P06 组长定稿 | AT1-04/10 支撑，AT4-01/04/06 主 |
| 11 | 宿主命令 | `/project configure\|confirm\|start\|stop\|resume\|result\|abandon` | 人工 | P04 组长（P22 矩阵既定） | AT1-10 主，AT1-09 支撑 |

## 6. 实施顺序与依赖

1. **S4 新切片工具包骨架**（建议包名 `@deepseek-ai/dsh-experimental-project-toolface`，切片编号建议 P23、由总控定夺）：`static inject` 五服务（`agentBindings`/`tools`/`agents`/`projectController`/`agentEvidence`；reliability 经命令与 pre-step 接线，不进工具包 inject）、调用者解析、两个拒绝词表、事件/日志义务。依赖：P00–P06 已全部合并 main（登记表第 6 节）。切片依据：Service Definition（五包）已稳定、Consumer 面（模型/命令）独立演化，符合 capability seam 三角色拆分条件。
2. **P04 板面 + verify/review/complete + P05 读取面**（同一切片一次交付，互相咬合：verify 落 P05 快照、move 受 P06 准入约束）。依赖第 1 步；交付即解除 P21-S 对"P04 接口"的最后一层依赖（L-Shadow 已实派，其四工具不含本文任何名称）。
3. **P02 拒绝词表**（P02 组长，与第 2 步并行）+ recorded-session 场景补课。
4. **P01 `project:identity` 节**（切片内，小改动）。
5. **P06 pre-step 拒绝词 + 停止/准入命令接线**（P06 组长）。
6. **`/project` 命令面**（P04 组长；AT1-10 全旅程）。依赖第 2、5 步。

顺序理由：工具先于命令（命令包装同一批已校验的操作，避免两套校验逻辑）；P21-S 的解除依赖最早化；AT1-10 旅程在全部构件就绪后收口。

## 7. 实施义务清单（仓库约定映射）

- 工具 schema 只含模型侧输入；宿主侧细节（域表、进程调用、marker 令牌）不出现在调用 schema（tool-worktree 先例）。
- 跨边界 id 用既有品牌（`TaskId`/`PluginId` 出自 project-contracts，`GoalId` 出自 dsh-goal，`SessionId` 出自 dsh-session），不收裸 `string`。
- 工具卡片/Web 呈现从原始事件与持久化回执派生，host presenter 保持纯函数。
- 新模型可见输入 → 会话事件；若动 `SessionEventMap`，同一变更内更新两套 SDK 投影。
- 非平凡变更同 PR 带 Agent Note；keyless recorded-session 场景覆盖新工具的调用/拒绝/冷恢复变体。
- coverage 门禁 per-file 100%（`packages/*/*/src`）；提交前按 dsh-pre-push-checks 选最小证据，不默认全量。
- AT 用例绑真实测试文件/测试名或可复现手动步骤；实现前全部维持 `not_run`，缺前置记 `blocked` 不记 `passed`。

## 8. 开放问题（交总控/组长裁决）

1. 切片编号与包名（本文建议 P23 / `project-toolface`）。
2. `project_task_move` 单工具封闭枚举 vs 拆分为多个小工具（本文取单工具：schema 面小、动作映射集中在服务层、与 `team_task_update` 风格对称；若评审倾向拆分，验收锚不变）。
3. `project:identity` 节的刷新时机（本文取会话期静态；若绑定可在会话中期变更，需补一条会话事件并随之重建节内容）。
