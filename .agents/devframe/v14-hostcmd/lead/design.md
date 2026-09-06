# v14-hostcmd L1 Lead Design — Host Command Surface Composition (P23/S4)

Author: L1 接入组长 (taskId=v14-hostcmd), session session-c1668d60-b936-45fd-84bc-77f121241cfe.
Base: main f5c680cacd (= codex/v14-hostcmd-lead HEAD). Status: VERIFIED — 接线点成立, wave proceeds.

## 1. 架构核对结论（主树只读核实，file:line 证据链）

**判定：安全接线点存在，组合路径成立。** 真实调用方 = 宿主命令面（`ctx.commands` 注册的人类 slash 命令）；controller 构造点 = 新实验性命令生产者包内的组合服务；GoalServicePort 用真实 `ctx.goals` + 接收 Agent 组装；verdict/receipt 落既有记录面，零 SessionEventMap 键变更。

### 1.1 宿主命令面（真实调用方）— 成立

- 扩展点权威：`docs/architecture.md:130` — "Add a human command | register on `ctx.commands`; it dispatches without a model turn"。
- 注册契约：`packages/interaction/commands/src/types.ts:28-58`（`CommandResult` = `{kind:'success', text?, sourceEventSeq?} | {kind:'error', text}`；`CommandDescriptor` name/description/input）；handler 收 `CommandInvocation`（含 `agent`、`rawInput`、`attachments`）。
- 日志落点自带：registry 在 handler 前后追加 `command/run`/`command/done`（`packages/interaction/commands/src/types.ts:85-110`；`dsh-commands` README:89 — "appends `command/run` before the handler runs, and appends `command/done` at settlement with the outcome kind and verbatim text"）。**verdict 的人类可读文本经 `command/done` 直接落 session log，零新增键。**
- 薄适配先例：`packages/goal/command-goal/src/index.ts:189-196`（函数插件 `name`/`inject=['commands','goals']`/`apply(ctx)` 内 `ctx.commands.register(...)`；领域拒绝→稳定 error 文本，意外失败 rethrow → dispatch 失败，README.md:45）。
- 命令效果包装先例（registrations are effects）：`packages/session-query/session-log-export/src/index.ts:74` — `ctx.effect(() => ctx.commands.register({...}), label)`。
- dsh-base 已同层挂载全链：`packages/bundle/base/cordis.patch.yml:292`（`commands` → `@deepseek-ai/dsh-commands`）、`:298`（`goal` → `@deepseek-ai/dsh-goal`）、`:304`（`command-goal`）。命令生产者包按 command-goal 同型插行即可。
- 关键空档确认：`/goal` 命令参考表（`packages/goal/command-goal/README.md:34-41`）只有 create/edit/pause/resume/clear，**无 complete 动词** — 人类完成路径当前不存在，正是本波 GAP。
- 归属约束：`command-goal` 是 release 包，依 `packages/experimental/AGENTS.md`（"Release packages and apps must not name packages here in dependencies/optionalDependencies/peerDependencies"）**不得依赖 experimental devframe** → 组合命令必须落新实验性包。

### 1.2 controller 构造点与 GoalServicePort 组装 — 成立

- 端口实现：`packages/experimental/devframe/src/controller/goal-binding.ts:212-241` — `GoalServicePort implements NativeGoalPort`，构造收 `{goals: GoalService, agent: Agent}`，五动词全部委托活服务；README.md:208-210 明示 "the adapter a host composition wires behind a GoalBindingController; there is no second, softer path"。
- 真实服务组装已实证：`packages/experimental/devframe/tests/goal-binding.spec.ts:81` — `port: new GoalServicePort({ goals: ctx.goals, agent })`；`:448-468` "completes through the real native GoalService via GoalServicePort"。
- QA 组合先例（真实 ctx、真实 GoalService、真实 tool 执行）：`packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts:45-48,71-83` — `ctx.plugin(GoalService)` 后用 `ctx.goals.*` 动词组装 NativeGoalPort、`new GoalBindingController({...ControllerSessionId(lead.id)...})`。
- controller 构造契约：`goal-binding.ts:354-359` `GoalBindingControllerOptions {workspaceId, controllerSessionId, goals: NativeGoalPort, store: GoalBindingStore}`；controllerSessionId = controller 会话 Agent 自身 id（QA 先例 `ControllerSessionId(lead.id)`）。
- store 现状：`MemoryGoalBindingStore`（`goal-binding.ts:126-174`）是唯一实现；`required-checks.ts:186` `MemoryRequiredChecksConfigStore` 同。**本波两 store 均保持参考实现，由组合服务持有并暴露为可替换边界（GAP-3 延期不变）。**

