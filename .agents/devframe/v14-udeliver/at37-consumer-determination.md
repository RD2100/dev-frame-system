# AT3-07 消费面与日志契约判定（B 线组长亲定，证据在案）

依据：`packages/experimental/project-memory/scenarios/AT3-07-vault-unavailable-degradation.md` 前提（宿主集成）+ 步骤 6——"警告 vs 失败"分级是**宿主装配面策略**，断言面是**会话日志事件**（录制布局：session.jsonl 含错误事件、警告事件与任务结果事件）；该场景开放问题自认"警告事件具体类型（宿主任务事件词汇）尚未存在"。

## 事实（全仓核实）

1. **任务旅程事件族唯一存在=devframe/***：`packages/experimental/devframe/src/events.ts` L253-276——role-policy/goal-binding/usage/verification/review/lifecycle 六种，声明合并进 SessionEventMap、zod 校验、可冷恢复。**无任何通用 `task/*` 事件**（全 packages grep 零命中）。
2. **memory 侧持久事实唯一=memory/receipt**（project-memory receipt-log；失败 append 不落 receipt——failure.spec L49-58 已证）。任务警告的**生产消费者今天不存在**。
3. **project-controller 任务板**：complete(taskId)/fail(taskId, 三元组) 是完成/失败两个既有权威入口；TaskRecord 无警告字段；板只负责状态/准入/持久化（README 职责）。

## 判定

- **警告的日志契约**：宿主装配层在完成决策点发**恰好一条**会话事件（类型名落位=场景开放问题，录制时绑定；归属包按事件语义定——任务旅程事件归 devframe 族或新的宿主装配事件声明，不由任务板持有可能性），payload 携带 taskId + 逐字 memory 失败码（'MEMORY_UNAVAILABLE'）+ 未保存标记。**永不**为失败保存发成功事件：memory/receipt 仍是保存成功的唯一事实（不重复 memory_saved）。
- **Model-visible ⟺ logged**：memory 工具错误本身已模型可见（tool result 事件在案）；分级决定是宿主决策，以新事件落日志满足录制重放断言（"恰一条警告事件"）。
- **A1/A2/A3 全部复用既有 complete/fail**：A1=宿主发警告事件 + `complete(taskId)`（板面无字段也成立——断言面是日志）；A2=无 receipt + 无成功声明事件（包级已成立）；A3=宿主走既有 `fail()`（三元组强制诚实，板面已支持）。
- **TaskRecord/共享契约扩展：现证据不支持，不动**（遵循总控修正：不改 project-contracts 与 taskRecordSchema）。任务意图（编码 vs memory-only）由宿主装配配置持有，不压成 code|memory 板面二选一；混合交付不丢信息。
- 仅当后续证据证明**任务板冷恢复必须重放警告**（板成为断言面），再提请总控裁定扩展。

## 后台追踪 Worker（补充接线点证据）

| 项 | 值 |
| --- | --- |
| SessionID | 4c7f3b68-cfa5-44db-91f4-92703b3442da（subagent 后台 run_in_background:true） |
| 继承账号 | 如实记录：随我当前路由（h2 / huoshan-2 · glm-5.3-flash）；429 有限退避 |
| worktree | `D:\dsh-udeliver-at37`（branch codex/v14-udeliver-at37，快进至 435a73c17a；只读，全部命令限定该 workdir） |
| 任务书要点 | 只读追踪 ①B2/B3 driver b2b3/b2b3verify 真实调用序 ②生产宿主链「任务开始→可选 recall→代码验收→候选摘要 append」（devframe /devframe-start 旅程 + memory 工具挂载 + receipt 日志）③现存任务结果事件消费者 ④产出=具体消费者+缺失接线点+TaskRecord 是否必须扩展的裁决建议；禁新框架、禁模型测试、零写入零提交 |
| 设计护栏（已入任务书） | 不压成 code|memory 二选一；不重复 memory_saved 事实（receipt 唯一） |

## Worker 追踪结果（已收敛，与上述判定合流）

- **链路现状**（文件+符号）：driver `b2b3` → `sessionController.create`（standard preset）→ `shadowRouter.openProject` → `/devframe-start`（command-goal-binding `startBoundGoal`：fingerprint→requiredChecks→`GoalBindingController.start`→落 role-policy/goal-binding/verification 三事件）→ 编码任务=真实 user message + goal-round-driver 续轮；memory 工具经 cordis 行挂载（shipped 默认 writeEnabled:false=MEMORY_UNAVAILABLE 面），receipt 成功才落且先于 `created`；验收 `/goal-complete` → `completeCurrent` → `GoalBindingController.complete` 准入 → `ctx.goals.recordReceipt` → `goal/change` receipt 事件。
- **缺失接线**：基础 SessionEventMap 无任务事件、全仓 `emit('task` 零命中、experimental 无任何 `tool/result` 消费者、project-controller 全程不在该链上（只被 agent-evidence 溯源账与 README 引用）。接线点=宿主装配监听器（cordis patch 行层，仿 goal-round-driver `ctx.on('session/event')`）折叠 `memory_*` 工具失败 → **恰好一条分级事件**（devframe/task-warning 形，declare-merge+zod 解码既有机制；原始失败已 Model-visible⟺logged，tool/result error {name,code} 在案，分级事件是宿主自有附加记录而非新模型可见输入）。
- **分级判别面（总控转达用户复核修正）**：~~shadow-router mode work|note 即任务形态缝~~ **不成立**——tools.ts:186 / service.ts:202 明文 work=调度 follow-up、note=静默输入，是**消息调度模式**而非代码任务 vs memory-only 验收目标。修正后判据：**显式宿主上下文**（具体任务验收目标 / 本次记忆操作是否必需）判定分级；禁止 mode=note 推断 memory-only、mode=work 推断可选记忆；测试必含反例（同为 work，一项记忆必需、一项可选，证明判别面独立于调度模式）；监听器只读消费，不改 shadow-router mode 语义。
- **裁决：TaskRecord 扩展不需要**——v14 生产链从不咨询 project-controller（devframe GoalBindingController 经 GoalServicePort 直绑 ctx.goals）；场景断言面是 session.jsonl。与组长亲定判定一致：宿主事件 + 既有 complete/fail 足够。
- 护栏维持：分级事件只载失败/警告，绝不载 memory_saved 成功事实（receipt 是保存成功唯一权威，场景步骤 5 回执 fault 子案已证）。
- Worker 全程只读零写入，失败命令为零（退出码 1 均为预期否定）；附注：glob 工具对两个存在模式误报 "No files found"，Worker 经 Get-ChildItem 绕行（工具异常，非 shell 失败）。

## 监听器片实现（总控令：宿主装配监听器片开立，我执行）

- **提交**：36a209f581（ProjectMemoryError extends HarnessError——tool 注册表只对 HarnessError 子类上浮 {name, code}，此前 memory 工具失败在 tool/result 事件上无分类可路由；类形状/名/码不变）+ 9931bfd868（devframe/task-warning 事件族扩展 + task-warning-listener 插件 + 分级纯函数 + 三断言测试）。
- **事件**：`devframe/task-warning`（version 1 / taskId 品牌化 / warning=封闭四成员保存退化词汇 MEMORY_UNAVAILABLE|WRITE_FAILED|RECEIPT_FAILED|APPEND_DISABLED / tool 名）；入 declare-merge map + zod 解码折叠（decodeDevFramePayload），durable 边界拒绝词汇外扩。
- **判据（修正后）**：显式宿主上下文 `ctx.devframeTaskGrading.declare(sessionId, {taskId, memory:'optional'|'required'})`；折叠只对 optional 落事件且每任务恰一条（去重）；required 与未声明均不落（保守默认，原始失败仍在 tool/result）。**mode 面零接触**（只读消费者，未写 shadow-router 任何语义）。
- **微任务延迟**：监听器在 tool/result 发布回调内不直接 append（嵌套发布危害），排队至 microtask 落盘。
- **测试**（3 例，断言面=会话日志+fold 单测）：A1 optional+真实 MEMORY_UNAVAILABLE（真实工具注册表+缺席 Vault）→恰一条警告、重试仍一条；A2 全程无 memory/receipt（receipt 唯一保存权威）；A3 同构 dispatch+required→零警告+grade=fail、未声明会话零事件；解码再品牌化+词汇外扩拒绝。
- **真实退出码**：片内 3/3 exit 0；devframe+project-memory 联合回归 **23 files / 261 tests passed exit 0**。路由：零模型调用（unit 层）；隔离 HOME 未涉及（无 boot；若需 boot，home 独立建禁 junction）。TaskRecord/project-contracts **零改动**。

## 监听器修复片（总控三条确定缺陷裁定，06dc601897）

- **①去重竞态**：原去重只查已落日志——drain 前同步落两条失败 tool/result 会产生两条警告。修复：入队时预占任务键（入队查"日志∪预占"，drain 只查日志——预占是监听器自己的，不得否决自己的落盘），补用例「两条失败先入队后统一 drain」恰一条。
- **②dispose 泄漏竞态**：pending 闭包捕获 session 且微任务晚于延迟派发的 disposed 通知。修复：drain 改宏任务调度 + 落盘前实时查 store 存活性（`ctx.sessions.get(id) === session`；挂载 context 已 inactive 视为不活，晚到计时器不抛）+ session/disposed 处理器与两级 disposer 清计时器/取消批次/清预占。补两用例「真实 store detach 后零 append」「插件 fiber dispose 后零 append」。为此插件声明 `inject: ['sessions']`，桶导出改为命名空间对象（函数改名会丢 inject——cordis 门禁实测）。
- **③真实消息形状缺陷**：监听器原读 `event.data.message.callId`——真实 ToolResultMessage 无此字段（call id 在 `message.source`），真实失败从未分级。修复：监听器读 `message.source.callId`；测试改用真实 `createToolResultMessage` 构造 fixture（id/role/source 齐），tool/call 行 arguments 为原始 JSON 串，outcome 类型对齐真实 ToolFailure（info 可选），结构化 error info 原样保留。
- **tsc 程序声明**：所跑程序为 **`tsc -b tsconfig.host.json`**（host 面，include 含 `packages/*/*/tests/**/*.ts` 即本 spec，references 含 devframe src），修复后 **exit 0**；该程序曾抓出 vitest 转译放行的 6 处 spec 类型错误，全部修复——vitest 转译≠tsc 程序，教训第三度坐实。
- **真实退出码**：监听器套件 **6/6 exit 0 零未处理错误**；联合回归 **23 files / 264 tests passed exit 0**；host tsc **exit 0**。路由：零模型调用；TaskRecord/project-contracts 零改动；未全仓 build。
- **边界如实标注**：required 纯函数返回 `grade='fail'` 仅为分级判定，**不替代实际任务失败验收**——真实任务失败路径（agent-loop 终态、goal 判定）尚未接线，本片不含；其余未完成的生产接线同此边界，暂不列缺陷。

## 原生 hook 真实补验（更正"宿主缺 bash"误判）

- **更正**：此前两笔提交（06dc601897/69381b5750）commit message 所写 "Hook skip: no bash on host" 为**误判**——宿主 bash 可用（GNU bash 5.2.37，临时副本 bash.exe + git usr/bin 前置 PATH）。今后不再把可用 shell 误判成宿主缺能力。
- **补验方法**：临时分支自 f46fe9f595 `cherry-pick --no-commit` 重放两提交的真实内容（暂存区=全部 6 文件，非空暂存），PATH 前置后真实 `git commit` 触发 lefthook pre-commit（临时提交 d862c99bf4，验后删支）。
- **逐项结果**（首轮 lint 抓出 spec L107 超 140 列——wrap 修复后重放）：✓ lint (staged)（oxlint --config .oxlintrc.staged.json，1.75s）✓ third-party notices（THIRD_PARTY_NOTICES.md 再生成）✓ whitespace（git diff --cached --check）✓ vendor manifest guard；(skip) translation pairing / archived agent notes（无匹配暂存文件，属 glob 无命中非跳过执行）；**HOOK-COMMIT-EXIT=0**。
- **既有证据维持**：264 tests / host tsc exit 0 不重跑（门禁未改动语义面）。

## mid-batch drain 生命周期补修（独立复核确定缺口，483c70f311）

- **缺口**：同 session 两条写同批待 drain 时，第一条 warning 的**同步** session/event 监听器可经 store 真实 detach 面（enter disposer→`detachRequested`→append finally 完成 `detachEntered`：store.delete+attachments.delete）把 session 拆除；原实现循环前只查一次存活，循环仍向已移出 store 的 session append 第二条 warning，且 pending 已删、session/disposed 找不到该批。
- **修复**：`mayAppend` 谓词（未 cancelled/未 disposed + `ctx.sessions.get(id)===session` + inactive context 视为不活）在**每次 append 前**重查；任何提前终止经 `releaseBatch` 释放整批预占键（已落键本已删，整批释放精确无副作用）；循环前检查复用同一谓词。已确认项（入队预占去重、真实 source.callId 链接）不动。
- **回归编排（总控四步，消除时序根因）**：①先取两次真实 dispatch outcome（无 result 排队即无计时器，await 间隙无从触发）；②注册 detach 观察者；③**无 await 连续** declare A→append A result→declare B→append B result（确保同批）；④drain 前断言 warning=0（证明确未提前 drain），await drain 后恰 ['task-f1']、killerRan=true。此前探针实测定位：初版编排首条排队后 await dispatch（真实 fs I/O 宏任务边界）会让首 timer 提前 drain——探针实证两写分属两批，按四步编排修正后同批成立。
- **真实退出码**：监听器套件 **7/7 exit 0**；host tsc（tsconfig.host.json，含本 src+spec）**exit 0**。路由：零模型调用；TaskRecord/project-contracts 零改动；不重复 264 全绿（范围限定）。

## grade=fail 消费联动片（总控"边界收口"裁定，571c05b3f9 + 0906e1d00a）

- **边界收口**：上文"监听器修复片"的边界注记（required grade='fail' 仅为纯函数判定、任务失败验收未接线）**已于本片闭合**——该注记保留为当时状态的历史记录，此后以本节为准。
- **分级持久化**（571c05b3f9）：`devframe/task-warning` 事件数据补 `grade` 字段（封闭二值 `complete-with-warning | 'fail'`，由既有 `gradeMemoryFailure` 纯函数从显式宿主声明产出）；监听器对 **required 判级也落事件**（恰一条，grade='fail'；此前 required 不落、只留原始 tool/result，goal 判定面无可消费证据）。未声明会话仍零事件；去重/存活/计时器机制未动；durable 解码拒绝判级外扩。
- **判定消费缝**（0906e1d00a）：`evaluateCompletionAdmission` 增 `taskWarnings` 证据面为**合取第一谓词**——grade='fail' 记录 → stage `'task-warning'` 拒绝（携带 warning/tool/grade），先于 fingerprint（纯内存、最廉、任务自身结局证据先于工作树证据）；`complete-with-warning` 与空证据不拒绝（optional 路径不回归）。`CompleteGoalRequest`/`GoalBindingController.complete` 透传；投影折叠 `state.taskWarnings`（同任务双记录 fail-loud）；`/goal-complete` 旅程只传归因于当前 goal 绑定 taskIds 的记录；`renderCompletionRejection` 增渲染臂。判定面即失败终态等价物：拒绝为数据、native Goal 未触碰（phase 不得 complete）、admission 关闭——原生 Goal 服务无 fail 动词，此为既有面内的真实失败路径。
- **持久化词汇洞补修**：`gen-persistence-catalog` 在监听事件并入 main 后未再生——KNOWN_SESSION_EVENT_TYPES 缺 `devframe/task-warning`，一方持久化后端将拒绝含该事件的日志。本片再生（known-event-types.ts + persistence-catalog.md，gen/verify exit 0）；另随 main 合并再生 agent-hierarchy 面文档（f7969c48db）。
- **测试**：事件 grade 断言（optional→complete-with-warning；required→恰一条 fail）；admission 拒绝例（fail 证据→拒绝且 native Goal 未触碰、admission 关闭；故意错 fingerprint 前置仍 task-warning 先拒；complete-with-warning→admitted 且完成）；投影 round-trip 折叠+重复 fail-closed；解码拒绝判级外扩。
- **真实退出码**：host tsc **exit 0**；受影响 7 文件 **82 tests exit 0**；devframe+project-memory 联合回归 **270 tests exit 0**；gen-persistence-catalog / verify-persistence-catalog / gen-cordis-catalog / verify-cordis-catalog 全 **exit 0**。路由：零模型调用；TaskRecord/project-contracts 零改动。
- **仍开放边界（如实）**：goal-round-driver 续轮面尚未消费 devframe/task-warning（完成判定拒绝已是任务真实失败终态；续轮驱动的停止/转向属后续片）；生产 journey 对 fail 终态后的人工 resume/修复环消费未接。

## 独立未完成项收口片（总控"恢复独立未完成项（不新增范围）"裁定，c4d05d66f9 + 51890974a8；已并入 main 4b3212719f）

上节两条"仍开放边界"于本片闭合；该行保留为当时状态的历史记录，此后以本节为准。

- **①续轮驱动消费**（c4d05d66f9，devframe 域内）：新插件 `devframe-task-fail-disarm`（src/task-fail-continuation.ts，inject agents/goals）在 session/event 面消费 `devframe/task-warning` grade='fail'，经**原生 goal port**（`ctx.goals.disarm`——goal-round-driver 遵从的同一张脸）解除驾驶 agent 的 armed active goal 自动续权：driver 不再预留新轮、排队续轮在 pre-step 失去 armed 前提、durable phase 保留给人工 resume。**driver 包零改动**——消费缝落在 devframe，driver 继续读本监听器改变的 goal 状态。complete-with-warning 刻意不动（容忍退化不停车）。disarm 收容在 try/catch：拒绝的 goal port 不得中止发布分级记录的 append（证据已 durable，人工 resume 是恢复路径；空 catch 已具名）。六用例：armed-active→disarm、容忍判级不动、非 armed/active 跳过、无 agent 跳过、拒收 port 收容且记录不丢、dispose 后停消费。
- **②fail 终态→修复环消费**（51890974a8）：`/goal-complete` 旅程对 task-warning 拒绝走新臂 `renderRejectedCompletion`——在 AT1-08 规定的 call point（changes_required 拒绝后回送工作）为 fail 终态**记一次修复环**（`beginRepairRound`）：准入→文本报告"Repair round N was charged (M remaining)"；耗尽→"repair limit (2) is exhausted after 2 charged rounds; continuing requires a human-authorized resume"。其余拒绝阶段渲染零变化（fingerprint 阶段反例断言文本无修复环字样）。controller 面未动：拒绝仍是纯数据，计费发生在回送工作的旅程。测试贯穿真实 composition：三轮 /goal-complete（round 1→2→耗尽）、goal 保持 active、零 receipt。
- **真实退出码**：host tsc **exit 0**；续轮消费套件 **6/6 exit 0**；real-composition **18/18 exit 0**；三包联合回归（devframe + command-goal-binding + goal-round-driver）**20 files / 308 tests exit 0**；gen/verify-persistence-catalog、verify-cordis-catalog 全 **exit 0**（无新事件类型、无新 service 面——纯监听器不设 ctx.* 缝，无需目录分类）。路由：零模型调用；TaskRecord/project-contracts 零改动；project-controller、profile/manifest/catalog、已删 src 产物路径零触碰。
- **仍开放（如实）**：修复环的 worker 侧回送（谁把 round 送回同一 worker）属编排域后续片；人工 resume 的原生面（goals.resume）本片未包测试（既有原生服务面，非本域新增）。

## 实装缺口补验片（总控转达独立同步审查"taskFailDisarm 未真实挂载"，4bd6345064；已并入 main dc118b84f5）

独立审查属实：上节①的 disarm 监听器（以及 graded 监听器本尊——同缺口）仅 barrel 导出+自身单测挂载，**生产宿主零挂载**，合并说明的"fail→driver disarm"不能标生产闭合。本片补验后该面才真闭合。

- **①真实挂载**（4bd6345064）：`GoalBindingComposition` 构造器（command-goal-binding 组合内，devframe 插件族的宿主装配点）经 `ctx.plugin` 在组合 fiber 上挂载两个监听器——graded 监听器（首次真实挂载）+ fail-disarm 监听器——**同进同出**（组合 fiber 生命周期）；无新 Loader 行、零 profile/manifest/config 写。挂载形状=模块命名空间（name/inject/apply）；直连 src 路径导入命名空间对象即 barrel 命名空间再导出所期望的形状（曾因按命名导出导入触发模块加载失败→Loader 报 invalid plugin，组合测试钉住）。
- **②真实 Loader 组合验证**（A2 loader-composition 模式，devframe/tests/loader-composition.spec.ts）：cordis.yml 全栈（session、llm、jsonl 持久化、投影、system-prompt、tools、agent、agent-loop、commands、原生 goal 服务、project-memory 缺席 Vault、command-goal-binding、goal-round-driver）经真实 Loader 引导、零未挂载行。三断言：真实 memory_append（缺席 Vault）→ 经挂载的 graded 监听器落恰一条 fail 记录 → armed goal 经原生 port 实际 disarmed（phase 保留）；容忍判级 complete-with-warning → goal 保持 armed；已 disarmed 的 goal → 分级证据照常落日志、goal 态不触碰（守卫路径）。
- **如实标注**：port 拒收收容语义仍在单测层钉住（对活 GoalService 同步派发窗内构造不出真实拒收，守卫路径即组合层的等价面）；零模型调用（无配置 agent、无轮次执行——真实 driver 在栈内但无可驱动面）。
- **真实退出码**：host tsc **exit 0**；Loader 组合套件 **3/3 exit 0**；三包联合回归 **21 files / 311 tests exit 0**；verify-persistence-catalog、verify-cordis-catalog **exit 0**。路由：零模型调用；TaskRecord/project-contracts 零改动；project-controller、profile/manifest/catalog 零触碰。
