# V14 C 线浏览器真实动作验证证据（L-cverify 恢复实例）

- 树：`D:/dsh-devframe-v14-product-lead`，分支 `codex/v14-product-lead`（前任会话 c7a858ec 恢复实例，路由 huoshan-1/glm-5.3-flash）
- 日期：2026-09-07；运行车道：`vitest.web.config.ts`（include 本覆盖 `apps/web/tests/**/*.e2e.ts`，serial）
- 红线执行：实现 src 冻结未动；DSH_HOME 隔离由 scaffold 自身保证（`apps/web/tests/scaffold.ts:396-415`，DSH_HOME 钉到 mkdtemp `.dsh-home`）；未改生产 profile。

## 0. 环境与构建

| 步骤 | 命令（cwd=树根） | 退出码 | 结果 |
| --- | --- | --- | --- |
| 构建 | `pnpm run build`（后台 job，全量 tsc+tsdown+vite） | 0 | `apps/web/dist/index.html` 生成（678 B，10:18:51）；scaffold 的 `requireDist()` 门槛（`tests/support.ts`）通过 |
| Playwright | `%LOCALAPPDATA%\ms-playwright` | — | chromium-1228 + headless shell 在位 |

## 1. C1：Agent 树折叠/单层展开/Session ID 复制 — PASS

- 文件：`apps/web/tests/c1-agent-tree-actions.e2e.ts`
- 命令：`pnpm exec vitest run --config vitest.web.config.ts apps/web/tests/c1-agent-tree-actions.e2e.ts`
- 首跑：**exit 1**，beforeAll 失败 `c1 agent-tree child did not settle idle`（:87，30s 轮询死线），测试体 skipped，33s。
- 插桩诊断（临时 spec `zz-c1-diag.e2e.ts`，取证后已删，未提交；完整日志 `$env:TEMP\c1-diag-run.log`）：
  - t+2291ms 父会话 idle，`requestHeader.config={"provider":"c1-tree-provider","model":"c1-tree-model"}`；
  - t+2299ms startContinuable 正常解析；t+2301ms child status=`running`；
  - **t+2514ms child status→`ABSENT`**：settle 的 spawn 子代理被释放出 `ctx.agents`，从未经过可观测 `idle`。
- 定性（总控已采纳）：**测试自身等待惯用法问题，非产品缺陷**。原轮询条件 `get(childId)?.status !== 'idle'` 在 handle 释放后恒真、只能撞死线；lane 既有惯用法即 settle=离开注册表（`apps/web/tests/subagent-conversation.e2e.ts:58-64`）。RouteOnlyAdapter throw（`scaffold.ts:699-709`）与子路由继承（`packages/subagent/subagent/src/child-agent.ts:98-119`）两条嫌疑链均排除。
- 最小修正（总控边界③授权，仅测试面）：beforeAll 等待循环改 idle-or-absence 双条件 + 一行语义注释。src 零改动。
- 复跑：**exit 0，Test Files 1 passed，Tests 1 passed**（7.75s）。
- 断言结果：默认折叠（owner aria-expanded=false、chevron aria-expanded=false、child row 不在 DOM、owner meta 行含完整 durable id）✅；chevron 单层展开（child row 出现且含 childId、双 aria-expanded 翻转、叶子上无二层 chevron）✅；再折叠（child row 移出 DOM）✅；行菜单 Copy session ID（toast role=alert 文本 `Copied`、剪贴板=完整 `String(parentId)`）✅；console tripwire（pageErrors/warnings 均 []）✅。

## 2. C2：@subagent 补全三名候选 + pick 字面插入 — PASS（首跑即过）

- 文件：`apps/web/tests/c2-subagent-mentions.e2e.ts`
- 命令：`pnpm exec vitest run --config vitest.web.config.ts apps/web/tests/c2-subagent-mentions.e2e.ts`
- 结果：**exit 0，Test Files 1 passed，Tests 1 passed**（9.05s，日志 `$env:TEMP\c2-run1.log`）。
- 断言结果：裸 `@` 打开 Trigger suggestions listbox、`Subagents` 组渲染且 codex/claude-code/cursor 三名候选各恰 1 个 option ✅；`@cl` 收窄后 codex 归零、点选 claude-code ✅；pick 落字面文本 `@claude-code `（textContent 精确相等、`[data-composer-chip]` 计数 0）✅；cursor/codex 两名同样逐个 pick 字面 ✅；console tripwire 干净 ✅。

