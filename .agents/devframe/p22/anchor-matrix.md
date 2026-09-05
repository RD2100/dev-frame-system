---
description: P22 验收锚点矩阵与遗留清单：逐 AT 条目的当前证据、覆盖状态、缺口归属与登记表已知遗留处置建议（p/anchors @ 213682a800）。
---

# P22 验收锚点矩阵（AT → 当前证据）与遗留清单

- 基线：`p/anchors` @ `213682a800`（独立工作树 `D:\dsh-devframe-p-anchors`；本文只落盘 `.agents/devframe/p22/`，不改任何 src/测试）。
- 输入：[插件化登记表](../pluginized-round-registry.md)（§6a 执行表、§6b 验收矩阵绑定、changelog）、[testAndAcceptance.md](../../../docs/testAndAcceptance.md)（AT 断言面定义权威）、[集成探针证据](../integration/e2e-evidence.md)、各包 `tests/` 与 `scenarios/` 实测清点。
- 用例计数口径：按 spec 文件逐条计数 `it(`/`it.skipIf(`/`test(` 条目（约数）；平台变体计入条目数。同一 spec 内多个 `describe` 按 AT 注释归组。
- 覆盖状态口径：**已锚定** = 与该 AT 断言面同名/同语义的真实测试存在（登记表含总控亲跑绿记录）；**部分** = 断言面只有一部分有测试锚点，或缺组合级/旅程级驱动；**缺失** = 无测试锚点（实现可能同时缺位）。
- 所有 `AT*` 用例按 testAndAcceptance.md 仍为 `not_run`（验收未执行）；本矩阵锚定的是"证据已存在"，不把任何条目标记为已通过。矩阵含 `AT*` 条目共 36 行（AT1×11、AT2×8、AT3×9、AT4×8），汇总见文末 §6。

集成探针证据引用约定：[e2e-evidence.md](../integration/e2e-evidence.md) 各节记为"探针 §1"（装配 dump-config）/"§2"（双进程冷恢复）/「§3」（recorded-session 回放）/"§4"（失败登记）/「§5」（SKIP_AUTH）。

## 1. AT1 单项目（责任：P02 / P05 / P04 / profile / W4）

