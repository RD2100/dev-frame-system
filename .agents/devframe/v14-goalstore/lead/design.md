# v14-goalstore Lead Design — GoalBindingStore 持久化实现波

- taskId: v14-goalstore（用户并行补位候选 2）
- lead 树: D:/dsh-devframe-v14-goalstore-lead（分支 codex/v14-goalstore-lead，基点 c79f85fb81，干净）
- 日期: 2026-07-30（波次记录以结算报告为准）
- 状态: design 定稿；唯一 Worker 待派发（workflow agent huoshan-2/glm-5.3-flash）

## 1. 波次目标

devframe 包内 `GoalBindingStore` 当前唯一实现是进程内存参考实现 `MemoryGoalBindingStore`（重启即失，绑定源非持久）。本波交付文件后备 durable 实现：新文件 `src/goal-binding-file-store.ts`，实现既有接口、零语义变更，持久化契约对照同包 `required-checks-file-store.ts` 先例。用户已裁定 durable 实现属真实未完成工作，本波交付。

## 2. 接口核实（主树只读，file:line 钉死）

### 2.1 接口定义 — packages/experimental/devframe/src/controller/goal-binding.ts

- L117-123 `GoalBindingStore extends ProjectBindingPersistence`：
  - L120 `load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]>`（"Load every binding for one controller Session, including completed Goals"）
  - L122 `save(binding: GoalBinding): Promise<void>`（"identical retries must be idempotent"）
- 继承面 `ProjectBindingPersistence`（src/shared/types.ts L99-104）：
  - L101 `read(workspaceId): Promise<ProjectBindingRecord | undefined>`（"without creating or changing a workspace"）
  - L103 `write(record): Promise<void>`（"Persist one already validated record atomically"）
- L126-174 `MemoryGoalBindingStore`（参考实现，本波零变更、保留为默认）：
  - L127-128 两个 Map：`values: Map<ControllerSessionId, GoalBinding[]>`、`current: Map<WorkspaceId, ProjectBindingRecord>`
  - L135-137 `load` 返回 detached 拷贝；L140-143 `read`；L146-148 `write` 按 workspaceId upsert
  - L155-173 `save` 语义：按 controllerSessionId 作用域内按 goalId 找已有（L156-157）；已有且 `sameBinding(current, binding) && binding.goalRevision >= current.goalRevision` → 原位替换（L158-165）；否则 `GoalBindingError('...', 'GOAL_BINDING_CONFLICT')`（L166-169）；无已有则追加（L171）
- 错误族 L322-348：`GoalBindingErrorCode`（含 L331 `GOAL_BINDING_PERSISTENCE`、L332 `GOAL_BINDING_CONFLICT`）+ `GoalBindingError`（name='GoalBindingError'，code 字段）
- 控制器消费（同文件）：
  - L354-359 `GoalBindingControllerOptions.store: GoalBindingStore`（构造注入边界）
  - L383-410 构造即 `store.load(controllerSessionId)` + `store.read(workspaceId)`；L392-397 workspace 归属他控 → `GOAL_BINDING_IDENTITY_MISMATCH`；L398-405 current 无匹配绑定 → `GOAL_BINDING_PERSISTENCE`；L780-791 载入重复 goalId → `GOAL_BINDING_CONFLICT`
  - L733-753 `saveBinding`：先缓存比对（L734-740），再 `store.save(binding)` + `store.write(toProjectBindingRecord(binding))` 两连发（L742-743），失败包 `GOAL_BINDING_PERSISTENCE`（L744-750）
  - L711-723 `ensureReady`：构造期 load 失败 → `GOAL_BINDING_PERSISTENCE`（cause 保留）
  - 私有助手不导出：`sameBinding` L1031-1043、`toProjectBindingRecord` L1059-1070、`copyBinding` L1103-1121
- 类型事实：全部品牌串为编译期品牌（shared/types.ts L8-20，`Branded<B>`），运行时是 plain string；JSON 序列化无损，读回需重品牌。

### 2.2 消费点（全部）

