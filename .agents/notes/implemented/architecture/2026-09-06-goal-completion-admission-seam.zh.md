# Agent Note: Goal 完成准入生产缝

Status: implemented

[English](2026-09-06-goal-completion-admission-seam.md) | 中文

## Problem

`evaluateCompletionAdmission` 作为纯评估面交付，没有任何生产调用方：运行时没有任何位置合取三个谓词——指纹比对、必需检查覆盖、授权审查——其拒绝力只由用例钉住，产品不可达。一个 DevFrame 绑定的 Goal 可以在不做任何完成证据检查的情况下到达原生 Goal 生命周期的 complete 变更，这正是该面要拒绝的"审查后源码已变"与"削弱必需检查"危害。[required-checks 接线提案](../../proposed/architecture/2026-09-06-required-checks-wiring.zh.md)把这段生产组装登记为延期；该提案对宿主工具面与裁定入账范围仍保持 active，本 note 记录收口控制器级缺口的首片。

## Decision

`packages/experimental/devframe/src/controller/goal-binding.ts` 的 `GoalBindingController.complete(identity, request)` 是完成准入合取守卫原生 Goal 生命周期 complete 变更的生产调用点。该尝试按精确身份解析绑定，在整个尝试期间关闭准入，校验原生 Goal 仍是本绑定的 Goal、未落后于绑定 revision、且尚未 complete，并要求审查证据归属到正被完成的 Goal（Goal id、controller Session、workspace）。随后三个谓词按固定证据链序、以 durable 绑定自身记录的指纹——绝非调用方宣称值——求值。拒绝以数据返回且原生 Goal 不被触碰，继续工作必须经人类授权的 `resume`。准入通过后按当前 revision 执行原生 complete，并把绑定持久化为服务返回的 revision。

`NativeGoalPort` 缝新增 required 的 `complete(ref)` 动词，`GoalServicePort` 是该端口的首个生产实现：每个动词都委托给端口所绑定的精确 live Agent 上已解析的 `ctx.goals` 服务，原生拒绝原样传播。模型侧 `update_goal` 完成路径与原生 Goal 服务契约零改动。

## Alternatives considered

**在原生 Goal 服务或 `update_goal` 工具内求值。** release 包不得依赖 experimental 包，且通用 Goal 生命周期不携带 DevFrame 证据；两种落点要么反转依赖规则，要么强迫每次 Goal 完成都出示 DevFrame 证据。控制器缝把求值留在身份所有者处。

**可选端口动词加运行时拒绝。** 可选 `complete` 会让半接线的端口通过编译、直到调用时才失败；required 动词把未接线失败前移到类型检查，与 `DevFrameSessionJournal` 审查门在构造期失败的先例一致，而不是发明一条更软的运行时路径。

**围绕 `ctx.goals.complete` 的宿主级拦截器。** 全局服务包装器能从所有路径观察到绑定 Goal 的完成，但它改变所有 Goal 消费方的全局组合；拦截属于宿主命令面切片，该切片同时拥有裁定入账。

**指纹由调用方宣称。** 从请求取指纹等于让调用方宣称树状态；控制器从 durable 绑定读取，记录的宣称值保持比对的权威侧。

## Consequences

- 三谓词拒绝力经控制器面产品可达；评估序、热路径异步契约与纯评估面零改动。
- 整个完成尝试期间准入关闭，被拒的尝试保持关闭：评估运行真实 git 子进程，不得与已准入的 model 步赛跑；证据链已破就不会在无人类再授权的情况下继续准入工作。
- 绑定的 `goalRevision` 推进到完成 revision，而 `ProjectBindingRecord.lifecycle` 保持现有词表——原生 Goal phase 持有完成态，lifecycle 词表仍无终态完成值。
- 证据归属只在身份三元组（Goal、controller Session、workspace）上强制；更深的 tuple 匹配（revision、snapshot、task ids）留给组合这些证据的宿主组合。
- 裁定返回给调用方、不入日志；记录裁定或经 `GoalService.recordReceipt` 记完成回执，仍属宿主命令面切片。
