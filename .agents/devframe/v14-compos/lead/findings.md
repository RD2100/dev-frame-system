---
description: v14-compos 波组长接口核实记录：主树只读复核前波证据链锚点，补充组合构造点/flush 时机/live 角色权威/跨重启恢复路径/依赖面的 file:line 证据。
---

# v14-compos 接口核实记录（findings）

- 核实人：v14-compos 插件接入组长（lead 树 `D:/dsh-devframe-v14-compos-lead`，分支 `codex/v14-compos-lead`，基点 `c79f85fb81`，与主树 HEAD 一致、树净）。
- 方法：主树 `D:\dsh-devframe` 只读逐文件精读（read 工具），零写入；前波证据链只复核锚点不重查全链；本波设计输入（组合构造点、flush 时机、角色权威、恢复路径、依赖面）为新增核实。
- 日期口径：2026-09-06（v14 台账 speed-up round 派发后）。

## 1. 前波证据链锚点复核（全部确认）

### 1.1 生产者（agent-evidence，EvJournal 波已并 main）

- 导出面：`packages/experimental/agent-evidence/src/index.ts:17-20` —— `createSubprocessRequiredChecksExecution` / `subprocessRequiredChecksExecution`（总控链中 "CheckRunner" 的真身；类型面 `RequiredChecksExecution`）、`AgentEvidenceJournal` + `AgentEvidenceJournalOptions` / `VerificationEvidenceRequest` / `ReviewEvidenceRequest`。
- 命名如实登记：包内没有名为 `CheckRunner` 的导出；执行面是 `subprocessRequiredChecksExecution`（默认 10 分钟 kill guard，`check-runner.ts:96-98`）与工厂 `createSubprocessRequiredChecksExecution`（`check-runner.ts:44-94`）。四态 = `passed`/`failed`/`timed_out`/`unknown`（`check-runner.ts:86`）；事件 schema 的 `checkResultSchema` 另有 `skipped`/`cancelled` 两态（`devframe/src/events.ts:423`），runner 本身只产四态。
- 构造即接线：`journal.ts:85-88` —— `new DevFrameSessionJournal(options.flush, new EvidenceReviewGate(options.reviewerDirectory))`；`reviewerDirectory` 是必填项（`AgentEvidenceJournalOptions`，`journal.ts:34-41`），缺目录即无法构造（未接线构造失败）。
- `recordVerification` = store.load→执行→聚合→append：`journal.ts:102-116`（load:103、execution:104、全 passed 聚合:105、append:106-114）。
- `recordReview` = 门交叉授权后 append：`journal.ts:131-143`；实际门执行在 `DevFrameSessionJournal.append` 内部（`session-journal.ts:107-111`，decode 之后、append 之前 `requireReviewer`）。

### 1.2 写入面（唯一）

- `devframe/src/session-journal.ts:66-166`：`append`（:90-156）= 每 Session 串行尾部（:95-97）→ 失败 latch 检查（:98-105）→ schema 解码（:106）→ review 门（:107-111）→ `session.append`（:114-115）→ 持久化 flush（:117-123）→ 失败 latch（:124-134）。
- `DevFrameFlush = (session: Session) => Promise<boolean | void>`（:20）。

### 1.3 投影面

- `devframe/src/projection.ts:479-484`（`applyEvent` 分派 verification/review 等）与 `:512-521`（`devFrameProjectionDefinition` 的 init/apply 纯公开面）；消费入口 `ctx.sessionProjections.stateOf(session, 'devframe')`（`command-goal-binding/src/composition.ts:184`）。

### 1.4 消费面

- `command-goal-binding/src/composition.ts:184-201`：`stateOf`:184 → `failure` 检查:187 → `latestAttributedVerification`:188 → `latestReview`:193 → `CompleteGoalRequest`:195-201。
- `NO_VERIFICATION_TEXT`/`NO_REVIEW_TEXT`：`command-goal-binding/src/command.ts:33-38`。

### 1.5 诚实执行契约

- `devframe/src/required-checks.ts:43-56`（`RequiredCheckCommand`/`DevFrameRequiredCheck`：executable+arguments+cwd+checkId）与 `:335-340`（`sameRequiredCheckCommand` 精确命令相等，无规范化）。
- `devframe/src/events.ts:442-481`（`verificationEventSchema` superRefine：status 与逐 check 一致 :446-452、digest 自洽 :463-469、声明 check 被逐字执行 :470-480）。
- 模型零写 = `s4-toolface-plan.md` §3 规则 4（`.agents/devframe/integration/s4-toolface-plan.md:47`）：提交/验证事实由宿主从真实进程与 git 观测采集后落账。

