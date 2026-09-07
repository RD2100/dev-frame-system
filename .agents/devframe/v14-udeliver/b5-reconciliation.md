# B5 — AT 验收矩阵 36 条逐条对账（汇总表）

对账基准：本树 codex/v14-udeliver-lead（=main@908f627101 + compos 7c21ed0fc2 + goalstore cd676781c3 及后续；当前含 B 线收口提交）。四分片 Worker 报告：`worker/at1-recon.md`（AT1×11）、`worker/at2-recon.md`（AT2×8）、`worker/at3-at4-recon.md`（AT3×9+AT4×8，权威编号 AT2=Shadow/AT3=Memory/AT4=可靠性）。每行判定三值=证据覆盖（覆盖/部分/缺口），**≠验收通过：全部 AT* 验收态仍 not_run**。硬规则执行：机制 B/keyless 证据一律标注范围；S2-S7 通过不提升为全范围验收；同提交同环境同命令通过结果复用不重跑。

## AT1×11（目标绑定与宿主命令面）

| ID | 判定 | 关键证据（详见 at1-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT1-01 | 覆盖 | 包级 `team_task_update` 具名探针闭合 p22 缺口 | fixture 录制归 snapshots 属主 |
| AT1-02 | 覆盖 | 包级三用例（由部分升级） | 无 |
| AT1-03 | 部分 | 缝级全锚；真实模型旅程缺（原 S1 keyless BLOCKED） | **B4 已翻面**：huoshan 显式路由真实调用 PASS（`b4-evidence.md`，request/header seq=10）；组合级真实旅程随 B1 链 S2/S3 站 |
| AT1-04 | 覆盖 | 缝级 | 无 |
| AT1-05 | 部分 | 4/6 具名+schema 收口；变体 5 untracked 边界差如实登记 | 补变体 5 用例（包内小切片） |
| AT1-06 | 覆盖 | 缝级+宿主命令面（compos 波 /devframe-start/resume REAL composition 测试） | 无 |
| AT1-07 | 覆盖 | 包级/装配层 | **shipped 挂载已落地**（2380aae9a3；boot-evidence.md：dump 152 行零重复+真实 boot 探针过） |
| AT1-08 | 缺口 | repairLimit 全树零实现零测试（grep 复核仅文档命中） | 需实现小切片（devframe 属主，Config 化 repairLimit+四断言） |
| AT1-09 | 部分 | 分立锚点齐含 durable 重启；旅程场景缺 | 旅程场景随 snapshots 录制 |
| AT1-10 | 部分 | /devframe-start/resume/goal-complete 已实现+REAL composition 测试（由缺失升级） | 余 stop/abandon/中断注入/用量保持面 |
| AT1-11 | 缺口→推进中 | 真实任务效用零证据（keyless 不可替代） | **B4 PASS 打通真实调用面；B1 链 S2-S7 站产出真实任务效用证据（进行中）** |

## AT2×8（Shadow 路由）

| ID | 判定 | 关键证据（详见 at2-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT2-01 | 覆盖（包级+组合级机制 B） | lifecycle.spec + S6 verdict + 集成 L1 | 产出面真实旅程→**B1 链 S11 站（进行中）**；fixture 录制归 snapshots 属主 |
| AT2-02 | 覆盖 | whitelist 五类拒面+s6-markshadow-scope+host-designation | open 级越权根具名用例（一行级）；滥用探测随 B1 链 |
| AT2-03 | 覆盖（包级） | provisioning 5 用例+行级冷恢复+S6 cold bonus | fixture 录制即可 |
| AT2-04 | 覆盖（包级，平台变体 skipIf） | aliases 5 条目+平台门控不宣称机制 | POSIX 分支对应平台验收时确认 |
| AT2-05 | 部分 | 投递两写/恢复/crash-window 齐；**双存储后端分句零锚点**（套件单挂 StorageJson） | 小切片：helpers 加 storageBackend 变体（json+sqlite）跑 delivery-recovery+s6-crash-window |
| AT2-06 | 覆盖 | delivery-limits 3 用例+S6 冲突面 | fixture 录制即可 |
| AT2-07 | 覆盖 | stop-isolation+s6-stop-settlement（p22 后新增） | 组合级真实 owned job 变体随 B2 站 |
| AT2-08 | 覆盖 | status 分页/received≠completed/零副作用/observedAt | queued 态读出断言（一行级）+UI 状态集映射归产品波 |

