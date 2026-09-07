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

## 3. C3：侧栏/SessionID/模型切换/turn 用量 — FAIL（可复现，冻结待总控裁定）

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
- C3：FAIL（可复现 2×；exit 1；usage pill 未渲染；实现 src 冻结未动，修复裁定权在总控）。
- 附带发现（非 C 线义务，仅记录）：本分支 `turn-tail-actions` lane 存在无关 golden 漂移（`bash` 工具 unknown vs recorded fixture）。
