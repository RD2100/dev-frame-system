---
description: P05 证据完整性加固设计（at105 缺口①错审查者交叉授权、④snapshotId⇄sourceFingerprint 绑定）：字段/校验/错误码/缝位置、影响面与放弃的替代案（p/p05harden @ 791e9270c4）。
---

# P05 证据完整性加固设计（at105 缺口①④ src 波）

- 基点：`p/p05harden` @ `791e9270c4`。范围：`packages/experimental/devframe/src`、`packages/experimental/agent-evidence/src`，及被 schema 变化强制更新的既有用例。
- 权威断言面：[testAndAcceptance.md AT1-05](../../../docs/testAndAcceptance.md)（"wrong reviewer identity / a review for a different snapshot … rejected with its actual blocking reason"）；[detailDesign-part1](../../../docs/detailDesign-part1.md)（`project_review` 仅审查者可用、"开发者冒充审查者时拒绝"）。
- 调查结论（缺口①落点选型依据）：全树 `devframe/review` 的真实记录路径只有 `DevFrameSessionJournal.append`（`decodeDevFramePayload` 的调用者、durable 事件写入者）；无任何生产 service 组合"角色权威 + review 记录"（`project_review` 命令面属未启动的 P23/S4）。hierarchy `roleOf(agent)` 与 session-identity `agentBindings.find(SessionId)?.role` 的 `AgentRole` 词表是 `controller|lead|worker`（`isAgentRole('reviewer') === false`），**结构上不可能授权 reviewer**；reviewer 角色只存在于 DevFrame 角色词表（`DevFrameRole` / durable `devframe/role-policy` assignments）。依赖方向：agent-evidence peer-depends devframe，devframe 反向 import 即成环。

## 缺口④：snapshotId⇄sourceFingerprint 绑定

**动机**（anchor-matrix AT1-05 "错快照" 行）：结果/证据可声明与 Goal 绑定一致的 `sourceFingerprint`，却引用另一棵源码树的 `snapshotId`；`resolveResultBinding` 全元组断言不覆盖 snapshotId，`applyReview` 只校验 snapshotId 存在于某条 verification（同 Goal），无跨字段绑定。

**方案**：
- 品牌 id 走工厂：`DevFrameSnapshotId` 类型+工厂从 `events.ts` 移至 `shared/types.ts`（与 `SourceFingerprint` 同族），`events.ts` 原 位 re-export（既有导入路径全部不变）。工厂前置 `nonEmptyId`（非空、trimmed）校验。
- 同录（request → make → record 全链，均为 required，exactOptionalPropertyTypes 下无 optional-undefined 语义）：`StartGoalRequest.snapshotId`、`GoalBinding.snapshotId`、`GoalResultBinding.snapshotId`；`resolveStartRequest` 经 `nonEmptyId`+工厂固化；`sameBinding`/`copyBinding` 纳入该字段。`ProjectWorkBinding`/`ProjectBindingRecord`（shared workspace 当前绑定视图，README 示例契约）保持不变——快照身份持久化在 `devframe/goal-binding` 事件与控制器自有 store 行。
- durable/file 边界校验（schema 层，进程内信任类型）：`goalBindingSchema`、`goalResultBindingSchema` 增 required `snapshotId`（strict）；`verificationEventSchema`/`reviewEventSchema` superRefine 增 `snapshotId === binding.snapshotId` 交叉校验。
- 交叉校验点：`assertResultTuple`（`resolveResultBinding` 全元组断言面）增 snapshotId 比较，不一致 → **既有族扩展** `GOAL_BINDING_IDENTITY_MISMATCH`（选既有码不加新码的理由：snapshotId 与 sourceFingerprint 同属一个身份元组，同一断言面同一路由；对旧行为是"只多拒"，GOAL_BINDING_IDENTITY_MISMATCH 元组面完全向后兼容）；投影重放 `sameResultTuple` 增同字段比较——与 schema 交叉校验构成完整链条（schema 层管"事件级 snapshotId = 载荷内绑定元组的 snapshotId"，投影层管"绑定元组 = 已存 Goal 绑定"），重放对裸 `Session.append` 绕过与 hostile 日志同样 fail-closed。