## AT3×9（Obsidian 记忆）

| ID | 判定 | 关键证据（详见 at3-at4-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT3-01 | 覆盖 | recall+receipt-log+agent-rehydration（真实 Vault+真实派发） | fixture 录制归 snapshots 属主；**B1 链 S12 站补 shipped 面冷恢复（进行中）** |
| AT3-02 | 覆盖 | recall UTF-8/上限截断 6 用例 | 无 |
| AT3-03 | 覆盖 | append 并发/幂等/冲突 + S7 真实 already_exists | 无 |
| AT3-04 | 覆盖 | path-safety 7 用例 | 非 Windows 语义平台验收时确认 |
| AT3-05 | 覆盖 | trust 数据身份+权限拒面 | 无逐字工具调用探针（非阻断） |
| AT3-06 | 覆盖 | trust 推断/矛盾/陈旧/supersession | 无 |
| AT3-07 | 部分 | failure 三态+cold-restore+S7 | 任务级联动（controller 旅程+memory_unavailable 警告）→小切片；**B1 链 S12 站补真实写/读（进行中）** |
| AT3-08 | 覆盖 | failure 畸形/秘密筛查/有界重试 | 无 |
| AT3-09 | 覆盖 | append 外部变更如实报告+cold-restore | 无 |

## AT4×8（可靠性）

| ID | 判定 | 关键证据（详见 at3-at4-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT4-01 | 部分 | agent-reliability+goal-binding+file-store 跨实例重启+compos 重启 resume | 单一旅程组装→S5 骨架补两分支注入小切片；**B1 链 S8-S10 站即真实跨进程重启+显式 resume（进行中）** |
| AT4-02 | 覆盖（包级真实路径旅程） | at4-02 journey（真实子进程写标记+context 终止） | 真实 harness 进程 kill 注入未做（机制 B 范围如实标注） |
| AT4-03 | 覆盖（包级真实进程树） | at4-03 journey（真实子+孙心跳树） | 无 |
| AT4-04 | 部分 | stop.spec 核心缝四断言 | needs_attention 态替代写入者探测一条用例 |
| AT4-05 | 缺口 | 全树零实现（README:112 自证 budget 只限任务态） | P06 记账小切片（Config 化+四断言），源码级缺失 |
| AT4-06 | 部分 | at4-06 准入关闭半边收口 | 在途任务有界取消半边待总控裁定语义后补用例 |
| AT4-07 | 部分 | 刷成功/失败闩锁+events JSONL 往返 | 真实磁盘层故障注入+脱敏断言小切片 |
| AT4-08 | 缺口（AT 层） | 无 AT4-08 语义绑定（core repair/版本机制是契机） | 绑定 dsh-session 属主+三场景具名锚定 |

## 汇总与翻转清单

- 判定分布（36）：覆盖 24 / 部分 9（AT1-03/05/09/10、AT2-05、AT3-07、AT4-01/04/06/07 中计入 9 个部分位）/ 缺口 3（AT1-08、AT4-05、AT4-08）。**全部验收态 not_run 不变。**
- 四态翻转清单（B 线交付引起的行级变更）：
  1. B1 源码行已有→**profile 行翻绿**（shipped 挂载四包，boot-evidence.md 实证）。
  2. B4：S1 场景 keyless BLOCKED→**真实凭据 PASS**（运行态真实证据，b4-evidence.md）。
  3. AT1-11 / AT1-03 / AT2-01/02 / AT3-07 / AT4-01 的"真实任务效用/shipped 面"缺口由 **B1 链逐站证据推进**（链结算后补链至本表）。
  4. p22 矩阵的"not_run+旧缺口"中已被树内增量覆盖的：AT1-01/02/06/07、AT2 全组（+S6/P21-S/集成 L1 新证据）、AT3-01、AT4-02/03/04——均已按上表链接，不重跑。