| AT | 断言面（testAndAcceptance） | 当前证据（包内测试 / 场景 / 探针） | 覆盖状态 | 缺口与建议归属 |
| --- | --- | --- | --- | --- |
| AT1-01 | 真实 dispatcher 角色拒绝（file/shell/workflow/Goal + scope-local `team_task_update`；restrict-only 必须失败） | [agent-hierarchy guard.spec.ts](../../../packages/experimental/agent-hierarchy/tests/guard.spec.ts)（11 用例，real dispatcher：worker 全拒创建面、lead 越界 fail-closed、深度预算第二拒绝路径、缺角色 fail-closed、陈旧身份）；[devframe permissions.spec.ts](../../../packages/experimental/devframe/tests/permissions.spec.ts)（2）+ [hierarchy-roles.spec.ts](../../../packages/experimental/devframe/tests/hierarchy-roles.spec.ts)（5）；core 语义基线 [scoped.spec.ts](../../../packages/core/tools/tests/scoped.spec.ts)（25，restrict 继承/本地区分） | 已锚定（包级） | 用例与 AT1-01 五探针清单为语义级映射，未逐字对齐（无 `team_task_update` 具名探针）；组合级 dispatcher 实跑未做。复验归集成波（L-Integration），补名探针归 P02/L-Hierarchy |
| AT1-02 | 冷恢复守卫重装、缺角色拒绝、dispose 不留陈旧守卫 | [cold-recovery.spec.ts](../../../packages/experimental/agent-hierarchy/tests/cold-recovery.spec.ts)（1 用例：重启后重建角色并重装守卫） | 部分 | 单用例未覆盖 AT1-02 全部断言面（缺角色拒绝、reviewer 变更保持拒绝、dispose 后无陈旧守卫）；组合级冷恢复探针已验服务激活（探针 §2）但未含角色探针。补用例归 P02/L-Hierarchy，组合级归集成波 |
| AT1-03 | 真实失败→修复→真通过旅程 + 宿主捕获命令/退出/日志 + 无关脏文件不变 | [agent-evidence ledger.spec.ts](../../../packages/experimental/agent-evidence/tests/ledger.spec.ts)（4 用例：绑定/提交/验证回执、追加式轨迹、畸形拒绝、冷恢复）——台账缝已锚 | 部分 | 旅程级驱动（真失败测试经 worker 路径修复、宿主捕获记录、脏文件隔离）无端到端测试；属真实模型/worker 旅程。台账归 P05/L-Foundation，旅程归 W4/产品波 |
| AT1-04 | 单一写入者：任务在飞时拒绝第二 writer 与完成 | [worktree-registry agent-lock.spec.ts](../../../packages/workflow/worktree-registry/tests/agent-lock.spec.ts)（8：幂等重绑、非 holder 全拒、force 拒绝、并发 create 恰一成功、同工作区分支唯一）+ [controller.spec.ts](../../../packages/experimental/project-controller/tests/controller.spec.ts)（合并门禁 controller-only 一次性消费、停止闭准入至 quiescence） | 已锚定 | 两缝（写入者排他、完成门禁）各自锚定；"任务在飞 ⇄ 完成阻断"的联动旅程未连测。联动场景归 P04+P03 波次复核 |
| AT1-05 | 证据拒绝矩阵：伪造成功/失败检查/错审查者/错快照/审查后改未跟踪文件/削弱必需检查 | [ledger.spec.ts](../../../packages/experimental/agent-evidence/tests/ledger.spec.ts)（4 用例；含畸形回执稳定错误码）——台账本体已锚 | 部分 | AT1-05 六个拒绝变体 0/6 有具名用例（现仅"畸形回执拒绝"相邻）；required-checks 削弱面无实现锚点。拒绝矩阵归 P05/L-Foundation |
| AT1-06 | 一次完成、重复请求无害、证据引用可解析、无独立验收数据库 | [goal-binding.spec.ts](../../../packages/experimental/devframe/tests/goal-binding.spec.ts)（8：并发 start 串行化并拒绝第二未完 Goal、恢复精确持久化 Goal 身份）+ [controller.spec.ts](../../../packages/experimental/project-controller/tests/controller.spec.ts)（合并标记一次性消费）+ [events.spec.ts](../../../packages/experimental/devframe/tests/events.spec.ts)（生命周期投影重置） | 部分 | "重复完成请求无害"与"证据引用解析"无直接用例；"无独立验收数据库"已由台账设计声明落实。补用例归 P04/P05 波次复核 |
| AT1-07 | profile 组装、安静消息不唤醒、失败成员计入上限、无工具名冲突 | [agent-team team.spec.ts](../../../packages/experimental/agent-team/tests/team.spec.ts)（47 用例内含：failed provisioning 持久计入上限、quiet mail 休眠/follow-up 唤醒/FIFO 去重）+ [persistence.spec.ts](../../../packages/experimental/agent-team/tests/persistence.spec.ts)（5：quiet 回放不唤醒）；装配层 [composition-smoke](../../../packages/test-support/composition-smoke/tests/workspace-composition.client.spec.tsx)（5）+ [agent-team-profile profile.spec.ts](../../../packages/experimental/agent-team-profile/tests/profile.spec.ts)（1）；探针 §1（六插件行 dump-config exit 0）+ §3（回放 exit 0） | 已锚定（native/装配层） | devframe 目标 profile（P00–P06 组合）的启动+失败 provisioning+上限组合实跑未做（集成 profile 只验到服务/工具面激活）。组合启动旅程归集成波；递归 spawn 不可用面由 P02 深度预算锚定 |
| AT1-08 | 修复上限=2：至多两轮修正/重测/审查 | 无实现无测试（全树 `repairLimit`/`repair limit` grep 零命中） | 缺失 | 需先有 repair-limit 配置面（profile/hierarchy 层）再补上限测试；登记表未给实现归属。建议归产品波，承载面随 S4 切片定 |
| AT1-09 | A/B 隔离、旧审查不收 B、预算跨 revision/restart、迟到 A 不收费 B | [goal-binding.spec.ts](../../../packages/experimental/devframe/tests/goal-binding.spec.ts)（Goal A 结果在 B 启动后仍归属 A、恢复精确身份、revision 存储）+ [events.spec.ts](../../../packages/experimental/devframe/tests/events.spec.ts)（跨记录预算/策略不匹配重放拒绝、事件类经原生 Session restore 往返）+ [controller.spec.ts](../../../packages/experimental/project-controller/tests/controller.spec.ts)（看板原样恢复） | 部分 | 分立锚定齐（绑定隔离/预算重放/恢复）；AT1-09 完整旅程（B 需求变更、迟到 A 结果不满足不收费、消费跨重启）无单一场景驱动。旅程场景归 P04 波次复核 |
| AT1-10 | /project 人工命令旅程（configure/confirm/start/陈旧预览拒绝/stop/改检查/resume/result/abandon；模型文本不可授权） | 设计提案 [s4-toolface-plan.md](../integration/s4-toolface-plan.md)（命令面未实现）；拒绝缝已锚：[goal-binding.spec.ts](../../../packages/experimental/devframe/tests/goal-binding.spec.ts)（拒绝模型形授权变更原生 Goal 态、持久化失败时准入保持关闭） | 缺失 | 命令面（`/project` 旅程+`project_verify/review/complete`）未实现——gaps.md S4 未启动，提案建议新切片 P23 承载。归属 P04 原组长（提案定稿）+ 产品波实现；"模型文本不可授权"缝已锚 |
| AT1-11 | 3–5 个真实小任务配对试用 + 用户记录 helpful/inconclusive/not_helpful | 无（W4 未启动，用户单独授权） | 缺失 | 按登记表：用户单独决定 Shadow/Memory 后授权执行；不可用测试替代。归属 W4/用户 |

