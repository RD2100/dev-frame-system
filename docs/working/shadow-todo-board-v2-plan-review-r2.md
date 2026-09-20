# Shadow Todo 看板 v2 实施计划 r2 — 独立第三方复评意见

- 待审计划：`docs/working/shadow-todo-board-v2-plan.zh.md`（front-matter status: draft-plan-r2，§3 逐条回应表）
- 上轮意见：`docs/working/shadow-todo-board-v2-plan-review.md`（r1，判打回）
- 复评方式：两名评审员分别复核源码事实与 P1/P2 覆盖度，均读计划正文、不采信 §3 自述；关键行号与 r1 复核结果互证。
- 复评日期：2026-09-20
- **结论：打回（小幅修订，r3 收尾轮）。** r1 两条 P0 的方向均已修正且经源码核实成立；剩余缺口窄而明确（5 条 P1），不涉及架构调整。补齐后即可通过。

---

## r1 P0 复核结果

### P0-1（空 checkset）— 方向成立，方案 b 可行

作者改走方案 b：放弃空 checkset，种子一个非空 check `git diff --check`（cwd=worker worktree），devframe schema 不动。源码逐条核实：

- 拒点 `delivery-consumer.ts:206-207` 属实：`:206` 取 digest，`:207 if (rawDigest === undefined) throw 'Task has no host-approved checkset'`。
- cwd 校验 `:210-212` 属实：`for (const check of approved.checks)` 内 `:211 if (!isAbsolute(check.cwd) || await realpathNormalize(check.cwd) !== await realpathNormalize(initial.sourcePath))` → `:212 throw 'Approved checks must execute in the assigned Worker worktree'`。
- 执行点 `:266-267` 属实：`execFileAsync(check.executable, [...check.arguments], { cwd: check.cwd, ... })`。
- 种子 check 能过 schema：`required-checks.ts:69-77` 的 requiredCheckSchema 只要求 checkId/executable 为 trimmedString、arguments 为 string 数组、cwd 非空无空白；外层 `:84-90` 的 `.min(1)` 对 1 条 check 满足。"cwd 必须绝对"由 delivery-consumer:211 拦截，schema 不管。
- checkId 唯一性 refine（:86-89）作用域是单个 checkset 内部，每 task 注册 1 元素 checkset 恒满足。

**结论：方案 b 技术可行。** 但见下方 P1-1 的 cwd 归一化残留。

### P0-2（approveTask 绕过前置）— 抽取可行，两处残留

作者改为复用从 task-consumer 抽取的 `resolveTaskStartAuthority(ctx, controllerAgent, taskId)`，单一真值源；caller gate 声明为 host-plane 人类动作、Shadow 无批准工具、shadowAllowlistGuard 不动。

- 抽取结构上无障碍：authority()（task-consumer.ts:59-78）与 start 前置（:80-102）只依赖 ctx 服务；唯一工具层局部是 `exec.signal`（:60）与私有 `stopped` 闭包（:61），注入 no-op / isStopped 谓词即可，无任何断言依赖 tails/args/briefing。
- :88-102 命中即 throw 的约束、:103-111 的 signature 快照与 unchanged() 重比对，都能由 authority 返回值复现。
- 新引用行号全部准确（controller.ts:400-431、:131 BLOCKABLE_STATES、index.ts:91、task-consumer.ts:71 等均核实）；阶段 A 新增的 devframe/agent-evidence/project-contracts 三个 package.json 真实存在。

**结论：抽取方案成立。** 但见下方 P1-2 / P1-3 的两处残留。

---

## P1 — 本轮必须补（5 条，均为窄口增补，不改架构）

### P1-1　Q3 注册前必须对 cwd 做 realpath 归一化
- 依据：digest 算法对**字面量 cwd 字符串**哈希（required-checks.ts:309 `JSON.stringify({checkId, executable, arguments, cwd})`），而 delivery-consumer:211 运行时比较的是 `realpathNormalize` 后的值。本仓 worktree 走 junction（development-project.ts:71 `symlinkSync(..., 'junction')`），同一物理 worktree 若以不同字面路径注册，会算出两个 digest。
- 要求：Q3 写明 host 在 `store.save` / 算 digest / 注册之前，先对 worker worktree 路径做 `realpathNormalize`，对齐 :211 比较语义。否则重启或换字面路径重注册会分叉 digest、deliver 时判 stale。