1. packages/experimental/command-goal-binding/src/composition.ts（组合）：
   - L49-54 `GoalBindingCompositionStores.bindings?: GoalBindingStore`（组合注入面）
   - L108 `this.bindingStore = stores.bindings ?? new MemoryGoalBindingStore()`
   - L180 `completeCurrent` 直读 `this.bindingStore.load(controllerSessionId)`（错误原样上抛 → 命令注册表按结构失败结算）
   - L226 `controllerFor` 传 `store: this.bindingStore`
2. devframe 控制器（2.1）。
3. 测试（全部继续用 MemoryGoalBindingStore，本波零 diff）：
   - devframe/tests/goal-binding.spec.ts（L156/L203/…/L716；L217-222 4 方法 fake store 钉死最小实现面）
   - agent-team/tests/devframe-qa-composition.spec.ts L82（`GoalBindingController` 直注 `store: new MemoryGoalBindingStore()`）
   - agent-evidence/tests/at105-rejection-matrix.spec.ts L218
4. 导出：devframe/src/index.ts L3（controller 桶）；command-goal-binding/src/index.ts L17（Stores 类型）。

### 2.3 最小实现面裁定

- 必须持久化的是全部四个方法：`load`（每 controllerSession 全量绑定含 completed）、`save`（绑定）、`read`/`write`（工作区当前 `ProjectBindingRecord`）。控制器构造路径同时消费 load+read（L383-410），saveBinding 同时消费 save+write（L742-743）——只做 load/save 是错误设计。
- 组合注入边界 = 既有 `GoalBindingCompositionStores.bindings` → `GoalBindingControllerOptions.store`，零新增接缝。
- goal-binding.spec.ts L217-222 的 fake store（load/save/read/write 四方法）是接口最小面的既有证词。

## 3. 持久化契约（对照 required-checks-file-store.ts 先例逐条）

先例事实（src/required-checks-file-store.ts）：LEDGER_VERSION=1（L38）；strict zod 信封（L51-54）；逐读全量校验 parseLedger（L81-117：非 JSON→corrupt、信封失败→corrupt、逐条 digest 自洽→corrupt，全部 `REQUIRED_CHECKS_STORE_CORRUPT`）；readLedger ENOENT→undefined、其他 fs 原样上抛（L127-138）；Options.path 按原样用、父目录必须已存在、无 mkdir（L141-148）；save 先读后写、corrupt 拒绝不修复（L186）、幂等（L188-190）、tmp `${path}.${randomBytes(6).toString('hex')}.tmp`（L195）+ rename（L197）、`JSON.stringify(document, null, 2)\n`（L196）；模块头明确无锁单写者 last-writer-wins（L14-21）、"wiring it into a profile or host Config belongs to the owning wave"（L20-21）。

### 3.1 账本 schema（单文件 JSON 账本）

```
{ "version": 1, "bindings": [GoalBinding...] , "currents": [ProjectBindingRecord...] }
```

- strict 信封：`version: z.literal(1)`；`bindings`/`currents` 为数组；未知顶层键 = corrupt。
- bindings 逐条（读回时全部经品牌函数重品牌，全部字段必填、strict）：
  - `version: z.literal(1)`（GoalBinding.version）
  - 非空 trimmed 串字段：workspaceId→`WorkspaceId()`、controllerSessionId→`ControllerSessionId()`（../controller/goal-binding.ts 导出函数）、goalId→`nativeGoalId`（@deepseek-ai/dsh-goal 的 GoalId 函数）、acceptanceHash→`AcceptanceHash()`、sourceFingerprint→`SourceFingerprint()`、snapshotId→`DevFrameSnapshotId()`（均 src/shared/types.ts 导出）
  - `goalRevision`：正 safe integer（对齐 assertNativeRevision 语义）
  - `taskIds`：非空数组、元素经 `TaskId()`、唯一（resolveStartRequest L951-953 保证写出侧如此）
  - `confirmation`：`{ id: ConfigurationConfirmationId(非空), acceptanceHash: AcceptanceHash(非空) }` strict
  - `lifecycle`: z.enum 六态（shared/types.ts L68-73）
  - `budget`: `{ maxAttempts: safe int >=1, consumedAttempts: safe int >=0 且 <= maxAttempts }`（resolveBudget L996-1007 不变量）
