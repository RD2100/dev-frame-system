---
description: v14-compos 波组合闭合 + /devframe-start 与 /devframe-resume 宿主命令面定稿设计：构造 AgentEvidenceJournal+CheckRunner、flush 与 live 角色权威接线、start/resume 命令面沿 /goal-complete 先例、具名最小文件清单与受控偏差登记。
---

# v14-compos 组合闭合 + start/resume 宿主命令面（design）

- 定稿人：v14-compos 插件接入组长（接替组长，树 `D:/dsh-devframe-v14-compos2-lead`，分支 `codex/v14-compos2-lead`）。
- 归属声明：本设计继承前任组长 dd23ebdd 的接口核实 findings（`findings.md`，提交 8ae99ffc29）；前任已停止并封存，其产物原样继承，本文件为接替组长定稿，不伪造归属。
- 基点：前任分支尖端 8ae99ffc29（与主树 HEAD c79f85fb81 之上的 findings 提交一致）。
- 日期口径：2026-09-06（v14 台账 speed-up round 之后）。

## 0. 范围与零触碰

- 写域（Worker 唯一写域）：`packages/experimental/command-goal-binding/**`（src + tests + README + package.json + tsconfig.json）与 `.agents/devframe/v14-compos/worker/**`；外加第 6 节登记的 `pnpm-lock.yaml` 受控偏差行。
- 零触碰（消费导出，不改文件）：`packages/experimental/devframe/**`、`packages/experimental/agent-evidence/**`、shadow-router、project-memory、vendor、snapshots、scripts、`.agents/devframe/v14/next/**`、主树 `D:\dsh-devframe`、其他链 worktree、历史 `D:/dsh-devframe-p-*`。
- 禁：push / PR / 发布 / 删文件 / 合并 main / 创建任何 Agent / 重复派发。

## 1. 锚点复核结论

本组长对前任 findings 的三个关键锚点做了独立主树只读复核，全部确认：

1. **组合组装点**：`command-goal-binding/src/composition.ts:102-118` —— `GoalBindingComposition` 构造器内 `super(ctx, 'commandGoalBinding')`:107、stores 装配:108-109、`ctx.sessionProjections.register(devFrameProjectionDefinition)`:110、`/goal-complete` 经 `ctx.effect(() => ctx.commands.register(...), 'command-goal-binding.register')`:111-117。生产者构造与新命令注册在此扩展。`startBinding`:130-141 只走 `controller.start`，全程无 journal 落账（GAP 本体，与 findings §2.5 一致）。
2. **flush 时机与签名**：`packages/core/session/src/index.ts:1086` —— `ctx.sessions.flush(session): Promise<boolean>`，THE flush 入口；与 `DevFrameFlush = (session) => Promise<boolean | void>`（`devframe/src/session-journal.ts:20`）结构兼容。`DevFrameSessionJournal.append` 每条事件后逐条 flush（session-journal.ts:117），无批量窗口，组合无需额外编排。
3. **live 角色权威（s4-toolface-plan §3 规则 4，:47）**：模型不可写原始证据；提交/验证事实由宿主从真实进程与 git 观测采集后落账。journal 的 review gate 义务 = "SessionId-keyed reviewer role authority; wired into the journal's review gate"（agent-evidence/src/journal.ts:37-38 注释 + review-gate.ts:22-34 的宿主接线说明）。落实方式见 §2.3。

其余锚点（生产者导出面、唯一写入面、投影折叠约束、事件序、跨重启语义、依赖面、指纹面）按前任 findings §1/§2 原样采信，不重复核实。接替后补核的两个新事实：

- `ctx.sessions.get(id): Session | undefined` 存在（`packages/core/session/src/index.ts:1119`）——角色目录可按 SessionId 反查 Session 再读投影。
- `admission_open` 可作日志首条生命周期记录（`projection.ts:312`：首记录接受 `ambiguous`/`admission_open`）——start 后落账 admitted binding 折叠合法。

## 2. 组合闭合设计

### 2.1 构造点扩展（composition.ts 构造器）

