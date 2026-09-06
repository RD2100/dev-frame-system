# v14-batteryfix 修复设计（漂移类进入修复；GAP-4 不修不掩）

前置：分类见同目录 `classification.md`（六红复现实证，基点 24b7db9189）。本设计只覆盖漂移类五场景；GAP-4（sdk/subagent-continuable，功能回归）**零改动零跳过**，作为已知残余红进入验收口径。

总原则：
- 期望值来源=真实 win32 回放输出。session 变体经 `test:snapshot:refresh` 由 shipped 稳定化 writer 收割（cp 基座占位 → 声明变体 → refresh 覆写为真实录制）；workspace 期望变体与 web 归一以 replay 失败 diff 的 actual 侧为准。禁止手写编造期望。
- 功能回归禁掩盖：GAP-4 不进任何变体/跳过；GAP-2(web) 的产品捕获硬化缺口登记上报，不在产品包动手。
- POSIX 面零变化：base 语料文件（session.jsonl/workspace.expected/cordis.yml/既有 golden）零 diff；新机制为纯增量缝，未声明场景行为逐位不变。

## 一、机制扩展：workspace 期望的平台变体缝（session-snapshot 包）

既有变体族（sessionVariants/expectations/childSessionVariants/childExpectations/stdoutVariants/wireVariants）缺 workspace 维度：`suite.ts:1600-1602` 与 corpus 门 `session-snapshot-corpus.corpus.ts:137-144` 都硬编码单一 `workspace.expected/`。三个变异 hook 场景的 win32 分歧恰在 hook 产物文件（`.posttool-blocked`/`.stop_fired`）不产生。新增最小缝：

1. `src/manifest.ts`：
   - 根键白名单（:274-294）增 `'workspaceVariants'`。
   - 解析（在 sessionVariants 块 :377-394 旁）：可选 `Partial<Record<SnapshotExpectationPlatform, true>>`；键 ⊆ `['win32','posix']`（:218）；值必须 `=== true`；至少一平台；**要求 `workspace.final === true`**（无 final 比较即无意义，fail loud）；并入解析产物（:594 附近）与 `SnapshotManifest` 类型 + JSDoc。
2. `src/expectations.ts`：仿 `sessionFixtureWriteName`（:108-112）/`resolveSessionFixturePath`（:127-145）新增：
   - `workspaceExpectedDirName(manifest, platform)`：宿主族已声明 → `workspace.<variant>.expected`，否则 `workspace.expected`；
   - `resolveWorkspaceExpectedDir(...)`：declared-but-missing 目录 → throw（fail loud，消息含缺失目录名）。
3. `src/suite.ts:1600-1602`：`join(dir, 'workspace.expected')` 改经 resolver。
4. `src/index.ts`：导出新 helper（保持 face 一致，附 @param/@returns JSDoc）。
5. corpus 门 `scripts/session-snapshot-corpus.corpus.ts`：
   - :137-144 的 presence/empty-marker 检查改经 resolver（按解析目录做 marker 语义）；
   - 仿 wireVariants 成对存在性断言（:206-209）：声明了的每个 workspace 变体平台，其 `workspace.<variant>.expected/` 目录必须已提交（不存在即红）。
6. 包测试（覆盖每条新验收路径 + invalid case，沿用既有 spec 模式）：
   - `tests/manifest.spec.ts`：workspaceVariants 合法解析；**invalid**：无 `workspace.final` 时声明 → manifest 解析 throw；非 true 值 → throw；未知平台键 → throw。
   - `tests/expectations.spec.ts`：宿主 win32 → 选变体目录；posix → base；**invalid**：declared-but-missing → throw。
   - `tests/suite.spec.ts`：带 workspaceVariants 的套件比较选变体目录（复用 `tests/fixtures/suite/*` 模式，如 plain-turn 加变体夹具）。
7. F3 兼容性：三个 hook 场景 `composition: default` 且目录内无 cordis.yml/cordis.snapshot.yml → shell-family 守卫（corpus :298-348）对其 continue 跳过，零交互；本设计零改 composition（除 GAP-1 场景自有 snapshot 补丁的 compaction 配置行，不涉 shell 行）→ 守卫输入不变。
8. 兼容性不变量：`declaredExpectationVariantFiles` 只产文件名清单（变体目录是目录，不入该清单）；`suite.ts` 各 inventory 过滤（:1626-1628 isFile；corpus :175 sessionFixtureNames 模式）不匹配 `workspace.*.expected` 目录名 → 无需扩名单。refresh/record 永不重写 `workspace*.expected/`（docs/testing.md 既有政策）——writer 侧零改动。

