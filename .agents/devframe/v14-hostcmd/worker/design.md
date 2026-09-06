# v14-hostcmd Worker 执行设计 — 宿主命令面 /goal-complete 组合（P23/S4）

任务：新建私有实验包 `packages/experimental/command-goal-binding`，把 `GoalBindingController.complete`（`packages/experimental/devframe/src/controller/goal-binding.ts:593-649`）经宿主命令面 `ctx.commands` 的 `/goal-complete` 真实派发接入组合逻辑。
工作树：`D:/dsh-devframe-v14-hostcmd-w1`（分支 `codex/v14-hostcmd-w1`，HEAD f9ae329095）。基线设计：`.agents/devframe/v14-hostcmd/lead/design.md`（VERIFIED）。

## 0. 主树事实复核（本 worktree 内 file:line 证据链）

- **命令面契约**：`packages/interaction/commands/src/types.ts:28-35` `CommandResult`；`:51-58` `CommandDescriptor`；`src/index.ts:333-400` `CommandRuntime.execute(agent, line, images, signal)`——handler 前后追加 `command/run`/`command/done`（`:345-350`、`:351-360`），抛错 handler `settleThrown` 后原样 rethrow（`:395-398`），结构性错误经 dispatch 以 rejection 到达调用方。registry 无 `static inject`（:254-266，`super(ctx, 'commands')`）。
- **注册先例**：`packages/session-query/session-log-export/src/index.ts:74-80` `ctx.effect(() => ctx.commands.register({...}), '...')`；`packages/goal/command-goal/src/index.ts:12-13,189-196` 函数插件 name/inject/apply 先例（无 Config、无默认导出）。
- **控制器构造**：`goal-binding.ts:354-359` `GoalBindingControllerOptions {workspaceId, controllerSessionId, goals, store}`；`GoalServicePort` 构造收 `{goals, agent}`（:212-241）；`CompleteGoalRequest`（:300-320）不含指纹（权威侧=durable binding，:296-298）；`MemoryGoalBindingStore`（:121-169 等价实现，read/write/load/save）、`GoalBindingController.start` 先例请求形状（tests/goal-binding.spec.ts:139-150）。
- **三谓词序（零改动）**：`evaluateCompletionAdmission`（goal-binding.ts:893-919）指纹→检查→审查固定序；结构错误（`SourceFingerprintError`、`RequiredChecksError`）fail-loud 原样传播（:883-887 注记）。
- **verdict/receipt 面**：拒绝=数据（`CompletionFingerprintRejection`/`CompletionChecksRejection`/`CompletionReviewRejection`，:832-864）；admitted=`{kind:'admitted', fingerprint, requiredChecksDigest}`（:822-830）。`GoalService.recordReceipt(agent, ref, evidence)`（`packages/goal/goal/src/index.ts:450-470`）仅 phase=complete 可录；`GoalEvidenceEntry`（`domain.ts:45-54`）kind=lower-kebab + 非空 summary + at；证据校验（index.ts:243-277）。
- **证据投影**：`packages/experimental/devframe/src/projection.ts:512-521` `devFrameProjectionDefinition`（key 'devframe'，host-only）；`DevFrameProjectionState.verifications/reviews`（:31-50）；fold 规则——`assertResultBinding` 要求先有 `devframe/goal-binding` 记录（:431-447、`applyVerification` 同），review 还要求匹配的 role-policy（policyVersion + reviewer 授权，:433-439）与同 snapshot 的 verification 存在（:440-442）。生产证据生产者尚不存在——**测试即生产者**（`tests/events.spec.ts:338-356` 先例：直接 `session.append('devframe/verification'|'devframe/review', ...)` 后经 fold 读取）。
- **真实组合先例**：`packages/experimental/devframe/tests/goal-binding.spec.ts:66-83`（realGoalPort：SessionStore + AgentRegistry + SessionProjectionRegistry + GoalService + minimal live Agent）；`packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts:35-50`（JsonlSessionPersistence `{root}` + flush/inspect 断言持久日志）。
- **git 夹具**：`packages/experimental/devframe/tests/completion-fixtures.ts:71-95`（隔离 git config 三子进程真实仓库）；指纹引擎只读、`ls-files -s` 读 index（src/source-fingerprint.ts:5-12）——篡改须 `git add` 落 index 才改变指纹。
- **schemastery Config 先例**：`session-log-export/src/index.ts:42-51` `Schema.object({...})`；cordis 对函数插件 `Config` 以 standard-schema 校验（vendor/cordis/src/registry.ts:326、fiber.ts:50-53）。
- **catalog 约束（裁定输入）**：`scripts/gen-cordis-catalog.ts:1033-1041` 独立 AST 扫描 `packages/*/*/src/**/*.ts` 的 **`declare module '@deepseek-ai/cordis'` Context merge**；新声明键必须进 `SERVICE_PAGE`（:56-135）+ subsystems 页并再生成 catalog。**本波门禁要求 catalog written=0 ⇒ 组合服务不得声明 Context merge**（服务仍以 Service 基类进程内注册，读取走 `ctx.reflect.get`，与 session-log-export 读 `connection` 的 `Reflect.get(ctx, 'connection')` 同型先例，session-log-export/src/index.ts:97-99）。零 Events merge——本波零新键，`SESSION_FORMAT_VERSION` 不动。