构造器内、`/goal-complete` 注册之后新增：

- **flush 闭包**：`const flush: DevFrameFlush = session => ctx.sessions.flush(session)`（§1 复核 2）。
- **live 角色权威目录**（§2.3）。
- **组合自有 `DevFrameSessionJournal`**（`@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts` 导出，经包 exports `./src/*` 消费）：构造 `(flush, new EvidenceReviewGate(directory))`，承担 role-policy 与 goal-binding 记录落账（AgentEvidenceJournal 只暴露 recordVerification/recordReview，无通用 append 面，且 agent-evidence 零触碰，不能加注入）。
- **`AgentEvidenceJournal`**（`@deepseek-ai/dsh-experimental-agent-evidence` 导出）：`new AgentEvidenceJournal({ flush, reviewerDirectory: directory })` —— 不传 `execution`，默认 `subprocessRequiredChecksExecution`（即总控链所称 CheckRunner 真身，`check-runner.ts:96-98` 默认 10 分钟 kill guard）。构造即接线 review gate，缺目录即构造失败（journal.ts:85-88），满足 p05harden"未接线 = 构造失败"。
- **两条新命令注册**：`ctx.effect(() => ctx.commands.register({...devframeStartDescriptor(), handler}), 'command-goal-binding.register-start')` 与 `...register-resume`，沿 `/goal-complete` 先例（单次激活注册、effect 包裹、dispose 即消失）。

### 2.2 双 journal 实例与 latch 语义（如实登记）

组合自有 journal（policy/binding 落账）与 AgentEvidenceJournal 内部 journal（verification 落账）是两个实例，各自持有 per-Session 失败 latch（session-journal.ts:68）。同一 flush 闭包下，理论上可能出现"一个实例 latch 而另一个未 latch"的窗口。fail-closed 性质不变：每个实例各自阻塞后续写入并抛 `DevFramePersistenceError`，结构性错误照常传播。登记为已知限制（§10），不在本波改 agent-evidence 注入面。

### 2.3 live 角色权威 = 日志派生

`EvidenceReviewerDirectory.roleOf(sessionId)` 实现（`src/host-evidence.ts` 新模块）：

1. `ctx.sessions.get(sessionId)` 反查 Session；无会话 → `undefined`（fail-closed：未绑定即无角色）。
2. `ctx.sessionProjections.stateOf(session, 'devframe')` 读投影；`state === undefined` → `undefined`。
3. `state.rolePolicy?.assignments.find(a => a.sessionId === sessionId)?.role ?? undefined`（DevFrameRole = 'controller' | 'worker' | 'reviewer'，events.ts:70，直接透传）。

满足 journal.ts:37-38 的宿主接线义务：目录权威来自会话日志投影（role-policy 事件快照），不是宿主内存另册。start 车道先落 role-policy（§3 步骤 5a），此后任何 review 提交（本波不产，未来波）都经此目录授权。

## 3. `/devframe-start` 命令面

### 3.1 语法与输入

- 命令名 `devframe-start`，hint `[<objective>]`，description 'start a new bound goal and produce real verification evidence'。
- 整段 trim 后余文 = objective（路径可含空格的先例沿用：整体一个参数）；空 → 稳定数据错误 `START_OBJECTIVE_REQUIRED_TEXT`。
- worktree 只取 `config.workspaceRoot`（激活时已校验绝对路径）；缺 → 稳定数据错误 `START_WORKTREE_REQUIRED_TEXT`。本波不支持命令行覆盖 worktree（objective 与路径无法无歧义拆分；可逆决策，记录于 §9）。

### 3.2 宿主采集（规则 4：模型零写）

