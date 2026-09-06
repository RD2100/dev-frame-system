# v14-b2acp 分类账本（B-2：image-compaction pin 侧车变体管线缺口）

- 组长树：`D:/dsh-devframe-v14-b2acp-lead`，分支 `codex/v14-b2acp-lead`，基点 `5e5a706f0a`（干净）。
- 口径：win32 宿主；`DSH_EXAMPLE_MODE=lib`（删全部 `*.tsbuildinfo` 后 `pnpm run build` exit 0）；keyless replay/refresh。
- 注：src 模式（DSH_EXAMPLE_MODE 未设）下本机 acp 场景以 `RequestError: Internal error: the ACP bridge has been disposed` 失败（两次复现），与 batteryfix 车道 lib 口径不符，未作为分类证据；batteryfix 分类/复现同为 lib 口径。

## 一、总控实证复核（三条全部成立，机制钉死）

### ① 「声明变体但文件缺失 → harvest 前抛」= 成立（鸡生蛋）

- 严格校验两处：包内 fixture 守卫 `packages/test-support/session-snapshot/src/suite.ts:1652-1654`（对 `declaredExpectationVariantFiles(manifest)` 逐文件 `existsSync` 断言，replay/record/refresh 全模式运行）；读路径解析器 `src/expectations.ts:84-96`（:90-92 对 declared-but-missing 抛 `declared platform expectation variant file is missing: <file>`）。
- 写路径复用读解析器选写目标：`src/suite.ts:1402-1409`（system-prompt）、`src/suite.ts:1421-1428`（tool-schemas）→ 同一解析器对 declared-but-missing 直接 throw，refresh 永远写不出尚不存在的变体文件。
- 级联半写状态：refresh 的 run test 先写 session 夹具（`src/suite.ts:1379-1380`）后写侧车（:1402）——侧车解析 throw 时 session 夹具已被改写（总控实证 ② 的 session.jsonl 漂移即此半写状态的产物，见 §三）。
- 对照先例缝：session 变体的写目标用**不查文件系统**的名字构建器 `src/expectations.ts:107-113`（`sessionFixtureFileName`，JSDoc 明言 "refresh write-backs can name a variant target that does not exist yet"），写点 `src/suite.ts:1359`；headless 套件同构 `snapshots/session/headless.snapshot.ts:229` 与子侧车 `childSidecarTarget`（`headless.snapshot.ts:215-220`）。主侧车（system-prompt/tool-schemas）没有对等的 fs-agnostic 写目标构建器——这就是 acp/authored pin 侧车与 sessionVariants 缝的机制差。

### ② 「refresh 级联覆写相邻 base 夹具」= 成立，本树完整复现（2026-02-11，diff 存档 `refresh-exp/`）

实验（lib 模式，`DSH_SNAPSHOT=refresh`，`-t image-compaction`，run test 自身 exit 0）后 `git status`：

```
 M snapshots/acp/image-compaction/session.jsonl
 M snapshots/session/read-image/system-prompt.expected.md
```

1. `session/read-image/system-prompt.expected.md` 被覆写为 win32 措辞（diff `-`侧 POSIX "Check the [exit code: N] marker…"，`+`侧 "Non-zero exits are reported as `[exit code: N]` markers… On Windows a killed process…" + worktree 段），且覆写后 blob = `af14c15dd4…` = **`session/read-image/system-prompt.win32.expected.md` 的既有 blob 逐字节相同**。机制（写路径三步）：
   - acp 套件走线 `snapshots/acp/acp.snapshot.ts:45-47` `localScenarioSource` 把跨语料源（含 `/` 的 `session/read-image`）从 Scenario 表丢弃 → `src/suite.ts:1230` `sourceFor` 回退 `promptSource = image-compaction 自身`；
   - 写目标 = `resolveExpectationPath({dir: snapshots/acp/image-compaction, manifest: image-compaction 自身 manifest})`，其 manifest 未声明 `expectations.variants`（`snapshots/acp/image-compaction/snapshot.yml` 全文 16 行无该键）→ 解析器回退 **base 路径**（`expectations.ts:95`）；
   - 该 base 路径在 git 里是 **symlink**（mode 120000，`git ls-files -s` → `7d5e489c` → `../../session/read-image/system-prompt.expected.md`，`git cat-file blob 7d5e489c` 实证），node `writeFile` 穿透 symlink → 字节覆写落在 **session 套件的 base 源**上。即总控所述「pin 源侧车被覆写为 win32 措辞——写入了 base 而非变体目标」的精确机制。
