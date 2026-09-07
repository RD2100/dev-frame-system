# B5 — 36 行判定的未覆盖面刷新（基准 = 2c965e5a61）

刷新方法：只做聚焦源检查——git 只读查询 + 文件读取；无 pnpm/tsc/安装/测试执行。纪律：每条判定带证据（路径:行或 commit hash）；核不到标 unverified；不把包级证据说成验收通过——**全部 AT\* 验收态仍 not_run 不变**。基线=对账基线 6b31951491 之后的树内增量（含 main 并入 76080fe40b / 80f74545e3 / 24bbe04a7d / 2859e1842c 及其支线提交，均验证为 HEAD 祖先）。对账文件"复核修订节"已翻面的行（AT2-05 / AT1-08 / AT3-07 / AT1-05 / AT1-09）只复核证据锚，不重复深挖（见 §c-确认）。

## a. 翻面/新增证据行表

| ID | 原判定 | 刷新判定 | 证据（路径:行） | commit |
| --- | --- | --- | --- | --- |
| AT4-05 | 缺口（请求预算记账零实现；README:112 自证 budget 只限任务态） | **覆盖（包级，源码级实现，Config 化+四断言齐）** | 源码：`project-controller/src/controller.ts:71`（Config `requestBudget?: number`）、`:159`（schema 默认 1）、`:191-193`（正整数校验 fail loud）、`:775-802`（`chargeModelRequest`：先持久化后回执，重试/重启不重置，拒绝码 `REQUEST_BUDGET_EXHAUSTED`/`ADMISSION_CLOSED`/`PERSISTENCE`，写失败闩锁）、`:220`（构造时从 durable domain 恢复）、`:812-820`（`requestBudgetUsage` 读出）；`project-controller/src/spec.ts:59-105`（`requestBudgetUsageSchema` durable global domain，初始 `{chargedRequests:0}`）；`project-controller/src/request-budget-consumer.ts:9,13-18,30,65`（public 插件 `project-request-budget`：`llm/stream` 预扣、Config `controllerSessionId`、根/Lead/Worker 层级权威、取消不退）。测试：`tests/at4-05-request-budget.spec.ts` 9 用例（:16 不确定写后闭账+reload 恢复、:122 满预算竞速恰一、:164 默认/显式预算、:195 越界 fail loud、:203 进程重启不重置）；`tests/request-budget-consumer-loader.spec.ts` 9 用例（:129 根+Lead+Worker 共享配额、:145 每次 AgentLoop retry 计费、:154 最后配额后停排程重试、:166 伪造/未绑定拒、:206 取消不退、:224 不确定持久化后不再发 HTTP）。四断言（竞速/重试/重启不重置/未知写不报零）逐条有具名用例。README 已改述：`README.md:39-40,51,146`（requestBudget 与 consumer 文档），旧 README:112 引用失效（见 §c） | 76080fe40b（merge；对命令面并集经 first-parent diff 029bd891958e→76080fe40b 核实） |
| AT4-04 | 部分（缺"needs_attention 态替代写入者探测"一条用例） | **覆盖（包级，真实锁面）**：具名小切片闭合 | `devframe/tests/reliability/stop-writer-exclusion.spec.ts:100-159`（4 用例，锁权威=真实 worktree-registry：:101 取消被拒→needs_attention+绑定保持+第二会话 bind 遇真实 `WorktreeLockError` 'already-locked'；:118 identity_unknown 同拒；:133 stopped 路径真实 unbind→第二会话接管；:149 release 被拒→绑定保持）。归属更正：本切片由 **e07c38260a** 落地（新建该文件），**不是 24bbe04a7d**——24bbe04a7d 实际落 AT1-09 旅程（start-resume-composition.spec.ts +215）+ AT1-05 记录更正 + shadow-router 双 backend 变体 + 对账文档本身（first-parent diff 核实，无 stop 用例）。如实登记：对账行提及的"运行中插件 dispose 触发"联动旅程仍未驱动（本 spec 经 stopProject 选项面直接驱动） | e07c38260a |
| AT4-07 | 部分（真实磁盘层故障注入+脱敏断言缺） | **覆盖（包级，真实磁盘层）** | `devframe/tests/reliability/stop-persistence-failure.spec.ts:13-93`：真实 SessionStore+JsonlSessionPersistence+真实 tmpdir；故障注入=根路径预置文件（:24 `writeFile(root, …, {flag:'wx'})`）→首次真实落盘失败（:67 断言真实 `EEXIST`/`ENOTDIR`）；**脱敏断言** :57-59（published result+observations 不含私路径与私内容）；故障臂 :69-74（needs_attention + `session:flush operation_failed` + writer 不释放 + 磁盘字节未动）；成功臂 :75-85（JSONL readRaw/load 往返+事件序列还原）。`it.each([false,true])` 双分支单 spec | eb313febfc → 2859e1842c（merge，+94 行） |
| AT4-08 | 缺口（无 AT 语义绑定，owner 未绑） | **覆盖（包级，dsh-session 属主，三场景具名）** | `packages/core/session/tests/at4-08-compat-reader.spec.ts`：:52 缺 decoder（构建词汇外事件不可解释，仅 `ignorable` 标记可被兼容读取器保留）；:79 不兼容 profile（版本 +99/−1 均在解释前明确拒绝、日志逐字节不变 :87）；:91-133 兼容读取器（含 ignorable 外来事件的检视+无损导出 :95-103）+ 失败 open 回滚不留 writer（:111-118 无条目无发布钩子）+ 同 id 可再开（:120-129）。三场景即对账要求的"缺 decoder/不兼容 profile/兼容读取+回滚"具名锚定；owner=packages/core/session（dsh-session） | 34b562ba03（基线后新落，非 6b31951491 祖先）+ f5f1db5cf0（类型修复） |
| AT1-10（子面） | 部分（余 stop/abandon/中断注入/用量保持面） | **维持部分**；用量保持子面闭合，其余仍缺 | 用量保持：`command-goal-binding/tests/start-resume-composition.spec.ts:632`（AT1-09 A→B 旅程"budget across restart"活性证明）。stop/abandon 命令面：全 experimental 树 `devframe-stop|abandon` 零命中；`command-goal-binding/src/composition.ts:162-181` 仅注册 /goal-complete、/devframe-start、/devframe-resume 三命令。启动中断注入：未见。required-checks 跨 boot 墙只登记（见 §b-3） | 232e6fe825 / 24bbe04a7d |
| AT2-01 / AT3-01 / AT3-07（处置面） | 覆盖，缺口列标"B1 链 S11/S12 站（进行中）" | **判定维持**；处置面更新：B1 链 S11/S12 = blocked/not_run；**B2/B3 独立线已收真实路径证据** | `chain-evidence.md:41-42,76`（S9/S10/S11/S12 ⛔ 阻塞；12 站链=blocked/not_run，S1-S3b/S8 进程级绿证据保留；根因=provider 流式 args 缺陷，恢复路径归总控，B 线不得自行开工 :7）。B2/B3：`b2b3-evidence.md:13-24`（Boot A：project_open→/devframe-start 真实绑定+幂等卫兵拒绝→setActiveGoal→project_send received→project_status 全行→memory_append Vault 真实落盘→memory_read verified；:26-33 Boot B 同 home 同 Vault 重启冷恢复读回：Shadow 绑定行整行恢复+memory_search 命中；:35-41 停止后日志 seq 证据；:45 结论——运行态翻转依据，验收态归总控） | b2b3-evidence.md / chain-evidence.md（均已提交） |

