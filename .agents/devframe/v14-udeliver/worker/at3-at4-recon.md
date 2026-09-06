---
description: "B5 对账：AT3×9 + AT4×8 逐条证据对账（工作树 codex/v14-udeliver-lead @ 6b31951491），判定三值覆盖/部分/缺口，不改变任何 AT* 的 not_run 验收态。"
---

# AT3×9 + AT4×8 逐条对账（v14-udeliver）

- 对账基线：主树 `D:/dsh-devframe/.agents/devframe/p22/anchor-matrix.md`（AT3 组 :46-60、AT4 组 :62-75）+ 主树 `D:/dsh-devframe/docs/testAndAcceptance.zh.md`（AT3 证据要求 :111-121、AT4 :129-138）。
- 编号口径说明：派单提示"AT3=Shadow/AT4=Memory"与两份权威文档不一致——anchor-matrix 与 testAndAcceptance 均：AT2=Shadow 路由、**AT3=Obsidian 记忆（9 条）**、**AT4=可靠性（8 条）**。本报告按权威编号执行；派单提示中"隔离/投递/持久化/冷恢复"等关键词在对应条目内如实体现。
- 判定三值 = **断言面证据覆盖**（覆盖=各通过条件子句均有具名在树测试/判定书锚定；部分=仅一部分；缺口=无实现无测试）。**不等于验收通过**：所有 `AT*` 用例仍为 `not_run`；机制 B（进程内）证据不构成全范围验收通过；keyless S2-S7 PASS（`.agents/devframe/v14-accept/lead/results.md:25-29`：无 key 事实、全程 `AcceptanceMockAdapter` 无 LLM 触碰）只作补充证据链接，不提升全范围验收。
- 执行纪律：本报告为纯静态对账，零测试执行、零重跑；同提交同环境同命令的通过结果只链接不重跑；除本文件外零写入。
- 工作树：`codex/v14-udeliver-lead` @ `6b31951491`（=main@908f627101 + compos/goalstore 已并）。相对 p22 矩阵的树内增量（旧缺口勿照抄）：AT4-02/03/06 旅程 spec（at406 波）、`devframe/tests/reliability/stop.spec.ts`（AT4-04 核心缝）、`project-memory/tests/agent-rehydration.spec.ts`（AT3-01 agent 侧再水化）、`command-goal-binding` 组合、`goal-binding-file-store` 跨实例重启、S1-S7 harness 判定书。
- snapshots/、apps/cli/、packages/bundle/ 三面已查（`git grep "AT3-|AT4-"` 零命中）：无 AT3/AT4 具名证据；snapshots/session 亦无 AT3 场景录制。

## 1. AT3 Obsidian 记忆（9 行）

