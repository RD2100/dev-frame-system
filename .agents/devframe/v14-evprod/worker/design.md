---
description: V1.4 evprod checksstore 切片设计（taskId v14-evprod-checksstore）：RequiredChecksConfigStore 的文件后备 durable 参考实现 FileRequiredChecksConfigStore——digest → config JSON 登记账本 schema、错误码族（沿用 NOT_FOUND/INVALID_CONFIG、新增 STORE_CORRUPT）、tmp+rename 原子发布与单写者边界、测试矩阵、精确文件清单与门禁计划。
---

# V1.4 FileRequiredChecksConfigStore 设计（file-backed durable 参考实现切片）

- 基点：worktree `D:/dsh-devframe-v14-evprod`，分支 `codex/v14-evprod` @ `6dd8c85bfc`（总控已建；开工时 `git status` 干净，HEAD `6dd8c85bfc947fb0d5513c89bad5a06303d7bf07`）。主树 `D:/dsh-devframe` 只读。
- 性质：在既有 `RequiredChecksConfigStore` 接口之后新增一个**可注入替代实现**（file-backed durable 参考实现），仅导出、不接线；`sameRequiredCheckCommand` 精确等值与 `acceptanceCheckComponent` 合成语义零改动。
- 已并上游事实（p05wave，worktree 逐条 file:line 自查核实，未照抄主树表述）：
  - 接口 `RequiredChecksConfigStore`：`packages/experimental/devframe/src/required-checks.ts:161-178`（`save` :168、`load` :177）；契约 JSDoc 钉死 "load is the untrusted durable read and must go back through `decodeRequiredChecksConfig`，failing loud（undecodable bytes → `REQUIRED_CHECKS_INVALID_CONFIG`、unregistered digest → `REQUIRED_CHECKS_CONFIG_NOT_FOUND`）instead of inventing a fallback configuration"（:151-159）。
  - Memory 参考实现：同文件 :186-221（同 digest 重复 save 首登记有效 :196-200；load 逐次经 decode :219；NOT_FOUND 抛点形态 :214-218）。
  - 错误码族 `RequiredChecksErrorCode`：:93-103；`REQUIRED_CHECKS_INVALID_CONFIG` 抛点 `decodeRequiredChecksConfig` :136-149。
  - 身份面 `requiredChecksDigest`：:293-305，格式 `dsh-required-checks-v1-<64 hex>`（:280、:304）。
  - 消费点（本波只提供注入件，不接线）：`src/controller/goal-binding.ts:312`（`CompleteGoalRequest.requiredChecksStore`）、:900（`evaluateCompletionAdmission` 内 `store.load`）。
  - 出口面：`src/index.ts:9` 对 required-checks 模块通配导出；`package.json:38` `"./src/*"` 深导入已开放（command-goal-binding 即经此导入 Memory 实现）。
- 零改动断言面（本波不触碰实现，测试经文件边界钉语义）：`sameRequiredCheckCommand` :333-338、`acceptanceCheckComponent` :319-321、`evaluateRequiredChecks` :357-389、`requiredChecksDigest` 算法 :293-305、`src/events.ts` 全部（含 verification 覆盖规则）。

## 模型裁定：digest → config 登记账本（非单配置文件）

任务令"从 Config 提供的 JSON 路径加载 required-checks 配置"。落点为一个 JSON **登记账本**文件（宿主经构造 Config 提供路径），而非"文件即单一配置"：

1. 接口契约要求登记可累积（"registering the same configuration again is the same registration" 且多个不同配置各自可解析；Memory 实现即累积 Map 的持久化同构）——单配置文件第二次 save 会覆盖丢失首次登记，违反契约；
2. 接口 JSDoc（:155）明示实现族 "JSONL, SQLite, or memory"——JSON 账本是该族的文件成员；
3. p05 设计 GAP#1 的表述即 "digest → config 的持久登记"（`.agents/devframe/p22/required-checks-design.md:99`）。

## 文件 schema（登记账本）

账本文件（UTF-8，2 空格 JSON，恰一尾随换行；首次 save 创建）：