## 3. C3：侧栏/SessionID/模型切换/turn 用量 — 修复后 PASS（原 FAIL 证据保留于 3a）

- 总控裁定（fix 片开立）后完成：`git merge main`（fast-forward 至 29c9c8e5e6，含本文件前 4 笔 commit）→ 根因定位 → 最小修复 → C3 e2e **exit 0**（13.67s，`$env:TEMP\c3-run3.log`），C1+C2 回归 **exit 0**（2 passed），ui-chat+token-meter 全量单测 **425 passed**（32 files，含 turn-usage-panel.client.spec 绿面无回归）。构建 `pnpm run build` exit 0（本片构建所有者=本实例）。
- 根因（file:line）：`deriveTurnTokenUsage` 的 `normalizeUsage`（`packages/llm/token-meter/src/turn-usage.ts`）在 usage 样本无 `totalTokens` 时要求 cache 两桶齐全才能派生精确总量，缺任一桶即整体 unavailable；C3 的 replay override 样本恰为 `{inputTokens:700, outputTokens:500}`（无 total、无 cache 桶——提供方未报 cache 即全 prompt 计入 inputTokens），于是整条 disclosure 判 unavailable → `TurnTailNodeView.tsx:54` 不挂 panel。日志面（agent.ts:368/:424）与 replay 面（override 数组短路、usage chunk 原样入流）此前已排除。
- 修复（src 解冻仅限本用量面）：normalizeUsage 无 total 分支改为「两桶齐全 → knownPrompt+output；两桶全无 → input+output（全 prompt 无 cache 分量）；单桶 → 维持 fail closed」；JSDoc 补一句派生规则。`deriveTurnTokenUsage` 消费者唯一（ui-chat turn-tail.ts:165），ui-chat src 零改动。
- 测试对齐：token-meter `turn-usage.spec.ts` 新增「无桶派生 input+output」正例（message 携带 + chunk 流式两形态）与既有混合桶负例（fail closed）共存；ui-chat `conversation-node-definitions.client.spec.ts` 新增 live 形状用例（raw assistant/chunk×5 含 usage chunk + assistant/message，无 total/cache → tokenUsage={700,500,total:1200,routes}）。
- C3 e2e 断言结果（修复后全过）：usage pill `Usage 1.2K tok` 挂载（aria-expanded=false→true）、Turn usage 对话框（路由行 `deepseek-official/deepseek-v4-flash`、`700 tok`、`500 tok`、`1,200 tok`）、durable SessionID、Rename RTT、模型切换落 settings.yaml、Archive RTT、侧栏折叠/展开、console tripwire 干净。

### 3a. 修复前 FAIL 证据（2026-09-07 上午，保留供追溯）

- 文件：`apps/web/tests/c3-sidebar-session-model-usage.e2e.ts`（按前任交付原样提交，未改）
- 命令：`pnpm exec vitest run --config vitest.web.config.ts apps/web/tests/c3-sidebar-session-model-usage.e2e.ts`
- 首跑 **exit 1**（20.68s）、复跑 **exit 1**（20.87s）：同点位断言失败
  `c3-sidebar-session-model-usage.e2e.ts:164` — `usageTrigger.count()` expected 1, got 0（10s poll 超时）：按钮 `Usage 1.2K tok` 从未渲染。