| ID | 原始描述(短) | 证据要求(短) | 最新覆盖证据(路径:行) | 判定 | 缺口/小切片建议 |
| --- | --- | --- | --- | --- | --- |
| AT3-01 | 新会话召回带出处、跨项目隔离、日志记录到达模型的上下文 | 召回允许事实+确认偏好带来源；他项目私有笔记不出现；原生日志记录到达模型的上下文 | packages/experimental/project-memory/tests/recall.spec.ts:15,55；receipt-log.spec.ts:60,76,90；plugin.spec.ts:227,258；agent-rehydration.spec.ts:1-7,164,237,287,348（真实 Vault+真实派发+真实日志，`agent/created` 再水化）；src/plugin.ts:355；src/receipt-log.ts:134；补充 S7 双进程冷恢复：.agents/devframe/v14-accept/lead/results.md:21 | 覆盖 | recorded-session 正式 fixture 未录制（snapshots/ 无 AT3 场景）；验收执行时录制回填 |
| AT3-02 | 中英 UTF-8 超限不破字符、字节/条数/候选上限显式截断 | 输出不超配置字节/数量且不破字符；显式标注不完整与截断 | packages/experimental/project-memory/tests/recall.spec.ts:79,100,125,151,189,203；notes.spec.ts:53 | 覆盖 | 无（录制待回填） |
| AT3-03 | 并发同源事件至多一完整笔记、重试幂等、冲突不覆盖、不完整排除并报告 | 最多一篇完整笔记；相同重试幂等、冲突不覆盖；中断写排除并上报 | packages/experimental/project-memory/tests/append.spec.ts:16,38,63,86；补充 S7 真实 `already_exists` 重试复现：.agents/devframe/v14-accept/lead/results.md:21 | 覆盖 | 无 |
| AT3-04 | 穿越/未授权命名空间/symlink-reparse 逃逸全拒、safe-create 失败禁 append 不落 shell | 不越界读写；不支持安全创建时关闭追加，不使用 shell 兜底 | packages/experimental/project-memory/tests/path-safety.spec.ts:15,27,35,49,67,90,107 | 覆盖 | reparse/junction 变体为 Windows 面；非 Windows 语义在对应平台验收时确认 |
| AT3-05 | 指令型笔记保持带标签数据、运行时策略不变 | 指令笔记保持数据身份；实际运行策略不变、未授权操作被拒绝 | packages/experimental/project-memory/tests/trust.spec.ts:11-35（服务无执行面、文本仅可引用数据）；策略拒绝面另锚 packages/experimental/devframe/tests/permissions.spec.ts:100 | 覆盖 | "尝试所要求工具调用"以服务无执行面断言+角色 guard 缝覆盖，无逐字工具调用探针（非阻断） |
| AT3-06 | 推断偏好不自动晋升、矛盾并显、陈旧可见、显式 supersession 保留旧笔记 | 推断不自动转确认；冲突/陈旧可见；显式替代保留旧笔记 | packages/experimental/project-memory/tests/trust.spec.ts:43,82,110,144,159 | 覆盖 | 无 |
| AT3-07 | Vault 禁用/只读/移除：编码任务可带警告完成、失败保存永不报成功、memory-only 保持失败 | 开发可带记忆警告完成；失败保存绝不报已保存；纯记忆任务仍失败/阻断 | packages/experimental/project-memory/tests/failure.spec.ts:17,31,49；cold-restore.spec.ts:14；补充 S7 冷恢复（write 0/read 0、Vault 恰 2 真实 .md）：.agents/devframe/v14-accept/lead/results.md:21 | 部分 | "编码任务带警告完成"的任务级联动（controller 旅程）未驱动；小切片：project-controller 旅程 + `memory_unavailable` 警告断言；writeEnabled 生产=否部署决定待用户 |
| AT3-08 | 畸形/秘密筛查拒绝不落原文、瞬态重试有界、稳定可恢复候选引用 | 无效/敏感拒绝且不记录原始秘密；重试有界停止；保留可恢复候选引用 | packages/experimental/project-memory/tests/failure.spec.ts:63,92,111,124,152 | 覆盖 | 无 |
| AT3-09 | 外部改/移/删如实报告并保留、内联摘要不换回执、显式修正才建新源笔记 | 改变/缺失如实报告并保留，不自动导入/重建；文件内摘要不替代会话回执；显式修正才建新笔记 | packages/experimental/project-memory/tests/append.spec.ts:108,131,156,176；cold-restore.spec.ts:14,48 | 覆盖 | 无 |

## 2. AT4 可靠性（8 行）