| 绑定字段 | 采集方式 |
| --- | --- |
| objective | 命令行（人类输入即批准行为，command/run 事件留痕） |
| sourceFingerprint | `computeSourceFingerprint({ worktreePath })`（devframe/src/source-fingerprint.ts:156-229，真实 git 三子进程） |
| snapshotId | 由指纹派生：`DevFrameSnapshotId('snapshot-v1-' + computed.headCommit + '-' + computed.trackedStateHash)`，确定性、可复现，精确描述被指纹刻画的树状态 |
| acceptanceHash | sha256（node:crypto）over 显式字段序规范化 JSON `{ objective, version, checks[] }`（approved config 的 checkId/executable/arguments/cwd 按声明序），十六进制小写 |
| taskIds / maxAttempts / maxGoalRounds | Config 字段（§5；部署可变项走 Config，禁硬编码） |
| confirmationId | 处理器内铸 `devframe-start:<sessionId>:<epochMs>`（每次调用唯一、command/run 日志可审计；授权只在命令适配器内、人类调用时铸造，模型输入永不满足） |
| approved checks config | Config `checks` 字段；start 时 `requiredChecksStore.save(config)` 后取 `requiredChecksDigest`（保存幂等） |

### 3.3 执行序（处理器）

1. 解析 objective → 空则数据错误。
2. `config.workspaceRoot` 缺 → 数据错误。
3. `ctx.goals.get(agent)` 存在且 phase ≠ 'complete' → 稳定数据错误 `START_GOAL_RUNNING_TEXT`（控制器自身 `GOAL_BINDING_ALREADY_RUNNING` 守卫保留为结构性后备，纵深防御）。
4. `computeSourceFingerprint`（`SourceFingerprintError` 结构性传播）。
5. `startBinding`（既有车道，authorization 在此铸造）→ 得 admitted binding（lifecycle='admission_open'，revision=created+1）。
6. journal 落账（组合自有 journal，逐条 flush）：
   a. role-policy —— 仅当投影 `state.rolePolicy === null` 时落账（幂等：同 version 重复落账会被折叠拒"recorded twice"，projection.ts:349-353）。记录：`{ version: 1, workspaceId, controllerSessionId: session.id, policyVersion: 'policy-' + workspaceId + '-v1', config: { controller/worker/reviewer 各空策略 }, assignments: [{ role: 'controller', sessionId: session.id }] }`（controller 必须为属主会话，events.ts:340）。
   b. goal-binding —— 原样落账 admitted binding（GoalBinding 即事件载荷，先例 real-composition.spec.ts:229；首记录 admission_open 折叠合法，projection.ts:312/367）。
   c. verification —— `evidenceJournal.recordVerification({ session, binding: resultTupleOf(admitted), requiredChecksDigest, requiredChecksStore })`。真实子进程执行，四态如实落账：status='failed' 不是命令错误，命令仍成功（诚实证据；`GoalResultBinding` = binding 的 controllerSessionId/goalId/goalRevision/taskIds/acceptanceHash/workspaceId/sourceFingerprint/snapshotId 八元组，先例 resultBindingOf）。
7. 成功文本：stage 形状、零 opaque id（不含 goalId/snapshotId/verificationId/指纹/confirmationId），报告真实执行 check 数与 verification status。

### 3.4 错误面

- 显式数据错误（`{ kind: 'error' }`）：objective 空、worktree 缺、goal 已在跑。
- 结构性 fail-closed 传播（不转换）：`SourceFingerprintError`、`RequiredChecksError`（config 未注册/schema 失败）、`DevFramePersistenceError`（flush 失败/no backend/latch）、`GoalBindingError`（控制器后备守卫、身份/修订异常）。
- 部分失败窗口（start 已建 native goal + store 绑定、日志落账失败）：本波不自动修复，fail-closed 抛出；resume 车道提供修复面（§4 步骤 4）；登记 GAP（§10）。

## 4. `/devframe-resume` 命令面

### 4.1 语法

- 命令名 `devframe-resume`，hint 空，description 'resume the current bound goal after a stop or restart'。
- 非空余文 → 稳定数据错误 `RESUME_INPUT_UNEXPECTED_TEXT`（显式拒绝优于静默忽略）。

### 4.2 执行序（处理器）

