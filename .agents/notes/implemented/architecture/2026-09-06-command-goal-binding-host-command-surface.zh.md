# Agent Note：/goal-complete 宿主命令面

Status: implemented

[English](2026-09-06-command-goal-binding-host-command-surface.md) | 中文

## 问题

[完成准入生产 seam](2026-09-06-goal-completion-admission-seam.zh.md) 让三谓词准入在控制器面上可达产品路径，但没有任何人类面分发它：宿主操作者无法说"现在通过准入完成这个 goal"，而且控制器所需的组合——哪个 workspace、哪个 worktree、哪个必需检查存储——没有归属。前一条 note 明确把经由 `GoalService.recordReceipt` 的完成回执与任何宿主级拦截延后到"宿主命令面 slice"。缺少这一 slice 时，准入只能从测试触达，而人类判定已完成的 goal 无法在已验证证据链下完成。

## 决策

私有实验包 `packages/experimental/command-goal-binding` 挂载一个 function plugin，其服务在同一次激活中把人类命令 `/goal-complete` 注册进 `ctx.commands` 并注册 devframe projection 单元，使命令与其读取的状态保持激活原子性。处理器为调用会话读取该 projection，取归属到当前 goal 的最新验证证据，并直接取最新审查记录而不按 goal 预过滤：审查归属由 `GoalBindingController.complete` 结构性强制，遇到外来审查会 fail closed，读取方不重复该检查。对组合持有绑定存储的预检查让"无绑定"保持稳定数据错误；worktree 路径从命令行或配置的 `workspaceRoot` 显式解析；声明的 digest 在组合持有的必需检查存储中解析。处理器随后分发 `GoalBindingController.complete`；获得准入的完成会经由 `GoalService.recordReceipt` 记录一条 `completion-admission` 回执——关闭延后的回执 slice——而每一类拒绝都渲染为指明阶段的稳定数据错误，绝不暴露 goal 身份。结构性 `GoalBindingError`、`SourceFingerprintError` 与 `RequiredChecksError` 原样传播并使分发失败。准入的评估顺序、fail-closed 语义与 complete 热路径 async 约定均未改动；goal、commands、devframe 与 core/session 源码零改动。

## 已考虑的替代方案

**用面向模型的 goal 工具替代人类命令。** 模型工具会把完成决定交还给模型，而准入存在的意义正是让完成由人类授权；仍然活跃的[必需检查接线提案](../../proposed/architecture/2026-09-06-required-checks-wiring.zh.md)单独保留了面向模型的工具面与更深入的裁决记账。

**在 projection 读取中按 goal 预过滤审查。** 预过滤会让外来的最新审查变得不可见而非大声失败；结构性传播才是 fail-closed 方向，测试矩阵也钉住了这一点。

**为组合声明 Context 服务键。** 组合是私有实验服务，因此它通过 Service 基类注册、调用方经反射读取；声明的 Context merge 会为 wave 范围的 seam 花费公共目录面。

**把结构性错误捕获为数据错误。** `RequiredChecksError`、`SourceFingerprintError` 与 `GoalBindingError` 表示错误组合、不可用 worktree 或篡改——不是用户输入；把它们转换成命令文本会在最错误的边界软化 fail-closed 行为。

## 后果

- 人类完成动词端到端可达产品路径：命令分发、projection 读取、控制器准入、原生 compare-and-set 完成、持久回执。
- 经由 `GoalService.recordReceipt` 的回执记账现在归属本 slice；回执之外的裁决记账与面向模型的工具面仍由仍然活跃的提案保留。
- 证据生产者仍然延期：组合的测试直接追加 role-policy、goal-binding、verification 与 review 记录，没有生产者的宿主会收到稳定的无证据错误。
- 默认绑定存储是进程本地内存，恢复时通过 Session projection 重建。挂载的插件通过配置的账本持久化必需检查；[命令检查登记持久化](../bug-fix/2026-09-07-persist-command-required-checks.zh.md)拥有该部署契约。