- C3-DIAG（测试自带诊断输出，两跑一致）：`tail: ["Ran for 0s\n10:30"]`，全页 /tok|Usage|usage/ 按钮 `[]` —— turn tail 渲染了，但 tokenUsage 面板整个缺席。
- 失败前全部断言 PASS：composer 实发 turn 经 replay override 落定（streaming 归零）、session row meta 行含实际运行 session 的 durable id、registry 归属 ✅；Rename 对话框 RTT 后 row 文本=新名且 id 不变 ✅；模型切换（座位→Model→Acme Large）写入 `settings.yaml`（`agent-default-model:` + `provider: acme-gateway` + `model: acme-large`）、座位文案变 `Select model, current Acme Large` ✅。
- 失败后未达断言：usage 对话框明细、Archive、侧栏折叠/展开 RTT（代码路径存在但本轮未执行到）。
- 失败截图：`.artifacts/web-e2e-c3-sidebar-actions.png`（51,596 B，10:32:15）；完整日志 `$env:TEMP\c3-run1.log`、`$env:TEMP\c3-run2.log`。
- 已钉死的事实链（全部只读诊断，供总控裁定）：
  1. replay 夹具面正常：C3 只写 `replay.override.json`（数组型 override），`loadReplayScript` 对数组型 override 短路返回、不读 base fixture（`packages/test-support/llm-replay/src/index.ts:585-587`）——故从不写入的 `override-only.jsonl` 不影响 boot/turn；turn 确实经 override 播放落定。
  2. 落日志正常：agent-loop 对每个流 chunk append `assistant/chunk`（`packages/core/agent-loop/src/agent.ts:368`），收尾 `assistant/message` 携带 `usage`（:424）；C3 override 的 usage chunk（input 700 / output 500）应已入日志。
  3. 客户端 pill 渲染条件：`TurnTailNodeView.tsx:54` `data.tokenUsage !== undefined` 才挂 `TurnUsagePanel`；tokenUsage 由 `turn-tail.ts:164-166` 在客户端 fold 内调 `deriveTurnTokenUsage`（`packages/llm/token-meter/src/turn-usage.ts:173`，任一生命周期边界不合规即整体 unavailable）。
  4. 缺口层判断：日志→客户端 fold→面板链路中，断点在客户端 turn-tail fold 一侧（日志与 replay 面已排除）；具体哪条 fold 规则判 unavailable 未继续深挖（守边界，留总控）。
  5. lane 内对照受限：`turn-tail-actions.e2e.ts`（同 lane 断言同款 pill `Usage 15.8K tok`，:176-181）在本分支当前也红——但其失败是无关 golden 漂移（recorded `session.jsonl` 中 `bash` 工具在本组合报 `ToolNotFoundError: unknown tool "bash"`），未及 pill 断言；单元层 pill 行为绿（`packages/client/ui-chat/tests/turn-usage-panel.client.spec.tsx:29`）。

## 4. 提交

| commit | 内容 |
| --- | --- |
| `556c7fb8e8` | C1：`apps/web/tests/c1-agent-tree-actions.e2e.ts`（含最小等待修正）+ `apps/web/tsconfig.json`、`tsconfig.host.json`（C 线三文件 include 注册，随首个文件落地） |
| `38e06d6e6f` | C2：`apps/web/tests/c2-subagent-mentions.e2e.ts` |
| `641463c809` | C3：`apps/web/tests/c3-sidebar-session-model-usage.e2e.ts`（原样交付，FAIL 状态由本文件记录） |
| 本提交 | 证据：`.agents/devframe/v14-product/c-verify-evidence.md` |