### 1.3 verdict/receipt 归属面 — 成立（零新键）

- 完成回执：`packages/goal/goal/src/index.ts:450-470` `GoalService.recordReceipt(agent, ref, evidence)` — 仅 phase=complete 可录（`:454-459` GOAL_INVALID_TRANSITION 兜底，**结构性阻止对未完成 Goal 记回执**）；追加 `goal/change` receipt 变体（`domain.ts:61-70`），revision 不动；证据条目开放 lower-kebab 分类 `kind` + 非空 `summary` + `at` + 可选 `ref`（`domain.ts:45-54`；校验 `index.ts:243-277`）。**verdict 数据乘 evidence 条目落日志，goal 侧零 schema 变更。**
- verdict 落日志（文本面）：`command/done`（`commands/src/types.ts:104-109`）— `kind` + verbatim text + `commandId` 关联，registry 自记。
- verdict 落日志（绑定面，非本切片）：`DevFrameSessionJournal.append`（`devframe/src/session-journal.ts:90-95`）+ `devframe/goal-binding` 键 + 投影折叠（`projection.ts:473-487`）。**本切片不触 journal**（理由见 §4）。
- 键集现状：`SessionEventMap` devframe 六键（`devframe/src/events.ts:252-276`）与 `packages/core/session/src/known-event-types.ts:36-41` 已登记；本波**零新增键、零 bump**。
- 投影读面（证据取数用）：`devFrameProjectionDefinition`（`projection.ts:512-521`）+ `ctx.sessionProjections.register(...)`（`events.spec.ts:484` 先例）+ `stateOf(session, 'devframe')`（`packages/session/session-projection/src/index.ts:319`）→ `DevFrameProjectionState.verifications/reviews`（`projection.ts:31-50`）。`DevFrameVerificationEventData.requiredChecks` 自带 `coverage {config, digest}`（`events.ts:181-204`）— **digest 从验证证据记录取，不从命令输入信任**。

### 1.4 生产证据生产者现状（诚实登记）

生产源码中目前**无任何 devframe/verification、devframe/review 事件追加者**（grep 全仓命中仅 devframe 自身 + tests），也无 controller.start 的生产调用方（GoalBindingController 全部命中为 devframe/agent-evidence/agent-team tests）。因此本波组合的目标是：**命令入口 → controller.complete → GoalServicePort → 真实 ctx.goals 的生产组合面真实存在且被 REAL-composition 测试端到端实证**；start 生产车道与证据生产者车道仍属延期 GAP（§7），本波不伪造其存在。

## 2. 接线点定稿（组合路径）

```
人类 slash 命令（Web/CLI 适配器 → ctx.commands.execute）
  → @deepseek-ai/dsh-experimental-command-goal-binding（函数插件，inject=['commands','goals','sessionProjections']）
    → handler({agent, rawInput})                       [agent = 接收命令的活 controller 会话 Agent]
      → GoalBindingComposition（Service, 本包）
        ├─ controller 注册表：Map<ControllerSessionId, GoalBindingController>（按 agent.id 惰性构造）
        ├─ new GoalServicePort({ goals: ctx.goals, agent })            [goal-binding.ts:212]
        ├─ new GoalBindingController({ workspaceId: config, controllerSessionId: ControllerSessionId(agent.id),
        │                               goals: port, store: 服务持有 MemoryGoalBindingStore })
        ├─ 证据取数：sessionProjections.stateOf(agent.session, 'devframe')
        │    → 最新 verification（checks + coverage.digest）与 review（goal 归属匹配者）
        ├─ controller.complete(identity, { worktreePath, checks, requiredChecksDigest, requiredChecksStore, review })
        │    [三谓词序指纹→检查→审查 在 evaluateCompletionAdmission 内，零改动]
        ├─ rejected → CommandResult error（stage 证据文本），native 零变更，无 receipt
        └─ admitted → ctx.goals.recordReceipt(agent, {id: completed.id, revision: completed.revision},
        │            evidence 条目携带 verdict 摘要) → CommandResult success
        结构性 throw（GoalBindingError/SourceFingerprintError/RequiredChecksError）原样传播 → dispatch 失败
```

命令名 `goal-complete`（`/goal-complete [worktreePath]`）；`worktreePath` 缺省取包 `Config.workspaceRoot`（显式 resolve defaults at package boundary，Config 域校验，非硬编码 tunable）。