## 1. 组合逻辑与关键裁定

### 1.1 调用链（全部真实面）

```
ctx.commands.execute(agent, '/goal-complete [path]', [], signal)
  → registry: append command/run → handler(invocation)
  → GoalBindingComposition.completeCurrent({agent, worktreePath: parse(rawInput)})
      1) current = ctx.goals.get(agent)；undefined → 数据错误；phase==='complete' → 数据错误
      2) 控制器懒构造（registry Map<ControllerSessionId>）：
         new GoalBindingController({
           workspaceId: Config 解析值, controllerSessionId: ControllerSessionId(agent.id),
           goals: new GoalServicePort({ goals: ctx.goals, agent }),   // goal-binding.ts:212
           store: 组合持有的 MemoryGoalBindingStore })                // :354
      3) 绑定前置检查：组合持有 store.load(controllerSessionId) 无该 goalId 绑定 → 数据错误
         （否则 controller.complete 走 GOAL_BINDING_NOT_FOUND 结构性路径，与矩阵"无绑定→稳定数据错误"冲突）
      4) state = ctx.sessionProjections.stateOf(agent.session, 'devframe')
         state.failure !== null → 数据错误（投影重放已 latch，证据不可信，fail-closed）
         verification = 最新一条 binding.goalId === current.id 的记录；无 → 数据错误
         review = 最新一条 review 记录（见 1.2 裁定）；无 → 数据错误
      5) worktreePath = 命令参数 ?? Config.workspaceRoot；二者皆缺 → 数据错误（显式 resolve 步骤）
      6) controller.complete({controllerSessionId, goalId: current.id},
         {worktreePath, checks: verification.checks, requiredChecksDigest: verification.requiredChecks.digest,
          requiredChecksStore: 组合持有 store, review})
         —— 拒绝 → CommandResult error（stage 文本）；结构性错误（GoalBindingError/SourceFingerprintError/RequiredChecksError）
            不捕获、原样传播 → execute rethrow（registry settleThrown 落 command/done error）
         —— admitted → view = ctx.goals.get(agent)（complete 已推进 revision）
            ctx.goals.recordReceipt(agent, {id: view.id, revision: view.revision}, [completionEvidence])
            evidence = {kind:'completion-admission', summary 有界（goal id + digest + 双值一致声明）, at: Date.now()}
  → registry: append command/done → success
```

### 1.2 裁定：review 取"最新一条"、不做组合内 goal 归属过滤

交付文本："取归属该 goal 的最新 devframe/verification……与最新 devframe/review"，且矩阵明确 "review 归属另一 goal → `GoalBindingError` 结构性传播"。review 归属的结构性校验是 `GoalBindingController.complete` 自己的职责（goal-binding.ts:597-616 审查证据归属校验；"enforce a decision in the operation that makes it"，packages/AGENTS.md）——组合若先按 goalId 过滤 review，该结构性拒绝经本 seam 不可达，矩阵用例无法成立。故：**verification 按 goal 归属过滤取最新；review 取投影内最新一条（组合不预过滤），归属由控制器结构性校验**。代价（诚实登记）：完成 G1 时若日志最新 review 属于 G2，得到结构错误而非更友好的数据错误——fail-closed、错误方向保守；README 登记此语义。

