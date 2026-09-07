# AT3-08 lead 审查证据投影入口（B 线实作记录）

外部 B1（ff bdcd3a096f 起）在 project-controller Git 事务面做准入实作，其验收链需要三层 lead 能落现有 `devframe/review` 证据并冷恢复可读。总控裁定本片收窄为两点：**实际授权三层 lead 能写现有 review 事件 + 冷恢复后可读**；外部侧自担投影读链（取最新 review→按 snapshotId+完整 binding 取 verification→拒 projection.failure/串任务/source/acceptance 不一致→agentBindings 核真实 lead/同插件/parent 是当前 controller/非被审 Worker→evaluateCompletionAdmission）；Git 域零接触。

## 契约钉死项

- **协议名不改**：`DevFrameReviewEventData.reviewerSessionId` 字段保留原义——审查权威归属的 Session 身份；lead 写审查时即其自身 Session。
- **禁自报角色**：写面 gate 经 ctx 层真实目录（`ProjectionEvidenceReviewerDirectory`：store 查活 Session→读 devframe 投影→取最新 rolePolicy 指派）解析角色，审查 payload 无任何角色字段可自证；fold 只消费日志内 rolePolicy 快照，冷恢复重推同一结论。
- **层级真相外部核**：lead 指派背后的 hierarchy 真实性（真实 lead/同插件/parent/被审 Worker 独立性）属宿主 durable agent bindings，本片不复制、不读、不存储；审查消费方（外部）在准入时再核，防错误指派下游兜底。

## 改动（2c095bb3b1）

- **`DevFrameRole += 'lead'`**（封闭并集加成员，不扩 string）：层级授权的 tier-1 lead。rolePolicy 快照可记多个 lead（每子树一个）；zod `superRefine` 与投影 `assertRoleAssignments` 的角色唯一性对 controller/worker/reviewer 三旧角色**保持单例不变**（旧合同不破），仅 lead 允许多指派；单 Session 双角色仍拒；controller 指派仍必须属主 controller Session。
- **`applyReview`（projection.ts）**：审查提交者须持「记录在案的审查权威」——专任 reviewer **或** hierarchy 授权 lead；否则 fail-loud（消息改为 `without reviewer authority`）。fold 只读持久 rolePolicy，冷恢复（fromRestore→fold）得出同一结论。
- **`EvidenceReviewGate`（agent-evidence，最小跨包触达，按裁定标注）**：reviewer-eligible = `reviewer | lead`，其余（controller/worker/未绑定）维持稳定码 `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`；目录返回并集本就含 'lead'（层级词汇无 reviewer——由宿主映射），此改即把 lead 纳入可写判据。
- **组合面不动**：`compositionRolePolicy` 仍只落 controller 指派——lead 指派落盘属生产指派波（后续片/部署接线）；本片交付「能写+可读」的机制面。生成的 persistence-catalog 行号漂移随片再生。

## 测试

- 解码层：两 lead 指派可解码恰 4 指派；reviewer/controller 重复仍拒；同 Session 双角色拒。
- fold 层：rolePolicy 含两 lead → lead 写的 review 实时折叠通过，且 `Session.fromRestore` 冷恢复后折叠同过、reviews 恰一条；未授权会话仍 fail-closed（既有 impostor 用例改断言新消息）。
- gate 层：journal 对 lead 角色 Session 放行恰一 review 事件；worker 角色与未绑定 Session 拒绝、零事件、稳定码不变。

## 真实退出码

host tsc **exit 0**；受影响 9 文件 **82 tests exit 0**；四包联合回归（devframe+agent-evidence+command-goal-binding+project-memory）**337 tests exit 0**；gen/verify-persistence-catalog **exit 0**；verify-cordis-catalog **exit 0**。路由：零模型调用；TaskRecord/project-contracts 零改动；Git 域零接触。

## 仍开放（如实）

- lead 指派的**落盘波**未接：组合面 rolePolicy 落地仍是 controller-only，谁在何时按 agentBindings 落 lead 指派属生产接线（后续片/部署）。
- 外部侧读链与 agentBindings 深核（同插件/parent/被审 Worker 独立性）为外部职责，本片未实现也未复制其存储。