## 2. AT2 Shadow 跨项目路由（责任：P21-S / L-Shadow，包级 21 用例，20 过/1 平台跳过）

场景草案 8 篇全部 aligned（[at2-runner-checklist.md](../accept/at2-runner-checklist.md)，vs `eff2e5b6af`），位于 [shadow-router/scenarios/](../../../packages/experimental/shadow-router/scenarios/)；fixture 化与中断/恢复驱动待回填（清单明示）。

| AT | 断言面 | 当前证据（包内测试 / 场景 / 探针） | 覆盖状态 | 缺口与建议归属 |
| --- | --- | --- | --- | --- |
| AT2-01 | 两独立控制器根、worker 挂正确根、无嵌套 Team、输出留目标项目 | [lifecycle.spec.ts](../../../packages/experimental/shadow-router/tests/lifecycle.spec.ts)（1：open→send→status→stop 全旅程跨 A/B）+ 场景 [AT2-01](../../../packages/experimental/shadow-router/scenarios/AT2-01-open-route-two-projects.md) | 已锚定（包级） | recorded-session fixture 未录制；组合级（集成 profile 加 shadow 行）验证中（L-Integration 第三轮已派）。fixture 归 snapshots 属主，组合级归集成波 |
| AT2-02 | 白名单拒绝面：worker 调用/禁用工具/伪造目标/未授权根/陈旧 revision，拒绝无项目内容 | [whitelist.spec.ts](../../../packages/experimental/shadow-router/tests/whitelist.spec.ts)（1：五类拒绝目标变更前失败）+ 场景 [AT2-02](../../../packages/experimental/shadow-router/scenarios/AT2-02-forbidden-probes.md) | 已锚定（包级） | 同上 fixture/组合级；未知参数键拒绝已由实现白名单覆盖（实现注记）。归属同上 |
| AT2-03 | 并发重复 open 收敛、预留中断恢复、无重复写入者/悄悄换根 | [provisioning.spec.ts](../../../packages/experimental/shadow-router/tests/provisioning.spec.ts)（5：并发收敛、预留中断同会话收敛、半就绪恢复+cwd 错位停靠、失败回滚+重试重预约、冷重启重放冲突）+ 场景 [AT2-03](../../../packages/experimental/shadow-router/scenarios/AT2-03-open-dedup-recovery.md) | 已锚定（包级） | 同上 |
| AT2-04 | 别名解析一致、物理重叠拒绝、未支持别名语义如实报告 | [aliases.spec.ts](../../../packages/experimental/shadow-router/tests/aliases.spec.ts)（5 条目：Windows 大小写/junction、POSIX symlink、双向重叠拒绝+段前缀无误报、缺失根拒绝）+ 场景 [AT2-04](../../../packages/experimental/shadow-router/scenarios/AT2-04-alias-overlap.md) | 已锚定（包级） | 平台变体 skipIf 分支（本机 20 过/1 跳）；非 Windows 语义宣称需在对应平台验收时确认。归属 L-Shadow + 平台矩阵 |
| AT2-05 | 投递两写边界中断收敛、回执恢复不重复模型可见任务、双存储后端 | [delivery-recovery.spec.ts](../../../packages/experimental/shadow-router/tests/delivery-recovery.spec.ts)（3：意图先行收敛、且回执退回不重写、意图未持久=新投递）+ 场景 [AT2-05](../../../packages/experimental/shadow-router/scenarios/AT2-05-delivery-interruption.md) | 已锚定（包级） | "both supported storage backends"双后端矩阵未参数化（包内走真实文件存储）——验收执行时确认或补后端变体。归属 L-Shadow |
| AT2-06 | 同负载去重/异负载冲突/超限拒绝/旧 Goal 绑定永不入新 Goal、限额不重置 | [delivery-limits.spec.ts](../../../packages/experimental/shadow-router/tests/delivery-limits.spec.ts)（3：重试去重+冲突+超长拒、队满接受前拒绝、旧 Goal `SHADOW_GOAL_STALE` 且重放限额不重置）+ 场景 [AT2-06](../../../packages/experimental/shadow-router/scenarios/AT2-06-retry-limits-stale-goal.md) | 已锚定（包级） | 同上 fixture/组合级 |
| AT2-07 | A 两次停止幂等排空、queued 取消/received 保留、B 全程不受影响 | [stop-isolation.spec.ts](../../../packages/experimental/shadow-router/tests/stop-isolation.spec.ts)（1：真实 owned job 双项目隔离停止）+ 场景 [AT2-07](../../../packages/experimental/shadow-router/scenarios/AT2-07-stop-isolation.md) | 已锚定（包级） | 同上 |
| AT2-08 | 状态有界只读含 observedAt、不唤醒模型、received≠completed | [status.spec.ts](../../../packages/experimental/shadow-router/tests/status.spec.ts)（2：分页有界只读、停靠 mismatch 显 blocked）+ 场景 [AT2-08](../../../packages/experimental/shadow-router/scenarios/AT2-08-status-readonly.md) | 已锚定（包级） | UI 状态集映射缺失（见遗留清单 #5）；宿主 `completeDelivery` 转发缝登记为开放方向。归属产品波 + L-Shadow |