### P1-2　Q1 host 侧 assign/startDevelopment 必须传 `{ beforePersist: unchanged }`
- 依据：task-consumer 真正把并发漂移复检咬在写边界的是 `assign(..., { beforePersist: unchanged })`（:113）与 `startDevelopment(..., { beforePersist: unchanged })`（:116）。计划 Q1 步骤 5 只写 `projectController.assign(worker.sessionId)` → `startDevelopment()`，未提 beforePersist。
- 后果：不传则 approveTask 只有"调用前一次性 check"，丢失 enqueue 内、persist 前的并发漂移复检（:104-111 的 unchanged 机制形同虚设）。
- 要求：host 侧两个调用同样传 `{ beforePersist: () => reCheck() }`（reCheck 即重调 authority 比签名）。

### P1-3　确认 typert 传输层对 approveTask 的 caller 鉴权，否则 RPC 内补校验
- 依据：新 RPC 暴露在 typert `shadow` namespace，与现有六方法同面；index.ts 现有方法体内**无任何 caller 身份校验**（requireRouter/requireConversationHost 只查服务在不在，不查谁调）。shadowAllowlistGuard（service.ts:78-84 markShadow 只装四个工具）只覆盖**模型工具白名单**，不覆盖 typert 通道。
- 后果："host-plane 人类动作"目前是约定而非方法内强制；任何能触达 `ctx.remote.shadow.approveTask(...)` 的 host 脚本/会话都能批准，不必用户点按钮。v1 #17"Shadow 自批绕过 gate"虽模型面堵住，typert 面仍可被任意 host 调用触发。
- 要求：要么确认 typert 传输层自身对 caller 做了鉴权并在计划中写明证据，要么在 approveTask 方法体内显式校验 host caller 身份。

### P1-4　#16 数据契约缺失：ShadowBoardSnapshot 无 branch/lastCommand 字段
- 依据：验收 #6（line 184）要求 building 卡片显示"当前 branch / 最近命令"，但阶段 C line 138 的卡片规格与 line 135 的 `ShadowBoardSnapshot` 字段（tasks + bindings + startReady + mounted）都没有这两项。
- 后果：验收要的 UI 元素没有数据源——readBoard 不采 branch/lastCommand，卡片无源可画。
- 要求：二选一——(a) 在 ShadowBoardSnapshot 加 branch/lastCommand 字段并定义 readBoard 如何采集（如对每个 developing task 的 worktree 跑一次 `git rev-parse --abbrev-ref HEAD`，最近命令从哪来需说明）；或 (b) 把 #16 从验收里撤掉，承认 v2 只显示状态列。

### P1-5　Goal 冷启动触发者需定一个，不要留冒烟临场挑
- 依据：阶段 B line 117 给了两条候选——"controller 自建 goal（create_goal）"与"host followup /devframe-start"，写"执行时冒烟选定"。但 Goal 是整个闭环的入口（task-consumer.ts:67-72 要求 admission_open + task 在 goal.taskIds 内）。
- 要求：送审前选定一条作为冷启动路径，另一条作为 fallback 写明触发条件；不要把入口选择留给实施时临场判断。

---

## P2 — 建议（不阻断，顺手修）

