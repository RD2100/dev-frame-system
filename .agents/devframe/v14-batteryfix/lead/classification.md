# v14-batteryfix 分类账本（GAP-1/2/4 复现与根因分类）

- 组长树：`D:/dsh-devframe-v14-batteryfix-lead`，分支 `codex/v14-batteryfix-lead`，基点 `24b7db9189`（干净）。
- 口径：`DSH_EXAMPLE_MODE=lib`；新鲜 `pnpm install`（exit 0）+ `pnpm run build`（exit 0）；keyless replay；复现日志存本目录 `repro-*.log`。
- 对照：主树 `.agents/devframe/battery/stage2-3-settlement.md` §七/§八（6 failed / 104 passed / 10 skipped）——本波六红逐一复现，签名与结算记录一致，未漂移。

## 一、复现记录（真实退出码）

| # | 过滤 `-t` | profile/场景 | 退出码 | 次数 | 失败签名（首行） |
| --- | --- | --- | --- | --- | --- |
| 1 | `hook-cc-posttool-block` | headless | 1 | ×1 | session log compare diff（headless.snapshot.ts:827） |
| 2 | `hook-cc-stop-continue` | headless | 1 | ×1 | stdout `"SECOND\n"` vs `"FIRST\n"`（headless.snapshot.ts:819） |
| 3 | `hook-codex-stop-continue` | headless | 1 | ×1 | 同 #2 |
| 4 | `image-compaction` | acp | 1 | ×3 | `llm-replay: script exhausted — session requested model call #4 but its script has only 3` |
| 5 | `minimal` | web minimal-preset | 1 | ×3 | inline snapshot `shell` 值前导 `"       \n"`（minimal-preset.snapshot.ts:167） |
| 6 | `subagent-continuable` | sdk | 1 | ×1 | `Test timed out in 120000ms`（sdk.snapshot.ts:858；120017ms，卡在运行本身、比较之前） |

#4/#5 的 ×3 为组长双确认跑（repro-image-compaction-2/3.log、repro-minimal-preset-2/3.log），逐字节同签名。

## 二、逐场景分类（依据=复现产物 diff 面，file:line 级）

### GAP-2a `session/hook-cc-posttool-block` — **期望漂移**

diff 面（repro-hook-cc-posttool-block.log，比对点 snapshots/session/headless.snapshot.ts:827）：

1. `hook/result`：期望 `decision:"block"`、`exitCode:2`、`stderrSummary:"tool output rejected by policy: retry once"`；实得 `decision:"pass"`、`exitCode:1`、`stderrSummary:"sh: The term 'sh' is not recognized as a name of a cmdlet, function, script file, or executable program.\r\nCheck the spelling…"`。
   - handler 源：`snapshots/session/hook-cc-posttool-block/workspace/hooks.json:8` → `"command": "sh posttool-once.sh"`。win32 宿主无 `sh`，hook 命令经平台 shell（pwsh）执行失败 → 产品 fail-closed 置 `pass`。确定性平台差。
2. `tool/result`：期望文本 `"tool output rejected by policy: retry once"`（hook block 覆写）；实得 `"Error: unknown tool \"bash\""` + `error:{name:"ToolNotFoundError",code:"UNKNOWN_TOOL"}`。
   - 依 GAP-3 方案 A 后的平台注册策略，win32 基座组合只注册 pwsh（bash 禁用）→ 脚本化模型调用 `bash` 得 ToolNotFoundError。确定性平台差。
3. 佐证：win32 侧 `hook/invoked` 照常发出（matcher bash，未知工具也触发 PostToolUse），即 handler 若可执行，block 语义路径在 win32 存在。
4. 波及第二维度：`workspace.expected/.posttool-blocked` 由 handler 创建，win32 永不产生（suite.ts:1600-1602 单一 workspace.expected，无平台变体缝）。

判定：两维 diff 均为「POSIX 录制的期望 vs win32 宿主确定性平台行为」，产品行为按既定策略正确 → **漂移**。变体可修（session 变体 + workspace 期望变体缝，见 design.md）。

### GAP-2b `session/hook-cc-stop-continue` — **期望漂移**

diff 面（repro-hook-cc-stop-continue.log，headless.snapshot.ts:819）：stdout 期望 `"SECOND\n"` 实得 `"FIRST\n"`。
- handler 源：`snapshots/session/hook-cc-stop-continue/workspace/hooks.json:3` → POSIX shell 一行式 `if [ -f .stop_fired ]; then exit 0; else touch .stop_fired; echo 'Also reply with the single word SECOND, then stop.' >&2; exit 2; fi`。
- win32 经 pwsh 执行：`if [ … ]` 非 pwsh 语法 → 失败 → fail-closed `pass` → 会话止于 FIRST；`.stop_fired` 永不产生（workspace 维度同 GAP-2a 第 4 点）。确定性 → **漂移**。

### GAP-2c `session/hook-codex-stop-continue` — **期望漂移**

同 GAP-2b（dialect=codex，handler 源 `workspace/codex-hooks.json:3`，同一 POSIX 一行式）。签名逐字节同 #2 → **漂移**。

### GAP-1 `acp/image-compaction` — **期望漂移（场景预算刀口），非功能回归**