### 1.3 裁定：组合服务形态

- 函数插件 `name='command-goal-binding'` / `inject=['commands','goals','sessionProjections']` / `Config` / `apply`（command-goal 先例；无默认导出，不混形态）。
- `apply(ctx, config)`：先 `resolveCommandGoalBindingConfig`（workspaceId 缺失/空白即 throw——misconfiguration fails loud，apply 期；workspaceRoot 存在时须非空绝对路径），再 `new GoalBindingComposition(ctx, resolved)`。
- `GoalBindingComposition extends Service`（cordis），`super(ctx, 'commandGoalBinding')`：构造期 `ctx.sessionProjections.register(devFrameProjectionDefinition)` + `ctx.effect(() => ctx.commands.register({...}), 'command-goal-binding.register')`。投影注册随本插件 fiber 卸载（GoalService 注册 goal 投影同型，goal/src/index.ts:298）。**不声明 Context merge**（§0 catalog 裁定）；服务经 `ctx.reflect.get('commandGoalBinding')` 进程内可达（测试用），README/JSDoc 记录。
- 测试可见面（申报）：`startBinding(request)`（产出 `StartGoalRequest` + `createHumanAuthorization(request.confirmationId)` 后委托 `controller.start`——人类授权铸造留在宿主适配器内，devframe src 注释 :261-266 契约）、`completeCurrent({agent, worktreePath?})`、`admissionOf(agent): GoalAdmission | undefined`（只读，供 fail-closed 矩阵断言 admission 保持关闭）、`bindingStore`/`requiredChecksStore` 只读暴露（参考实现可替换边界，本波均为 memory——GAP-3 延期不变）。`start` 不进命令语法（§7.1 车道延期）。

### 1.4 渲染文本契约（沿 command-goal 先例，不暴露 goal branded id/revision）

- 数据错误：固定稳定文本（无 id/revision）：无 goal / 无绑定 / 无 verification / 无 review / 已 complete / 投影重放失败 / worktree 路径缺失。
- 拒绝：stage 前缀 + 证据陈述。fingerprint：不渲染指纹值（文本说明双值不一致）；required-checks：渲染 digest + `checkId: reason` 列表（digest 非 goal 身份，lead §4 指定；条目数天然以人工批准的 checklist 为界）；review：渲染 decision + findings 数（不渲染 reviewId）。
- 成功：固定文本，无 id/revision。
- receipt summary（日志面，非渲染面）：`Goal <goalId> completion admitted: source fingerprint verified (recorded equals fresh), required checks <digest> satisfied, authorized review passed.`（有界；lead §4 指定 goal id + digest + 双值一致声明）。

## 2. 精确文件清单（新增 12 + 修改 1）

**新增 `packages/experimental/command-goal-binding/`**：