- currents 逐条（`ProjectBindingRecord` 形，无 version/taskIds/snapshotId/budget）：workspaceId、controllerSessionId、goalId、goalRevision、acceptanceHash、sourceFingerprint、confirmation、lifecycle，strict。

### 3.2 逐读完整性与稳定损坏码

- 逐读全量校验：非 JSON → corrupt；信封失败（含未来 version、未知键、缺键、类型错）→ corrupt；逐条 schema/品牌/不变量失败 → corrupt；重复 `(controllerSessionId, goalId)` 绑定对 → corrupt（save 只能替换，不可能写出）；重复 workspaceId 的 current → corrupt（write 只能 upsert）。
- 与先例的域差异（记录，非缺口）：先例有 digest 重算自洽检查；绑定域无可重算派生字段（acceptanceHash 覆盖 objective+配置，不覆盖绑定本体），逐读完整性 = 全量 strict schema + 结构唯一性，深度与"写出侧保证什么就校验什么"一致。
- 稳定损坏码（任务给定分支判定）：绑定域已有错误族 `GoalBindingError`/`GoalBindingErrorCode`（goal-binding.ts L322-348，已导出）→ **复用**，不新增码。corrupt/不可读账本 → `GoalBindingError('goal binding ledger "<path>" is corrupt: <summary>', 'GOAL_BINDING_PERSISTENCE', { cause })`；身份复用冲突 → `'GOAL_BINDING_CONFLICT'`（消息镜像 memory store）。不触碰 goal-binding.ts（本波该文件语义零变更冻结）；控制器自身把 load 失败包成 GOAL_BINDING_PERSISTENCE（L713-719），族一致；composition L180 直读路径上抛的也是同族 GoalBindingError。

### 3.3 方法语义（镜像 MemoryGoalBindingStore，零语义变更）

- `load(controllerSessionId)`：读→校验→按 controllerSessionId 过滤、保文件序（=插入序）→解码新对象（天然 detached）。账本缺失 → `[]`。
- `read(workspaceId)`：读→校验→按 workspaceId 找，无则 undefined。
- `save(binding)`：读→校验（corrupt 即抛，**绝不修复/覆盖**）→ 在 `binding.controllerSessionId` 作用域内按 goalId 找已有：有且 immutable 元组相同且 `goalRevision >=` 已有 → 替换；有但不满足 → `GOAL_BINDING_CONFLICT`；无 → 追加。发布 = 整账本 tmp+rename 重写。
- `write(record)`：读→校验→按 workspaceId upsert current→整账本重写。
- 入参不做运行时校验（同进程 typed 边界信任规则，AGENTS.md）；运行时校验只在 durable/file 边界（读回侧）。

### 3.4 类与命名（先例形态）

- 文件 src/goal-binding-file-store.ts（任务定名）；`@module @deepseek-ai/dsh-experimental-devframe/goal-binding-file-store`
- `export interface FileGoalBindingStoreOptions { readonly path: string }`
- `export class FileGoalBindingStore implements GoalBindingStore`
- 模块 JSDoc 照先例结构：durable 边界叙述、无锁单写者、injectable alternative、production wiring 属 owning wave。

### 3.5 本地比较镜像与 jscpd

控制器私有 `sameBinding`（L1031-1043）不可导入（该文件冻结）。新文件本地实现 `sameImmutableBinding`：字段集逐项一致（identity 对、workspaceId、acceptanceHash、sourceFingerprint、snapshotId、confirmation.id、confirmation.acceptanceHash、budget.maxAttempts、budget.consumedAttempts、taskIds 长度+逐位），结构采用字段对数组 + `every`（与控制器的 `&&` 链不同形，规避 jscpd minTokens 60/minLines 6，src 不豁免）；注释引用冻结的控制器私有助手。不需要 copyBinding/toProjectBindingRecord 镜像（解码天然新对象；write 入参已是投影记录）。

