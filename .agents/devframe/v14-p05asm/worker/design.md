# v14-p05asm 设计文档 — P05 完成准入 × native Goal 生命周期生产组装（首片）

任务：把已并主树的 `evaluateCompletionAdmission` 三谓词评估面接入 native Goal 生命周期的真实生产调用点。
本片=GAP"admission 与 native Goal 生命周期生产组装归 P23/S4"（p05wire 登记，合并 d22f705d8c）的生产组装首片。

## 0. 主树起点事实（D:/dsh-devframe 只读核实，基点 2aaec82d24 同源）

- **三谓词评估面（纯评估，无生产调用点）**：`packages/experimental/devframe/src/controller/goal-binding.ts:700-726` —— `evaluateCompletionAdmission` 固定序 指纹先（:703 `verifySourceFingerprint`）→ 检查次（:707-708 `store.load` + `evaluateRequiredChecks`）→ 审查收尾（:712-720），admitted（:721-725）；violation `reason` 即稳定码；结构错误（`SourceFingerprintError`、`RequiredChecksError`）原样 fail-loud 传播；显式 async。
- **控制器与端口**：`GoalBindingController`（goal-binding.ts:285-599）；`NativeGoalPort`（:185-194）只有 `create/disarm/get/resume` 四动词，**无 complete**；`start`（:338-400）先关准入再动 native；`resume`（:410-457）精确身份 + `closeAdmission` + native 校验（revision 回退/已 complete → `GOAL_BINDING_IDENTITY_MISMATCH`，:425-436）+ `assertRevisionAdvance`；`enqueue`（:533-537）串行化；`saveBinding`（:540-560）；`findBinding`（:563-584）；`MemoryGoalBindingStore`（:121-169）。
- **native 生命周期完成变更点**：`GoalService.complete`（`packages/goal/goal/src/index.ts:428-438`）经 `transition`（:577-590，允许 active/paused/blocked）→ CAS `expectCurrent`（:526-536，`GOAL_STALE_REVISION`）→ commit 并 disarm；`assertLive`（:539-543）。`recordReceipt`（:450-470）为后续切片的完成回执面（注记证据，不推进 revision）。
- **通用模型完成路径（本片不触碰）**：`update_goal` action=complete → `ctx.goals.complete`（`packages/goal/tool-goal/src/index.ts:306-307`）。
- **p05harden fail-loud 先例**：`DevFrameSessionJournal` 构造器 required `DevFrameReviewGate`（`packages/experimental/devframe/src/session-journal.ts:66-77`）——未接线即构造失败，无静默绕过。
- **评估面依赖的源面**：`verifySourceFingerprint`（`src/source-fingerprint.ts:260-269`）；`RequiredChecksConfigStore`/`MemoryRequiredChecksConfigStore`/`REQUIRED_CHECKS_CONFIG_NOT_FOUND`（`src/required-checks.ts:161-221`，码表 :103）；`DevFrameCheckResult`（`src/events.ts:154-171`）、`DevFrameReviewEventData`（:221-238）。
- **端口现有实现者（全部为测试内联实现，无生产实现）**：`devframe/tests/goal-binding.spec.ts:51-73`（realGoalPort，ctx.goals 内联适配）与 :75-114（fakeGoals）；`agent-evidence/tests/at105-rejection-matrix.spec.ts:154-176`（fakeGoalPort）；`agent-team/tests/devframe-qa-composition.spec.ts:71-76`（字面量）。
- **在案裁定**：`.agents/notes/proposed/architecture/2026-09-06-required-checks-wiring.md` 明确记录备选"Fold admission into the GoalBindingController lifecycle now……归 P23/S4 tool surface"，其 Risks 第 1 条即本片要收的 GAP。

## 1. 生产调用点 seam 定位与裁定

**seam 选择：`GoalBindingController.complete(identity, request)` —— DevFrame 绑定 Goal 的完成操作，即三谓词评估面的第一个生产调用方；评估通过后经 `NativeGoalPort.complete(ref)` 落到 native `GoalService.complete` 的真实生命周期变更。**