## 3. AT3 Obsidian 记忆（责任：P21-M / L-Memory，包级 61 用例全绿）

场景草案 9 篇全 drafted 且逐条对齐 main 包契约（[at3-runner-checklist.md](../accept/at3-runner-checklist.md)），位于 [project-memory/scenarios/](../../../packages/experimental/project-memory/scenarios/)；组合级只读装配已验（探针 §2 RESTORE OK：工具注册/搜索覆盖/读路径/写拒绝四断言）。

| AT | 断言面 | 当前证据（包内测试 / 场景 / 探针） | 覆盖状态 | 缺口与建议归属 |
| --- | --- | --- | --- | --- |
| AT3-01 | 新会话召回带出处、跨项目隔离、日志记录到达模型的上下文 | [recall.spec.ts](../../../packages/experimental/project-memory/tests/recall.spec.ts)（2：授权事实+confirmed 偏好召回带出处、他项目私有笔记缺席）+ 场景 [AT3-01](../../../packages/experimental/project-memory/scenarios/AT3-01-workspace-isolation.md)；回执落日志：[receipt-log.spec.ts](../../../packages/experimental/project-memory/tests/receipt-log.spec.ts)（7）+ [plugin.spec.ts](../../../packages/experimental/project-memory/tests/plugin.spec.ts)（12，含先落日志再建结果、无 agent 拒收） | 已锚定（包级） | "Native logs record what context reached the model"的 agent 侧再水化路径未驱动（见遗留清单 #8）；组合级待带 agent 会话回放。归属 L-Memory + 集成波 |
| AT3-02 | 中英 UTF-8 超限不破字符、字节/条数/候选上限显式截断 | [recall.spec.ts](../../../packages/experimental/project-memory/tests/recall.spec.ts)（6：UTF-8 往返、字节计数、返回字节/条数上界、候选上限显式部分覆盖、查询校验、码点边界截断）+ [notes.spec.ts](../../../packages/experimental/project-memory/tests/notes.spec.ts)（3）+ 场景 [AT3-02](../../../packages/experimental/project-memory/scenarios/AT3-02-byte-limit-truncation.md) | 已锚定（包级） | 无（执行态待验收）；正式录制归 snapshots 属主 |
| AT3-03 | 并发同源事件至多一完整笔记、匹配重试幂等、冲突不覆盖、不完整排除并报告 | [append.spec.ts](../../../packages/experimental/project-memory/tests/append.spec.ts)（4：并发单笔记、already_exists/memory_conflict、incomplete_note 保留、无回执匹配内容确认）+ 场景 [AT3-03](../../../packages/experimental/project-memory/scenarios/AT3-03-concurrent-append-idempotency.md) | 已锚定（包级） | 无 |
| AT3-04 | 穿越/未授权命名空间/symlink-reparse 逃逸全拒、safe-create 失败禁 append 不落 shell | [path-safety.spec.ts](../../../packages/experimental/project-memory/tests/path-safety.spec.ts)（7：畸形 id、不安全 workspaceId、越界 namespace 链接、reparse 组件/文件位逃逸、独占创建失败显式拒绝、未配置 Vault 只读）+ 场景 [AT3-04](../../../packages/experimental/project-memory/scenarios/AT3-04-path-containment-rejection.md) | 已锚定（包级） | 无 |
| AT3-05 | 指令型笔记保持带标签数据、运行时策略不变 | [trust.spec.ts](../../../packages/experimental/project-memory/tests/trust.spec.ts)（1：指令形笔记不获授权）+ 场景 [AT3-05](../../../packages/experimental/project-memory/scenarios/AT3-05-trust-label-carry.md) | 已锚定（包级） | 无 |
| AT3-06 | 推断偏好不自动晋升、矛盾并显、陈旧可见、显式 supersession 保留旧笔记 | [trust.spec.ts](../../../packages/experimental/project-memory/tests/trust.spec.ts)（5：不自动晋升、矛盾并显不判胜者、快照差异/无快照双路陈旧、拒绝自我 supersede）+ 场景 [AT3-06](../../../packages/experimental/project-memory/scenarios/AT3-06-trust-promotion-contradiction.md) | 已锚定（包级） | 无 |
| AT3-07 | Vault 禁用/只读/移除：编码任务可带警告完成、失败保存永不报成功、memory-only 任务保持失败 | [failure.spec.ts](../../../packages/experimental/project-memory/tests/failure.spec.ts)（3：vault 根消失 memory_unavailable、只读可读拒写、memory-only 失败显式）+ [cold-restore.spec.ts](../../../packages/experimental/project-memory/tests/cold-restore.spec.ts)（2）+ 场景 [AT3-07](../../../packages/experimental/project-memory/scenarios/AT3-07-vault-unavailable-degradation.md) | 已锚定（包级） | "编码任务带警告完成"的任务级联动未驱动（需 controller 旅程）；writeEnabled 部署决定未做（生产=否）。联动场景归 P04+P21-M 产品波 |
| AT3-08 | 畸形/秘密筛查拒绝不落原文、瞬态重试有界、稳定可恢复候选引用 | [failure.spec.ts](../../../packages/experimental/project-memory/tests/failure.spec.ts)（5：密型只报规则名、环境倾倒/控制字符拒、邻词正常放行、重试有界、失败后候选引用）+ 场景 [AT3-08](../../../packages/experimental/project-memory/scenarios/AT3-08-secret-screening-rejection.md) | 已锚定（包级） | 无 |
| AT3-09 | 外部改/移/删如实报告并保留、内联摘要不换回执、显式修正才建新源笔记 | [append.spec.ts](../../../packages/experimental/project-memory/tests/append.spec.ts)（4：memory_changed 保留文件、编辑摘要不换回执、memory_missing 不重建、显式修正建新笔记保旧）+ [cold-restore.spec.ts](../../../packages/experimental/project-memory/tests/cold-restore.spec.ts)（2：重启后重试幂等、外删重启后报告）+ 场景 [AT3-09](../../../packages/experimental/project-memory/scenarios/AT3-09-external-change-honest-reporting.md) | 已锚定（包级） | 无 |