2. tool-schemas 写同样发生但零 diff：schemaSource = `escalation-approved`（无 `/`，本地源，`acp.snapshot.ts:56`），其 manifest 声明 win32 且 win32 文件是 symlink → `../../session/text-turn/tool-schemas.win32.expected.json`（`git cat-file blob 5910a719` 实证）→ 写穿透到 session 套件的 win32 变体文件，但收割字节与既有内容逐字节相同 → 无痕。跨套件写无 claim 守卫（`claimSharedSnapshot`（`suite.ts:316-329`）的 claims map 是单套件实例，跨 suite 不设防）——同机制 class 的隐性风险，本波不动其语义，记录在案。
3. `session.jsonl` 漂移 = 半写状态 + 写回稳定化缺口（根因见 §三），已随实验还原（`git checkout --`，树回到干净，`git status --porcelain` 仅余本记录域未跟踪目录）。

### ③ 「三 hook 场景先例证明 refresh 能写 session.win32.jsonl 变体，pin 侧车无对等写入」= 成立

- 先例机制：`sessionFixtureFileName`（fs-agnostic）+ `childSidecarTarget`（`headless.snapshot.ts:215-220`，JSDoc 同句式）→ refresh 把声明的变体**写出来**（可新建）；batteryfix worker 报告 §A② 即由此收割三场景 `session.win32.jsonl`。
- pin 侧车写点无此缝：`src/suite.ts:1402-1409/1421-1428`（acp 套件）与 `headless.snapshot.ts:261-272`（headless 套件主侧车）都走会查会抛的 `resolveExpectationPath`。text-turn / escalation-approved / read-image 的既有 `.win32.expected.*` 是历史批量手工落地（`git log`：`30e33d66a2` "land win32 session variants for twenty single-session headless scenarios"、`f219800a32` "land the win32 recording and pin variants for the default header class"），非 refresh 自举。

## 二、残余红的代码定位（三处路径 file:line）

- **读路径（比较）**：`src/suite.ts:1503-1511`（prompt）/ `:1515-1523`（schemas）经 `resolveExpectationPath` 读源侧车；初始 prompt 比对断言在 `:1580-1581`（`toEqual(childPrompt ?? initialPromptSnapshot)`）。本机 lib 复跑红签名与 briefing 逐字节一致：expected=POSIX 措辞（base symlink 内容），received=win32 措辞+worktree 段（= read-image win32 sidecar 内容）→ `session 3e09c5dc…: initial system prompt #1 diverged from image-compaction/system-prompt.expected.md` @ `suite.ts:1581`。exhausted 已消失（thresholdRatio 0.923 定心生效）、session 规范化比对绿——残余红唯一面即 pin 侧车。
- **写路径（refresh）**：见 §一①/②。目标选择 = 读解析器（查文件系统、会抛、undeclared 回退 base）；写点 `:1409`/`:1428` 直接 `writeFile`（穿透 symlink）。
- **校验路径（manifest 严格校验）**：结构校验 `src/manifest.ts:281-392`（`expectations` 仅查形状，不查文件存在）；存在性校验 = `suite.ts:1652-1654`（守卫）+ `expectations.ts:90-92`（读/写共用解析器）。corpus 门 `scripts/session-snapshot-corpus.corpus.ts:155-171` 支持跨语料源解析并校验本地 symlink 指向 manifest 源（:167-169），但其变体存在性检查只覆盖 `.jsonl`（:186 filter）与 child sidecar（:201-208），**不查** system-prompt/tool-schemas 主侧车的 `.md/.json` 变体存在性——该缺口由 suite 守卫兜底。

