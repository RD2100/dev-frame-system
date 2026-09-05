---
description: 与需求关联的 DSH 原生 DevFrame 功能测试步骤与验收标准。
---

# 基于 DSH 的 DevFrame：测试与验收

[English](testAndAcceptance.md) | 中文

## 概述

本文为[总体设计](generalDesign.zh.md)及四个详细设计部分定义可观察的验收标准。下文所有 `AT*` 用例都是拟议 DevFrame 功能的测试规格，均未标为已经实现或通过。已有原生 Team 测试证据单独记录，只能证明注明的范围。文档校验不等于产品验收。各验收矩阵中的证据锚点列只登记既有测试、场景或集成探针产物；逐行覆盖状态以 [P22 锚点矩阵](../.agents/devframe/p22/anchor-matrix.md)为准，仍由所属分支产出中的证据以待链接占位，任何锚点都不改变 `not_run` 结果。

## 目录

- [测试环境与结果规则](#rules)
- [已有基线证据](#baseline)
- [第 1 部分验收](#part1)
- [第 2 部分验收](#part2)
- [第 3 部分验收](#part3)
- [第 4 部分验收](#part4)
- [实际效用试用](#usefulness)
- [交付与证据](#delivery)

<a id="rules"></a>

## 测试环境与结果规则

使用总体设计固定的源码基线、可丢弃项目、临时运行存储和临时 Vault 子树。涉及 Windows 的结论要经过所选 Windows 文件系统／子进程提供方验证。不得对真实用户 Vault、无关进程、生产系统或共享工作目录执行破坏性故障注入。

采用四种互补验证：确定性策略的聚焦单元检查、经过真实会话／工具／存储路径的无密钥集成、用户批准的真实模型演示，以及故障注入／重启检查。mock 模型响应适合确定性工具测试，但不能证明真实提供方可用，也不能证明自主任务执行有实际效果。

实现时，每个验收编号必须关联实际测试文件／测试名称，或可复现的人工步骤。拟议编号、虚构命令或缺少执行上下文的截图都不是证据。真实提供方测试需要明确凭据／开销授权；缺少前提时记为 `blocked`，不能记为 `passed`。

| 结果 | 含义 |
| --- | --- |
| `passed` | 指定路径实际运行，所有规定断言均有记录证据。 |
| `failed` | 路径实际运行且至少一项断言失败，包括虚假成功声明。 |
| `blocked` | 缺少必需能力、环境、授权或前提。 |
| `not_run` | 用例尚未执行；这是所有拟议 `AT*` 用例的当前状态。 |

对于每一项权限、假完成、数据丢失或取消问题修复，都必须包含原本能够暴露问题的真实路径反例。能够安全验证实际工具／进程路径时，只测辅助函数不够。

<a id="baseline"></a>

## 已有基线证据

2026-09-02 源码分析期间，以下命令已在固定版本工作目录成功运行：3 个测试文件、63 个测试通过。这些测试使用 mock 模型行为，并验证原生 Team／会话行为，包括持久化场景；它们不实现或验收新增 DevFrame 层。

在 DSH 仓库根目录的 PowerShell 中运行：

```powershell
pnpm.cmd exec vitest run packages/experimental/agent-team/tests/team.spec.ts packages/experimental/agent-team/tests/persistence.spec.ts packages/experimental/tool-agent-team/tests/tool-team.spec.ts
```

对应源码测试为 [Team 行为](../packages/experimental/agent-team/tests/team.spec.ts)、[持久化](../packages/experimental/agent-team/tests/persistence.spec.ts)和 [Team 工具](../packages/experimental/tool-agent-team/tests/tool-team.spec.ts)。实现改变相关路径时重新运行，不能把历史结果当作后续代码的新验证。

在 2026-09-02 本次设计修订期间，执行了以下原生作用域测试：1 个文件、27 项通过。它确认 `restrict()` 对继承／本地工具的区别和原生单调 guard 行为，不代表尚未实现的 DevFrame 角色集成已通过。

```powershell
pnpm.cmd exec vitest run packages/core/tools/tests/scoped.spec.ts
```

现有快速文档命令检查链接、配对、文字结构和其他仓库文档规则。它既不构建 DevFrame，也不运行拟议验收用例：

```powershell
pnpm.cmd run test:docs
```

<a id="part1"></a>

## 第 1 部分验收

这些用例验证[单项目开发](detailDesign-part1.zh.md)。除明确要求连续 Goal 或恢复的场景外，使用新的可丢弃状态。记录完整 Goal／任务／验收／源码关联，不只记录源码快照。`AT1-11` 在独立的实际效用章节中定义。

| 编号／需求 | 准备与操作 | 可观察的通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| `AT1-01`／`R1.1` | 经真实分派器探测禁用的文件／shell／工作流／Goal 调用，以及参数满足原生成员／任务规则的本地 `team_task_update`，并强制前置执行策略允许。 | 角色 guard 仍在工具体之前拒绝本地 Team 修改；继承工具限制与未挂载插件同样生效。允许的读取可用。仅实现 `restrict()` 必须不能通过此用例。 | [agent-hierarchy guard.spec.ts](../packages/experimental/agent-hierarchy/tests/guard.spec.ts)、[devframe permissions.spec.ts](../packages/experimental/devframe/tests/permissions.spec.ts)、[devframe hierarchy-roles.spec.ts](../packages/experimental/devframe/tests/hierarchy-roles.spec.ts)、[core scoped.spec.ts](../packages/core/tools/tests/scoped.spec.ts)；组合级在线角色拒绝证据：分支 `p/hier2` 产出（仍在飞，待链接） |
| `AT1-02`／`R1.1` | 持久化角色，释放运行时并冷恢复；在角色恢复前后重复继承／本地作用域探测，并在缺少角色记录时尝试分派。 | 新 guard 在执行前安装；缺少角色时拒绝；开发者工具仍可用，审查者修改仍被拒绝；已释放注册不遗留旧 guard。 | [agent-hierarchy cold-recovery.spec.ts](../packages/experimental/agent-hierarchy/tests/cold-recovery.spec.ts)；[探针 §2](../.agents/devframe/integration/e2e-evidence.md#2-双进程冷恢复探针重启恢复exit-0--2) |
| `AT1-03`／`R1.2` | 向团队提供一个修改前测试真实失败的小型 fixture 缺陷，经正常开发者路径实现。 | 同一真实检查在修改前失败、修改后通过；存在宿主采集的命令／退出码／日志记录，无关未提交文件保持不变。 | [agent-evidence ledger.spec.ts](../packages/experimental/agent-evidence/tests/ledger.spec.ts) |
| `AT1-04`／`R1.2` | 开发者所属修改任务仍在运行时，尝试第二个写入者与审查／完成操作。 | 不接收第二个写入者，完成被阻止；直到真实任务结束才允许释放所有权。 | [worktree-registry agent-lock.spec.ts](../packages/workflow/worktree-registry/tests/agent-lock.spec.ts)、[project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT1-05`／`R1.3` | 分别提供虚构成功、失败／跳过的检查、错误审查者身份、其他快照的审查；审查后修改相关未跟踪文件，并尝试通过项目配置删除必需检查。 | 每个变体均以实际阻断原因被拒绝；`HEAD` 相同不能掩盖未跟踪文件变化，必需检查不能被悄悄削弱。 | [agent-evidence ledger.spec.ts](../packages/experimental/agent-evidence/tests/ledger.spec.ts) |
| `AT1-06`／`R1.3` | 对一个未变化快照完成必需任务、检查和独立审查，连续两次请求完成。 | 原生目标只完成一次，重复请求无害；证据引用可解析，无需单独验收数据库。 | [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts)、[project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts)、[devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts) |
| `AT1-07`／`R1.4` | 启动组合后的 profile，先发送安静消息再发送工作跟进，并测试创建失败和原生成员上限。 | 无工具名冲突；安静投递不唤醒，工作跟进会唤醒；失败成员计入上限，递归 spawn 不可用。 | [agent-team team.spec.ts](../packages/experimental/agent-team/tests/team.spec.ts)、[agent-team persistence.spec.ts](../packages/experimental/agent-team/tests/persistence.spec.ts)、[composition-smoke workspace-composition.client.spec.tsx](../packages/test-support/composition-smoke/tests/workspace-composition.client.spec.tsx)、[agent-team-profile profile.spec.ts](../packages/experimental/agent-team-profile/tests/profile.spec.ts)、[探针 §1](../.agents/devframe/integration/e2e-evidence.md#1-装配验证dump-configexit-0)、[探针 §3](../.agents/devframe/integration/e2e-evidence.md#3-recorded-session-无钥匙回放真实启动--真实工具调用exit-0)；built-bin 冒烟证据：[builtbin-smoke-evidence.md](../.agents/devframe/p22/builtbin-smoke-evidence.md)（`7569b2f98e`，已并入 main）——fail-loud 记录：构建红，built-bin 启动项未执行 |
| `AT1-08`／`R1.4` | 将修复上限设为二，让审查者持续要求修改。 | 首次审查后最多两次修改／重测／复审；剩余问题交人工处理，不通过替换成员或新运行绕过。 | `status: missing`，见[锚点矩阵 AT1-08 行](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4) |
| `AT1-09`／`R1.5` | 同一控制器／团队完成 A 后启动 B，任务板保留一个无关待办。源码不变但改变 B 的要求；消耗预算后停止／重启、恢复，并投递一个 A 的迟到结果。 | A／B 的 Goal／任务／证据归属不同；旧审查不能验收 B，无关任务不阻挡它。B 跨版本／重启保留消耗，A 的迟到结果不能满足或计入 B。最后用 B 自身证据完成它。 | [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts)、[devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts)、[project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT1-10`／`R1.6` | 执行拟议人工命令流程：configure／confirm／start、拒绝陈旧预览、停止、修改检查、恢复、查看结果和放弃已停止未完成 Goal。在创建原生 Goal 与关联持久化之间中断启动，并尝试让模型调用批准。 | 关联与授权完成前不执行；修改检查使证据失效但不重置用量；不确定状态阻止恢复；结果链接可解析；放弃不等于完成，模型文本不能授予批准。 | `status: missing`，见[锚点矩阵 AT1-10 行](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4)；已锚拒绝缝：[devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts)；设计提案：[s4-toolface-plan.md](../.agents/devframe/integration/s4-toolface-plan.md) |

<a id="part2"></a>

## 第 2 部分验收

这些用例验证 [Shadow 路由](detailDesign-part2.zh.md)。使用互不重叠的临时项目 A 和 B，并设置可以区分的任务与输出文件。

| 编号／需求 | 准备与操作 | 可观察的通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| `AT2-01`／`R2.1` | 从 Shadow 打开 A、B，并分别发送不同工作。 | 存在两个独立控制器根会话；开发者分别是正确根的直接子会话；没有嵌套 Team，输出留在目标项目。 | [shadow-router lifecycle.spec.ts](../packages/experimental/shadow-router/tests/lifecycle.spec.ts)、[AT2-01 场景](../packages/experimental/shadow-router/scenarios/AT2-01-open-route-two-projects.md) |
| `AT2-02`／`R2.1` | 让开发者调用项目工具；探测 Shadow 被禁用的 shell／原始会话工具；提交任意目标会话 ID、未授权工作区和旧关联版本。 | 所有禁用请求在修改目标前失败；拒绝响应不返回秘密或项目内容。 | [shadow-router whitelist.spec.ts](../packages/experimental/shadow-router/tests/whitelist.spec.ts)、[AT2-02 场景](../packages/experimental/shadow-router/scenarios/AT2-02-forbidden-probes.md)；S6 markShadow 调用方 fail-closed 证据：[s6-evidence.md](../.agents/devframe/p22/s6-evidence.md)（`efd88d2e6c`，已并入 main） |
| `AT2-03`／`R2.2` | 并发重复打开，在预留关联与根会话就绪之间中断后恢复。 | 同一获授权工作区解析到一个预留／当前控制器，不产生重复写入者或被悄悄替换的根会话。 | [shadow-router provisioning.spec.ts](../packages/experimental/shadow-router/tests/provisioning.spec.ts)、[AT2-03 场景](../packages/experimental/shadow-router/scenarios/AT2-03-open-dedup-recovery.md)；S6 markShadow 绑定行级冷恢复证据：[s6-evidence.md](../.agents/devframe/p22/s6-evidence.md)（`efd88d2e6c`，已并入 main） |
| `AT2-04`／`R2.2` | 在受支持文件系统上打开大小写／junction 别名及物理范围重叠根目录。 | 别名解析一致；重叠的并发写入者被拒绝。不受支持的别名语义明确报告，不声称已经测试。 | [shadow-router aliases.spec.ts](../packages/experimental/shadow-router/tests/aliases.spec.ts)、[AT2-04 场景](../packages/experimental/shadow-router/scenarios/AT2-04-alias-overlap.md) |
| `AT2-05`／`R2.3` | 分别在目标接受前、目标刷盘后、发送方回执前中断投递，再重新打开真实存储。 | 同一消息 ID 最终对应一次接受输入；恢复回执不重复面向模型的任务。只有两个受支持存储后端都测过，才声称都支持。 | [shadow-router delivery-recovery.spec.ts](../packages/experimental/shadow-router/tests/delivery-recovery.spec.ts)、[AT2-05 场景](../packages/experimental/shadow-router/scenarios/AT2-05-delivery-interruption.md) |
| `AT2-06`／`R2.3` | 重试相同／不同内容，超过消息／队列限制，并在控制器开始另一 Goal 后投递旧 Goal 消息。 | 稳定重试去重；冲突或过大输入被拒绝；旧 Goal／验收关联不会变成新 Goal 的输入，也不重置重试次数。 | [shadow-router delivery-limits.spec.ts](../packages/experimental/shadow-router/tests/delivery-limits.spec.ts)、[AT2-06 场景](../packages/experimental/shadow-router/scenarios/AT2-06-retry-limits-stale-goal.md) |
| `AT2-07`／`R2.4` | 在 A、B 运行真实受控后台任务，连续两次停止 A。 | A 停稳后幂等停止；B 的后台任务、队列和控制器继续运行且不受影响。 | [shadow-router stop-isolation.spec.ts](../packages/experimental/shadow-router/tests/stop-isolation.spec.ts)、[AT2-07 场景](../packages/experimental/shadow-router/scenarios/AT2-07-stop-isolation.md) |
| `AT2-08`／`R2.4` | 对空闲、排队、已收到、被阻断和完成运行重复读状态，并包含一次陈旧观察。 | 状态有界且只读，包含观察时间，不唤醒模型，不把回执或空闲等同于验收完成。 | [shadow-router status.spec.ts](../packages/experimental/shadow-router/tests/status.spec.ts)、[AT2-08 场景](../packages/experimental/shadow-router/scenarios/AT2-08-status-readonly.md) |

<a id="part3"></a>

## 第 3 部分验收

这些用例在真实临时文件系统上验证 [Obsidian 记忆](detailDesign-part3.zh.md)。使用合成内容和模拟凭据格式的测试字符串，绝不使用真实秘密。

| 编号／需求 | 准备与操作 | 可观察的通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| `AT3-01`／`R3.1` | 追加获授权的项目观察与人工确认偏好，再启动没有前序对话上下文的新项目会话。 | 召回得到允许的事实及来源，其他项目私有笔记不出现；原生日志记录了哪些上下文到达模型。 | [project-memory recall.spec.ts](../packages/experimental/project-memory/tests/recall.spec.ts)、[project-memory receipt-log.spec.ts](../packages/experimental/project-memory/tests/receipt-log.spec.ts)、[project-memory plugin.spec.ts](../packages/experimental/project-memory/tests/plugin.spec.ts)、[AT3-01 场景](../packages/experimental/project-memory/scenarios/AT3-01-workspace-isolation.md)、[探针 §2](../.agents/devframe/integration/e2e-evidence.md#2-双进程冷恢复探针重启恢复exit-0--2)；agent 侧再水化证据：[memory-rehydration-evidence.md](../.agents/devframe/p22/memory-rehydration-evidence.md)（`dd60bbc489`，已并入 main） |
| `AT3-02`／`R3.1` | 搜索／读取超过字节、结果和候选限制的中文与混合 UTF-8 笔记。 | 输出不超过配置字节／数量且不破坏字符；明确标注搜索不完整与截断。 | [project-memory recall.spec.ts](../packages/experimental/project-memory/tests/recall.spec.ts)、[project-memory notes.spec.ts](../packages/experimental/project-memory/tests/notes.spec.ts)、[AT3-02 场景](../packages/experimental/project-memory/scenarios/AT3-02-byte-limit-truncation.md) |
| `AT3-03`／`R3.2` | 并发追加同一源事件，重试相同与冲突内容，再模拟写入期间中断。 | 最多创建一篇完整笔记；相同重试幂等，冲突不覆盖，不完整笔记被排除并报告。 | [project-memory append.spec.ts](../packages/experimental/project-memory/tests/append.spec.ts)、[AT3-03 场景](../packages/experimental/project-memory/scenarios/AT3-03-concurrent-append-idempotency.md) |
| `AT3-04`／`R3.2` | 经真实适配器探测目录穿越、未授权命名空间 ID 和 symlink／reparse 越界。 | 不发生越界读写；不支持安全创建时关闭追加，不使用 shell 兜底。 | [project-memory path-safety.spec.ts](../packages/experimental/project-memory/tests/path-safety.spec.ts)、[AT3-04 场景](../packages/experimental/project-memory/scenarios/AT3-04-path-containment-rejection.md) |
| `AT3-05`／`R3.3` | 存入要求模型改变权限或写另一个项目的笔记，并尝试所要求的工具调用。 | 笔记保持带标签的数据身份；实际运行策略不变，未授权操作被拒绝。 | [project-memory trust.spec.ts](../packages/experimental/project-memory/tests/trust.spec.ts)、[AT3-05 场景](../packages/experimental/project-memory/scenarios/AT3-05-trust-label-carry.md) |
| `AT3-06`／`R3.3` | 提供推断偏好、相互矛盾笔记和旧源码快照的观察。 | 推断偏好不自动变成确认事实；冲突／陈旧状态可见；明确获授权的替代保留旧笔记。 | [project-memory trust.spec.ts](../packages/experimental/project-memory/tests/trust.spec.ts)、[AT3-06 场景](../packages/experimental/project-memory/scenarios/AT3-06-trust-promotion-contradiction.md) |
| `AT3-07`／`R3.4` | 关闭 Vault、设为只读，并在访问中移除；分别测试开发任务和纯记忆任务。 | 开发可以带记忆警告完成；失败保存绝不报告已保存，纯记忆任务仍为失败／阻断。 | [project-memory failure.spec.ts](../packages/experimental/project-memory/tests/failure.spec.ts)、[project-memory cold-restore.spec.ts](../packages/experimental/project-memory/tests/cold-restore.spec.ts)、[AT3-07 场景](../packages/experimental/project-memory/scenarios/AT3-07-vault-unavailable-degradation.md) |
| `AT3-08`／`R3.4` | 提交格式错误笔记与已知秘密模式 fixture，并耗尽瞬时失败重试。 | 无效／敏感内容被拒绝且不记录原始秘密；重试在配置上限停止，保留稳定可恢复候选引用。 | [project-memory failure.spec.ts](../packages/experimental/project-memory/tests/failure.spec.ts)、[AT3-08 场景](../packages/experimental/project-memory/scenarios/AT3-08-secret-screening-rejection.md) |
| `AT3-09`／`R3.2` | 编辑已确认笔记的正文／元数据，移动／改名／删除它，重试原追加操作，并明确提交修正。 | 改变／缺失被报告并保留，不自动导入、覆盖或重建。编辑文件内摘要不能替代会话回执。只有明确确认的修正才创建新的有来源笔记。 | [project-memory append.spec.ts](../packages/experimental/project-memory/tests/append.spec.ts)、[project-memory cold-restore.spec.ts](../packages/experimental/project-memory/tests/cold-restore.spec.ts)、[AT3-09 场景](../packages/experimental/project-memory/scenarios/AT3-09-external-change-honest-reporting.md) |

<a id="part4"></a>

## 第 4 部分验收

这些用例验证[可靠性](detailDesign-part4.zh.md)。故障注入必须使用进程所属资源与明确超时；记录准确中断点，并验证恢复后的源码／存储状态，不只检查内存标志。

| 编号／需求 | 准备与操作 | 可观察的通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| `AT4-01`／`R4.1` | 控制器／子会话有排队工作时重启；分别在任何模型／工具步骤执行前触发一次前置步骤拒绝，并在工具步骤已经执行后的续步前置检查中再触发一次，然后分别明确恢复同一 Goal。 | 没有未授权模型／工具工作。只有明确证明未开始的输入才能按原操作引用恢复并明确重发一次；已有执行步骤的工作保持中断状态，无法确认执行的工作保持 `ambiguous`；两者都不能作为未开始工作重放。身份与限制保持完整。 | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts)、[devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts) |
| `AT4-02`／`R4.1` | 测试命令写入标记后，harness 在记录结果前终止，再重新打开运行。 | 执行被核对或标为不确定；命令不自动重跑，标记不重复。 | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts) |
| `AT4-03`／`R4.2` | 启动真实长运行子进程及持续写心跳的孙进程，再停止所属项目。 | 所属进程树结束、输出停止、回调完成后才释放写入所有权。 | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts) |
| `AT4-04`／`R4.2` | 模拟取消被拒绝／进程身份未知，以及运行中的插件 dispose，再尝试替代写入者。 | 项目带诊断保持不可写；不虚报 `stopped`、不接收替代写入者、不杀无关进程。 | `status: missing`，见[锚点矩阵 AT4-04 行](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定) |
| `AT4-05`／`R4.3` | 将项目请求预算设为一，让控制器／子会话竞争，并包含提供方重试与重启。 | 发送次数不超过获准且已计费的尝试；兄弟竞争、重试／重启不重置用量，未知 token 用量不报告为零。 | `status: missing`，见[锚点矩阵 AT4-05 行](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定) |
| `AT4-06`／`R4.3` | 超过活动项目／并发请求／队列限制，并在工作运行时触发短截止时间。 | 超额工作被拒绝或保持可见未启动；到期后关闭接收并开始有界取消，不产生新的续跑。 | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts)、[project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT4-07`／`R4.4` | 在输入接受与完成时注入真实存储写入／刷盘失败，检查日志和显示状态。 | 不宣布未持久化成功，后续修改停止；脱敏诊断能定位项目／操作，不泄漏内容或凭据。 | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts)、[devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts) |
| `AT4-08`／`R4.4` | 使用缺失必需解码器或不兼容 profile 打开功能会话，再使用保留的兼容读取器。 | 不兼容使用明确失败且不改日志；兼容路径能检查／导出。回退不删除证据、不遗留活动写入者。 | `status: missing`，见[锚点矩阵 AT4-08 行](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定)；core 修复／版本机制缝：[core repair.spec.ts](../packages/core/session/tests/repair.spec.ts)、[core session.spec.ts](../packages/core/session/tests/session.spec.ts) |

<a id="usefulness"></a>

## 实际效用试用

受控单项目检查通过后，选择 3—5 个真实用户小任务，不仅使用预设 fixture 缺陷。连续任务保留团队控制器／成员，并包含一次停止／恢复。直接 DSH 单 agent 对照使用匹配的初始快照和验收要求，记录模型／提供方配置及实质差异。交替顺序或使用可比独立任务，减少学习效应。这是小规模观察试用，不是统计意义上的提速证明。

| 编号／需求 | 准备与操作 | 可观察的通过条件 | 证据锚点 |
| --- | --- | --- | --- |
| `AT1-11`／`R1.7` | 完成成对真实任务试用，并与用户检查记录。 | 记录两种方式的实际任务结果、干预、时间、请求／用量及有效／无效审查问题，保留失败。用户给出 `helpful`、`inconclusive` 或 `not_helpful`，并选择继续、简化重试或停止。不预设效率提升百分比。 | `status: missing`，见[锚点矩阵 AT1-11 行](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4) |

把一次性设置成本与逐任务操作分开。除补充说明、纠偏和手动救场之外，也统计必需确认次数；人工实际操作时间与总经过时间分开记录。只有具体问题得到验证，才把审查发现计为有效，不能只因审查者输出文字就计数。未知 token／成本保持未知。

现有试用报告中的一张简短对照表就够。完成评估也可能得到没有收益的结果；评估完成不等于产品有用。扩展首轮验证范围需要用户根据这些事实作出明确决定。`inconclusive` 或 `not_helpful` 时优先简化角色或停止扩展，不为证明流程合理而增加基础设施。

<a id="delivery"></a>

## 交付与证据

执行前选定交付范围。文档部分编号不决定安全检查何时运行；在处理普通用户工作前，必须通过下列提前选定的单项目子集。多项目、记忆和完整版本恢复矩阵仍随用户实际选择的功能验证。

| 交付 | 必需证据 | 不声称的内容 |
| --- | --- | --- |
| 聚焦接入试验 | 原生作用域回归，加上经过实际 Team 组合的 `AT1-01`、`AT1-02` 与 `AT1-10` 启动顺序部分。 | 已可用或已发布的开发流程。 |
| 受控单项目试用 | `AT1-01` 至 `AT1-10`；单项目 `AT4-01` 至 `AT4-05`、`AT4-06` 的截止时间部分、`AT4-07` 的接收／完成刷盘失败，以及一个获准真实模型任务。 | 多项目、记忆或整个可靠性矩阵。 |
| 价值判断 | 3—5 个真实任务后的 `AT1-11` 与用户记录的选择。 | 自动批准实现所有剩余部分。 |
| 候选多项目扩展 | 用户单独决定、试用基线、`AT2-*` 与 `AT4-06` 其余适用并发／队列部分。 | 可选记忆或恶意用户隔离。 |
| 可选记忆扩展 | 选用记忆时执行 `AT3-*` 和获授权临时 Vault 试用。 | Obsidian 双向同步或笔记语义必然正确。 |
| 已选择功能的日常可用版本 | 这些功能的所有适用用例、完整相关 `AT4-*`（含兼容数据回退）与独立审查。 | 未选功能、多租户或自动生产发布。 |

只运行某个 `AT4-*` 用例的一部分时，记录具体子场景通过，整个用例仍保持未完成；不把部分检查转成全部通过。请求／时间限制从首轮试用起生效。对纯开发版本，禁用记忆不构成阻断。

必需用例失败、被阻断、被跳过或未运行时，都不能声称对应交付完成。权限越界、修改错误项目、假完成、用户数据丢失／被覆盖，以及遗留失控写入者都是必须停止交付的条件。影响较低的限制必须明确说明并明确接受；通过率不能豁免失败的必需用例。

每次运行报告包含源码提交与未提交输入快照、profile／策略版本、平台与存储提供方、模型身份证据或缺失说明、验收编号、准确命令／人工步骤、退出码、产物路径、审查者、结果和已知缺口。使用原生运行存储与一份简短报告，不创建新的审批层级，也不把每条运行事件重复成 Markdown。

对于委派代码交付，在同一报告中包含简短 Reviewer Index：准确改动文件、关键代码路径、已执行测试、生成产物、已知缺口和建议审查重点。保留无关改动，不把暂存、提交、推送或部署作为验收测试副作用。

## 开发备注

紧接着的实施试验是原生 Team 权限接入与 Goal 关联启动顺序，之后再运行一个用户选定的真实任务。2026-09-02，一次可丢弃的无密钥真实组合探针在包含 8 个文件、199 项测试的命令中通过了 2 项聚焦断言；它支持聚焦试验，但不把任何拟议 `AT*` 用例标记为完整通过。这些文档不代替任务选择，也不授权模型开销。更广实施取决于首轮试用观察结果；紧凑证据记录见[时间线](timeline.zh.md)。