- **P2-1　"种子"术语统一**：Q3 标题（line 59）写"种子最小非空 check"，阶段 A line 103 却写 `requiredChecksByTask: {}（种子空，运行时经注册面写入）`。逻辑自洽（静态空 map + approve 时逐 task 注册非空 check），但字面"非空" vs "空"打架。建议统一为"静态 seed 为 `{}`，运行时按 task 注册唯一一条 git-diff-check"。
- **P2-2　其余三处"执行时选定"可保留为验证动作**：Shadow prompt 注入点（line 148，在 shadow-agent 还是桌面 preset）、project-contracts link 加不加按解析验证（line 97）、agent-dispatch 必要时 restate（line 98）——这三处影响面小、可由实施时一行验证定夺，不必现在拍死。
- **P2-3　#15 指标替换为已知偏离，接受**：review 字面要"token 超 N% 黄底"，v2 交付的是"等待/无进展 >30min 黄底"（基于 updatedAt），已在 §0/§7 明记为已知偏离。最低兑现（一张会变黄的等待卡）成立；提醒：v2 内无 token 维度提醒，后续 request-budget 落地时再补。
- **P2-4　readBoard 未挂载走降级而非 fail-loud，接受**：计划返回 `mounted:false` + 空 board（沿用 `ctx.get()` 可选取模式），对只读投影路径比硬 fail 友好，且 UI 可见（不是静默跳过）。记录此偏离即可，不必改回 fail-loud。
- **P2-5　task-consumer 区间 :59-120 不再要求改**：源码复核 authority 段在 :59-78、start 前置在 :80-102，:59-120 作为"start 全流程前置"引用准确，r1 提的 :79-120 反而漏掉 authority。
- **P2-6　其余 P2 行号修正已核实**：delivery-consumer 真拒点 :207 / :334 为 evidence 只读分支（Q3 line 65 已改对）、§7 硬伤编号 cancelTodo 已从 #6 改为 #4、shadow-routing findBinding:237 / listBindings:243 / ProjectStatusEntry.controllerSessionId at types.ts:201 已点准。

---

## r1 P1/P2 复核结论（已修项，不再展开）

- P1-1 #15 黄底等待标记：v2 内落地（时间阈值替代 token%，见 P2-3）。
- P1-2 #18 触发规则：阶段 D line 148 已写规则 + 正例 2 / 反例 2（注入点见 P2-2）。
- P1-3 Goal 生命周期：常驻 Goal + update_goal 追加 taskIds（引 task-consumer.ts:71 精确）+ 单 Goal 复用 + plan 前冒烟断言，四要素齐；唯冷启动触发者见 P1-5。
- P1-4 node_modules：owner=host 预配、`pnpm install --frozen-lockfile --prefer-offline`、失败 fail-loud 阻止 start、junction 兜底复用 mirrorDependencyLinks、首次引导进原生 Windows 冒烟，全部到位。
- P1-5 插件挂载：devframe / agent-evidence / project-contracts 三条 link 已补；agent-dispatch 声明"devframe-profile bundle 已 insert 其 row、阶段 A 验证挂载，必要时 restate"，处理合理。
- P1-6 注册时序：已从 plan 时移进 approveTask 内、与 start 同一 host 调用，两条单测（approve→注册→start→deliver 成功；未 approve 直接 deliver 被拒）锁定，与 Q3 自洽。
- P1-7 验收：keyless test:snapshot 场景、#13 杀进程 reconcile、#19 block/stop-rebind、#20 Windows 阻塞冒烟、#11 加载期 fail-loud、#21 repairLimit 撞限显示"已回退次数+末次失败命令"均已进 §4；唯 #16 见 P1-4。
- P2 其余：审批 disabled 与 5s 轮询竞态已三层兜底（Q5 line 85 / 阶段 C line 138）；BoardView 每帧 sessionId 自检已写（Q5 line 81/83）；#5/#9/#10 收口句已补（阶段 D line 149）。

---

## r3 复评要点（改完这 5 条即可通过）

1. P1-1：Q3 加一句"注册前 realpathNormalize(cwd)"。
2. P1-2：Q1 步骤 5 的 assign/startDevelopment 补 `{ beforePersist: () => reCheck() }`。
3. P1-3：写清 typert caller 鉴权的证据或在 RPC 内补校验。
4. P1-4：ShadowBoardSnapshot 加 branch/lastCommand 字段并定义采集方式，或撤掉 #16 验收。
5. P1-5：选定 Goal 冷启动触发者一条主路径。
