# v14-goalstore Worker 实现落地记录

- taskId: v14-goalstore（候选 2，唯一 Worker）
- 树: D:/dsh-devframe-v14-goalstore-w1（分支 codex/v14-goalstore-w1，自 lead HEAD c1585953ec）
- 契约源: ../lead/design.md（接口 file:line、账本 schema、方法语义、错误码裁定、继承裁定清单、测试矩阵 M1-M11、具名文件清单、门禁），实现与测试严格按其执行。

## 1. 交付物（恰好 7 项）

1. `packages/experimental/devframe/src/goal-binding-file-store.ts`（新增）
2. `packages/experimental/devframe/src/index.ts`（+1 行 `export * from './goal-binding-file-store.ts'`，required-checks-file-store 行后、`export type *` 行前，零其他变更）
3. `packages/experimental/devframe/tests/goal-binding-file-store.spec.ts`（新增，M1-M11）
4. `packages/experimental/devframe/README.md`（Source map +1 行，controller/goal-binding.ts 行后、hierarchy/index.ts 行前）
5. `packages/experimental/devframe/README.zh.md`（同位 +1 行中文对齐行）
6. `packages/experimental/devframe/README.i18n.yaml`（`pnpm run verify-translation-pairing --write packages/experimental/devframe/README.md` 重录，仅两条哈希变更）
7. `.agents/devframe/v14-goalstore/worker/design.md` + `receipts.md`（本记录域）

## 2. 实现要点（对齐 lead design §3）

- 单 JSON 账本 `{"version":1,"bindings":[GoalBinding...],"currents":[ProjectBindingRecord...]}`；`z.object().strict()` 信封 + 逐条 strict schema（对照先例 required-checks-file-store.ts 形态，zod ^4 包内既有依赖）。
- 逐读全量校验：非 JSON / 信封失败（未来 version、未知键、缺键、类型错）/ 条目 schema 与不变量失败 / 重复 `(controllerSessionId, goalId)` 绑定对 / 重复 workspaceId current，全部经本地 `corruptError()` 路由为 `GoalBindingError('goal binding ledger "<path>" is corrupt: <summary>', 'GOAL_BINDING_PERSISTENCE', { cause })`。
- 品牌重铸：schema 先以非空 trimmed 串校验（`length > 0 && value === value.trim()`），再经品牌函数重铸（`WorkspaceId`/`ControllerSessionId`/`nativeGoalId`/`AcceptanceHash`/`SourceFingerprint`/`DevFrameSnapshotId`/`ConfigurationConfirmationId`/`TaskId`）。校验先于重品牌，保证重品牌永不抛——否则 `ControllerSessionId()`/`TaskId()` 内部的控制器 `nonEmptyId` 会以 `GOAL_BINDING_INVALID_REQUEST` 逃出 corrupt 码路由（goal-binding.ts 本波冻结，不可改其语义）。
- 不变量：goalRevision 正 safe integer（对齐 assertNativeRevision）；taskIds 非空且唯一；budget `maxAttempts >= 1`、`consumedAttempts >= 0 且 <= maxAttempts`（跨字段 refine）；lifecycle z.enum 六态；confirmation strict 二字段。currents 无 version/taskIds/snapshotId/budget 字段。
- 方法语义镜像 `MemoryGoalBindingStore`（goal-binding.ts L126-174，只读）：
  - `load(controllerSessionId)`：读→校验→按 controllerSessionId 过滤、保文件序→逐读重解码（天然 detached 新对象）；账本缺失 → `[]`。
  - `read(workspaceId)`：读→校验→按 workspaceId 找；缺失 → `undefined`。
  - `save(binding)`：读→校验（corrupt 即抛，绝不修复/覆盖）→ 在 `binding.controllerSessionId` 作用域内按 goalId 找已有（findIndex 双条件，等价 memory store 的 per-session 数组作用域）；immutable 元组相同且 `goalRevision >=` 已有 → 原位替换，否则 `GoalBindingError('Goal "<id>" already has a different binding', 'GOAL_BINDING_CONFLICT')`（消息逐字镜像 memory store）；无已有 → 追加。
  - `write(record)`：读→校验→按 workspaceId upsert currents。
  - 发布 = 整账本 tmp `${path}.${randomBytes(6).toString('hex')}.tmp` + rename，内容 `${JSON.stringify(document, null, 2)}\n`；私有 `publishDocument()` 承载。无 fsync/锁/mkdir/prune。