```json
{
  "version": 1,
  "registrations": [
    { "digest": "dsh-required-checks-v1-<64 lowercase hex>", "config": { "version": 1, "checks": [ ... ] } }
  ]
}
```

zod envelope（模块私有，不导出）：

- 顶层 `.strict()`：`version: z.literal(1)`（账本格式代际，未来版本 fail-loud）、`registrations: z.array(entrySchema)`（允许空数组：空账本是合法状态）；
- entry `.strict()`：`digest: z.string().regex(/^dsh-required-checks-v1-[0-9a-f]{64}$/)`、**`config: z.unknown()`**；
- `config` 故意不过 envelope schema：registered 载荷必须经 `decodeRequiredChecksConfig` 回解析（接口契约 :156-158、:173-175 钉死其失败码为 `REQUIRED_CHECKS_INVALID_CONFIG`）——若并入 envelope，载荷 schema 失败会被错误地路由到新码。新码只归**账本自身**的 durable 边界。
- 载荷解码之外再查 **digest 内容漂移**：`entry.digest !== requiredChecksDigest(decoded.config)` → 账本损坏（claimed 与内容矛盾 = 篡改/半写痕迹，fail-loud，不可静默返回非该 digest 的配置）。同 claimed digest 的重复 entry 若内容一致则自然通过漂移检查（跨实例重复 save 的幂等痕迹，首登记有效）；内容不一致必被漂移检查拦截，无需独立去重规则。

## 错误码族

| 码 | 触发 | 层 | 状态 |
| --- | --- | --- | --- |
| `REQUIRED_CHECKS_CONFIG_NOT_FOUND` | `load`：账本文件不存在（尚无任何登记）/ 账本 `registrations` 为空 / 请求 digest 无登记 | 存储解析边界 | 沿用既有码 |
| `REQUIRED_CHECKS_INVALID_CONFIG` | 账本内 registered config 载荷未过 `requiredChecksConfigSchema`（经 `decodeRequiredChecksConfig`，cause 保留 ZodError） | 存储载荷边界（接口契约钉死路由） | 沿用既有码 |
| `REQUIRED_CHECKS_STORE_CORRUPT` | 账本文件存在但不是期望的 JSON 文档：字节不可解析 / envelope schema 不合（含 version 2、strict 未知键、digest 形状不合）/ digest 内容漂移；`save` 面对损坏账本同码拒绝 | 账本 durable 边界 | **本波新增** |

单新码 + message 区分子因的裁定：任务令"文件损坏/schema 不合=fail-loud 新稳定码"；三种子因补救动作一致（人工修复或重放审批），机器路由无需再分，避免码族膨胀。漂移检查使 digest 形状正则与内容校验互为冗余防线（非常规 digest 串先在 envelope 层被拦）。

## save / load 语义细目

`save(config)`（config 为 typed 同进程批准边界来的 validated 配置，不再重复校验——仓库"信任 typed 边界"规则）：

1. 读 + **全量校验**既有账本（文件缺失 = 空账本；损坏 → `REQUIRED_CHECKS_STORE_CORRUPT` 原样抛出——save 不修复、不覆盖损坏证据，静默重建会销毁损坏痕迹）；
2. `digest = requiredChecksDigest(config)`（共用身份面，零改动语义）；账本已有该 digest → 不写盘，返回既有 digest（首登记有效，对齐 Memory :196-200）；
3. 追加 `{ digest, config }`，序列化（2 空格 + 单尾随换行）后经同目录 tmp 文件（`${path}.${randomBytes(6) hex}.tmp`，house pattern 对齐 session-persistence-jsonl `src/index.ts:643`）+ `rename` 发布；返回 digest。

`load(digest)`：

1. `readFile` → ENOENT → `REQUIRED_CHECKS_CONFIG_NOT_FOUND`（message 命名路径与 digest：文件不存在 = 该 digest 无登记）；其余 fs 错误（EACCES/EISDIR/…）**原样传播不包装**（fail-loud 真因，见裁定请求 R4）；
2. `JSON.parse` 失败 → `REQUIRED_CHECKS_STORE_CORRUPT`；
3. envelope `safeParse` 失败 → `REQUIRED_CHECKS_STORE_CORRUPT`（zod issues 聚合进 message，cause 保留）；
4. 按序**全量**处理每条：config 过 `decodeRequiredChecksConfig`（失败 → `REQUIRED_CHECKS_INVALID_CONFIG` 原样传播）→ digest 漂移检查（失败 → `REQUIRED_CHECKS_STORE_CORRUPT`）；
5. 全量通过后按 digest 查找：命中（首个）→ 返回 config；未命中 → `REQUIRED_CHECKS_CONFIG_NOT_FOUND`。