## 二、逐场景修复

### 1. `session/hook-cc-posttool-block`（GAP-2a，漂移）

- `snapshot.yml` 增：
  ```yaml
  sessionVariants:
    win32: true
  workspaceVariants:
    win32: true
  ```
- 变体文件清单与来源：
  - `session.win32.jsonl`：先 `cp session.jsonl session.win32.jsonl`（占位，模型剧本平台无关）→ 声明后跑 `pnpm run test:snapshot:refresh -t hook-cc-posttool-block` → shipped writer 以真实 win32 回放（sh handler 失败→pass、`unknown tool "bash"`）覆写。**refresh 后必须 `git status` 证明仅 session.win32.jsonl 变动、base 零触碰**（结算 §五.4 风险披露的对策）。
  - `workspace.win32.expected/`：hand-author 自 replay 失败 diff 的 actual 侧（真实 win32 终态）：`hooks.json` + `posttool-once.sh`（seeded 原样），**无 `.posttool-blocked`**。
- 红绿路径：基线红（分类 §二）→ 机制落地后 refresh+变体 → `pnpm run test:snapshot -t hook-cc-posttool-block` 绿 ×2（逐字节同签名）。
- 已知残余风险（登记，不掩盖）：win32 变体 golden 含宿主 pwsh 错误文本（英文 en-US 稳定面；与前波 spawn ENOENT 类 golden 同一先例）。本地化宿主可能漂移 → 归 CI 平台矩阵口径。

### 2. `session/hook-cc-stop-continue`（GAP-2b，漂移）

同 §二.1：`sessionVariants`+`workspaceVariants` 声明、`session.win32.jsonl` 经 refresh（真实输出：Stop handler pwsh 解析失败→pass→止于 FIRST）、`workspace.win32.expected/` = 仅 `hooks.json`（无 `.stop_fired`）。stdout 断言（headless.snapshot.ts:819）以变体 fixture 的 final text 为期望，自动跟随 → 绿 ×2。

### 3. `session/hook-codex-stop-continue`（GAP-2c，漂移）

同 §二.2（dialect=codex；`workspace.win32.expected/` = 仅 `codex-hooks.json`）。绿 ×2。

### 4. `acp/image-compaction`（GAP-1，漂移——场景预算刀口）

约束：`request/context` 事件把 `contextWindow:11600` 冻进 fixture（改 cw 必红）→ **不动 contextWindow、不动 fixture**；改用 compaction-basic 配置的自由旋钮 `thresholdRatio`（默认 0.8，config.ts:20；不出现在任何已记录事件：`request/context` 仅含 contextWindow，`compaction/summary` 仅含 provider/model/maxTokens/usage）。

- 唯一编辑面：`snapshots/acp/image-compaction/cordis.snapshot.yml` 的 compaction-basic 块加 `thresholdRatio: <定心值>`（3 位小数）+ 注释更新（说明定心算术与平台余量论证）。live `cordis.yml` 零改动（authored 场景不重录）。
- **二分定心法**（每轮 replay ~3-9s，keyless）：
  1. 红态语义：`script exhausted call #4` = 阈值过低（压缩后仍 ≥ 阈值 → 文档化重试吃掉第 2 次 summarizer 调用）；`compaction 事件缺失`红 = 阈值过高（不触发，fixture 的 compaction 事件失配）。绿带 = 阈值 ∈ (post′, pre′]（pre′/post′=win32 触发前/压缩后压力）。
  2. 从 0.80（红：double-compaction）向上步进/bisect ratio（步长 0.005，即 ~58 token），先探出「无双压缩」上界与「不触发」下界，再取带中心，round 3 位小数。
  3. 定心后两侧余量各 ≈ 半带宽（预估 ≥100 token）≫ 平台 cwd/用户名差异（~8-25 token）→ 双平台确定性由构造保证；POSIX CI keyless replay 复验在案。
  4. 场景证明目标保持：纯文本压力 = pre′−2304 ≪ 定心阈值 → 「图片 route 定价驱动压缩」的证明余量反而增大。
  5. **失败处置**：若实测带宽 < 60 token（定心后余量 < 30，抗宿主差不足）→ 停手上报，禁止扩旋钮（retainTokens 改动会变压缩选区=变 transcript=越权）。
- 验收：定心值下 `pnpm run test:snapshot -t image-compaction` 绿 ×2（逐字节同签名）；receipts 记录带边界、选定值、两侧余量。

### 5. `web/minimal-preset`（GAP-2 web，漂移——渲染残渣）