- 剩余小切片清单（按依赖排序）：①AT2-05 双后端参数化（纯测试改动）②AT1-05 变体 5 用例 ③AT1-08 repairLimit 实现（devframe 属主）④AT4-05 请求预算记账（P06，源码级）⑤AT4-08 语义绑定（dsh-session 属主）⑥AT4-06 在途取消（待总控裁定）⑦AT4-04/07 各一条用例 ⑧fixture 录制批次（snapshots 属主，29 篇草案）。

## 复核修订（huoshan-2 Worker，2026-09-08）

抽核上文行级判定对当前 main（本树 codex/v14-udeliver-lead）的过时项；仅核存在性/翻面，不重跑已绑定版本绿项，全部 AT* 验收态仍 not_run。其余未列行维持原表判定，存疑不深挖。

### 翻面行

| ID | 原判定 | 修订判定 | 证据（路径:行） |
| --- | --- | --- | --- |
| AT2-05 | 部分（"双存储后端分句零锚点"） | **覆盖（包级双 backend）**：小切片①已闭合于树内增量 | `shadow-router/tests/helpers.ts:49-51`（`HARNESS_BACKENDS=['json','sqlite']`）；`delivery-recovery.spec.ts:63,111,156`、`s6-cold-restore.spec.ts:17`、`s6-delivery-flow.spec.ts:53`、`s6-crash-window.spec.ts:49` 均已 `it.each(HARNESS_BACKENDS)`（先于本次改动存在，不重跑） |
| AT1-08 | 缺口（"全树零实现零测试"） | **覆盖（包级，durable consumer 面）**：V1.2 标准下按 main 76080fe40b durable repair-admission 面为准（本树 c469e0863c 并入）——内存 map 包级证据不替代 | `devframe/tests/repair-admissions.spec.ts` 9 用例（controller replacement 重建记账/冷 Session restore 恢复消费与 cause receipt/allowance 共享/拒面/durable 重放拒绝）；`devframe/src/session-journal.ts:150,202-203`（durable append+owned 校验）、`src/projection.ts:616`（fold）、`src/events.ts:369,388`（`devframe/repair-admission` 词汇）；旅程×durable 集成：`command-goal-binding/src/composition.ts:441-453`（task-warning 拒绝按新签名带 reason 记账）+ `real-composition.spec` 修复环三轮在合并树全绿（52 文件/492 通过） |
| AT3-07 | 部分（"任务级联动缺小切片"） | **覆盖（包级）**：grade 联动已闭合 | `devframe/src/events.ts:344,646,744`（`grade` 字段+`z.enum(['complete-with-warning','fail'])`+`gradeMemoryFailure`）；`devframe/src/task-warning-listener.ts:164,183,203`（每任务至多一条分级 `devframe/task-warning` append）；`devframe/src/controller/goal-binding.ts:1009`（completion-admission 谓词 `taskWarnings.find(grade === 'fail')`）；测试 `task-warning-listener.spec.ts`、`completion-admission.spec.ts:103,123,161`、`goal-binding.spec.ts:646,680` |

### 双 backend 遗漏扫描与新增变体（本次改动，均实测跑绿）

判定标准：套件断言持久化恢复/故障/中断语义（seedHarness 残留、冷重启重开、收敛）且该语义跨存储边界应成立。共补 9 个 sqlite 变体（5 个既有 spec 文件，`it.each(HARNESS_BACKENDS)`，仅改测试不改 src）：