全量校验裁定：账本任一条损坏，则所有 load/save 一致 fail-loud——不因请求 digest 不同而结果漂移（损坏状态对全部查询可见），且 save 永不建立在未校验状态上。

## durable 语义边界（最小合理解 + 裁定请求）

- **原子性**：tmp + 同目录 rename 发布——读侧只见旧或新完整文件，无撕裂读。不做 fsync（掉电级 crash durability 超出参考实现最小面）→ **裁定请求 R1**。
- **并发**：单写者假设，无锁；并发写者文件级 last-writer-wins（一次 save 可能丢失另一次的登记）→ **裁定请求 R2**；读与写并发安全（rename 原子替换）。
- **路径**：Config 原样使用；不 mkdir（父目录缺失时 save 以原始 ENOENT fail-loud）→ **裁定请求 R3**；不做 normalize/allow-list——typed 同进程 Config 边界信任 TS，untrusted 的是文件内容（已全量校验）。
- **非 ENOENT fs 错误不包装**（raw 传播，错误码族不扩张）→ **裁定请求 R4**（是否需要专属码属码族扩张决策）。
- **账本单调增长**：无 prune/compaction → **裁定请求 R5**。

## 测试矩阵（`tests/required-checks-file-store.spec.ts`，20 例）

正向（6）：
1. save 返回 `requiredChecksDigest(config)`；load 深等返回原 config（同实例）。
2. 跨实例持久：同 path 的第二个 store 实例 load 同 digest 成功（文件是事实源）。
3. 同集重复 save（check 序反排 + key 序不同 → 同 digest）→ 同 digest，账本仅 1 条登记（不重复写盘）。
4. 两个不同 config → 两条登记，各自可 load（新实例）。
5. 身份面 store 无关：file store save 的 digest === `requiredChecksDigest(config)` === `acceptanceCheckComponent(config)`（钉合成面零改动）。
6. 端到端零改动：load 出的 config 进 `evaluateRequiredChecks`——精确执行集 → satisfied；削弱执行集（换 argv + 缺项）→ COMMAND_MISMATCH + MISSING（`sameRequiredCheckCommand` 精确等值语义经文件边界不变）。

缺失 → `REQUIRED_CHECKS_CONFIG_NOT_FOUND`（3）：
7. 文件不存在 → NOT_FOUND（message 命名路径与 digest）。
8. 存在但空账本（`registrations: []`）→ NOT_FOUND。
9. 有登记但请求未登记 digest → NOT_FOUND。

损坏 → `REQUIRED_CHECKS_STORE_CORRUPT`（6）：
10. 非 JSON 字节 → STORE_CORRUPT。
11. 合法 JSON 非对象（数组 / 字符串）→ STORE_CORRUPT。
12. envelope 不合参数化 6 形：缺 `registrations`；`version: 2`；顶层未知键；entry 缺 `digest`；digest 形状不合；entry 未知键。
13. digest 内容漂移：save 后手工改写 entry.config 为另一 schema-valid config、保留 digest 字段 → STORE_CORRUPT。
14. 账本损坏时 save → STORE_CORRUPT（save 不修复）。
15. 全量校验钉：账本 = [合法登记 A, 漂移登记 B]，`load(digestA)` 仍 STORE_CORRUPT。

schema 不合 → `REQUIRED_CHECKS_INVALID_CONFIG`（1）：
16. entry.config 载荷 schema 不合（如 `checks: []`、payload version 2）→ INVALID_CONFIG 而非新码（接口路由边界钉）。