### 1.6 残余归属

- `agent-evidence/tests/at105-rejection-matrix.spec.ts:29`：错审查者变体的残余 = "生产组合接线归 P23/S4 工具面" —— 即本波收口对象。

### 1.7 组合注入边界

- `composition.ts:48-54`（`GoalBindingCompositionStores` 可替换注入）与 `:108-109`（默认内存参考实现 `MemoryGoalBindingStore`/`MemoryRequiredChecksConfigStore`）。GoalStore 波在飞交付 durable 绑定存储，接口已固定；本波用现有注入点，不做 durable 集成。

## 2. 本波新增核实（设计输入）

### 2.1 组合构造点

- `GoalBindingComposition` 构造器 `composition.ts:102-118`：投影注册 :110、`/goal-complete` 注册 :111-117（effect 包裹）、stores 装配 :108-109。producer（`AgentEvidenceJournal`）在此扩展构造。
- 函数插件入口 `index.ts:52-57`（`apply` → `new GoalBindingComposition(ctx, resolveCommandGoalBindingConfig(config))`）；`inject = ['commands', 'goals', 'sessionProjections']`（`index.ts:40`）——本波需增 `'sessions'`（flush 接线，见 2.2）。

### 2.2 flush 时机与签名

- `ctx.sessions.flush(session): Promise<boolean>`（`packages/core/session/src/index.ts:1086`）——与 `DevFrameFlush`（`session-journal.ts:20`）结构兼容，直接以 `session => ctx.sessions.flush(session)` 接线。
- 时机：`DevFrameSessionJournal.append` 每条事件后逐条 flush（`session-journal.ts:117`），无批量窗口；组合无需额外 flush 编排。

### 2.3 live 角色权威

- `EvidenceReviewerDirectory.roleOf(sessionId) → 'controller' | 'lead' | 'worker' | 'reviewer' | undefined`（`agent-evidence/src/review-gate.ts:27-34`）。
- 投影状态 `state.rolePolicy` = 最新 `devframe/role-policy` 事件快照（`projection.ts:37`；`applyRolePolicy`:341-356；`applyReview` 校验 policyVersion 与 reviewer assignment：433-438）。
- 结论：组合以 `stateOf(controllerSession, 'devframe').rolePolicy.assignments` 实现目录 = 日志派生的活权威（journal.ts:37-38 注释明示 "SessionId-keyed reviewer role authority; wired into the journal's review gate" 的宿主接线义务）。
- 投影约束：controller 角色必须 = 投影拥有会话（`projection.ts:334-336`）；每 Session 至多一角色（:331）；role 词汇 `DevFrameRole = 'controller' | 'worker' | 'reviewer'`（`events.ts:70`）。

### 2.4 生产事件序约束（折叠合法性）

- `applyVerification` 需先存 `devframe/goal-binding` 事件（`assertResultBinding`:272-283 经 `bindingFor`:251-253）。
- `applyReview` 需先存 role-policy（:433-438）且存在同 snapshotId+同 goalId 的 verification（:440-443）。
- 故生产落账序必须：`devframe/role-policy` → `devframe/goal-binding` → `devframe/verification`（→ `devframe/review`，本波不产）。
- `sameResultTuple` 不比较 goalRevision（`projection.ts:239-248`）——resume 后 revision 前移不破坏后续证据折叠。
- role-policy 重复落账规则（`applyRolePolicy`:344-353）：同 version+同 config+同 assignments = "recorded twice" 拒；同 version 不同 config = "changed its tool configuration" 拒；不同 version 或仅 assignments 变化 = 合法替换。

### 2.5 现生产缺口实证（GAP 的精确形态）

- `command-goal-binding/tests/real-composition.spec.ts:217-233` `appendEvidence` 注释原文："The production producers are deferred, so the test is the producer" —— 测试替生产者做 5 件事：`requiredChecksStore.save`:227、role-policy:228、goal-binding:229、verification:230、review:231。
- `startBinding`（`composition.ts:130-141`）只写 `GoalBindingStore`，不落会话日志：`GoalBindingController.start`（`devframe/src/controller/goal-binding.ts:423-485`）全程无 journal append —— hostcmd gapLedger "journal binding log deferred with start lane" 确认，本波 start 车道补上。

### 2.6 跨重启语义（resume 路径）