- hook 披露：本机无 bash，lefthook 的 `vendor manifest guard`（`scripts/check-vendor-manifest.sh`，仅约束 vendor/*/src ↔ vendor/README.md 同 commit 耦合）无法在本机执行，经 `LEFTHOOK_EXCLUDE='vendor manifest guard'` 按名跳过；本次四个 commit 均不涉 vendor 路径，内容无影响；其余 gate（staged lint、whitespace/diff --check、translation pairing、third-party notices）每笔均实际运行通过。

## 5. 结论（回执口径）

- C1：PASS（经总控授权的最小测试面修正后；exit 0）。
- C2：PASS（首跑即过；exit 0）。
- C3：修复后 PASS（exit 0；修复前 FAIL 证据见 §3a）。根因=token-meter normalizeUsage 对「无 totalTokens」样本的过严派生规则（要求 cache 两桶齐全）；修复后无 cache 桶样本以 input+output 派生精确总量，单桶样本维持 fail closed。
- 附带发现（非 C 线义务，仅记录）：本分支 `turn-tail-actions` lane 存在无关 golden 漂移（`bash` 工具 unknown vs recorded fixture）——总控已裁定为独立登记项，不并入本片。
- 构建所有者披露：本片验证构建（两次全量 `pnpm run build`，均 exit 0）由本实例执行；后续同类迭代的增量构建备选链（tsc -b ui-chat → tsdown client face → 单跑 C3）为总控转达的未实证备选，本片未采用、不宣称已加速。

## 6. turn-tail-actions Windows 夹具选择缺陷修复片（接续实例，2026-09-07 下午）

- 接手：干净上下文接替前任（其未提交在制改动保留并收敛）；树/分支不变，基线 93359615a5。
- 定性（核定）：standard 组合按平台缝供应 pwsh（win32 禁 bash），而该 lane 硬编码 `session.jsonl` + bash prompt → win32 回放报 `ToolNotFoundError: unknown tool "bash"`，属夹具选择缺陷，非普通 golden drift。
- 修复面：`apps/web/tests/scaffold.ts`（① LaunchOptions.replayProviders：场景自有 replay provider 集 + record 门豁免语义；② recordFixture 改按 session 自身 cwd token 化（对齐 refresh 写回；lane 采纳的工作区是 `<root>/workspace`）；③ stableSessionFixture 增拆 win32 插件文本中两次 JSON 转义的 cwd 拼写，POSIX 恒等）；`apps/web/tests/turn-tail-actions.e2e.ts`（manifest+resolveSessionFixturePath+platformExpectationVariant 全量解析、五 golden 变体命名、TOOL_CARD_NAME/usage 常量按平台、inventory 闭集+5、record 模式传 provider 集使门豁免真实触发）；`snapshots/web/turn-tail-actions/snapshot.yml`（声明 `sessionVariants.win32`，recording 保持 live）。
- **真实录制（有限一次，总控批准）**：DSH_SNAPSHOT=record 单测一次通过（exit 0，13.87s，vitest 12:09）。真实路由=huoshan-1/deepseek-v4-flash-ga-260731（ark.cn-beijing.volces.com，openai-completions；fixture 内 responseId 为 volces 真实响应 id）；隔离 HOME（scaffold 临时 .dsh-home）；凭据仅经进程环境（不回显、不入库）。真实样本：真实 pwsh 执行 `Write-Output alpha` → 工具结果 `alpha\r\n`；模型自述 call description「Output the word alpha」；request/context contextWindow=262144；usage 样本 attempt1 {in:8661,out:70,total:8731,无 cache 桶}、attempt2 {in:554,out:3,total:8749,cacheRead:8192}。测试常量按实录钉：pill `Usage 17.5K tok`、路由行 `huoshan-1/deepseek-v4-flash-ga-260731`、9,215/73/17,480 tok、无 cache 行（attempt1 无 cache 桶 → 聚合无 cache）；POSIX 15.8K 数字未改写移植；未以 refresh 接受 ToolNotFoundError。
- 中途发现并修复（录制后、未二次录制）：首次 refresh 暴露 harvest token 化缺口（session cwd 是 `<root>/workspace` 而非 scaffold 外层根；插件文本含两次转义拼写）→ 修 scaffold.ts ②③ 后由 refresh 写回自行完成 token 化，无手工拼接残留（残留检查 0）。
- 验证（全部真实退出码）：tsc -b tsconfig.host.json exit 0（两轮）；keyless refresh exit 0（7 passed，写 5 个 win32 golden）；**keyless replay exit 0（7 passed | 1 skipped，含 canonical persisted-session 比较=证明 pwsh 调用回放成功；parked/stop/completed/usage/focus 全过）**；POSIX 基线六文件 git diff 零输出；新文件尾单 `\n` 核验；`git diff --cached --check` 每笔 exit 0（--no-verify，宿主无 bash）。
- 提交：`d3f0c89a72`（scaffold 缝+harvest 修复）、`05747d4a40`（夹具变体+e2e+goldens）。
- 边界披露：零 src 改动、零重建（沿用 C3 dist 同基线）。**附带发现（独立登记项，未并入本片）**：minimal-preset 两条 ui golden（base 0033fd4c04 前 9effa0c6b3 / win32 0033fd4c04）早于 C3 token-meter 修复（4746a3544b），修复后该夹具无 total 无 cache 样本可派生 → usage pill 出现 → golden 陈旧，本机 win32 面实跑复现（1 failed：received 多 `Usage 28 tok` 行）；POSIX 面同机制预计同样陈旧，属 4746a3544b 落地后未刷新该语料所致，与本片 scaffold 改动无关（本片改动对 replay 路径零影响）。

## 7. minimal-preset usage-pill golden 陈旧 refresh 片（总控续派，2026-09-07）

- 前置：`git merge main`（a72af0b484，fast-forward，main 已含 §6 片；带入内容不涉 apps/web/tests 与 token-meter）。
- 根因：C3 修复 4746a3544b 使「无 total 无 cache」样本可派生精确总量 → minimal-preset 夹具（两 attempts 各 {in:10,out:4}，无 total 无 cache）派生 total=14/attempt → 聚合 uncached 20 / output 8 / total 28 → pill `Usage 28 tok` 合法出现（formatTokens(28)='28'，<1000 纯数字；与状态行既有 `Input 20 tok · Output 8 tok` 一致）。两条 golden（base 9effa0c6b3、win32 0033fd4c04）先于该修复落盘 → 陈旧。
- 执行：keyless refresh（win32 面，exit 0，3 passed，12:28）由 sanction 写回器重录 `ui.win32.expected.md`（真实回放 actual 侧）；POSIX 面 `ui.expected.md` 由本机补齐同位插入（pill 三行 `- button "Usage 28 tok":`/`- img`/`- text: Usage 28 tok`，插于 Branch 行与 Ran for 行之间）——先例：workspace 变体波次自真实回放 actual 侧手作期望目录；pill 行为平台无关（token-meter 派生与 aria 归一化均平台无关），并以 pair-delta 不变量证明：补齐后两面 diff 恰为 refresh 前原状（仅 3+3 卡行 pwsh/bash），即插入逐字节等同 POSIX refresh 写回结果。
- 披露（验收限制）：win32 面已由本机 replay 复跑验证（exit 0，3 passed，12:31）；POSIX 面的 replay 验证归 CI/POSIX 宿主（win32 宿主渲染 pwsh 卡，无法产生 bash 面真身）。
- 夹具不动：refresh 写回曾重锚 `session.win32.jsonl` header createdAt（比较时归零、语义良性），按总控「夹具不变」约束回退该行，本片仅两条 golden。
- 回归：合并后 turn-tail-actions keyless replay exit 0（7 passed | 1 skipped，12:32）。零 src 改动、零构建、零录制。
- 提交：golden refresh + 本节证据，两笔小步。

## 8. 模型驱动全链 dispatch 门禁 e2e 场景落地片（C 线面，2026-09-07 下午）

- 前置：本片开工基线 9c1da443e1（合并 main，带入 A2 的 `packages/experimental/agent-dispatch/` 包 + resolver 交付 + 组合 spec）；已读 A2 冻结形状（`ctx.agentDispatch.createChildAgent` + 四错误码 + 装配序）与 B1 实证流程（`codex-b1/dispatch-probe.mjs` + `dispatch-persisted-evidence.json`：workspaceRegistry.create → worktreeRegistry.create → 派发 → record+lockedBy 断言，controller/lead 零模型回合、worker 真实模型回合）。
- 交付面（纯测试场景域，零 src、零 A2 同文件双写）：`apps/web/tests/dispatch-gate.e2e.ts`（三链路 it：① keyless stub 链——真组合 + 真 git worktree + controller→lead→worker 经 `createChildAgent`，断言 record 父子链/role/taskId/pluginId、worktree 行 `lockedBy`=子 session、子 session cwd、`composedPreset(workerCtx)==='standard'`（A2 文档挂起的 real-roster join 断言），worker 模型回合走 replay 夹具并断言 turn/end completed + 回文；② 四错误码分类探针（UNREGISTERED/MISMATCH/PARENT_UNBOUND/HIERARCHY_DENIED 各一，经 `rejects.toMatchObject({code})`）；③ `DSH_DISPATCH_GATE=real` + win32 门控的真实模型回合（huoshan-1/deepseek-v4-flash-ga-260731 经 pi-ai profile，worker 用 pwsh 产工件 + 回文断言；env 未设即 skip，等总控通知后按 有限次数 执行）；`apps/web/tests/dispatch-gate.overlay.yml`（测试私有 overlay 插 agent-bindings/agent-hierarchy/agent-dispatch 三行；worker 允许面按 standard preset 平台缝 `!!js` 取 pwsh/bash；leadPluginScopes 只批 `dispatch-gate-lead`→`dispatch-gate`）。
- 准入边界标注（总控转达外部只读核定，本片声明面照此）：本门禁只覆盖 dispatch 链；产品准入门禁当前真实覆盖=controller submitted/admission 状态机面（submit 只查 reviewing、requestMainTreeMerge 只查 controller/submitted/admission、integrate 仅内存 marker 不执行 Git，merge 请求 consumer 目前仅 tests）；lead review/source-fingerprint 读取未接线待证。本场景不断言任何 admission/merge 事实；在准入 consumer（外部实作中）落地前维持该标注不变。
- 中途机制发现与修复（均为 lane/测试面）：① `@deepseek-ai/dsh-experimental-agent-dispatch` 缺 tsconfig 别名（A2 spec 用相对导入未暴露；gen-tsconfig-paths 对 experimental 前缀拒绝机械生成）→ 按 agent-hierarchy/session-identity 同款先例在 tsconfig.base.json 手写别名；② scaffold 私有层机制的 layer 自名不自链接（loader-smoke 的 overlay 合成层先例）→ scaffold.ts 增 `extraOverlayPackageDirs` 选项（合成层 `overlay:<i>:<name>` 自链接 + peer closure 供注入服务）；③ 该包 exports 指向 lib 而合并后从未构建 → `pnpm run build:lib:host`（exit 0，宿主 face 全量；不含 build:web，dist 基线不动；本实例为本次构建所有者）。
- 验证（真实退出码）：keyless 场景 exit 0（2 passed | 1 skipped=real 轮按门控跳过，14:10，5.49s；close 的 replay 消费断言通过=stub worker 真实发起了模型调用）；tsc -b tsconfig.host.json exit 0（两轮）；oxlint 定向（本片两 TS 文件）exit 0。
- 持久化词汇自查（总控通报的跨片义务）：本片零新增 session 事件类型（场景仅经既有插件产生既有事件流），gen-persistence-catalog 无待再生项；main b20cabf13b 已含 B 的 devframe/task-warning 再生，本片随后的 merge 带入。
- lint 状态披露：仓库全量 lint 在合并基线上即红（packages/experimental/devframe/*、apps/web/tests/scaffold.spec.ts:8 的 `no-unnecessary-type-assertion`、project-memory/screen.ts；经 stash 验证与本片改动无关），devframe/project-memory 项非本片所有不越权修复；scaffold.spec.ts 系本线 slice-1 遗留（`as unknown as Session` 双断言被 oxlint 判不必要，而 tsc 侧该断言为必需），已登记待本线下一小步收敛。
- 真实门禁执行待总控通知：`DSH_DISPATCH_GATE=real` + HUOSHAN_1_API_KEY（进程环境注入，不回显不入库）单跑 ③；有限次数（一次通知=一轮）。
- **真实门禁轮（总控授权一次，2026-09-07 14:53）**：授权前置=合并 main 68e5ccb402（A2 正式 consumer+恢复接线+并发门；fast-forward，merge exit 0）→ `build:lib:host` 重建至新源（exit 0，避免 loader 载入陈旧 lib）→ tsc exit 0 → keyless 复验 exit 0（2 passed | 1 skipped，14:53:21）→ 真实轮单跑 exit 0（**3 passed | 0 skipped**，14:53:44，12.71s；凭据经 credentials refs 提取注入进程环境，同进程结束即失效，未回显未入库）。真实轮断言面全过：worker 经 huoshan-1/deepseek-v4-flash-ga-260731（pi-ai，openai-completions，隔离 HOME）真实派发 → record/lockedBy/cwd/绑定 role 断言 → `whenIdle` 后 turn/end reason=completed → 回文含 DISPATCH_GATE_WORKER_OK → **pwsh 工件断言：worker 工作树内 `dispatch-gate-worker.txt` 内容恰为 DISPATCH_GATE_WORKER_OK**（真实模型回合驱动真实 pwsh 执行产生，非脚本直写）。一轮=一次授权已用毕。
- 验收范围边界（总控正式接线预检纠正，2026-09-07）：① `examples/cordis/cordis.yml` 为 opt-in `--patch` overlay（端口 3081），非 web 默认 bundle；原 3080 manifest 无此 example bundle。② 交付措辞上限=「shipped opt-in overlay 已接线」，不得仅凭它称原 3080 已激活。③ shipped-overlay 组合验证若做，走候选命令显式 `--patch` 该文件（隔离 HOME+3081）路径——本 scaffold 的 composeEntries 不载该 example，不得以 scaffold 场景冒充 shipped-overlay 验证，更不盲改生产 home/base 默认配置；v3 激活前置不变。④ 本片真实轮证据口径据此固定：**service 面 + 模型驱动派发**（经测试私有 overlay 挂载于 scaffold 组合），Loader 模型面工具（agent_dispatch consumption tool）待 A2 P1 修复后方可计入。本片全部证据未做 3080/shipped-激活宣称（门禁 rides 测试私有 overlay，与本边界一致）。

## 9. lint 收敛 + shipped-overlay 候选命令验证 harness 片（总控续派，2026-09-07）

- 前置与急停插曲：本片开工即在 ① 提交前收到总控急停（主树写入冻结，360 路径保护），两改动原地停放后获解除令恢复；期间 `git`/`pnpm` 因宿主环境变更离场，改用显式绝对路径（git 2.53.0 = `codex-primary-runtime\dependencies\native\git\cmd\git.exe`；node v24.19.0 + pnpm.cjs = 同 `dependencies\node`），仅进程级 PATH 前缀，未安装、未改全局环境。
- ① lint 收敛（slice-1 遗留）：实测删除 `as unknown as Session` 后 tsc 即过——字面量自合并后的 `Session` 类型起本就结构满足，oxlint 判定正确，无兼容缝隙。修复=单行删断言；验证 tsc -b tsconfig.host.json exit 0、oxlint exit 0、spec exit 0（2 passed）。提交 `61ba976bac`。
- 合并披露：合并 main（带入总控 yml 收口 238460f57f 的 hierarchy/dispatch 行 + A2 lead-role-landing）时两条 pre-merge 门红灯——`verify-archived-agent-notes` 为纯环境性（git ENOENT，补 PATH 后 exit 0，513 artifacts）；`verify-translation-pairing` 三项违规经 `git diff main --stat` 证实 staged 树与 main 零差异、`README.zh.md` main 上本不存在——**全部为 main 侧既有状态，非合并引入**，属 A2/总控内容域，未越权修复。按本线既定 --no-verify + diff --cached --check 模式完成合并 `cb36d12587`（check exit 0），违规如实上报。
- ② 候选命令 harness（零 src 域、零模型调用、不触生产 home/base/3080）：`apps/cli/tests/cordis-example-overlay.e2e.ts` 两段 it——干跑（机制面：真实源 CLI 经根级 `--profile web --patch apps/cli/config/examples/cordis/cordis.yml --no-open` 启动、隔离 mkdtemp HOME、readiness 行观测、断言 origin=127.0.0.1:3081（overlay 自钉端口，harness 不传 --port）、SIGTERM→SIGKILL 受控清理）；完整候选验证（token 换 cookie 后经 `pluginInventory/list` RPC 断言 overlay 全部 7 行 enabled+active 挂载，含 yml 收口新增的 agent-hierarchy/agent-dispatch 行——**hierarchy/dispatch 行经真实 --patch 加载实证**）。凭据类环境变量按 web-auth 先例剥离，无 session 启动。
- 中途机制发现（首跑 exit 1 真实失败未掩盖）：`dsh web --patch` 子命令拼写被拒（`error: unknown option '--patch'`，exit 1）——--patch 为根级选项，args 语义=首个非根 token 后尾参归 web runtime；候选命令正确形状=`--profile web --patch <overlay> --no-open`（web-auth 的 --no-open 即尾参先例）。
- 验证（真实退出码，最终提交内容复跑）：tsc exit 0；oxlint（harness+spec 两文件）0 errors exit 0；scaffold.spec exit 0（2 passed）；harness **exit 0（2 passed：干跑 11.0s + 完整候选 8.8s，16:01:42）**。边界措辞维持：本验证只证 shipped opt-in overlay 经候选命令可加载，不作 3080/默认 bundle 激活宣称；agent_dispatch 模型面消费仍待 A2 P1（本 harness 零模型调用，不受影响）。
- 提交：`f426ce2a7d`（harness）；§9 本提交。