边界（4）：
17. argv 空串元素经文件往返保留（卫生豁免过 durable 边界）。
18. save 落盘文件为可解析 JSON、`version: 1`、恰一尾随换行。
19. 父目录缺失时 save → 原始 fs 错误传播（非 `RequiredChecksError`，fail-loud 不吞）。
20. load 时 path 指向目录 → 非 ENOENT fs 错误原样传播（非 `RequiredChecksError`）。

覆盖设计：20 例覆盖 readLedger 的 ENOENT/非 ENOENT、parse 成败、envelope 成败、decode 成败、漂移成败、查找命中/未命中、save 的缺失/命中免写/追加/损坏全部分支——对齐 per-file 100% 覆盖门（vitest.config.ts `thresholds.perFile`）。

## 精确文件清单（写入域）

1. `packages/experimental/devframe/src/required-checks.ts` — `RequiredChecksErrorCode` 增 1 成员 `REQUIRED_CHECKS_STORE_CORRUPT` + JSDoc（对既有文件的唯一语义编辑）。
2. `packages/experimental/devframe/src/required-checks-file-store.ts` — 新模块：`FileRequiredChecksConfigStoreOptions`（`{ readonly path: string }`，宿主 Config 提供账本路径）+ `FileRequiredChecksConfigStore implements RequiredChecksConfigStore`；账本 zod schema 模块私有。
3. `packages/experimental/devframe/src/index.ts` — 增 1 行通配导出。
4. `packages/experimental/devframe/tests/required-checks-file-store.spec.ts` — 新测试（上述矩阵；tmp 根 `mkdtemp` + afterEach 有界重试排空，对齐 completion-fixtures 先例）。
5. `packages/experimental/devframe/README.md` / `README.zh.md` — Source map 表各增 1 行（双语对；src 文件全列先例）。
6. `.agents/devframe/v14-evprod/worker/design.md` — 本文档。

禁区（零触碰）：`snapshots/**`、`packages/test-support/session-snapshot/**`、`scripts/session-snapshot-corpus*`、`vendor/**`、`packages/experimental/command-goal-binding/**`（刚并主树，须零 diff）、`packages/experimental/shadow-router/**`、`packages/experimental/project-memory/**`、主树 `D:/dsh-devframe`（只读）。不做：evidence/journal producer 切片域、start/resume 车道、任何 profile/composition 生产接线（属主波裁定）。

## 导出与目录面

- 新类经 `src/index.ts` 通配导出，可注入替代 `MemoryRequiredChecksConfigStore`；`entry-exports.spec.ts` 为抽查制（无闭合清单断言），零破坏。
- gen-cordis-catalog：`MemoryRequiredChecksConfigStore` 全树无 catalog/doc 引用，本 store 非 Cordis Service Definition/插件贡献，预期 0 written；门禁实跑验证，非 0 则按生成器补行复跑至 0。

## 门禁计划（真实退出码，未跑不得声称通过）

1. `pnpm install`（worktree）— 已跑：exit 0（24s；两条 dsh bin 警告系 CLI lib 未构建的环境既有产物）。
2. 聚焦 vitest：`pnpm vitest run packages/experimental/devframe` 全绿。
3. 删全部 `*.tsbuildinfo` → `pnpm run build` exit 0。
4. `pnpm run gen-cordis-catalog` → 0 written。
5. `git diff --check` exit 0（提交时含 `--cached --check`）；每文件恰一尾随换行。
6. 提交 `--no-verify`（宿主无 bash，lefthook vendor manifest guard exit 127 环境事实），message 登记 skip + 替代验证收据；禁 push/PR/发布/删除。

## GAP/未尽

1. **生产接线缺席（有意）**：composition/profile 注入（command-goal-binding `composition.ts:53,109` 的 `stores.requiredChecks`、未来宿主 Config 布线）归属主波裁定；本切片仅交付可注入参考实现。
2. **durable 边界裁定请求 R1–R5**（fsync / 多写者锁 / mkdir / 非 ENOENT 包装 / prune）。
3. **无并发写测试**：竞态不可确定性钉死；单写者语义以 JSDoc + 本设计登记。
4. **Agent Note**：仓库规则要求非平凡变更同 PR 附 Agent Note；本 worktree 写入域不含 `.agents/notes/**`——正式 Note 归属主树合流波，列裁定请求。