理由：
1. 完成准入的三谓词证据（worktree 指纹、必需检查、授权审查）是 DevFrame 域证据；native goal 域（tool-goal 的通用完成路径）没有也不应有这些证据。把评估塞进 `dsh-goal`/`tool-goal` 会造成 release→experimental 反向依赖（仓库规则禁止），且会让通用 goal 完成被迫携带 DevFrame 证据——否决。
2. 控制器拥有绑定（`sourceFingerprint`/`snapshotId`/身份），是"证据是否关于本 Goal"的身份权威；`start/resume` 已是 native 生命周期前的控制器闸门先例，complete 是同一序列的第三个人类生命周期动词。
3. `.agents/notes/proposed/architecture/2026-09-06-required-checks-wiring.md` 在案备选正是"fold admission into the GoalBindingController lifecycle"——本片即该备选按 P23/S4 首片范围落地（仅控制器面，不含宿主命令面/verdict 落日志）。

## 2. 接线方式（最小面）

### 2.1 端口动词（`NativeGoalPort` 增加第五动词，required）

```ts
/** Mark the current native Goal complete at one exact revision and disarm it. */
complete(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState
```

required（非可选）：未接线=类型级构造失败（TS 编译红），强于运行时可选+调用失败的弱语义；全部三个测试内联实现者随之补齐（见 §6 文件清单）。CAS 语义与 native `complete(agent, ref)` 同构，revision 由控制器先 `get()` 读取后精确传入。

### 2.2 生产适配器（新增 `GoalServicePort implements NativeGoalPort`）

构造注入 `{ goals: GoalService; agent: Agent }`（绑定一个 live Agent，宿主组合时传 `ctx.goals` 解析出的服务实例）；五个动词一一委托 native 服务并把 `GoalView` 投影为窄三icity `{id, revision, phase}`。这是端口的首个生产实现——P23/S4 宿主组合直接可用，避免首片仍是"仅测试组合"。native `assertLive`/`GOAL_STALE_REVISION` 等结构错误按 typed 同进程边界信任 TS 原样传播（resume 先例）。

### 2.3 完成请求（新增 `CompleteGoalRequest`）

与 `StartGoalRequest` 对称命名：`worktreePath`、`checks`、`requiredChecksDigest`、`requiredChecksStore`、`review`。**不含 `sourceFingerprint`**——指纹的权威侧是 durable binding（控制器从 `findBinding(identity)` 取 `binding.sourceFingerprint` 传入评估面），不接受调用方宣称值。

### 2.4 控制器操作（`GoalBindingController.complete`，序=resume 先例）

```
enqueue 串行 → ensureReady → findBinding(identity)（精确身份；未知名/跨域 → NOT_FOUND/IDENTITY_MISMATCH，准入态不动）
→ closeAdmission()（进完成态即封 admission：评估含真实 git 子进程，完成裁定不得与已准入 model 步赛跑；
   被拒后继续工作必须走人类 resume —— fail-safe 方向）
→ native get() 校验：undefined/id 不符/revision < binding/phase==='complete' → GOAL_BINDING_IDENTITY_MISMATCH（resume 同款预检）
→ 审查证据归属校验：request.review.binding 的 goalId/controllerSessionId/workspaceId 必须等于本绑定
  （否则完成操作在无声接受别 Goal 的证据=身份域静默绕过；revision 不比——resume 推进 revision 不使既有证据失效，深 tuple 归属留后续片）
→ evaluateCompletionAdmission({ ...request, sourceFingerprint: binding.sourceFingerprint })   // 三谓词固定序，本片零改动
→ rejected：原样返回 verdict（数据不是异常），native 零变更
→ admitted：port.complete({id: current.id, revision: current.revision}) → assertNativeRevision + id 复核 +
  assertRevisionAdvance（native complete 推进 revision）→ saveBinding({ ...binding, goalRevision: completed.revision })
  （resume 同款 revision 同步持久化；lifecycle 词表不动——binding 生命周期管 stop/写权，完成相由 native goal phase 持有）
→ 返回 admitted verdict
```

### 2.5 fail-loud 行为（沿 p05harden 先例）

- 端口动词 required：未实现=编译失败（构造级）。
- 结构错误原样穿透：`SourceFingerprintError`（5 码）、`RequiredChecksError`（`REQUIRED_CHECKS_CONFIG_NOT_FOUND`/`REQUIRED_CHECKS_INVALID_CONFIG`）、native `GoalError`、`GoalBindingError`（身份/持久化域）。
- 无任何静默跳过评估的旗标/可选路径；`complete()` 本身就是接线，评估无条件执行。
- 拒绝=verdict 数据（评估面语义不变），不是异常；但 admission 已封，恢复需人类 `resume`。