1. `current = ctx.goals.get(agent)`：无 → 数据错误 `RESUME_NO_CURRENT_GOAL_TEXT`；phase='complete' → 数据错误 `GOAL_ALREADY_COMPLETE_TEXT`（复用）。
2. 读投影 `state.bindings` 与 store `bindingStore.load(controllerSessionId)`，按 `goalId === current.id` 对齐：
   - store 缺、投影有（**跨重启恢复路径**：MemoryGoalBindingStore 进程本地，重启后空；投影由日志惰性重建，projection.ts bindings 全量折叠 goal-binding 事件）→ `bindingStore.save(投影绑定)`（save 幂等，goal-binding.ts:155-173）。
   - 投影缺、store 有（**start 部分失败修复面**）→ 组合自有 journal 落账 role-policy（若缺）+ goal-binding（store 绑定，first-record admission_open 合法）。
   - 两者皆缺 → 数据错误 `RESUME_NO_BINDING_RECORD_TEXT`。
3. 恢复性驱逐：若步骤 2 实际写入了 store 且 `controllers` 已缓存该 agent 的控制器（其绑定缓存于构造时装载，goal-binding.ts:385，无法外部刷新）→ `controllers.delete(agent.id)` 后走 `controllerFor` 重建（新控制器装载含恢复绑定的 store）。驱逐仅发生在重启后 admission 本就 closed 的窗口，安全。
4. `controllerFor(agent).resume({ controllerSessionId: ControllerSessionId(agent.id), goalId: current.id }, createHumanAuthorization('devframe-resume:<sessionId>:<epochMs>'))`。控制器约束按 findings §2.6 原样：native goal 现行且 revision ≥ binding、native resume +1、saveBinding、admission open。
5. journal 落账 resume 返回的 admitted binding（revision 前移、lifecycle 仍 admission_open → 折叠合法：revision ≥ prior 且非全等三元组，projection.ts:377-387）。保持"日志 = 持久权威"（模型可见 ⟺ 已记录），下次重启的投影与 store 重建一致。
6. 成功文本：stage 形状、零 opaque id。

### 4.3 错误面

- 显式数据错误：无现行 goal、goal 已完成、无绑定记录（投影与 store 皆缺）、非空输入。
- 结构性传播：`GoalBindingError`（native 身份/修订/phase 异常、GOAL_BINDING_NOT_FOUND 等）、`DevFramePersistenceError`、`RequiredChecksError`/`SourceFingerprintError`（resume 不产证据，理论上不触达，传播面保持开放）。

## 5. Config 扩展（config.ts）

`CommandGoalBindingConfig` 新增（全部激活时响亮校验，misconfiguration fails loud）：

- `checks: DevFrameRequiredChecksConfig` —— 人工批准的必需检查清单（版本 1、checks 数组非空、executable 非空、arguments 字符串数组、cwd 绝对路径）。启动时注册进 `requiredChecksStore`（批准时点 = 部署批准 + start 注册）。
- `taskIds: string[]` —— 非空、逐项 trim 后非空、去重。
- `maxAttempts: number` —— 正整数（`GoalBudgetInput.maxAttempts`）。
- `maxGoalRounds?: number` —— 可选正整数。

`ResolvedCommandGoalBindingConfig` 相应携带 branded/规范化值（`WorkspaceId` 既有；checks 为校验后的只读配置；taskIds 为 `TaskId[]`）。Config schema（schemastery）同步扩展；`resolveCommandGoalBindingConfig` 补校验（沿用既有响亮 TypeError 风格）。

## 6. 依赖面（受控偏差，预登记）

按前任 findings §2.8 与 hostcmd 波 d000c84ca5 先例（"new private package … + lockfile install consequence" 被总控接受）同口径登记：

1. `packages/experimental/command-goal-binding/package.json`：`dependencies` + `devDependencies` 各增 `"@deepseek-ai/dsh-experimental-agent-evidence": "workspace:^"`（src 运行时构造 AgentEvidenceJournal/EvidenceReviewGate → 必须是真实依赖，非仅 dev）。
2. `packages/experimental/command-goal-binding/tsconfig.json`：`references` 增 `"../agent-evidence"`。
3. `pnpm-lock.yaml`：**受控偏差** —— 仅允许 importers 段 `packages/experimental/command-goal-binding` 块新增该依赖的机械行（dependencies/devDependencies 各一行）；零无关解析漂移。Worker 以 `pnpm install` 生成后须自证 diff 范围，`pnpm install --frozen-lockfile` 复验 exit 0。
4. `tsconfig.base.json` 零改动（agent-evidence alias 已在 ：235）。