## 4. Config 注入路径

- 唯一新配置面：`FileGoalBindingStoreOptions.path`（按原样使用；首写创建；父目录必须已存在——继承先例，无 mkdir；显式传入，无隐藏默认）。
- 注入链全部既有、零变更：`GoalBindingCompositionStores.bindings`（composition.ts L51）→ 构造 `stores.bindings ?? Memory`（L108）→ `GoalBindingControllerOptions.store`（goal-binding.ts L358）；`completeCurrent` 直读 `bindingStore.load`（L180）。
- 本波不改 composition 默认值、不加 cordis.yml Config 字段——继承先例裁定（FileRequiredChecksConfigStore 同样未接线 composition）。

## 5. 继承裁定清单（沿用先例，记录为继承而非新开口）

1. 无 fsync、无锁、无 mkdir、无 prune、无并发合并；单写者假设，并发写 last-writer-wins。
2. tmp+rename 原子发布；读者见旧或新完整账本，永不撕裂。
3. 拒修损坏：save/write 前置读校验，corrupt 即抛，绝不覆盖写。
4. 账本缺失 = 空态（load→[]、read→undefined），非错误。
5. 非 ENOENT fs 错误原样上抛，不包错误族。
6. 逐读全量校验；未来版本 fail loud。
7. 重启等价面 = 重建 store 实例（先例无子进程测试，本波同样不引入）。
8. save+write 两阶段缝：进程在两发布之间崩溃 → current 落后 bindings → 下次构造 sameProjectBinding 不匹配 → GOAL_BINDING_PERSISTENCE fail loud，不自愈（fails-loud 原则 + 拒修延伸）。

## 6. 重启测试矩阵（tests/goal-binding-file-store.spec.ts）

| # | 用例 | 断言 |
|---|---|---|
| M1 | 绑定跨实例等值 | store A save(b)；同 path 新实例 load → `[b]` toEqual（品牌完好） |
| M2 | 工作区记录跨实例等值 | A write(r)；新实例 read(ws) → toEqual r |
| M3 | 控制器级重启 | 控制器 A（file store）start → 新控制器 B（新实例同 path + 匹配的 fake NativeGoalPort）resume(同 identity) → 等值 binding、admission open |
| M4 | 幂等重复保存 | 同元组再 save（revision>=）→ 原始 JSON 读回 bindings 长度不变 |
| M5 | 身份复用冲突 | 同 identity 不同 acceptanceHash → GOAL_BINDING_CONFLICT；新实例上同样 |
| M6 | 拒修损坏 | corrupt 账本 + save → corrupt 抛出且**文件字节不变**（readFile 前后比对，强于先例） |
| M7 | corrupt 矩阵 it.each | 非 JSON、version 0/2、未知顶层键、缺 bindings/currents、非数组、非对象根、条目缺字段/未知键、空/空白品牌串、revision 非正、consumedAttempts>max、lifecycle 越界、重复身份对、重复 workspace current → load 与 save 均 GOAL_BINDING_PERSISTENCE（name='GoalBindingError'） |
| M8 | 缺失账本 | load→[]、read→undefined |
| M9 | raw fs | save 入缺失父目录 → 非 GoalBindingError 的原始错误；path 为目录 → 同 |
| M10 | 格式钉死 | 2 空格 pretty、version 1、恰一尾随换行（`endsWith('\n') && !endsWith('\n\n')`） |
| M11 | detached 与 upsert | 改动返回对象不影响再读；两 workspace 的 currents upsert 各自独立、账本长度=2 |

## 7. 最小待改文件清单（具名，Worker 写域全集）