对账文件"复核修订节"已翻面行的证据锚复核（全部存在，行号逐一对上，维持其修订判定）：AT2-05（`shadow-router/tests/helpers.ts:49-51` `HARNESS_BACKENDS=['json','sqlite']`；it.each 分布与修订节引用逐行一致：delivery-recovery:63,111,156、delivery-limits:49,114、provisioning:49,85,136,189、s6-cold-restore:17、s6-crash-window:49、s6-delivery-flow:53、s6-stop-settlement:56、status:96、stop-isolation:14）；AT1-08（`devframe/tests/repair-admissions.spec.ts` 9 用例、`devframe/src/session-journal.ts:150,202-203`、`command-goal-binding/src/composition.ts:441-453` :448 新签名、`devframe/src/events.ts:369,388`）；AT1-05（`devframe/tests/source-fingerprint.spec.ts:205,235,249,621` 用例名逐字在位，80f74545e3）；AT1-09（232e6fe825 为 HEAD 祖先，旅程用例 :632 在位）。

## b. 真实未闭合面清单（按可派单性排序）

| # | 面 | 属主域/包 | 切片大小 | 阻塞 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 1 | AT2-02 open 级越权根具名用例（一行级） | shadow-router/tests | 一行级 | 无 | 对账行 :26 处置项；套件全绿基线在位，仅缺该具名用例 |
| 2 | AT2-08 queued 态读出断言（一行级） | shadow-router/tests | 一行级 | 无 | 对账行 :32 处置项 |
| 3 | AT4-01 S5 骨架两分支（步前/步后）pre-step 拒绝注入 | agent-reliability + devframe tests | 小切片（纯测试组装，复用 service.spec/at2c-05 锚） | **不被 required-checks 墙或 B1 链阻塞**（零模型调用即可组装）；B1 S9/S10 站 blocked 与本切片无关 | at3-at4-recon.md:32；agent-reliability 包基线 6b31951491 后仅 docs 提交（ec19eac59a），零新测试；组合级重启+显式 resume+身份/预算保持已由 AT1-09 旅程证明（start-resume-composition.spec.ts:366,632），缺的是排队工作两分支 pre-step 拒绝进同一旅程 |
| 4 | AT1-10 stop/abandon 宿主命令面 + 启动中断注入 | command-goal-binding（接线）+ devframe reliability（库面已备） | 中切片 | 部分依赖 required-checks 收敛线裁定（命令面挂载波） | stopProject 库面+stop.spec/stop-writer-exclusion/stop-persistence-failure 包级证据齐；命令注册面只有三命令（composition.ts:162-181），无 /devframe-stop |
| 5 | AT1-09(e)+AT1-10 跨 boot 完成面：required-checks durable 注入缝**接线**（只登记不修） | command-goal-binding index 挂载波（host 需裁定 ledger 路径归属） | 小-中切片（源码改动在挂载点一行级，但涉 shipped 挂载波与路径 Config 化） | **被 required-checks 收敛线阻塞**：注入缝+File store+agent-dispatch 共享已落（`command-goal-binding/src/composition.ts:82,145,149` stores.requiredChecks；`devframe/src/required-checks-file-store.ts:161` + tests/required-checks-file-store.spec.ts；`agent-dispatch/src/run.ts:201-203,244-255` 单一 ledger），但命令面出厂挂载 `index.ts:84` 不传 stores → `composition.ts:149` 仍默认每进程 Memory → 任何 goal 在非其 start 所在 boot 完成结构性命中 `REQUIRED_CHECKS_CONFIG_NOT_FOUND`（232e6fe825 旅程以最小可达阶段如实断言，未掩盖） | 本次核实；对账 :124 墙登记的注入缝半边已闭合，剩出厂接线 |
| 6 | AT4-06 截止后在途任务有界取消半边 | agent-reliability（用例）+ 总控（语义裁定） | 小切片（裁定后补用例） | **待总控裁定**，非代码阻塞 | `at4-06-admission-deadline-closed.spec.ts:2-4` 现行文件头仍明示 GAP、语义待总控裁定 |
| 7 | AT1-03 组合级真实旅程（B1 链 S2/S3 站结算）/ AT1-11 真实任务效用 / AT2-07 组合级真实 owned-job stop 变体 | B 线链路（总控恢复路径先行） | 大（链级） | **被 provider 流式 args 缺陷阻塞**（chain-evidence.md:7 恢复路径归总控，B 线不得自行开工） | chain-evidence.md:76 12 站链=blocked/not_run；B2/B3 已收投递/状态/冷恢复面（b2b3-evidence.md），无 owned-job stop 注入站 |
| 8 | fixture 录制批次（AT1-01/AT2-01/AT2-03/AT2-06/AT3-01 等 29 篇草案） | snapshots 属主 | 批量 | 无（属主不同线） | 对账行 :9,25,27,30,38 处置项；对账 :69 ⑧ |
| 9 | AT4-04 残余：运行中插件 dispose 触发联动旅程 | devframe tests | 小（可选，非验收必需） | 无 | 具名小切片已闭合（§a AT4-04）；联动旅程未驱动，如实登记 |
| 10 | 平台验收时确认项（AT2-04 POSIX 分支、AT3-04 非 Windows 语义） | 平台验收轮 | 无代码切片 | 平台验收时 | 对账行 :28,41；机制性登记，非本树缺口 |
| 11 | AT3-05 逐字工具调用探针 | — | 非阻断 | — | 对账行 :42 自述非阻断，维持登记 |