### text-turn / escalation-approved 先例机制（本波照抄的形态）

- escalation-approved（acp 套件内、同构 image-compaction 的活例）：manifest 声明 `expectations.variants.win32: [system-prompt, tool-schemas]`（`snapshots/acp/escalation-approved/snapshot.yml:16-20`），本地 base+win32 四份侧车全部为 symlink 指向跨语料源 `session/text-turn` 同名文件（git mode 120000，目标经 `git cat-file` 实证），win32 replay 绿。
- image-compaction 缺的恰是：本地 `system-prompt.win32.expected.md`（symlink → `../../session/read-image/system-prompt.win32.expected.md`）+ manifest `expectations.variants.win32: [system-prompt]` 声明。tool-schemas 无需本地动作（源 escalation-approved 已声明+有文件，win32 比较已经由源侧解析到 win32 变体）。

## 三、session.jsonl 漂移根因（实证钉死）

漂移恰 2 行 = 两条 `assistant/message` 记录，唯一差异字段 `sourceEventSeqs` 的**编码形态**：

```
夹具（展开形）: "sourceEventSeqs":[12,13,14,15]        / [29,30,31,32]
fresh（范围形）: "sourceEventSeqs":[[12,15]]           / [[29,32]]
```

- 比较绿的原因：`normalize.ts:401-403` 对 `sourceEventSeqs` 过 `decodeSeqRanges`（来自 `@deepseek-ai/dsh-session`，`normalize.ts:9-16`）→ 两种形态解码同值 → `normalizeSessionSnapshots` 相等。
- 写回漂移的原因：`src/suite.ts:913-971` `preserveNormalizedVolatiles` 的数组分支（:921-938）要求 `fresh.length === existing.length`（范围形 1 元素 vs 展开形 4 元素）→ :930 `return fresh` 保留 fresh 编码；其「normalized 相等则复用 existing」的契约只在字符串叶（:960-969）与结构对齐时生效，**数组形状被归一化改变时不生效**。夹具的展开形是 authored/早期收割形态，产品现产范围形 → refresh 重写 authored 夹具时该字段必然翻转为范围形。
- 判定：**非模型非确定性、非产品回归**——是 refresh 写回稳定化对「归一化等价但编码不同」的数组字段不保持夹具拼写的缺口。refresh 重写 authored session 夹具本身是设计行为（sessionVariants 收割配方依赖它，batteryfix §A② 先例），**不改触发条件**；修法 = 写回侧对 decoded 等价的 `sourceEventSeqs` 复用夹具既有拼写（design §二.3）。

## 四、分类结论

| 缺口 | 类 | 修复动作（design 展开） |
| --- | --- | --- |
| pin 侧车变体写目标无 fs-agnostic 缝（declared-but-missing 抛、undeclared 回退 base 穿透 symlink） | 夹具/管线（本波车道） | 写路径改 fs-agnostic 变体目标名构建器；refresh 对 declared-but-missing 可自举写入 |
| 校验次序（守卫在 refresh 写出前即断言存在） | 夹具/管线 | refresh 模式对 declared-but-missing 的 expectation 变体豁免（先写后验）；replay/record 维持 fail-loud |
| `sourceEventSeqs` 写回拼写翻转 | 夹具/管线 | 写回稳定化：decoded 等价 → 复用夹具拼写 |
| image-compaction 缺 win32 侧车变体 + 声明 | 期望漂移（escalation-approved 同构先例） | 新增本地 win32 symlink + manifest 声明（base 零触碰） |

硬边界核验：本分类实验只发生 `M`（可还原）状态，已全部还原；`git status` 干净（仅本记录域未跟踪）。