| ID | 原始描述(短) | 证据要求(短) | 最新覆盖证据(路径:行) | 判定 | 缺口/小切片建议 |
| --- | --- | --- | --- | --- | --- |
| AT4-01 | 排队工作重启：pre-step 拒绝两分支、显式 resume、身份与限额保持 | 步前/步后两分支前置拒绝；仅证实未开始可恢复重发一次；已执行保持中断/无法确认保持 ambiguous；两者不作未开始重放；身份限额完整 | packages/experimental/agent-reliability/tests/service.spec.ts:20,30,45,96；at2c-05-admission-cutoff-fail-closed.spec.ts:46,66,85；devframe/tests/goal-binding.spec.ts:153,214,303；goal-binding-file-store.spec.ts:270-271（跨实例重启 resume）；command-goal-binding/tests/start-resume-composition.spec.ts:363-364（重启后同持久化根 resume）；补充 S5 双进程续跑（ctx.agents.resume 冷加载、事件单调接续）：.agents/devframe/v14-accept/lead/results.md:19 | 部分 | "排队 controller/child 工作跨进程重启 + 步前/步后两分支 pre-step 拒绝 + 显式 resume 同一 Goal"单一旅程未组装；小切片：在 S5 双进程骨架上补两分支注入 |
| AT4-02 | 命令已写标记但结果未记录：对账或标 ambiguous、不自动重放、标记不重复 | 执行被核对或标不确定；命令不自动重跑；标记不重复 | packages/experimental/agent-reliability/tests/at4-02-command-marker-reconciliation-journey.spec.ts:165-206（真实子进程写标记+context 终止+重开；:197-201 恰一次执行、不重跑）、:208-234（缺席重试恰一次）、:236-261（在飞 ambiguous 永不重发）；service.spec.ts:62,78,96；at2c-06-uncertain-call-probe-settlement.spec.ts:20 | 覆盖（包级真实路径旅程） | "harness 终止"以同进程 context dispose 模拟（机制 B），真实 harness 进程 kill 注入未做 |
| AT4-03 | 真实长跑子进程+孙进程心跳：停止属主项目→进程树终止、输出停、回调落定、writer 后释放 | 所属进程树结束、输出停止、回调完成后才释放写入所有权 | packages/experimental/agent-reliability/tests/at4-03-process-tree-stop-journey.spec.ts:152-232（真实子+孙心跳树；:216-220 释放时孙进程已不在；回调顺序 closeAdmission→quiescence→flush→releaseWriter :225-229）；devframe/tests/reliability/stop.spec.ts:130-156（真实 owned 后代先停、marker 停写）；service.spec.ts:153 | 覆盖（包级真实进程树） | 无 |
| AT4-04 | 取消拒绝/未知进程身份/处置期工作：保持不可写、无假 stopped、不误杀无关 | 项目带诊断保持不可写；不虚报 stopped；不接收替代写入者；不杀无关进程 | packages/experimental/devframe/tests/reliability/stop.spec.ts:44-51（取消被拒→needs_attention+writer 保留）、:53-62（identity_unknown 保留所有权）、:109-127（仅杀 owner job，unowned 不杀）、:37-41（pending inbox 保留、quiescence+flush 后才释放）；替代写入者排他另锚 workflow/worktree-registry agent-lock + project-controller 门禁 | 部分 | "运行中插件 dispose"触发与"停止 needs_attention 态下替代写入者"联动旅程未驱动；小切片：needs_attention 态替代写入者探测一条用例 |
| AT4-05 | 请求预算=1 竞速（controller/child）+ provider retry + 重启不重置 | 发送不超获准且已计费次数；兄弟竞争/重试/重启不重置用量；未知 token 不报零 | 无实现无测试：全树 `requestBudget|request-budget|REQUEST_BUDGET` 零命中；packages/experimental/project-controller/README.md:112 自证 budget 只限 developing 任务态、非模型请求上限 | 缺口 | 请求预算记账面（Config 化禁硬编码）+ 竞速/重试/重启不重置 + 未知 token 不报零；归 P06 记账小切片 |
| AT4-06 | 超并发/队列/截止：超额拒绝或可见未启动、截止闭准入并开始有界取消 | 超额拒绝或保持可见未启动；到期闭接收并开始有界取消、不产生新续跑 | packages/experimental/agent-reliability/tests/at4-06-admission-deadline-closed.spec.ts:69,97,122,143,166,186,205,252（截止时刻起逐字拒绝、三拒绝可区分、reconciler 重试经 cutoff、ADMISSION_CLOSED 优先、显式重开）；超额面：project-controller at2b-04 场景 PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED + service.spec.ts:20-45 | 部分 | spec 头 :2-4 明示"截止后在途任务的有界取消"半边 GAP、语义待总控裁定，本文件不覆盖在途取消；裁定后补在途取消用例 |
| AT4-07 | 真实存储写/刷失败（受理与完成两处）：无未持久化成功宣告、停止后续变更、脱敏诊断 | 不宣布未持久化成功；后续修改停止；脱敏诊断定位项目/操作不泄漏内容 | packages/experimental/agent-reliability/tests/service.spec.ts:120,134（刷成功准入不动/刷失败闭准入留写权）；at2c-05 spec:85；devframe/tests/events.spec.ts:279,299,505（durable flush 串行、失败闩锁永不接纳后续变更、JSONL 往返）；goal-binding.spec.ts:571（完成侧 store 失败 fail-loud、无原生变更）；stop.spec.ts:100-106（诊断仅 resource/reason 不含内容） | 部分 | 注入为单元级 throw；真实磁盘层错误（EIO/EBUSY）+日志/展示态组合检查未全覆盖；小切片：进程自有文件层真实故障注入+日志脱敏断言 |
| AT4-08 | 缺 decoder/不兼容 profile 打开录制会话：明确失败不改日志、兼容读取器可检视/导出、回滚不留 writer | 不兼容明确失败且不改日志；兼容路径能检视/导出；回退不留活动 writer | 无 AT4-08 语义绑定（`git grep AT4-08` 仅主树 anchor-matrix 命中）；底层契机：packages/core/session/tests/repair.spec.ts（repair 语义：不合成结果、标记 not started）+ packages/core/session/tests/session.spec.ts:943,999（SESSION_FORMAT_VERSION） | 缺口（AT 层） | 绑定 dsh-session 属主（§6b 仍未入表）；缺 decoder/不兼容 profile/兼容读取三场景具名锚定 |