1. `provisioning.spec.ts:49` — reservation 中断恢复（残留→重开收敛同一 reserved session id）
2. `provisioning.spec.ts:85` — 半成品 root 恢复（reconcile 完成/cwd mismatch 停车）
3. `provisioning.spec.ts:136` — provisioning 失败回滚+重开重供给
4. `provisioning.spec.ts:189` — 请求结果冷重启重放/冲突
5. `delivery-limits.spec.ts:49` — 残留占满有界队列→`SHADOW_QUEUE_FULL` 先于接受拒绝
6. `delivery-limits.spec.ts:114` — 旧 Goal 残留跨重启收敛 cancelled（本次将 h1 存活期改为世代顺序模式，见下）
7. `stop-isolation.spec.ts:14` — stop 排干残留+幂等重放+B 隔离（跨冷重启）
8. `status.spec.ts:96` — provisioning mismatch 残留→`needs_attention` 读出
9. `s6-stop-settlement.spec.ts:56` — 残留冷恢复后 stop 结算对比（cancelled/received 保持+closed receiver 拒绝）

实施中发现（如实登记）：`delivery-limits.spec.ts` 旧 Goal 用例原结构在 seed/h2 打开期间保持 h1 存活，json 容忍而 sqlite 于 teardown 报 `EBUSY: unlink shadow-state.db`（sqlite 单写者文件锁，断言本身全过）；已按 `s6-crash-window.spec.ts` 的世代顺序模式重构句柄寿命（h1.close → seed → h2），断言零改动，与 crash-residue 语义（"无 router 进程持有 root 时写残留"）更一致。

### 判定"无需双 backend"的套件/用例（不编造缺陷）

- `lifecycle.spec.ts`（AT2-01）：单进程 lifecycle 旅程，无重启/残留/中断断言。
- `whitelist.spec.ts`（AT2-02）：拒面全部先于变更发生，纯进程内守卫。
- `aliases.spec.ts`（AT2-04）：规范化/物理重叠/缺失根，纯进程内。
- `s6-markshadow-scope.spec.ts`：scope 工具安装，内存态 registry 断言。
- `host-designation.spec.ts`：designation 语义为内存态；其冷重启用例（:190）的 binding 行逐字段恢复断言与已双 backend 的 `s6-cold-restore.spec.ts` 同构，已闭合不重跑。如实登记：该文件 spec-local `boot()` 硬编码 StorageJson/`backend: 'json'`（:69-70），未参数化。
- 单用例级：provisioning 用例 1（并发重复 open，进程内幂等）、delivery-limits 用例 1（去重/冲突/超长，进程内两写面）、status 用例 1（分页/读出，进程内）、s6-stop-settlement 用例 2（stopping 窗口内 closed-receiver 守卫，无跨重启）。

### 验证（本节改动实测）

- 5 个改动套件 vitest run（provisioning/delivery-limits/stop-isolation/status/s6-stop-settlement）：22/22 passed，exit 0。
- shadow-router 全量 vitest run：14 files，47 passed + 1 skipped（aliases POSIX 用例按平台 skipIf，Windows 上预期跳过），exit 0。
- host `tsc -b tsconfig.host.json`：exit 0。

### 归属与合并集成更正（组长，2026-09-08 合并 c469e0863c 后）

- **AT1-05 变体 5**：本线切片**永久取消**——V1.2 已接手（B1 隔离树 owner），fingerprint v2 已落 main（80f74545e3：实际内容指纹+完成拒绝），旧"registered boundary"豁免不再承认；本线不重派不落用例。**原验收要求保持有效并由实现满足，非"待裁定"替代**（总控强化指令 2026-09-08）：合并树实测 source-fingerprint.spec 41 passed+1 平台 skip，exit 0——`:205 includes nonignored untracked files`（指纹含未忽略 untracked 内容）、`:235` size/mtime 还原后仍检出 untracked 字节改动、`:249` 忽略输入排除、`:621 rejects when an untracked file appears after the recorded snapshot`（完成时拒绝面）——"HEAD 相同不能掩盖未跟踪文件变化"由实现闭合。
- **AT1-08**：上表证据已按 V1.2 证据标准更正为 durable consumer 面（main 76080fe40b → 本树 c469e0863c 并入；worker 初核引用的内存 map 行号即其交付前树态，已过时不再引用）。合并把 main 新签名 `beginRepairRound(identity, {kind:'task-warning', taskId})` 与本线旅程消费臂整合（composition.ts:441-453）。
- **合并集成修复**：main 新增 `devframe/repair-admission` 事件后 `events.spec.ts` "registers every project event" 断言数组补齐该类型（52 文件/492 通过 + 1 平台 skip，exit 0）。
- **cordis-catalog 门**：main 新 agent-dispatch `src/run.ts:171` 缺显式返回类型标注致门失败（A2 属主面，本线不碰，登记待修）。