## c. unverified / stale 清单

**stale（旧证据引用失效，给出新指向）**

1. 对账表 :56 "README:112 自证 budget 只限任务态"——当前 `project-controller/README.md:112` 是 delivery-consumer 表行；requestBudget 文档现位于 `README.md:39-40,51`（76080fe40b 落地后改述）。旧引用不得再用于 AT4-05 判"缺口"。
2. 对账表 :119 "cordis-catalog 门：run.ts:171 缺显式返回类型标注"——当前树 `agent-dispatch/src/run.ts:172` 已有显式标注 `get candidateTaskIds(): readonly string[] | undefined`（ef8a137dcae，2026-09-07）。**门是否转绿未重跑**（纪律），登记为"标注在位、门转绿 unverified"。

**unverified（本 Worker 不执行验证，如实标注）**

3. 提交信息所载实测数字未复核：232e6fe825/24bbe04a7d 的"11/33/267 passed + tsc 0"、4bd6345064 的"Loader composition suite 3/3"、复核节"52 文件/492 通过"、34b562ba03 的 dsh-session 结果——均只核文件/提交存在与内容形状，未重跑（任务纪律禁止执行套件）。
4. chain-evidence.md:40 S8 停止=进程级（"进程内 drain 式 stop 未及驱动（S8 语义级待恢复轮）"）——证据文件自述，语义级 S8 未收，未验证。
5. boot-evidence.md 的 dump 152 行零重复+真实 boot 探针（对账 :17 AT1-07 引用）——文件在树（已提交），内容未复核（超本任务范围）；2380aae9a3 已验证为 HEAD 祖先。