1. `package.json` — name `@deepseek-ai/dsh-experimental-command-goal-binding`，version `0.1.2-alpha.4`，`private:true`、无 publishConfig、`type:"module"`；main/lib/types 与 `./src/*`、`./package.json` exports（devframe 同型）；dependencies：`@deepseek-ai/dsh-experimental-devframe workspace:^`；peer：`@deepseek-ai/cordis`、`@deepseek-ai/dsh-agent`、`@deepseek-ai/dsh-commands`、`@deepseek-ai/dsh-goal`、`@deepseek-ai/dsh-session`、`@deepseek-ai/dsh-session-projection`、`@deepseek-ai/schemastery`（均 workspace:^）；devDeps：peer 全集 + devframe + `@deepseek-ai/dsh-session-persistence-jsonl`（测试需要）。
2. `tsconfig.json` — extends `../../../tsconfig.base.json`，rootDir `src`，outDir `lib/types`，include `["src"]`；references：vendor/cosmokit、vendor/schemastery、vendor/cordis、core/agent、core/session、goal/goal、interaction/commands、session/session-projection、experimental/devframe（相对路径 `../../...`）。
3. `src/index.ts` — 模块 JSDoc `@module`；定义并导出 `name`/`inject`/`Config`/`apply`（apply 薄：resolve config → `new GoalBindingComposition`）；类型再导出 `CommandGoalBindingConfig`、`GoalBindingComposition`（type）、`StartGoalBindingRequest`、`ResolvedCommandGoalBindingConfig`；**无默认导出**。
4. `src/config.ts` — `CommandGoalBindingConfig` 接口 + `Config: Schema<CommandGoalBindingConfig>`（workspaceId `Schema.string().required()`；workspaceRoot 可选）+ `resolveCommandGoalBindingConfig`（trim/非空/绝对路径校验，违规 throw）。
5. `src/composition.ts` — `GoalBindingComposition extends Service`（§1.3 全部职责）+ `StartGoalBindingRequest` 类型 + `controllerFor` 懒构造 + 证据选取 + receipt 落地。全导出带 @param/@returns。
6. `src/command.ts` — `COMMAND_NAME='goal-complete'`、命令 definition 工厂（name/description/input hint）、`parseGoalCompleteInput`（trim；空=bare/undefined，否则整段为 worktreePath）、稳定文本常量、`renderCompletionRejection`（closed-union switch + assertNever）、`renderCompletionSuccess`、`completionAdmissionEvidence`（receipt summary 构造）。
7. `tests/real-composition.spec.ts` — 矩阵全套（§3）。
8. `tests/command-grammar.spec.ts` — 纯语法/渲染小套件。
9. `README.md` / 10. `README.zh.md` — YAML frontmatter（description/kind:"package-reference"）；Summary / Use this package（命令参考表 + Compose it）/ Understand the implementation（Source map 表）/ Model Experience（What the model sees、Token effect、KV Cache effect）/ Known Limitations and Deferred Work（两个 memory store、start/resume 车道延期、devframe 证据生产者延期、通用模型完成路径不经本 seam、review"最新一条"语义）/ Dev Note。
11. `README.i18n.yaml` — 双语对账记录（`pnpm run verify-translation-pairing --write` 生成）。

**修改（1 个登记文件）**：

12. `tsconfig.host.json` — references 于 `:308` devframe 行后插 `{ "path": "./packages/experimental/command-goal-binding" }`。Host-only 包不进 client 面。`pnpm-workspace.yaml` glob `packages/*/*` 已覆盖，不动。

## 3. 测试矩阵落点（tests/real-composition.spec.ts，除注明外）

真实组合 boot：`new Context()` + SessionStore + AgentRegistry + SessionProjectionRegistry + JsonlSessionPersistence{mkdtemp root} + GoalService + CommandRuntime + 本插件（Config.workspaceRoot 仅部分用例给）+ `ctx.sessions.create` + minimal live Agent（goal-binding.spec.ts:45-63 同型）+ `ctx.agents.register`。afterEach：`ctx.fiber.dispose()` + `drainWorktreeFixtures()` + rm storage root（组合卸载=投影与命令注册随之移除）。worktree 夹具照 `completion-fixtures.ts` 模式（隔离 git config、三子进程真实执行、`{ timeout: 30_000 }`）。

