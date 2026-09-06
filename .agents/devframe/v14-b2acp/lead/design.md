# v14-b2acp 修复设计（B-2 最小管线修复：pin 侧车变体目标 + 校验次序 + 写回拼写保持）

前置：分类见同目录 `classification.md`（三条总控实证全复核成立；refresh 级联本树复现并还原；修复形态实验已单点验证绿）。基点 `d82cbfd5fa`。

总原则：
- 最小缝：只动 acp/authored pin 侧车的**写目标解析**与**校验次序**，读路径（replay fail-loud）与 sessionVariants 既有缝零语义变化。
- base 夹具零触碰：任何场景的 `session.jsonl`、既有 base 侧车、`cordis.yml`/`cordis.snapshot.yml` 既有内容零 diff；全部新面为**新增变体文件 + manifest 增量声明**。
- 期望值来源 = 真实 win32 回放：变体文件以 symlink 指向 session 套件既有 win32 侧车（escalation-approved 先例形态，`git cat-file` 实证其四份侧车全部如此），禁止手写编造；refresh 实验已证 image-compaction 的 win32 收割字节 = `session/read-image/system-prompt.win32.expected.md` 既有 blob（`af14c15dd4…`）。

## 一、机制修复（session-snapshot 包）

### 1. pin 侧车变体写目标 fs-agnostic 化（`src/expectations.ts` + `src/suite.ts`）

- 新增导出 `expectationWriteName(manifest, kind, platform): string`（镜像 `sessionFixtureFileName`（:107-113）的先例缝，JSDoc 同句式：never consults the filesystem, so refresh write-backs can name a variant target that does not exist yet）：
  ```ts
  const variant = platformExpectationVariant(platform)
  return manifest.expectations?.variants[variant]?.includes(kind) === true
    ? expectationFileName(kind, variant)
    : expectationFileName(kind)
  ```
- `src/suite.ts` 写路径改写目标来源：
  - :1402-1409（system-prompt）与 :1421-1428（tool-schemas）中 `resolveExpectationPath({...})` → `join(dir, expectationWriteName(await manifestOf(source.name), kind, process.platform))`；
  - 读路径（:1503-1511、:1515-1523）**保持 `resolveExpectationPath`**——declared-but-missing 在比较侧继续 fail-loud。
- 语义结果：宿主平台被声明 → 写变体名（可自举新建）；未声明 → base 名（现状保留；不引入新跳过/新失败面）。chicken-and-egg（分类 §一①）闭合：声明先行、文件可由 refresh 写出。
- `src/index.ts`：导出新 helper（face 一致，`@param`/`@returns` JSDoc）。

### 2. 校验次序：refresh 模式先写后验（`src/suite.ts` 守卫）

- `suite.ts:1652-1654` 守卫改为：declared expectation 变体文件缺失时，**REFRESHING 模式豁免**（变体由本 run 的 run test 写出，先写后验；refresh 是维护者动作，replay 为 CI 存在性口径）；REPLAY/RECORD 维持 fail-loud（断言消息不变）。
- 非法用例保持：非 refresh 模式 + 声明指向缺失文件 → 红（守卫）+ 读路径 throw（`expectations.ts:90-92`）双证，测试矩阵 §三 I-3。

### 3. 写回拼写保持：`sourceEventSeqs` decoded 等价 → 复用夹具拼写（`src/suite.ts`）

- 分类 §三实证：fresh 范围形 `[[12,15]]` vs 夹具展开形 `[12,13,14,15]`，`preserveNormalizedVolatiles` 数组分支长度不等（1 vs 4）→ 保留 fresh → refresh 重写 authored 夹具必翻字节；比较侧因 `decodeSeqRanges` 归一而绿。
- 修法（外科式，不动通用数组分支）：`preserveFixtureVolatiles`（:864-883）增一分支——记录含 `sourceEventSeqs` 且与 existing 的 **decoded 值相等**（两侧各过 `decodeSeqRanges` 后 deep-equal；`decodeSeqRanges` 已在包内使用，`normalize.ts:10` 自 `@deepseek-ai/dsh-session` 导入）→ `record.sourceEventSeqs = existing.sourceEventSeqs`（复用夹具拼写）。decoded 不等 → fresh 照旧（新事件结构 fresh 权威不变）。
- session.jsonl 处置判定：refresh 重写 authored 夹具是设计行为（sessionVariants 收割配方依赖，batteryfix §A② 先例），**不改 `writesSessionFixtures` 触发条件**（:1350-1351）。

### 4. headless 套件主侧车写点（`snapshots/session/headless.snapshot.ts:261-272`）

同缺陷 class（写走 `resolveExpectationPath`）。但该写点仅在 `promptOwner === scenario.name` 时触达，当前 headless 语料中可自写的 pin（text-turn 等二十场景）全部已声明+文件在位，无在飞缺口；且该文件属 session 套件注册面（非 acp 车道）。**本波不改**，登记为后续缝统一项（与 corpus 门 `.md/.json` 变体存在性缺口同批，见 §四）。

## 二、场景修复（image-compaction，escalation-approved 同构先例）

1. 新增 `snapshots/acp/image-compaction/system-prompt.win32.expected.md` = **symlink** → `../../session/read-image/system-prompt.win32.expected.md`（corpus 门 symlink 规则 `session-snapshot-corpus.corpus.ts:167-169` 合规：指向 manifest 源同名文件）。
2. `snapshots/acp/image-compaction/snapshot.yml` 增（`toolSchemasSource` 行后）：
   ```yaml
   expectations:
     variants:
       win32:
         - system-prompt
   ```