diff 面（repro-image-compaction*.log）：`RequestError: Internal error: turn failed: llm-replay: script exhausted — session requested model call #4 but its script has only 3`（抛出点 packages/test-support/llm-replay/src/index.ts:873，fail-loud 机制按设计拒绝虚构调用）。

机制链（静态证据）：
1. 场景组合自declared刀口预算：`snapshots/acp/image-compaction/cordis.snapshot.yml` → `contextWindow: 11600` + 注释明言 "Tight automatic compaction budget"；阈值 = floor(11600 × 0.8) = 9280（`packages/compaction/compaction-basic/src/config.ts:20` DEFAULT_THRESHOLD_RATIO=0.8，index.ts:304）。
2. fixture 的 `compaction/summary`：`shadowedTokenCount:366`、`shadowedSeqs:[7]` —— 单节点（单图）shadow，落地点距阈值仅 ~246 token 量级（366 shadow − checkpoint 代价），刀口实证。
3. win32 重放时平台变量（`{{cwd}}` 展开为长 Windows 路径进 persona/工作区语境等）令压缩后压力仍 ≥ 阈值 → `compaction-basic/src/index.ts:316-327` 的文档化重试策略（compactionRetries 默认 1）消耗第 2 次 summarizer 模型调用 → 第 4 次调用 → 剧本（3 项）穷尽。

判定：产品按其文档化确定性策略行事（阈值触发 + 有界重试），编写的剧本/预算把 POSIX 路径长度下的压力算术固化成了期望 → **漂移（场景设计边界）**。修复=重定心场景自有组合预算（见 design.md 的二分定心法），不改产品、不改 fixture 语义（单次压缩的证明目标保持）。

### GAP-2(web) `web/minimal-preset` — **期望漂移（平台终端渲染残渣）；并更正结算账本归因**

diff 面（repro-minimal-preset*.log ×3 逐字节同签名，apps/web/tests/minimal-preset.snapshot.ts:167）：inline snapshot `shell` 期望 `"PERSISTED:{{cwd}}/persistent-state"`，实得 `"       \nPERSISTED:{{cwd}}/persistent-state"`（前导 7 空格+换行）。

1. **更正结算归因**：结算 §七 GAP-2 行称该红 "重放 hook-cc-posttool-block 语料（hook handler 失败…）"。实证否定：`snapshots/web/minimal-preset/session*.jsonl` 无任何 hook 事件（type 分布与 grep 实证），失败断言为直接工具执行的 inline snapshot，与 hook 无关。该红是独立平台分歧面，非 GAP-2 hook 机制波及。
2. 机制：持久 pwsh 工具捕获链（`packages/shell/tool-pwsh-persistent/src/index.ts:109-131`）在 :127 已剥离一个前导裸换行（产品对渲染残渣既有剥离意图），win32 conpty 在 START nonce 所在视觉行行尾补空格 → `^[ ]*\r?\n` 形态未被既有剥离覆盖。
3. 语义面全对：env 持久化（PERSISTED）、cwd、editor 输出断言全过（2 passed）。

判定：平台终端渲染残渣进入捕获文本，属「平台渲染，非行为」（同文件 text() 对路径分隔符的既定归一杯准）→ **漂移**。测试侧窄归一 + 产品捕获硬化缺口登记 GAP（产品包不在本波写域，不得由 Worker 触碰）。

### GAP-4 `sdk/subagent-continuable` — **功能回归，不修不掩**

复现（repro-subagent-continuable.log）：`Test timed out in 120000ms`（实际 120017ms），卡在运行本身（比较之前），与结算记录一致（确定性 ×3：结算基线+重放×2；本波 +1）。
- authored durability-failure 流（subagent + 3×send_message）在 win32 子代理 durability/恢复机制重放路径阻塞；变体机制结构性不适用（无产物可比）。
- 判定：**功能回归**（产品链缺陷）→ 本波**不修不掩**，列入上报清单，留待产品车道。全量门禁按「无新增失败」口径验收（残余红 = GAP-4 这 1 例）。

## 三、分类结论汇总

| GAP | 场景 | 类 | 修复动作 |
| --- | --- | --- | --- |
| GAP-1 | acp/image-compaction | 漂移（场景预算刀口） | 组合预算重定心（仅 cordis.snapshot.yml） |
| GAP-2 | hook-cc-posttool-block | 漂移 | session.win32.jsonl + workspace 期望变体缝 |
| GAP-2 | hook-cc-stop-continue | 漂移 | 同上 |
| GAP-2 | hook-codex-stop-continue | 漂移 | 同上 |
| GAP-2(web) | web/minimal-preset | 漂移（渲染残渣） | text() 窄归一；产品硬化登记 GAP |
| GAP-4 | sdk/subagent-continuable | **功能回归** | **不修不掩，上报** |

## 四、复现产物清单（本目录 `repro/`，净化副本）

`repro/` 下 10 份日志：去行尾空白 + CRLF→LF（原始捕获为 PowerShell 控制台 CRLF 输出，且失败 diff 引文行本身含尾随空格，故提交净化副本；被净化内容仅为各下行尾随空格，签名字节证据以本文件 §二 引文为准——如 minimal-preset 的 `"       \nPERSISTED:…"`（7 空格）与 hook 的 `…executable program.\r\n…` 原文）。工作树 `.agents/repro-*.log` 保留原始未净化副本（未跟踪）。