| # | 用例 | 断言 |
|---|---|---|
| 1 | 正向：startBinding → 补录 role-policy/goal-binding/verification/review → bare `/goal-complete`（Config.workspaceRoot 生效） | execute success；goal phase complete；binding store goalRevision = 完成后 revision（=complete 前+1）；`goal/change` receipt 变体（operation 'receipt'、evidence[0].kind 'completion-admission'）；`command/run`+`command/done` 同 commandId 配对且 done kind success；成功文本不含 goal id/revision；`ctx.sessions.flush` + `ctx.sessionPersistence.inspect` 持久日志含 run/done/receipt |
| 2 | 正向：`/goal-complete <path>` 显式参数覆盖 Config.workspaceRoot | execute success 且 fingerprint 匹配该参数树（双 worktree 夹具：Config 指树 A、参数指树 B，绑定按 B 计算） |
| 3 | 拒绝×指纹：start 后篡改文件并 `git add -A` | execute resolve 为 `{kind:'error'}`，文本含 `source-fingerprint`；phase 不变；log 无 receipt；`admissionOf` 为 closed |
| 4 | 拒绝×checks：verification 的 lint status 'failed'（命令与 config 精确一致，schema 可解码） | error 文本含 `required-checks` 与 `REQUIRED_CHECKS_NOT_PASSED`；phase 不变；无 receipt；admission closed |
| 5 | 拒绝×review：review decision 'changes_required' | error 文本含 `review`；phase 不变；无 receipt；admission closed |
| 6 | 边界：无 goal（未 create） | 数据错误（无 goal 文本），log 仅 command/run+done(error) |
| 7 | 边界：无绑定（`ctx.goals.create` 直建、未经 startBinding） | 数据错误（无绑定文本） |
| 8 | 边界：无归属证据（startBinding 后不补录 verification） | 数据错误（无 verification 文本） |
| 9 | 边界：goal 已 complete（正向完成后再次执行） | 数据错误（已 complete 文本） |
| 10 | 边界：digest 未登记（不注册 requiredChecksStore） | `execute` rejects.toMatchObject `{name:'RequiredChecksError', code:'REQUIRED_CHECKS_CONFIG_NOT_FOUND'}`；command/done kind error；phase 不变；无 receipt；admission closed |
| 11 | 边界：review 归属另一 goal（补录 G2 完整三元组，最新 review 属 G2，current=G1） | `execute` rejects 且 error 为 GoalBindingError（message 含归属 goal 不符）；phase 不变；无 receipt |
| 12 | 边界：SourceFingerprintError 传播（worktreePath 指向不存在目录） | `execute` rejects `{name:'SourceFingerprintError'}` |
| 13 | 边界：投影重放失败 latch（追加损坏 verification——重复 verificationId） | 数据错误（投影失败文本），fail-closed |
| 14 | apply 期 misconfiguration（`ctx.plugin(plugin, {workspaceId:''})`） | rejects（fail loud） |

`tests/command-grammar.spec.ts`：bare/带路径/两侧空白解析；渲染文本契约（拒绝三分支文本含 stage、不含 goalId 字面量；成功文本；evidence summary kebab kind 可过 `resolveEvidenceEntry` 语义——kind 形状单测）。

## 4. 预期门禁与预期退出码（逐条真实执行并记录）

1. `pnpm install`（worktree 根）→ exit 0。
2. `pnpm exec vitest run packages/experimental/command-goal-binding packages/experimental/devframe` → exit 0；记录通过/失败计数（预期新包 15+ 用例、devframe 既有全绿）。
3. 删除全部 `*.tsbuildinfo` 后 `pnpm run build` → exit 0。
4. `pnpm run gen-cordis-catalog` → exit 0 且输出 written=0（零 Context/Events merge ⇒ catalog 不变）。
5. `git diff --check`（HEAD 相对与暂存区两侧）→ exit 0；自检每触及文件恰一尾随换行；触及域零 vendor 路径。
6. 附加：`pnpm run verify-translation-pairing --write packages/experimental/command-goal-binding/README.md` 生成双语对账记录。

## 5. 语义约束自检口径（交付时逐条复核）

1. `evaluateCompletionAdmission` 三谓词序零改动——本波 devframe 包源码零 diff（门禁 5 的触及清单佐证）。
2. fail-closed：拒绝=数据、native 零变更（不调用 port.complete）、admission 保持关闭；投影失败/证据缺失/无绑定/已 complete 均为拒绝方向的稳定数据错误。
3. complete 热路径契约：组合只在显式命令调用中触发 `controller.complete`（内部 enqueue 串行 + 指纹 recompute 仅在该调用），`assertAdmitted` 热路径零触碰。
4. `SESSION_FORMAT_VERSION` 与 `SessionEventMap` 键集零变更（零 Events merge、零新键）。
5. goal/commands/devframe/core-session 包源码零改动；唯一源码写入域内新增 1 包 + tsconfig.host.json 登记。

## 6. 提交计划（逐笔 --no-verify + 尾部 gate-skip 登记行）

1. `docs(v14-hostcmd): worker execution design for the host command surface wave`（本文件）。
2. `feat(command-goal-binding): add the /goal-complete host command composition package`（§2.1-6 + tsconfig.host.json）。
3. `test(command-goal-binding): pin the /goal-complete real composition matrix`（§2.7-8）。
4. `docs(command-goal-binding): bilingual README for the /goal-complete composition`（§2.9-11）。
5. `docs(notes): record the host command completion surface decision`（Agent Note 双语，implemented/architecture，引用既有 proposed note 的剩余范围不动）。