## 4. AT4 可靠性（责任：P06 / L-Foundation；AT4-08 未绑定）

登记表 §6b 绑定 AT4-01–05（停止/终止/写入者/预算/截止）与 AT4-06/07（并发队列/flush 失败）至 P06；AT4-08（兼容读取/回滚）未入绑定表。包内证据 [agent-reliability service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（9 用例：准入切断 3 + 不确定调用对账 3 + 刷写屏障 2 + 进程树停止产品化 1）。

| AT | 断言面 | 当前证据（包内测试 / 探针） | 覆盖状态 | 缺口与建议归属 |
| --- | --- | --- | --- | --- |
| AT4-01 | 排队工作重启：pre-step 拒绝 vs 已执行步后续拒绝两分支、显式 resume、身份与限额保持 | [service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（admission cutoff 3：默认关闭 fail-closed、精确身份接纳/错绑拒绝、reopen 代际替换+fail-loud 关闭）+ [goal-binding.spec.ts](../../../packages/experimental/devframe/tests/goal-binding.spec.ts)（持久化失败准入保持关闭、恢复精确 Goal 身份） | 部分 | "排队 controller/child 工作跨进程重启 + 两类 pre-step 分支 + 显式 resume 同一 Goal"旅程未测（现有为进程内缝级）；stop 对账身份跨重启持久化=S5 未启动（遗留清单 #7）。补旅程归 P06/L-Foundation |
| AT4-02 | 命令已写标记但结果未记录：对账或标 ambiguous、不自动重放、标记不重复 | [service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（uncertain-call 3：probe 证实即 settled 且永不盲重、probe 证实缺席才重试一次、absent/不 resends） | 部分 | 构造级对账缝已锚；真实"子进程写标记+宿主死亡"注入路径未测。故障注入用例归 P06（进程自有资源+显式超时，按 testAndAcceptance 口径） |
| AT4-03 | 真实长跑子进程+孙进程心跳：停止属主项目→进程树终止、输出停、回调落定、writer 后释放 | [service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（1：委托 DevFrame stop 契约——admission 先行、quiescence 先于释放） | 部分 | 契约顺序已锚；真实孙进程心跳树终止未测（需真实进程树故障注入）。归 P06 |
| AT4-04 | 取消拒绝/未知进程身份/处置期工作：项目保持不可写、无假 stopped、不误杀无关进程 | 无对应用例 | 缺失 | 取消拒绝与身份分类面未实现/未测。归 P06 产品波 |
| AT4-05 | 请求预算=1 竞速（controller/child）+ provider retry + 重启不重置 | 无对应用例（[controller.spec.ts](../../../packages/experimental/project-controller/tests/controller.spec.ts) 的并发预算为任务并发，非请求预算） | 缺失 | 请求级预算记账面未实现。归 P06（记账）+ P04（接线） |
| AT4-06 | 超并发/队列/截止时限：超额拒绝或可见未启动、截止闭准入并开始有界取消 | [service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（admission cutoff 3）+ [controller.spec.ts](../../../packages/experimental/project-controller/tests/controller.spec.ts)（1：按配置预算约束并发 developing 任务） | 部分 | 准入/并发面已锚；短截止过期闭准入+有界取消无用例。归 P06 |
| AT4-07 | 真实存储写/刷失败（受理与完成两处）：无未持久化成功宣告、停止后续变更、脱敏诊断 | [service.spec.ts](../../../packages/experimental/agent-reliability/tests/service.spec.ts)（flush barrier 2：刷成功准入不动、刷失败闭准入留写权）+ [events.spec.ts](../../../packages/experimental/devframe/tests/events.spec.ts)（flush 失败闩锁、此后永不接纳 DevFrame 变更；JSONL 往返） | 部分 | 单元级注入已锚；"受理与完成两处真实存储失败 + 日志/展示态检查"组合未全覆盖；EIO/EBUSY 真实注入需提权（登记表已知边界，重试经单元+永久路径验证）。归 P06 收尾 |
| AT4-08 | 缺 decoder/不兼容 profile 打开录制会话：明确失败不改日志、兼容读取器可检视/导出、回滚不留 writer | 底层契机：[repair.spec.ts](../../../packages/core/session/tests/repair.spec.ts)（11）+ [session.spec.ts](../../../packages/core/session/tests/session.spec.ts)（73，含 SESSION_FORMAT_VERSION 机制）——core 层修复/版本机制存在，但无 AT4-08 语义绑定 | 缺失（AT 层） | §6b 未绑定 owner；建议绑定 dsh-session 属主/核心组长，把 repair/版本机制面用 AT4-08 场景（缺 decoder + 不兼容 profile + 兼容读取）具名锚定 |

## 5. 遗留清单（登记表已知遗留逐项现状 + 建议处置）

门禁运行限制：本工作树未安装 `node_modules`，`pnpm run test:coverage`、`check-workspace-constraints`（缺 typescript）、`verify-translation-pairing`（缺 mdast 依赖）均无法在本树运行；下述现状凡标注"实测"者为本树实际执行/静态比对结果，标注"登记表口径"者以 changelog 为准，最终复核在主树执行。

| # | 遗留项 | 现状 | 建议处置 | 归属 |
| --- | --- | --- | --- | --- |
| 1 | coverage 门 | 登记表口径=遗留 P22（P02 已知风险条目）；[vitest.config.ts](../../../vitest.config.ts) coverage include 覆盖全部包 src，六个新实验包无豁免登记 → 100%/文件门对它们生效但本轮未运行验证 | 主树跑 `pnpm run test:coverage` 定位未覆盖文件；按仓规补测试或加有理由豁免（排除清单进 coverage-exempt/vitest config 并说明） | L-Foundation + 总控复核 |
| 2 | constraints 范围外红 | 登记表口径=P03 合并时实测"基线红四项"之一；本树无法运行（缺依赖） | 主树复跑 `tsx scripts/check-workspace-constraints.ts` 定位残余红项；属 experimental 范围声明问题则补范围登记而非放宽门禁 | 总控 + 基建 |
| 3 | verify-package-paths | **实测红，已收窄至 2 处**：[docs/agent-orchestration-plan.md:40](../../../docs/agent-orchestration-plan.md) 与 [zh:40](../../../docs/agent-orchestration-plan.zh.md) 引用 `packages/experimental/devframe/src/commands`（目标不存在；changelog 所记"引用未来目录"的 P00–P06 目录均已存在） | 双语对同步修正该引用（改为概念性表述或移除失效路径），门禁转绿；本项可直接修 | 文档属主（P22 可承接） |
| 4 | experimental README 配对失同步 | **实测（静态比对）**：[agent-worktree README.md](../../../packages/experimental/agent-worktree/README.md) 169 行 vs [README.zh.md](../../../packages/experimental/agent-worktree/README.zh.md) 172 行，分歧在 Known Limitations/维护者上下文 details 块（zh 侧多 3 行、EN 155/157 两列表项无 zh 对应行）；其余九新包行数相等。配对门禁本树无法运行 | 重排 agent-worktree zh 侧 details 块使逐行配对，主树跑 `verify-translation-pairing` 验证 | agent-worktree 属主（L-Worktree） |
| 5 | UI 状态集（P22） | shadow-router 五观察态（idle/queued/received/needs_attention/completed+blocked，含 observedAt）仅服务层与测试；memory 三工具无 UI 卡；无任何 client UI 面映射 | 产品波定义状态集→UI 呈现映射（从原始事件与持久化元数据派生，host presenter 保持纯函数），随后录 GIF+快照 | client UI 组长/产品波 |
| 6 | S4 工具面 | gaps.md S4 未启动：五基础插件均为纯服务（无会话级工具/命令面）；设计提案 [s4-toolface-plan.md](../integration/s4-toolface-plan.md) 在册（P01 提示节/P02 拒绝词表/P04 六工具+/project 命令面/P05 零写一读/P06 结构化拒绝；命名冲突表；建议新切片 P23 承载）；memory 三工具已全局注册但未纳入 hierarchy 角色允许表（部署选择） | 按提案开 S4/P23 切片实现工具面；先决=hierarchy 允许表部署决定；实现后回填 AT1-10 拒绝矩阵与 P05 拒绝变体 | P04/P05 原组长定稿 + 产品波实现 |
| 7 | S5（reliability stop 身份持久化） | gaps.md S5 未启动：agent-reliability 无自有持久化域，stop 对账身份跨重启保留归 host 语义未实现 | P06 补 host 持久化语义 + 冷恢复测试（直接支撑 AT4-01"identity and limits remain intact"） | P06 原组长 |
| 8 | 回执 agent 侧路径 | 回执落会话日志已锚（receipt-log 7+plugin 12 用例，先落日志再建结果）；gaps.md 明示"回执再水化的 agent 侧路径未驱动"（无带回执 agent 可用） | 集成波驱动 `agent/created` 钩子再水化探针（可无钥匙：构造带 memory/receipt 事件的会话日志重放） | L-Memory + L-Integration |
| 9 | recorded-session 场景 fixture 化 | 29 篇场景草案（AT2×8 aligned + AT2B×6 + AT2C×6 + AT3×9 drafted）齐备；`snapshots/session/` 无一正式录制；AT2 清单明示"fixture 化与中断/恢复驱动仍待回填"；checklist 执行状态（passed/failed/blocked）零回填 | snapshots 属主按草案逐篇录制 keyless 快照并回填执行状态；录制属主本地刷新期望并逐 diff 评审 | snapshots/session 属主 + 各包组长 |
| 10 | AT1-08 修复上限 | 全树 `repairLimit`/`repair limit` 零命中——无实现无测试 | 随 S4/产品波补 repair-limit 配置面（Config 化，禁硬编码）+ 上限测试（绑 AT1-08） | profile/L-Foundation + 产品波 |
| 11 | AT1-11 效用试用 | W4 未启动；用户单独决定 Shadow/Memory 后授权 | 等用户授权；试用设计按 testAndAcceptance 效用节（配对任务、干预与用时分开计数、用户记录三态结论） | 用户/W4 |
| 12 | agent-evidence README.zh 骨架（changelog 旧记） | **现树复核已闭合**：[README.zh.md](../../../packages/experimental/agent-evidence/README.zh.md) 87 行与英文版逐行对齐，含完整 Summary/TOC/Model Experience | 无需行动；登记表下次修订移除该条 | —（已闭合） |
| 13 | hierarchy README model-experience（changelog 旧记） | **现树复核**：[agent-hierarchy README.md](../../../packages/experimental/agent-hierarchy/README.md) 已含 `## Model Experience` 与 `## Known Limitations and Deferred Work` 段；门禁本树无法运行 | 主树跑 `verify-package-readme-model-experience` 终验一次 | L-Hierarchy |
| 14 | P00 devframe 15 条 export-jsdoc | 登记表口径（S3 复查重现，属 P00/P04 属地）；本树未复核（门禁需依赖） | P00/P04 波次复核清零；与 #1 同批主树门禁跑 | L-Foundation |
| 15 | P-sched 运行时级验证 | 事件门控修复已合并（goal-round-driver 58/58）；运行中会话仍载旧码，重启后生效 | 宿主重启后验证"无事件挂起零请求"运行时行为，回填验证记录 | L-Sched/总控 |
| 16 | L-Verify skipped=6 + commandcode 未下载 | W3 报告：7/7 verified、0 blocked、6 SKIP（不计通过）；commandcode 包未下载 | 按各自唤醒条件补验或显式接受为范围外；纳入 P22 报告四态分表 | L-Verify 波次收尾 |

## 6. 汇总

- 矩阵行数：36（AT1×11、AT2×8、AT3×9、AT4×8）。
- 覆盖状态分布：已锚定 20（AT1-01/04/07，AT2-01…08 全部，AT3-01…09 全部）；部分 10（AT1-02/03/05/06/09，AT4-01/02/03/06/07）；缺失 6（**AT1-08、AT1-10、AT1-11、AT4-04、AT4-05、AT4-08**）。
- 缺失项共性：三项系产品面/命令面未实现（AT1-08/10）或用户授权未到（AT1-11）；两项系 P06 预算/取消记账面未实现（AT4-04/05）；一项系 §6b 未绑定 owner 且无 AT 语义绑定（AT4-08）。
- 组合级主线缺口（横切）：集成 profile 尚未纳入 shadow 行（L-Integration 第三轮进行中）；AT2/AT3 组合级证据停在"包级全绿 + memory 只读装配探针"。
- 本文件只登记证据现状，不改变任何 `AT*` 用例的 `not_run` 验收状态（[testAndAcceptance.md](../../../docs/testAndAcceptance.md)）。