**影响面清单**（逐一更新，不削弱断言）：`tests/goal-binding.spec.ts`（request/resultReference 夹具 + 新拒绝探针）；`tests/events.spec.ts`（夹具 + 新 schema/replay 拒绝 + journal 门禁入参）；agent-evidence `tests/at105-rejection-matrix.spec.ts`（RESULT_BINDING/startRequest/resultReference + "错快照"用例扩展 snapshotId 探针 + 文件头对照表）；`agent-team/tests/devframe-qa-composition.spec.ts`（两处字面量，host tsc 编译强制，机械更新）；evidence 台账 receipt 不变——receipt 是工作身份解析词表，从不重构 `GoalResultBinding`（无 taskIds），快照身份属 devframe 绑定+证据事件面（README 已声明台账不判验收）。无生产 src 创建点（无 `devframe/*` 事件生产写入者，pre-release 无旧盘上语料，符合"Backends reject old on-disk formats"）。

**放弃的替代案**：可选 snapshot 引用重载（`GoalResultBinding & { snapshotId }` 第三引用形态）——留有"不传即不校验"的静默跳过侧门，违背 fail-loud；`ProjectWorkBinding` 层加字段——波及无跨包消费者的 README 契约视图，churn 大于收益。

## 缺口①：错审查者交叉授权

**动机**（anchor-matrix AT1-05 "错审查者" 行）：`reviewEventSchema` 只校验 `reviewerSessionId` 形状；review 请求者 ⇄ role-policy assignment 交叉校验未实现——开发者/任意未授权会话可冒充审查者提交 review。

**方案**（schema 形状校验不动；授权在最早可解析点）：
- 缝位置 = `DevFrameSessionJournal`（即"谁调 schema.parse/谁写 durable 事件"的那个 service 方法）。新增结构接口 `DevFrameReviewGate { requireReviewer(sessionId): void }`，**构造器 required**：未接线即在构造时失败（误配 fail-loud，杜绝静默跳过）；`append('devframe/review')` 在 schema 解码后、append 前调用门禁，门禁拒绝则事件永不落日志（不闩锁持久化失败态）。
- 读取面选择：**SessionId 键**。事件携带的是 `reviewerSessionId: SessionId`；hierarchy `roleOf` 需 live Agent（该缝不可达）；session-identity `agentBindings.find(SessionId)` 虽按 SessionId 可解析，但其 `AgentRole` 词表无 reviewer——按可解析性与词表所有权，授权面取 **DevFrame 角色词表**：live 面 = `RolePolicy.roleOfSession(sessionId)`（本波新增的 SessionId 直读面，等价于 agentBindings 直读面在该词表内的对应物）；durable 面 = role-policy 事件 assignments（投影重放层使用）。
- 新码入 evidence 错误族：`AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`（`agent-evidence/src/errors.ts`）。抛出实现 `EvidenceReviewGate`（`agent-evidence/src/review-gate.ts`）：对注入的 `EvidenceReviewerDirectory { roleOf(sessionId) }`（SessionId 键角色目录，宿主可接 RolePolicy.roleOfSession 或未来组合）判 `role !== 'reviewer'` 即抛 `AgentEvidenceError`；以结构类型满足 devframe 门禁接口，**零反向依赖，不成环**。
- 投影重放层（第二道、无注入）：`applyReview` 校验 `reviewerSessionId` 必须出现在当前 durable role-policy assignments 且角色为 `reviewer`，否则 fail-closed（与既有 policyVersion 相邻校验同面同风格，只多拒）。

**影响面清单**：`tests/events.spec.ts`（journal 构造补门禁 + 夹具补 reviewer assignment + 新拒绝用例）；agent-evidence `tests/at105-rejection-matrix.spec.ts`（新增错审查者端到端用例：journal+`EvidenceReviewGate`+目录 → 稳定码拒绝、事件未落、放行正例、未绑定探针）；`tests/permissions.spec.ts`（`roleOfSession` 直读面）。`agent-hierarchy/src` 零改动。

**放弃的替代案**：journal 可选门禁参数——缺省即静默放行，违背 fail-loud；把码放进 devframe 自有错误类——违背"新码入 evidence 错误族"且 family 归属错面；经 devframe 反向 import `AgentEvidenceError`——与 agent-evidence→devframe 依赖成环。

## 残余缺口（fail-loud 登记）

- 生产组合接线缺失：尚无宿主组合把 `EvidenceReviewerDirectory` 接到 live/durable 角色权威（`project_review` 命令面属 P23/S4）。现无任何 src 代码记录 review 事件，且 journal 构造器强制门禁，故不存在绕过路径；组合落地时必须接线，未接线即构造失败。
- "审查后改未跟踪文件"（真实指纹重算）与"削弱必需检查"两个变体仍为 GAP（anchor-matrix 原登记，非本波范围）。