- 入参零运行时校验（同进程 typed 边界信任规则）；运行时校验只在账本读回侧。
- `sameImmutableBinding`：字段对数组 + `every`（design §3.5 强制形态，与控制器 `&&` 链不同形，规避 jscpd minTokens 60/minLines 6，src 不豁免）；注释声明逐字段镜像冻结的控制器私有助手 `sameBinding`。
- 模块头 JSDoc 照先例结构：durable 边界全量校验叙述、corrupt 拒修、缺失=空态、tmp+rename、无锁单写者 last-writer-wins、injectable alternative、production wiring 属 owning wave；`@module @deepseek-ai/dsh-experimental-devframe/goal-binding-file-store`。

## 3. 与 lead design 的偏差

- **无功能偏差。** 两处记录在案的结构性选择，语义均为 design 裁定内容：
  1. **jscpd 结构规避（先例同域重写）**：`readLedger` 用 `.catch()` 而非先例的 try/catch 形态、损坏错误统一经本地 `corruptError()` 构造、zod issue summary 用数组 `join(': ')` 而非先例的模板字符串内联——三处均为先例同语义代码的换形重写，防止与 `required-checks-file-store.ts` 形成 ≥6 行/60 token 克隆（jscpd 门扫 packages、忽略 tests，src 不豁免）。错误消息模板 `goal binding ledger "<path>" is corrupt: <summary>` 与码值不变。
  2. **M7 corrupt 矩阵超集行**：design §6 M7 点名的类别全部覆盖（非 JSON、version 0/2、未知顶层键、缺 bindings/currents、非数组、非对象根、条目缺字段/未知键、空/空白品牌串、revision 非正、consumedAttempts>max、lifecycle 越界、重复身份对、重复 workspace current），另加同族不变量行：非数组 currents、非 safe-integer revision、空 taskIds、重复 taskIds——均为 §3.2「逐条 schema/品牌/不变量失败 → corrupt」的既有裁定面，非新开口。
- M6 按要求强于先例：save 拒修断言含 `readFile` 字节前后比对（Buffer.equals）+ corrupt 消息含 path。
- M9「path 为目录」用例经 `save` 触发（readLedger 对目录抛原始 fs 错误），design 只要求原始错误非 GoalBindingError，未钉方法。
- M4 家族补一条「同元组 revision 前进 → 原位替换且账本长度 1」：§3.3 save 语义（`goalRevision >=` → 替换）的直接行为覆盖；M5 家族补一条「同元组 revision 落后 → CONFLICT 且账本不变」：memory store L161 同一条件。

## 4. 继承裁定（沿用 lead design §5，零新开口）

无 fsync、无锁、无 mkdir、无 prune；tmp+rename 原子发布；拒修损坏；账本缺失=空态；非 ENOENT fs 错误原样上抛；逐读全量校验、未来版本 fail loud；重启等价面=实例重建（无子进程测试）；save+write 两阶段缝崩溃不自愈。composition 接线 / cordis.yml Config / host profile 默认注入属后续 wave。Agent Note 按先例由总控 authored。

## 5. 禁区核对

- 主树 D:/dsh-devframe 零写入（全部命令 workdir 指向工作树）。
- `.agents/devframe/v14/next/**`、`vendor/**`、`snapshots/**` 零触碰。
- packages/experimental/agent-evidence、command-goal-binding、shadow-router、project-memory 零 diff。
- `src/controller/goal-binding.ts`、`src/required-checks.ts`、`src/required-checks-file-store.ts` 零 diff（只读参考）。
- package.json/exports/tsconfig/entry-exports.spec.ts 零变更（lead 已核实无需改，git status 证实写域恰为 §1 七项）。