## 7. 具名最小文件清单

| 文件 | 变更 |
| --- | --- |
| `packages/experimental/command-goal-binding/package.json` | +agent-evidence 依赖（§6.1） |
| `packages/experimental/command-goal-binding/tsconfig.json` | +references ../agent-evidence（§6.2） |
| `pnpm-lock.yaml` | importers 机械行（§6.3 受控偏差） |
| `packages/experimental/command-goal-binding/src/config.ts` | Config 扩展 + 响亮校验（§5） |
| `packages/experimental/command-goal-binding/src/command.ts` | start/resume descriptor、稳定数据错误文本、输入解析、成功渲染（零 id 泄漏；沿 goalCompleteDescriptor 先例） |
| `packages/experimental/command-goal-binding/src/host-evidence.ts` | **新增**：flush 闭包、投影派生 `EvidenceReviewerDirectory`、role-policy/goal-binding 落账 helper（§2.2/§2.3/§3.3.6/§4.2.2） |
| `packages/experimental/command-goal-binding/src/composition.ts` | 构造 AgentEvidenceJournal（默认 CheckRunner）+ 组合自有 journal、注册两条命令、start 车道补日志落账、resume 车道（restore/repair/驱逐/落账） |
| `packages/experimental/command-goal-binding/src/index.ts` | `inject` 增 `'sessions'`；导出新命令面符号 |
| `packages/experimental/command-goal-binding/tests/start-resume-composition.spec.ts` | **新增**：§8 测试计划 |
| `packages/experimental/command-goal-binding/tests/real-composition.spec.ts` | 仅注释更新：appendEvidence 的 "The production producers are deferred" 过时（start 车道已补），改为指明该手工 append 是 /goal-complete 错误面测试的装配手段；测试行为零变更 |
| `packages/experimental/command-goal-binding/README.md` | 命令面文档 + `## Known Limitations and Deferred Work`（§10 GAP） |
| gen-cordis-catalog 产物 | 若 src/index.ts 导出面变化触发（§8 门禁 3），生成文件 diff 随附 |

预期之外的新文件一律视为越域。

## 8. 测试计划（新 `tests/start-resume-composition.spec.ts`）

REAL-composition 标准沿 real-composition.spec.ts boot 先例（native SessionStore + JsonlSessionPersistence + CommandRuntime + AgentRegistry + SessionProjectionRegistry + GoalService + 本插件；stubAgent 精确身份）。必需检查用真实快速子进程（如 `node -e "process.exit(0)"` / 退出 1 变体），配 `createCommittedWorktree` 先例提供真 worktree。

1. **start 产真证据**：`/devframe-start <objective>` → 成功；日志含 `devframe/role-policy`（controller 指派属主会话）、`devframe/goal-binding`（admission_open）、`devframe/verification`（真实退出码 0、精确命令面、声明 check 逐字执行）；`/goal-complete` 读到真 verification 证据、至 review 门返回 `NO_REVIEW_TEXT`（诚实状态，findings §3）。
2. **verification failed 诚实落账**：checks 含退出 1 变体 → verification status='failed' 落账、命令仍成功；`/goal-complete` 在 required-checks 门拒绝（REQUIRED_CHECKS_NOT_PASSED）。
3. **resume 跨重启续跑**：同 persistence root 二次 boot（新 Context + 全插件栈 + `sessions.prepare(id, { seedSource: 'persistence', ... })` 恢复会话，参照 session-persistence prepare :207-221 与 agent-loop resume.spec.ts:150-153 先例）→ `/devframe-resume` → 成功；goal 投影恢复现行、admission open、store 重建绑定、日志再落 goal-binding（revision+1）；随后 `/goal-complete` 仍读 pre-restart verification（sameResultTuple 不比 revision，findings §2.4）。
4. **start 数据错误**：objective 空、无 workspaceRoot、goal 已在跑 → 稳定文本且零结构副作用。
5. **resume 数据错误**：非空输入、无现行 goal、已完成 goal、无绑定记录 → 稳定文本。
6. **结构性传播**：worktree 不可用 → `SourceFingerprintError` 传播；无持久化后端 → `DevFramePersistenceError('unavailable')` 传播（沿 real-composition 传播断言先例）。
7. **注册生命周期**：两条新命令 dispose 即消失（HMR 安全先例扩展）。
8. **配置响亮失败**：checks/taskIds/maxAttempts 缺失或非法 → 激活 reject。