- 唯一编辑面：`apps/web/tests/minimal-preset.snapshot.ts` 的 `text()` 归一器（:151-160）追加**窄**归一：剥离至多一行前导空白行 `replace(/^[ \t]*\r?\n/, '')`，注释引用同文件既定「平台渲染非行为」标准（:156-159）与 product 捕获既有剥离意图（tool-pwsh-persistent/src/index.ts:127 剥裸换行；win32 conpty 行尾补空格形态未覆盖）。
- 语义断言零松动：PERSISTED env、{{cwd}}、editor 输出、tools 名单、commandProbe、ui.win32 golden 全部保持精确匹配。
- 平台中立：POSIX 输出无前导空白行 → 归一为 no-op；产品未来硬化捕获后亦 no-op。
- GAP 登记（上报，不在本波修）：`packages/shell/tool-pwsh-persistent/src/index.ts:127` 建议扩展剥离 `^[ ]*\r?\n` 形态（产品包不在本波写域）。

## 三、测试矩阵与门禁（Worker 验收，全为真实退出码）

| # | 门禁 | 期望 |
| --- | --- | --- |
| G1 | 修复前基线红 ×5 场景：`-t hook-cc-posttool-block / hook-cc-stop-continue / hook-codex-stop-continue / image-compaction / minimal` | 各 exit 1（Worker 树内重立，与本分类一致） |
| G2 | 包聚焦 vitest（session-snapshot） | exit 0（新 spec + invalid cases 全绿；基线 330/1skip 不回退） |
| G3 | 每修复场景修复后 `-t <name>` ×2 | 各 exit 0 ×2，签名逐字节一致 |
| G4 | 全量 `pnpm run test:snapshot` | 失败集合恰 = {replays subagent-continuable through dsh --profile sdk}（GAP-4 已知红），**零新增失败名**，其余全绿 |
| G5 | 删全部 `*.tsbuildinfo` → `pnpm run build` | exit 0 |
| G6 | `pnpm run gen-cordis-catalog` | 0 written / 0 refreshed |
| G7 | `git diff --check`（HEAD 树 + 逐笔 staged） | exit 0；每文件恰一尾随换行 |
| G8 | `pnpm run test:docs`（15 门） | exit 0 |
| G9 | `pnpm run typecheck` | exit 0 |

- 提交纪律：`--no-verify` + 收据（pre-commit lefthook vendor guard exit 127 系环境事实），每笔收据含：staged `git diff --cached --check` exit 0、尾随换行核验、触及域零 vendor 路径声明。
- 触及包聚焦：session-snapshot 包 vitest（G2）+ 根 snapshot 套件（G1/G3/G4）；不跑全仓 test/test:coverage。
- 文件域（Worker 写域全集）：`packages/test-support/session-snapshot/{src/manifest.ts,src/expectations.ts,src/suite.ts,src/index.ts,tests/manifest.spec.ts,tests/expectations.spec.ts,tests/suite.spec.ts}`、`scripts/session-snapshot-corpus.corpus.ts`、`snapshots/session/{hook-cc-posttool-block,hook-cc-stop-continue,hook-codex-stop-continue}/snapshot.yml` + 各自 `session.win32.jsonl` 与 `workspace.win32.expected/**`、`snapshots/acp/image-compaction/cordis.snapshot.yml`、`apps/web/tests/minimal-preset.snapshot.ts`、`.agents/devframe/v14-batteryfix/worker/**`。
- 禁区（零触碰）：`.agents/devframe/v14/next/**`；`vendor/**`；`packages/experimental/{devframe,agent-evidence,command-goal-binding,shadow-router,project-memory}`（零 diff）；主树；EvJournal 在飞链（agent-evidence 域）零交互；GAP-4 场景（`snapshots/sdk/subagent-continuable/**`、sdk.snapshot.ts）零 diff；任何产品包（含 `packages/shell/**`）；禁 push/PR/发布/删文件/合并 main；禁创建任何 Agent。

## 四、review 口径（组长独立审查）

1. 复跑五修复场景 replay（红→绿实证以 Worker receipts + 组长复跑双源）。
2. 全量 snapshot 失败集合 = {GAP-4} 精确匹配。
3. 文件域核对：`git diff --stat 24b7db9189..HEAD` 逐文件对 §三文件域，越域即打回。
4. 变体期望值与真实回放一致性抽查：session.win32.jsonl 关键事件（hook/result pass、unknown tool、无 SECOND/无 block）逐事件比对 refresh 收割签名；workspace.win32.expected 目录内容对失败 diff actual 侧。
5. 机制 diff 审读：manifest 校验/existsSync fail-loud/invalid case 完备性；未声明场景零行为变化（包 vitest + 全量 G4 双证）。