### AT1-09 旅程闭合（组长验收，2026-09-08，232e6fe825）

- **AT1-09 部分→覆盖（包级，单一旅程场景驱动）**：huoshan-2 Worker（显式路由 spawn 参数）在 start-resume harness 落一条 A→B 旅程（command-goal-binding/tests/start-resume-composition.spec.ts，+213/−2，既有 10 用例零改动）：A 起始/消费/授权完成 → B 需求变更（新 goalId/新 hash/新 budget，A 提前起 B 拒、旧审查不收 B 归属门拒）→ **预算跨 restart 保留活性证明**（重启若重置消费投影折叠即闩锁，实测 B 第二次消费折叠成功）→ 迟到 A 结果落 A 完整身份元组不计入 B → B 自身证据到 required-checks 阶段。复用既有判据零新增实现。验收复跑：11/33/267 passed + tsc 0，全 exit 0。
- **源码级墙（待裁定，旅程诚实登记未掩盖）**：`MemoryRequiredChecksConfigStore` 每进程实例（required-checks.ts:188-223）、插件 apply 无 store 注入缝（index.ts:80-84 硬默认）——任何 goal 在非其 start 所在 boot 完成（含生产跨进程重启）必命中 `REQUIRED_CHECKS_CONFIG_NOT_FOUND`；硬互斥"resume 成功⇔之后可完成"。durable required-checks 注入缝裁定后 AT1-09 (e) 与 AT1-10 跨 boot 完成面才可开展。
- 附带登记：`devframe/usage` 全树无生产写入者（测试装配与既有 review/role-policy fixture 同型）；task-delivery 迟到面因投影 `currentDeliveryGoal` 约束（delivery goalId 须等于最后一条 open binding）不可用于旅程运行时断言。

### 未覆盖面刷新（huoshan-2 Worker，2026-09-08，基准 2c965e5a61）

详表见 [b5-uncovered-refresh.md](b5-uncovered-refresh.md)（同 Worker 交付，逐行证据）。刷新后分布：**覆盖 31 / 部分 4（AT1-03/10、AT4-01/06）/ 缺口→推进中 1（AT1-11）；全部 AT* 验收态仍 not_run 不变。**要点：
- 再翻面 4 行：**AT4-05** 缺口→覆盖（76080fe40b durable request budget：Config 化+先持久化后回执+重启不重置+写失败闩锁，18 具名用例）；**AT4-04** 部分→覆盖（真实 WorktreeLockError 锁面 4 用例——**归属更正：落地 commit e07c38260a，非 24bbe04a7d**）；**AT4-07** 部分→覆盖（2859e1842c 真实 EEXIST/ENOTDIR 注入+脱敏+writer 保持）；**AT4-08** 缺口→覆盖（34b562ba03 三场景具名，dsh-session 属主）。
- 真实未闭合面（可派单序）：AT2-02/AT2-08 一行级用例；AT4-01 两分支 pre-step 注入（agent-reliability，纯测试组装）；fixture 录制批次（snapshots 属主）。被 required-checks 收敛线阻塞：AT1-09(e)+AT1-10 跨 boot 完成面（命令面出厂挂载 index.ts:84 仍不传 stores→Memory 默认——收敛后一次到位）。待裁定：AT4-06。
- **cordis-catalog 门更新**：run.ts:171 标注已修（ef8a137dcae）但门现失败于同型新面 **run.ts:191** 缺显式返回标注（A2 属主面滚动新增，组长实测 exit 1 于 2c965e5a61）——继续登记待修。