## 3. 最小可回滚切片边界

- **切片内**：一个新私有实验包 `packages/experimental/command-goal-binding/`（组合 Service + 命令语法 + REAL-composition 测试 + 双语 README + tsconfig/package 登记）。删除该目录 + 还原 2 个登记文件（tsconfig aggregate、pnpm-workspace 无需动——workspace glob 已覆盖）即整体回滚。
- **切片外（禁止触碰）**：devframe 包本体（三谓词/fail-closed/热路径零改动）；goal 包本体；commands 包本体；snapshots/**、packages/test-support/session-snapshot/**、scripts/session-snapshot-corpus*、vendor/**、battery 域、主树写入。
- **不触的语义**：`evaluateCompletionAdmission` 三谓词评估序；拒绝=数据且 native 零变更、admission 保持关闭；complete 无 HumanAuthorization（三谓词证据链即授权，裁定不变）；热路径异步契约（complete 的 enqueue 串行化 + 显式 admission 期 recompute 不上热路径）；`SESSION_FORMAT_VERSION`/`SessionEventMap` 键集。
- **组合服务 API 面**：仅暴露命令 handler 所需最小面（`completeCurrent`）；start/resume 不进命令语法（其生产车道未定，防猜测性扩张）。

## 4. verdict/receipt 归属面定稿

| 数据 | 归属面 | 机制 | 本波键变更 |
|---|---|---|---|
| verdict 文本（人类可读裁定，含 stage/digest/失败理由） | session log `command/done` | commands registry 自记 verbatim text | 无 |
| 完成回执（admitted） | session log `goal/change`（operation:'receipt'） | `ctx.goals.recordReceipt(agent, completedRef, evidence)`；evidence 条目 ≥1：`kind:'completion-admission'`，summary 有界（goal id + digest + fingerprint 双值一致声明），`at`=Date.now() | 无 |
| 拒绝回执 | 无 receipt（结构不可能：phase≠complete 时 recordReceipt 抛 GOAL_INVALID_TRANSITION，且组合不调用） | fail-closed 结构保证 | 无 |
| 绑定日志面（`devframe/goal-binding` journal） | 延期 | 属未来 start 车道组合（start 时记录绑定，complete 时才有前后绑定可对照）；本波引入需凭空接 review-gate 权威，属猜测性扩张 | — |

## 5. 测试矩阵（REAL-composition 先行）

测试落新包 `tests/`；组合测试按 `devframe-qa-composition.spec.ts` 既有先例：真实 Context + 真实 `@deepseek-ai/dsh-commands` + 真实 `@deepseek-ai/dsh-goal` + 真实 JSONL persistence + SessionProjectionRegistry + 组合插件，经 `ctx.commands.execute(agent, line, [], signal)` 真实派发；git worktree 夹具沿 `devframe/tests` 既有模式（真实三 git 子进程路径，timeout 30s 级）。

- **正向**：start（经组合服务测试可见面构造绑定）→ 会话 log 追加归属该 goal 的 verification（passed，含 coverage）与 review（pass）→ store 登记 digest → `/goal-complete` → success 文本；`ctx.goals.get(agent).phase==='complete'`；log 含 `goal/change` receipt 变体（operation:'receipt'、evidence.kind='completion-admission'）与配对 `command/run`/`command/done`；绑定 store revision 已推进。
- **拒绝**：(a) 指纹不匹配（篡改 worktree 文件）→ error 文本指认 source-fingerprint stage；goal phase 不变；log 无 receipt；(b) required-checks 不足（弱化 checks）→ stage=required-checks 拒绝，同上；(c) review changes_required → stage=review 拒绝，同上。三者均验证 admission 保持关闭、native 零变更（fail-closed 回归）。
- **边界**：无 goal / 无绑定 / 无归属 verification 或 review / goal 已 complete → 稳定数据 error；digest 未登记 → `RequiredChecksError` 结构性传播（command/done error，非 data 拒绝）；review 归属另一 goal → `GoalBindingError` 结构性传播；`rawInput` 带 worktreePath 覆盖 Config 缺省（resolve defaults explicitly）。

## 6. 精确待改文件清单（Worker 申报基准）

**新增**（`packages/experimental/command-goal-binding/`）：
1. `package.json` — name `@deepseek-ai/dsh-experimental-command-goal-binding`，`private:true`，`type:module`，无 publishConfig；deps: `@deepseek-ai/dsh-experimental-devframe workspace:^`；peer: `@deepseek-ai/cordis`、`@deepseek-ai/dsh-agent`、`@deepseek-ai/dsh-commands`、`@deepseek-ai/dsh-goal`、`@deepseek-ai/schemastery`、`@deepseek-ai/dsh-session`、`@deepseek-ai/dsh-session-projection`；devDeps 补测试所需（cordis、goal、commands、session、session-projection、session-persistence-jsonl 等）。
2. `tsconfig.json` — extends `tsconfig.base.json`，`rootDir: src`，`outDir: lib/types`，引用工作区依赖；登记进对应 aggregate。
3. `src/index.ts` — 模块 JSDoc + 函数插件导出（`name`/`inject`/`Config`/`apply`）+ 类型再导出；无默认导出混淆（函数插件规约，packages/AGENTS.md）。
4. `src/composition.ts` — `GoalBindingComposition` Service（inject `['commands','goals','sessionProjections']`；[Service.init] 注册 `devFrameProjectionDefinition` + 效果化命令注册 `ctx.effect(() => ctx.commands.register({...}), 'command-goal-binding.register')`；controller 注册表；证据取数；completeCurrent；receipt 落地）。全部导出带 @param/@returns JSDoc。
5. `src/command.ts` — `/goal-complete` 语法（bare/带 worktreePath）、稳定错误文本、verdict 文本渲染（不暴露 branded id/revision——沿 command-goal 先例）。
6. `src/errors.ts`（如需）或并入 composition（命令侧稳定文本 + 结构性错误原样传播的分界）。
7. `README.md` / `README.zh.md` — Summary/Use/Implementation/Model Experience（命令零模型 token、receipt 使后续 goal 轮可见）/Known Limitations and Deferred Work（列 memory store 两项、start 车道延期、证据生产者延期）/Dev Note。
8. `tests/real-composition.spec.ts` — §5 矩阵（正向/拒绝/边界）。
9. `tests/command-grammar.spec.ts`（可选，若语法解析独立可测）。

**修改**（登记面，最小触碰）：
10. aggregate tsconfig（packages 实际聚合文件——Worker 以 `pnpm run build`/typecheck 实际报错为准登记确切路径）。
11. 若 `verify-package-readme-limitations` 要求：scripts 侧 allowlist 不动——README 必须自带 Limitations 节（见 7），不允许走 allowlist。

**禁止改动**：devframe、goal、commands、session*、core/session known-event-types、snapshots 域、vendor、scripts/session-snapshot-corpus*、docs/architecture.md（本波不新增顶层机制，扩展点既有）。

## 7. 诚实 GAP 登记（本波不动，上报总控）

1. **start/resume 生产车道**：谁在生产组合中调用 `controller.start`（宿主命令/UI/webhook）未定；本波组合服务保留该扩展位但不实现。
2. **证据生产者**：`devframe/verification`/`devframe/review` 的生产源（host 校验执行者、journal 审查门）仍未接线；本波组合读取这些记录而非生产它们。
3. **两 store 仍 memory 参考实现**：`MemoryGoalBindingStore`/`MemoryRequiredChecksConfigStore`（重启丢绑定、digest 登记进程内）；组合服务将其收敛为可替换注入边界，durable 实现属后续波。
4. **通用模型完成路径不经本 seam**：tool-goal/get_goal 等模型车道不变，本波只接人类命令车道。
5. **绑定日志面（devframe journal goal-binding 记录）**：随 start 车道延期（§4）。

## 8. Worker 边界与门禁（派发用摘要）

- 唯一源码写入域：`D:/dsh-devframe-v14-hostcmd-w1`（分支 `codex/v14-hostcmd-w1`，自 lead HEAD）；证据域其内 `.agents/devframe/v14-hostcmd/worker/**`。
- 设计先行：`worker/design.md` 先申报精确文件清单再动源码；逐笔提交 `--no-verify`（宿主无 bash，pre-commit lefthook exit 127 系环境事实），每笔提交信息登记：跳过门禁 + 替代验证真实结果（staged diff --check exit 0、每文件恰一尾随换行、触及域零 vendor 路径）。
- 门禁链（worktree 内）：`pnpm install` → 触及包聚焦 vitest 全绿 → 删全部 `*.tsbuildinfo` 后 `pnpm run build` exit 0 → 新增/变更导出服务类型则 `gen-cordis-catalog` 0 written → `git diff --check` exit 0。
- 硬语义约束（§3）逐条复核后交付。