门禁映射（Worker 收据逐项真实退出码）：

1. 触及包聚焦 vitest 全绿：`pnpm vitest run packages/experimental/command-goal-binding`（含既有 real-composition 与新 spec；组合接线 + start/resume 数据错误面全覆盖）。
2. 删全部 `*.tsbuildinfo` 后 `pnpm run build` exit 0。
3. `gen-cordis-catalog`（导出面变化时）exit 0、diff 仅生成物。
4. `git diff --check`（staged）exit 0；每文件恰一尾随换行。
5. `pnpm run test:docs` exit 0（15 门必跑）。
6. `pnpm install --frozen-lockfile` exit 0（受控偏差复验）。
7. git 提交一律 `--no-verify`（宿主无 bash），收据登记 skip + 上述替代验证。

## 9. 实现决策记录（总控预授权内落定，最小可逆）

1. `/devframe-start` worktree 只取 config（不支持命令行覆盖）——objective/路径无歧义拆分；可逆，后续可加显式 flag。
2. snapshotId 由指纹确定性派生（`snapshot-v1-<headCommit>-<trackedStateHash>`）——无快照捕获服务可消费，派生值精确描述被刻画的树状态且可复现。
3. acceptanceHash = sha256 over 显式字段序规范化 {objective, checks}——宿主计算的批准摘要；人类批准行为 = 命令调用本身（command/run 留痕）。
4. confirmationId 铸 `devframe-start|resume:<sessionId>:<epochMs>`——每次调用唯一、可审计；授权仅命令适配器铸造。
5. role-policy 条件落账（仅投影为空时）+ 确定性 policyVersion `policy-<workspaceId>-v1`——规避折叠 "recorded twice" 拒绝。
6. resume 落账 updated binding——保持日志为持久权威，跨重启一致。
7. 恢复性驱逐 stale controller——组合私有 map，驱逐仅限重启后 closed 窗口。
8. 双 journal 实例（组合自有 + AgentEvidenceJournal 内部）——agent-evidence 零触碰约束下唯一构造路径；latch 窗口登记 §10。
9. resume 非空输入 → 显式数据错误——显式优于静默忽略。

## 10. GAP 与已知限制（移交登记）

1. **review 生产路径不在本波**（findings §3 裁定维持）：`/goal-complete` 在 start 后到达 review 门返回 `NO_REVIEW_TEXT` 是诚实状态。
2. **start 部分失败窗口**：native goal + store 绑定已建、日志落账失败时本波不自动回滚；resume 的 repair 面（§4.2.2 投影缺/store 有分支）提供人工恢复路径；持久化失败 latch 后组合自有 journal 阻塞后续写入。
3. **双 journal latch 窗口**（§2.2）：两实例 latch 状态理论上可分歧；fail-closed 性质不变。
4. **MemoryGoalBindingStore/MemoryRequiredChecksConfigStore 仍为内存参考实现**：跨重启绑定经日志投影重建（§4.2.2），durable store 集成归 GoalStore 波既有注入点（findings §1.7）。
5. role-policy 仅 controller 指派：本波无 reviewer 会话，review 授权面为空（fail-closed：任何 review 提交会被拒）；reviewer 指派归 review 生产波。