### 2.6 不接线/其他备选为何否决

- **把评估塞进 `dsh-goal` 服务或 `tool-goal` 工具**：release 包禁依赖 experimental 包（packages/experimental/AGENTS.md）；且通用 goal 完成无 DevFrame 证据，等价于强加新谓词。否决。
- **在 `ctx.goals.complete` 外层做宿主级拦截器/包装服务**：改全局服务组合，爆炸半径大，属 P23/S4 宿主命令面切片；本片"最小接线"不做。登记为未尽。
- **`NativeGoalPort.complete` 设为可选方法**：运行时才暴露未接线，弱于类型级构造失败；且引入"端口半成品"合法态。否决。
- **指纹由调用方随请求宣称**：权威侧必须是 durable binding，否则等于放开指纹宣称权。否决（评估面请求形状不动，控制器侧固定取 binding 值）。
- **admitted 前不封 admission / 被拒不封**：评估含真实 git 子进程（秒级），完成裁定与已准入 model 步并发=竞态；被拒后证据链已破，继续 model 工作不经人类 re-authorize=不安全方向。否决（start/resume 的 closeAdmission 纪律同源）。

## 3. 行为保持声明

- `evaluateCompletionAdmission` 三谓词评估序（指纹→检查→审查）零改动；本片只新增调用方。
- 热路径异步契约：`assertAdmitted`（绑定热路径）零触碰；`complete()` 是显式 async 的离热路径调用（git 子进程只在调用时发生）。
- `SessionEventMap` 键集、`SESSION_FORMAT_VERSION`、durable schema、tool-goal 的通用完成路径、native goal 服务的公共面：零改动。

## 4. 测试矩阵（正向/拒绝/边界；全部真实 git worktree，describe timeout 30s）

正向：
- T1 fake 端口：admitted → trace `goal:get`+`goal:complete:<id>:<rev>`；binding 持久化为完成 revision；admission 关闭；verdict 携带 binding 指纹。
- T2 真实组合（生产调用点实证）：真 git worktree 指纹做 start 指纹 → `GoalServicePort` over 真 `GoalService`（SessionStore+AgentRegistry+SessionProjectionRegistry+GoalService）→ complete → `ctx.goals.get(agent).phase==='complete'` 且 revision 推进；store.read revision 同步；适配器裸面（无 goal 时 `get()/disarm()` 返回 undefined 双臂覆盖）。
- T3 真实组合 resume 先例测试改用 `GoalServicePort`（原 realGoalPort 内联实现退役为适配器）。

拒绝（native 零变更+admission 封闭+binding revision 不变）：
- T4 指纹不符 → stage `source-fingerprint`，双值证据（recorded vs computed）。
- T5 弱化必需检查（改参）→ stage `required-checks` + `REQUIRED_CHECKS_COMMAND_MISMATCH` violation。
- T6 审查 changes_required → stage `review` + findings 原样。
- T7 空配置 store → `REQUIRED_CHECKS_CONFIG_NOT_FOUND` fail-loud（不是 rejection）。

边界：
- T8 未知名身份 → `GOAL_BINDING_NOT_FOUND`，admission 态不动（仍 open）。
- T9 native goal 缺失（get undefined）→ IDENTITY_MISMATCH。
- T10 native 当前是另一 goal → IDENTITY_MISMATCH。
- T11 native revision 回退（< binding）→ IDENTITY_MISMATCH。
- T12 native 已 complete → IDENTITY_MISMATCH（resume 同款预检）。
- T13 审查证据归属他 Goal → IDENTITY_MISMATCH，且评估未执行（错误类型即序证明：真 worktree 下若进入评估只会返回 verdict 不会抛 GoalBindingError）。
- T14 native complete 返回异 id → IDENTITY_MISMATCH，binding 持久化值未被污染。
- T15 entry-exports：`GoalServicePort` 经根入口与 controller 模块同一性。

## 5. 门禁计划（真实退出码，未跑不声称）