3. **与任务简报的偏差（实证裁定）**：简报预期"两份 .win32 侧车"。实验证明 tool-schemas 无需本地变体——schema 比较读 schemaSource（`escalation-approved`，本地源无 `/`）的 dir+manifest（`suite.ts:1515-1523`），其已声明 win32 且文件在位（symlink→text-turn win32 schemas）；实验（symlink+仅 system-prompt 声明）聚焦 replay 全链绿（含 :1593-1597 schema 比对与头一致性）。本地再声明 tool-schemas 对读路径无效果（读解析用 schemaSource 的 manifest）、对写路径同样无效果（写解析也用 schemaSource 的 manifest，`suite.ts:1420-1426`）——故不添加。
4. base 零触碰声明：`session.jsonl`、`system-prompt.expected.md`（symlink 本体）、`cordis.yml`、`cordis.snapshot.yml`、`stdout.expected.jsonl`、`input.json` 全部零 diff。

## 三、测试矩阵（Worker 验收，全为真实退出码）

| # | 门禁 | 期望 |
| --- | --- | --- |
| G1 | 基线红重立：修复前 `-t image-compaction`（lib 模式） | exit 1，签名 = `initial system prompt #1 diverged …` @ suite.ts:1581（与本分类 §二一致） |
| G2 | 包聚焦 vitest（`packages/test-support/session-snapshot`） | exit 0；新增 spec 全绿（基线 342 passed \| 1 skipped 不回退） |
| G3 | 修复后 `-t image-compaction` ×2（lib 模式） | exit 0 ×2 |
| G4 | 全量 `pnpm run test:snapshot` | 失败集合如实记录当时状态：both-mode-turn/ptc-turn 维持树根嵌入归因红、subagent-continuable 维持 GAP-4 红（若 gap4 波已并则如实记录其缺席）；**零新增失败名**；image-compaction 绿 |
| G5 | 删全部 `*.tsbuildinfo` → `pnpm run build` | exit 0 |
| G6 | `git diff --check`（每笔 staged） | exit 0；每文件恰一尾随换行 |
| G7 | `pnpm run test:docs`（15 门） | exit 0（含 corpus 门全语料） |

新 spec 用例（`tests/expectations.spec.ts` + `tests/suite.spec.ts`）：
- E-1 `expectationWriteName`：win32 宿主 + 声明 → 变体名；posix → base 名；未声明平台 → base 名；不查文件系统（对不存在的变体名也返回变体名）。
- E-2（invalid）declared-but-missing 在 replay 读路径 throw（既有行为回归覆盖）。
- S-1 suite refresh：声明变体但文件缺失 → refresh run 写出变体文件且 run 绿（用 `tests/fixtures/record-suite/rec-pin` 模式或 suite 夹具增量）。
- S-2（invalid）非 refresh 模式守卫对 declared-but-missing 红。
- S-3 stabilizeRefreshLog：`sourceEventSeqs` 范围形 fresh + 展开形 existing → 写回保持展开形；decoded 不等 → fresh 保留；packed/其余字段行为不变（既有用例零回退）。

## 四、具名最小待改文件清单（Worker 写域全集）

```
packages/test-support/session-snapshot/src/expectations.ts        （新增 expectationWriteName）
packages/test-support/session-snapshot/src/suite.ts               （写路径 :1402/:1421 改写目标来源；守卫 :1652-1654 refresh 豁免；preserveFixtureVolatiles sourceEventSeqs 分支）
packages/test-support/session-snapshot/src/index.ts               （导出新 helper）
packages/test-support/session-snapshot/tests/expectations.spec.ts （E-1/E-2）
packages/test-support/session-snapshot/tests/suite.spec.ts        （S-1/S-2/S-3）
snapshots/acp/image-compaction/snapshot.yml                       （expectations.variants.win32: [system-prompt] 增量声明）
snapshots/acp/image-compaction/system-prompt.win32.expected.md    （新增 symlink → ../../session/read-image/system-prompt.win32.expected.md）
.agents/devframe/v14-b2acp/worker/**                              （收据与日志）
```

禁区（零 diff，git status 审计口径）：`packages/sdk/**`、`snapshots/sdk/**`（GAP-4 域）、`packages/experimental/{devframe,agent-evidence,command-goal-binding,shadow-router,project-memory}`、`vendor/**`、`.agents/devframe/v14/next/**`、任何场景 base 夹具（`session.jsonl`、既有 base 侧车、`cordis.yml`/`cordis.snapshot.yml` 既有内容）、主树、其他链 worktree（compos-w1/accept-w1/gap4-w1/batteryfix-w1）。禁 push/PR/发布/删除；禁创建任何 Agent。

## 五、review 口径（组长独立审查）

1. 复跑聚焦 vitest + build + test:docs + 全量快照（lib 口径），失败集合与 G4 口径精确对账。
2. base 零修改逐文件核对：`git diff --stat <base>..HEAD` + `git status --porcelain` 逐行对 §四清单，任何 base 夹具 `M` 状态即打回。
3. 变体文件一致性抽查：symlink 目标 `git cat-file` 实证；refresh 实验已证收割字节 = read-image win32 既有 blob（分类 §一②）。
4. 与 text-turn/escalation-approved 先例机制一致性：声明形态、symlink 形态、corpus 门 symlink 规则逐项对。
5. 机制 diff 审读：fs-agnostic 名构建器不查文件系统；replay fail-loud 不回退（E-2/S-2）；未声明场景零行为变化（包 vitest + 全量 G4 双证）。