### 跨 boot 完成面闭合（消费 B1 审定提交 b0aafa900a，2026-09-08，bf4984f833）

- 收敛线解除：main 0d739d2df2 并入 B1 审定提交（durable required-checks 面：requiredChecksPath 必填绝对路径+FileRequiredChecksConfigStore 插件注入+单写者；冷重启 19 项+ACP 双进程录制+独立审查 PASS）。本树消费后 AT1-09 旅程末尾由"REQUIRED_CHECKS_CONFIG_NOT_FOUND 最小可达阶段断言"推进为**真实 completed**（此前登记的结构墙闭合）：B 在非 start boot 带自身授权审查真实完成（成功文本/身份保持/phase complete/revision+2/admission closed）；同一绝对 checks ledger 跨三 boot 字节不变（A 起始注册→B 幂等重注册→完成仅 load）；AT1-10 完成侧保持=receipt 注明 B 完成身份+completion-admission 证据、B 预算跨 boot 保持 [1,2] 不重置、A 迟到结果保持 A 元组、durable 日志载 receipt（下一 boot 可恢复）。harness 适配由 b0aafa900a 自带（boot() 从共享 storageRoot 派生 requiredChecksPath）。20/20 exit 0 ×3（Worker×2+Lead 验收×1）；实现 Worker 显式 huoshan-2 路由+Lead 独立 diff 审查。
- 登记事实：binding lifecycle 词汇表无 `completed` 值（完成经原生 goal/change receipt 可观察，devframe binding 停在最后 admission_open）——词汇面事实非缺陷，未改。第 4 boot 未加（durable receipt 断言已覆盖恢复内容，范围决策）。AT1-10 的 stop/abandon 专用命令面与启动中断注入仍未闭合（独立后续切片）。

### AT1-10 范围纠偏（V1.2 增量核对触发，2026-09-08，8bfe2d28ad 后）

- **纠偏成立**：AT1-10 原文（docs/testAndAcceptance.zh.md:86）要求旅程"停止→**修改检查、恢复**→查看结果→放弃"且"**修改检查使证据失效**但不重置用量"。8bfe2d28ad 的 checks-change 切片只闭"不重置用量"半边；其 spec（checks-change-composition.spec.ts:295-297 断言恢复保持 v1 冻结 hash、:346-349 断言改检查前旧证据照常 admitted）与"证据失效"要求**方向相反**——现状态=改检查只铸造下一个 Goal 的 hash，运行中 Goal 永不采纳新检查。**AT1-10 checks-change 面保持未完成**，此前报告不得读作该面闭合。
- **缺口 #1（改检查→证据失效路径）**：须补真实授权路径=人工改检查→恢复→绑定在新代际采纳新 acceptanceHash→旧代际证据在新代际 admission 下被拒→用量跨代际保持→新检查下重新取证→完成。immutable binding 折叠拒改（'changed its immutable binding'）保护证据归属完整性，方案须在现有契约内：新代际绑定记录（沿用 resume revision+1 代际机制）显式承继旧代际并携带用量连续性，同代际 hash 变更仍拒；设计待总控裁定后实施，不降验收标准。
- **缺口 #2（真实 stop 可靠性接线）**：8bfe2d28ad 的 stop flow quiescence/stopped 记录为词汇级测试手落，非真实可靠性链；接线时注意已登记的重复 stop_requested 折叠缺口（绑定已进 stop_requested 后 flow 首个同名记录 fold 失败——applyLifecycle 拒重复观察）。
- 主树 background workflow 激活协调期（h2 reviewer 75a7 收尾中）：不再开同步前台 workflow 派发。