- `GoalService` "backed exclusively by the owning session log"（`packages/goal/goal/src/index.ts:279-281`；`goalProjectionDefinition`:165-172；`state()`:546-551 经 `sessionProjections.stateOf`）——goal 状态随会话日志持久，重启后由投影重建。
- activation 进程本地：`agent/session-start` 后 disarmed（:295-297），`resume` 重臂（:401-420，revision 恰 +1）。
- 会话恢复原语：`sessions.prepare(id, {seed, meta, inheritedEventCount, seedSource: 'persistence'})`（`packages/core/session/src/index.ts:927-953`，`Session.fromRestore`:936-938）；持久化服务 `prepare`（`packages/session/session-persistence/src/index.ts:207-221`）；生产恢复入口 `ctx.agents.resume({resumeSessionId})`（`packages/core/agent-loop/tests/resume.spec.ts:150-153` 先例）。
- 投影惰性重建：`cellFor` 折全量 in-memory log（`packages/session/session-projection/src/index.ts:614-629`）——恢复会话首次 `stateOf` 即从日志重建投影。
- `GoalBindingController.resume`（`controller/goal-binding.ts:495-542`）：需 native goal 当前且 revision ≥ binding（:502-515）、native resume +1（:523-531）、saveBinding（:537）、admission open（:539）。

### 2.7 指纹计算面（start 的宿主采集）

- `computeSourceFingerprint({worktreePath}) → ComputedSourceFingerprint`（`devframe/src/source-fingerprint.ts:156-229`）；fingerprint = `dsh-source-fp-v1-<headCommit>-<trackedStateHash>`（:225）。`verifySourceFingerprint` 为 admission 消费面（`controller/goal-binding.ts:896`）。

### 2.8 依赖面（预登记边界事实）

- `command-goal-binding/package.json:23-45`：**agent-evidence 非现有依赖**。构造 `AgentEvidenceJournal`/`EvidenceReviewGate` 必须新增 `"@deepseek-ai/dsh-experimental-agent-evidence": "workspace:^"`（dependencies + devDependencies），连带：
  - `pnpm-lock.yaml` importers 段机械新增（`pnpm install` 后果）；
  - 包内 `tsconfig.json` references 增 `../agent-evidence`（现为 devframe 一行，`tsconfig.json` references 列表）；
  - `tsconfig.base.json:235` 已有 agent-evidence alias，无需改。
- 先例：hostcmd 波同构事实（新包依赖的 "lockfile install consequence"）被总控接受并入 `d000c84ca5`（登记册 controllerGates："18 files 0 forbidden zone (new private package … + tsconfig.host.json 1 line + lockfile install consequence)"）。本波按同口径预登记为受控偏差：lockfile diff 必须仅为该依赖的 importers 机械行，零无关解析漂移。

### 2.9 组合不变量：agent.id === session.id

- `completeCurrent` 以 `ControllerSessionId(agent.id)` 查 store、以 `agent.session` 查投影（`composition.ts:179-184`）；投影 `assertResultBinding` 校验 `binding.controllerSessionId === state.controllerSessionId`（= header.id，`projection.ts:273-275`）。组合既已依赖该不变量（hostcmd 波建立），本波 start/resume 沿用；真实宿主 `agents.create({sessionId})`/`agents.resume` 亦满足。

## 3. GAP 语义精化（review 生产路径不在本波）

- `s4-toolface-plan.md` §4.3/§4.4（:79、:94）：`project_review` 是 S4 工具面的审查者模型工具；review 是独立 reviewer 角色的判定动作，不是宿主可采集的进程/git 事实。
- 裁定：`/devframe-start` 只产 verification 证据（真实子进程执行）；不伪造任何 review 决策（AT1-05 三谓词独立性——预填 review 会掏空第三谓词）。start 后 `/goal-complete` 读到真 verification 证据、至 review 门返回 `NO_REVIEW_TEXT` 是诚实状态，不是本 GAP 的"无证据"症状复现（GAP 症状 = 无任何生产路径能产出证据）。

## 4. 与预授权决策的关系

- 决策 1（沿用 /goal-complete 命令面先例）：确认可行，全部先例锚点在 `command.ts` / `index.ts` / `real-composition.spec.ts`。
- 决策 2（命名 `/devframe-start` / `/devframe-resume`）：核实命令注册名空间无冲突（现存注册命令 `goal`/`compact`/`feedback`/plan-mode/session-log-export/permission-presets 族，s4-toolface-plan.md:26；`/project` 前缀保留给 P04 命令面——本波 devframe 前缀与其不相交，且明确不占用 `project_*` 任何动词）。维持建议命名。
- 决策 3（composition.ts 既有组装处扩展）：确认构造点在 `composition.ts:102-118`；live 角色权威以投影 rolePolicy 落实（§2.3）。