1. worktree 内 `pnpm install`（仅 worktree 本地）。
2. 聚焦 vitest：`packages/experimental/devframe` + `agent-evidence` + `agent-team` 全绿。
3. 删 worktree 全部 `*.tsbuildinfo` → `pnpm run build` exit 0。
4. `pnpm run gen-cordis-catalog` exit 0（预期 0 written——devframe 无 cordis.yml 注册；新增类型非 cordis 服务类）。
5. `git diff --check` exit 0；每文件恰一尾随换行（自检脚本）。
6. 文档面：新 Agent Note 三件套 + `verify-translation-pairing --write` 重录 sidecar + `verify-agent-note-format`；README en/zh 同改。
7. 提交用 `--no-verify`（本仓库便携 git 无 bash，pre-commit lefthook vendor manifest guard "/usr/bin/env: bash" exit 127=环境事实）；完成报告逐笔登记跳过+替代验证（diff --check/尾换行/触及域零 vendor 路径声明）。

## 6. 精确待改文件清单（申报后动源码）

源码（packages/experimental/devframe，P05/goal 生命周期 seam 直接相关）：
1. `src/controller/goal-binding.ts` —— 模块头 JSDoc 一句；`NativeGoalPort.complete`；`GoalServicePort` + 私有投影 helper；`CompleteGoalRequest`；`GoalBindingController.complete`。
2. `tests/goal-binding.spec.ts` —— 新 describe（T1-T15 中 fake+真实组合用例）；fakeGoals 补 complete；realGoalPort 改用 GoalServicePort；引入共享 fixture 与 afterEach 排空。
3. `tests/completion-fixtures.ts` —— **新增**共享测试 fixture 模块（真 git worktree 构造、CONFIG、executionFor、reviewEvent、排空函数），自 completion-admission.spec.ts 上收，消除双文件复制。
4. `tests/completion-admission.spec.ts` —— 改用共享 fixture（删除本地副本），断言零改动。
5. `tests/entry-exports.spec.ts` —— 增 GoalServicePort 入口同一性行。

跨包（`NativeGoalPort` 接口动词新增的强制连带，均属 goal 生命周期 seam 的测试实现者）：
6. `packages/experimental/agent-evidence/tests/at105-rejection-matrix.spec.ts` —— fakeGoalPort 补 complete（镜像 resume+phase complete）。
7. `packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts` —— goals 字面量补 `complete: ref => ctx.goals.complete(lead, ref)`。

文档/过程（仓库非平凡变更契约）：
8. `README.md` —— 源码地图增 controller/goal-binding 行 + 实现节补完成准入 seam 段 + Known Limitations 补生产组装未尽。
9. `README.zh.md` —— 对应镜像（行级配对）。
10. `.agents/notes/implemented/architecture/2026-09-06-goal-completion-admission-seam.md` + `.zh.md` + `.i18n.yaml` —— 新 implemented 注记（含对 required-checks-wiring 提案的 partial-supersession 声明与相对链接；该提案反向链接修复登记为移交项，见 §8）。

证据（不入库提交以外域）：本文件 `.agents/devframe/v14-p05asm/worker/design.md` 及后续收据。

禁区遵守：零触碰 snapshots/**、packages/test-support/session-snapshot/**、scripts/session-snapshot-corpus*、vendor/**；主树只读。

## 7. 提交拆分

- C1 设计：本文件。
- C2 实现+测试+跨包连带+README（en/zh）。
- C3 Agent Note 三件套（p05wire 三件套先例：注记独立一笔）。
- message 记录门禁收据与领域声明；--no-verify 并登记。

## 8. GAP/未尽（如实预登记，完成后复核）

1. 宿主命令面/cordis 组合（把 `GoalServicePort`+控制器接到真实 profile、verdict 落 `devframe/lifecycle` 或完成回执 `recordReceipt`）仍未接线——P23/S4 主体。
2. 证据归属校验仅到 goalId/controllerSessionId/workspaceId 身份三元组；revision/snapshot/taskIds 深 tuple 归属策略留后续裁定。
3. `ProjectBindingRecord.lifecycle` 词表无终态完成值（native goal phase 持有完成相，本片不改 durable 词表）。
4. required-checks store 仍仅 memory 参考实现（p05wire 登记，未变）。
5. `.agents/notes/proposed/architecture/2026-09-06-required-checks-wiring.md` Risks#1 文案因本片部分失准；反向链接与该提案 zh 镜像的修复（含 sidecar 重录）移交总控/属主链，避免跨链改他人提案双语对。
6. 通用模型完成路径（tool-goal `update_goal` complete）不经过本 seam——DevFrame 绑定 Goal 的模型侧完成拦截属宿主组合切片。
