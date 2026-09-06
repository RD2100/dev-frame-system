# v14-b2acp 组长独立审查记录（Worker w1 交付验收）

- 审查对象：`D:/dsh-devframe-v14-b2acp-w1`（codex/v14-b2acp-w1），Worker 三笔 `f471f56c5f`/`29d966ebcd`/`cc532292f9` + 组长 fixup `28cced071e`。
- 口径：win32 宿主，`DSH_EXAMPLE_MODE=lib`，keyless replay；所有退出码为本组长亲手复跑所得。

## 一、门禁复跑（组长侧真实退出码）

| 门禁 | 结果 | 备注 |
| --- | --- | --- |
| G2 包聚焦 vitest | exit 0，**358 passed \| 1 skipped** | 基线 342\|1 不回退，+16 全绿 |
| G3 聚焦 replay（组长复跑 ×1；Worker ×2 存档） | exit 0 | `snapshot: image-compaction` 全链绿（含 schema 比对与头一致性） |
| G5 删 tsbuildinfo → build | exit 0 | 全量重建 |
| G6 `git diff --check b915db85ee..HEAD` | **首查 exit 2 → fixup 后 exit 0** | 见 §三审查发现 |
| G7 `test:docs`（15 门） | exit 0（15 passed, 0 failed, 0 skipped） | 含 corpus 全语料门 |
| G4 全量 `test:snapshot` | exit 1（预期残余红）；**3 failed \| 107 passed \| 10 skipped** | 失败集合恰 = {`replays subagent-continuable through dsh --profile sdk`（GAP-4，本树基点 5e5a706f0a 先于 main 的 92825045d0 修复，禁并 main 故仍在），`replays both-mode-turn …`、`replays ptc-turn …`（录制树根 `dsh-devframe-p-battery` 嵌入，diff 仅路径拼写差异）}；**image-compaction 绿，零新增失败名** |

Worker 自证门禁（G1 基线红 exit 1 签名 @ suite.ts:1581、G3 ×2、G4 首跑）日志抽查与本案证据一致（`worker/logs/g1-baseline-red.log` 签名与组长树基线逐字节同型）。

## 二、base 零修改与文件域审计（逐笔）

逐笔 `git diff --name-status` + blob 级核对：

- 笔 a `f471f56c5f`：M 仅 design §四具名包文件 5 个（src/expectations.ts、src/index.ts、src/suite.ts、tests/expectations.spec.ts、tests/suite.spec.ts）+ 新增包内测试夹具 `tests/fixtures/suite-refresh/variant-pin/**`（S-1/S-2 依赖，包内测试域）。
- 笔 b `29d966ebcd`：M 仅 `snapshots/acp/image-compaction/snapshot.yml`（+4 行 `expectations.variants.win32: [system-prompt]`）；新增 `system-prompt.win32.expected.md`（**A**，mode 120000，blob = `../../session/read-image/system-prompt.win32.expected.md` 正斜杠，指向目标 blob `af14c15dd4…` = 分类 §一② 收割等值实证的既有 blob）。
- 笔 c `cc532292f9` + fixup `28cced071e`：worker 记录域。
- **任何场景 base 夹具（session.jsonl/base 侧车/cordis.yml/cordis.snapshot.yml/stdout/input.json）在四笔历史中零 M**；image-compaction 其余 6 文件 blob 与 base 全同（`session.jsonl` = `e5120fd490`、base 侧车 symlink = `7d5e489c` 等逐一比对）。
- 禁区零 diff：`packages/sdk/**`、`snapshots/sdk/**`、experimental 五包、`vendor/**`、`.agents/devframe/v14/next/**`、`snapshots/session/**`、`apps/web/**`、`scripts/**`。

## 三、审查发现（1 项，已修复并披露）

- **Worker 笔 c 的 G6 收据不符**：`git diff --check` 在 6 份 worker 日志上报 `new blank line at EOF`（EOF 双换行），笔 c 自身 range check exit 2——与 Worker 报告「G6 exit 0 each」相悖（其净化只去了行尾空白，未去 EOF 空行）。属 records-only 机械缺陷，组长以 fixup `28cced071e`（6 文件恰一尾随换行）修复，修复后全域 range check exit 0。不涉任何产品/夹具字节。
- Worker 报告偏差 2/3（守卫提取为 `assertDeclaredVariantFiles` 导出以便 S-2 可断言；S-1 夹具双平台声明）核验为合理设计内选择，读路径 fail-loud、session 变体 refresh 仍 fail-loud 均有 spec 钉死（S-2 两例）。

## 四、机制审读与先例一致性

- `expectationWriteName`：镜像 `sessionFixtureFileName` 的 fs-agnostic 契约（不查文件系统，declared → 变体名，undeclared → base 名）；写路径两点（system-prompt/tool-schemas）改经此解析，读/比较路径保持 `resolveExpectationPath` fail-loud——分类 §一①鸡生蛋缺口闭合。
- 守卫 `assertDeclaredVariantFiles`：豁免集精确 = `manifest.expectations` 经 `expectationFileName` 派生的 expectation 侧车变体名，且仅 REFRESHING 且文件缺失时；session/child/stdout/wire/workspace 变体存在性断言不变。
- `preserveFixtureVolatiles` `sourceEventSeqs` 分支：decoded（`decodeSeqRanges`）相等 → 夹具拼写保持；不等 → fresh 权威；插入点在 hook/result 早退之前，全部记录类型覆盖。分类 §三漂移根因闭合（S-3 双向 + 不等例三 spec）。
- 先例一致性：escalation-approved 同构（跨语料源 + 本地 symlink + manifest 声明）；corpus 门 symlink 规则（`session-snapshot-corpus.corpus.ts:167-169`）合规；简报「两份 .win32 侧车」预期按 design §二.3 实证裁定为仅 system-prompt 一份（tool-schemas 源侧已解析 win32，G3 全链绿为证）。

## 五、Worker 车道实证

- 单 Worker 派发（workflow，显式 `provider: 'huoshan-2', model: 'glm-5.3-flash'`，label `v14-b2acp-w1`）；Worker 回执照录 dispatch 声明，并如实声明无法自内省服务模型。无多派发、无重复派发记录。
- Worker 报告 + 11 份日志存档于 worker 树 `.agents/devframe/v14-b2acp/worker/**`（笔 c + fixup）。

## 六、结论

B-2 三处管线缺口（变体写目标、校验次序、写回拼写）+ 场景期望漂移全部闭合；image-compaction 在 win32 replay 绿；验收口径达成（image-compaction 绿 + 其余 2 红维持原归因 + 零新增失败）。合并权在总控。