**非证据登记**

6. 工作树 untracked：`.agents/devframe/v14-udeliver/at11-task-ledger.json` 与 `.agents/devframe/v14-udeliver/tools/`——不属于 2c965e5a61 树内容，本刷新不以其为任何判定依据。
7. 工作树他人遗留修改：`pnpm-lock.yaml`（M）——未触碰。

**确认（存在=维持原判定，未标 stale）**

- 66 个抽样证据文件全部在位（AT1 组 agent-hierarchy/agent-team/agent-team-profile/agent-evidence/devframe/command-goal-binding/test-support 各 spec；AT2 组 shadow-router 全套件；AT3 组 project-memory 全套件；AT4-02/03 agent-reliability 旅程 spec；AT4-06 at2c-05；events/goal-binding/completion-admission/goal-binding-file-store/source-fingerprint/repair-limit 等）——批量 Test-Path 66/66，路径零失效，故 AT1-01/02/03/04/06/07、AT2 全组、AT3 全组、AT4-02/03 维持对账表原判定（含其复核修订）。
- 四个 main 并入 commit（24bbe04a7d、2859e1842c、80f74545e3、76080fe40b）与 232e6fe825、2380aae9a3、e07c38260a、34b562ba03 均验证为 HEAD 祖先（merge-base --is-ancestor exit 0）。

## 判定分布刷新

- 本刷新翻面 4 行：AT4-05 缺口→覆盖、AT4-04 部分→覆盖、AT4-07 部分→覆盖、AT4-08 缺口→覆盖。复核节已翻 5 行（AT2-05/AT1-08/AT3-07/AT1-05/AT1-09）维持，本次仅复核其证据锚。
- 刷新后分布（36 行，按对账表行判定列 + 复核节与本刷新翻面）：**覆盖 31 / 部分 4（AT1-03、AT1-10、AT4-01、AT4-06）/ 缺口→推进中 1（AT1-11）**。缺口 0。
- 口径说明：AT1-03 行判定列=部分（B4 真实调用 PASS 翻的是 S1 场景腿；组合级真实旅程随 B1 链 S2/S3 站，链=blocked），维持部分；AT1-11 真实任务效用证据仍为零（B1 链 S4-S12 未达），维持"缺口→推进中"。**全部 AT\* 验收态仍 not_run 不变**；覆盖=证据覆盖，非验收通过。