汇总：17 条 = 覆盖 10（AT3-01…06/08/09、AT4-02/03）、部分 5（AT3-07、AT4-01/04/06/07）、缺口 2（AT4-05、AT4-08）。全部 `AT*` 仍 `not_run`。

## 最重要缺口 Top3

1. **AT4-05 请求预算记账面未实现**（缺口）。全树零实现、零测试，且 project-controller README.md:112 明示现有 budget 只约束任务态、非模型请求——受控单项目交付必需线（AT4-01…05）中唯一源码级缺失。小切片：Config 化请求预算记账（禁硬编码）+ 竞速/provider 重试/重启不重置/未知 token 不报零四断言。
2. **AT4-08 兼容读取/回滚面无 AT 语义绑定**（缺口，owner 未绑）。36 行矩阵中唯一 owner 未绑项在 v14 树仍未收口；core 层 repair/版本机制（repair.spec.ts、session.spec.ts:943）只是契机。小切片：绑定 dsh-session 属主，把"缺 decoder、不兼容 profile、兼容读取器检视/导出、回滚不留 writer"具名锚定为三条用例。
3. **AT4-06 截止后在途任务的有界取消半边**（部分→注册 GAP）。at4-06 spec 头 :2-4 已明示该半边 GAP、语义待总控裁定；准入关闭半边已收口。小切片：总控裁定取消语义后补"到期→有界取消在途任务、不产生新续跑"用例（进程自有资源+显式超时，按 testAndAcceptance 第 4 部分前言口径）。

## 车道回执

- 实际请求 provider/model：本车道为 DeepSeek Harness 子代理，运行时上下文如实声明模型 `glm-5.3-flash`；provider 字符串未在运行时上下文中暴露，不冒充（未证实）。
- retry/429：本任务零外部模型/API 调用（纯静态对账），运行时未上报任何 retry/429（未观察到；"绝对无"未证实）。
- 结论一句话：17 条对账完成——AT3 8 覆盖 1 部分、AT4 2 覆盖 4 部分 2 缺口（AT4-05/AT4-08），树内证据较 p22 矩阵净增（AT4-02/03 旅程、stop.spec、agent-rehydration 闭合旧缺口），所有 AT* 仍 not_run，机制 B/keyless 证据未作全范围验收。
- 证据清单（路径:行）：主树 D:/dsh-devframe/.agents/devframe/p22/anchor-matrix.md:46-75、D:/dsh-devframe/docs/testAndAcceptance.zh.md:111-138；工作树 packages/experimental/project-memory/tests/{recall,notes,append,path-safety,trust,failure,cold-restore,receipt-log,plugin,agent-rehydration}.spec.ts（各 it 行号见表）、packages/experimental/agent-reliability/tests/{service,at4-02-command-marker-reconciliation-journey,at4-03-process-tree-stop-journey,at4-06-admission-deadline-closed,at2c-05-admission-cutoff-fail-closed,at2c-06-uncertain-call-probe-settlement}.spec.ts、packages/experimental/devframe/tests/{goal-binding,goal-binding-file-store,events,permissions}.spec.ts、packages/experimental/devframe/tests/reliability/stop.spec.ts、packages/experimental/command-goal-binding/tests/start-resume-composition.spec.ts、packages/experimental/project-controller/README.md:112、.agents/devframe/v14-accept/lead/results.md:15-29、:19（S5）、:21（S7）。