| # | 文件 | 变更 |
|---|---|---|
| 1 | packages/experimental/devframe/src/goal-binding-file-store.ts | 新增（§3） |
| 2 | packages/experimental/devframe/src/index.ts | +1 行 `export * from './goal-binding-file-store.ts'`（现 L10 required-checks-file-store 行后、`export type *` 行前） |
| 3 | packages/experimental/devframe/tests/goal-binding-file-store.spec.ts | 新增（§6） |
| 4 | packages/experimental/devframe/README.md | Source map +1 行（按路径序插 `src/controller/goal-binding.ts` 行与 `src/hierarchy/index.ts` 行之间，即现 L100 后） |
| 5 | packages/experimental/devframe/README.zh.md | 同位 +1 行（现 L104 required-checks 行所在的对应位置，与英文行语义对齐） |
| 6 | packages/experimental/devframe/README.i18n.yaml | `pnpm run verify-translation-pairing --write packages/experimental/devframe/README.md` 重录哈希 |
| 7 | .agents/devframe/v14-goalstore/worker/** | Worker 记录域（design 落地记录、门禁收据） |

先例对照：required-checks-file-store 落地同样只有 Source map 行（无散文段、无 tests 行、无 package.json exports 变更、entry-exports.spec.ts 无需改——它只断言具名导出身份，不穷举）。tests/required-checks-file-store.spec.ts 在 Source map 无行，本波 tests 新文件同样不加行。

## 8. Worker 门禁（真实退出码，全部在 Worker 树内跑）

1. `pnpm install --frozen-lockfile`（worktree 无 node_modules，先例波同）
2. `pnpm exec vitest run packages/experimental/devframe` 全绿（含新 spec；goal-binding.spec 等既有 spec 不得回归）
3. 删全部 `*.tsbuildinfo` → `pnpm run build` → exit 0
4. `pnpm run gen-cordis-catalog` → 预期 0 written（catalog 是 ctx.&lt;key&gt; 服务/事件投影，devframe 纯类导出无 catalog 行——先例即无）；若非 0 written → 停止、上报阻塞，不得提交未具名文件
5. `git diff --check` → exit 0
6. 每个触及文件恰一尾随换行
7. `pnpm run test:docs` → exit 0（doc-quick 15 门，含双语配对）
8. commit 用 `--no-verify` + 收据：宿主无 bash，pre-commit lefthook/vendor manifest guard exit 127 系环境事实；替代验证 = staged diff --check exit 0、逐文件尾随换行核对、触及域零 vendor 路径，三项写入 worker 记录域

## 9. Worker 边界（写进 Worker prompt）

- 禁创建任何 Agent；不派发、不再分层。
- 写域 = §7 具名 7 项；工作树 = D:/dsh-devframe-v14-goalstore-w1（分支 codex/v14-goalstore-w1，自 lead HEAD）。
- 禁区（零触碰）：`.agents/devframe/v14/next/**`、`vendor/**`、`snapshots/**`；packages/experimental/agent-evidence、command-goal-binding、shadow-router、project-memory 零 diff；既有 `src/controller/goal-binding.ts` 与 `src/required-checks*.ts` 语义零变更（只许 §7 声明的新增文件/index.ts 一行/README 行/记录域）；主树 D:/dsh-devframe 零写入；BatteryFix 链（快照域）零交互。
- 禁 push/PR/发布/删除；禁合并 main。
- 真实容量错误才记退避。

## 10. GAP / 非目标

- Agent Note：按 v14-evjournal 先例由总控 authored，本波记录域不含。
- composition 接线 / cordis.yml Config 字段 / host profile 默认注入：属后续 wave（先例同裁定）。
- 跨进程真子进程重启测试：证据面 = 实例重建（先例同），不引入子进程测试。
- docs/architecture.md：无 devframe 章节（仅 L123/L141 通用 Goal 行），零 diff 安全，已核实。
- 并发写合并、跨进程锁：继承先例明确不做。

## 11. 派发与车道

- 唯一 Worker：workflow 工具 `agent(prompt, { provider: 'huoshan-2', model: 'glm-5.3-flash' })`，单 agent、单轮、前台等待。
- 车道说明：lead 自身 subagent schema 无 provider 参数，lead 走 huoshan-1，如实登记；Worker 显式点名 huoshan-2。
- 禁重复派发/多 Worker；与在飞 BatteryFix 链零共享文件。
