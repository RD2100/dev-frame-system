---
description: 宿主平台债泛化波阶段①逐例分类持久化记录（p/battery @ c93b86c43e，V1.4 stage-2 approval precondition）：88 红基线复现、期望漂移 69 vs 机制不可达 19、H1-H6/F1-F4 组表、环境口径、refresh 前 token 卫生清单、组长批复与 V1.4 裁定登记。
---

# 阶段①逐例分类记录（B 族变体机制泛化波）

- 基点：`p/battery` @ `c93b86c43e0a7fa9c5720ea70575241b0c990a22`（树净，全程只跑不改）。本文件=阶段②任何提交前的持久化 precondition（V1.4 battery-approval-request revision=2）。
- 执行者：Worker `57d0355f-86ff-4f21-9edc-37d33d17e580`（L-Foundation），组长 `0c852cbc-0f17-4a59-a43e-7a141f034efe` 抽查实锤并批复。

## 环境口径

- win32 宿主；`DSH_EXAMPLE_MODE=lib`；`pnpm run build` 先行 exit 0；逐文件 `pnpm exec vitest run --config vitest.snapshot.config.ts <file>`（replay）。
- 所有失败均为确定性断言/启动错误，无超时类基础设施失败；A 族 grep（`waiting for services|workspaceRegistry|worktreeRegistry`）三份日志 **0 命中**；SyntaxError **0**（套件日志内）。
- 既有绿面：`apps/web/tests/minimal-preset.snapshot.ts` **3/3 绿**（B 族先例在位）；`message-feedback-protocol.snapshot.ts` **1/1 绿（C 族 0）**；9 个 `platform: posix` 场景正常 skip（agent-instructions, background-job-admission, fs-glob-sampling, missing-sandbox-runner, partial-landlock-child-failure, ptc-python-turn, ptc-read-image, ptc-read-image-attachment-path, session-query-spill）。

## 88 红基线（收缩前红名单）

| 套件 | 红 | 过 | skip |
| --- | --- | --- | --- |
| snapshots/session/headless.snapshot.ts | 67 | 6 | 9 |
| snapshots/sdk/sdk.snapshot.ts | 16 | 0 | 0 |
| snapshots/acp/acp.snapshot.ts | 5 | 9 | 1 |
| 合计 | **88** | 15 | 10 |

## 期望漂移组表（69/88，变体可达）

| 组 | 计数 | 签名/锚点 | 用例 |
| --- | --- | --- | --- |
| H1 request header #1 工具目录漂移 | 42（headless 41 + acp cancel） | committed POSIX pin 有 `bash`，win32 实跑为 `pwsh`（平台门控）；叠加 worktree_* 四工具新增与 interrupt_agent/list_agents/send_message 描述更新（目录演进，变体重录一并吸收）；acp 侧 escalation-approved 为 default 头类 pin 持有者，共享 sidecar → 一个 tool-schemas win32 变体服务全类 | advanced-toolchain, advanced-toolchain-runtime, cordis-inspect-jsdoc, empty-response-retry, error-finish, fs-edit, fs-policy-reject, fs-read, fs-read-window, fs-write, fs-write-overwrite, fs-write-overwrite-bounded, hook-cc-invalid-matcher, hook-cc-pretool-ask, hook-cc-promptsubmit-context, hook-codex-invalid-matcher, hook-codex-promptsubmit-context, lsp-definition, parallel-tool-calls, product-subagent-both, product-subagent-codex, product-subagent-result-diagnostic, pty-tools-sandbox-backend, ralph-loop, read-image, read-image-dimension, read-image-reencode, read-image-text-route, repeat-tool-reminder, skill-load, subagent-child-question-rejection, subagent-depth-two-rejection, subagent-max-tokens-partial, subagent-multi, subagent-parallel, subagent-published-run-failure, subagent-spawn-in-process, text-turn, todo-write, web-search-endpoint-guidance, workflow-run, acp/cancel |
| H2 UNKNOWN_TOOL 会话漂移 | 7（headless 5 + acp 2） | POSIX authored 录制脚本调用 `bash`，win32 目录只注册 `pwsh` → 拒识；`session.win32.jsonl` 重录可达 | headless: compaction-recovery, fs-delete-recreate, hook-cc-posttool-context, hook-codex-posttool-context, workspace-edit; acp: escalation-approved, escalation-rejected |
| H3 sandbox:policy 双形态 cwd 泄漏 | 4（headless 3 + acp 1） | system-prompt 插件 snapshot 的 sandbox:policy 文本中 win32 cwd 以 JSON 转义双反斜杠形态残留未 token 化（期望侧 `{{cwd}}`）。**机制缺口实锤**：1624f7a5a6 只修 apps/web scaffold；共享包 normalize.ts `replaceCwd`/`scrubString`（比较方向）与 `tokenizeSessionFixtureCwd`（稳定化方向）均无双形态处理 | headless: pwsh-tool-turn, session-sandbox-root, web-fetch; acp: fs-escalation-approved |
| H4 平台流程/形态会话漂移 | 11 | 事件序/内容形态与 POSIX authored 录制漂移（多为 H2 连带或平台事件形态差）；session.win32.jsonl 重录可达 | headless: bash-tool-turn, both-mode-turn, hook-cc-posttool-block, hook-cc-pretool-deny, hook-codex-posttool-block, hook-codex-pretool-block, packed-chunks, ptc-turn, ptc-workspace-context, tool-call-turn, bash-spill（spill 内容形态差） |
| H5 stderr/stdout 平台行为漂移 | 4 | hooks.json POSIX 命令在 win32 执行语义不同 → promptsubmit 拦截/stop-continue 流分叉；stderr 投影取自 fixture turn 状态，变体重录自洽可达 | hook-cc-promptsubmit-block, hook-codex-promptsubmit-block（stderr 期望 '' 实得 script exhausted）; hook-cc-stop-continue, hook-codex-stop-continue（stdout SECOND 实得 FIRST） |
| H6 script exhausted（acp image-compaction） | 1 | `llm-replay: script exhausted — session requested model call #4 but its script has only 3`：win32 工具目录改变重放流程消耗；变体重录可达 | acp: image-compaction |

账目：headless 67 = H1×41 + H2×5 + H3×3 + H4×11 + H5×4 + F×3（F2/F3/F4 各 1）；acp 5 = H1×1 + H2×2 + H3×1 + H6×1。组口径合计（H1 42 + H2 7 + H3 4 + H4 11 + H5 4 + H6 1 = 69 期望漂移）+（F1 16 + F2 1 + F3 1 + F4 1 = 19 机制不可达）= **88** ✓。

## 机制不可达清单（19/88，fail-loud 报批）

| 项 | 计数 | 根因（file:line 实锤） | 处置（组长批复 + V1.4 CONCUR） |
| --- | --- | --- | --- |
| F1 sdk 水合缝隙 | 16 | `snapshots/sdk/sdk.snapshot.ts:311` `hydrateReplayFixtures` 朴素 `replaceAll('{{cwd}}', cwd)` 把 win32 反斜杠 cwd 写坏 JSONL → 子运行时 `llm-replay: session snapshot line 10 contains invalid JSON` → `SyntaxError: Bad escaped character in JSON` → context inactive → 16 场景统一 `JsonRpcResponseError: cannot create effect on inactive context`（探针实锤，探针已删除树净） | **阶段②修**（APPROVED）：按 JSON 字符串转义形态注入替换或共享双形态 helper |
| F2 subagent-acp-diagnostic | 1 | 场景自组补丁 `!!js` 参数用 `decodeURIComponent(new URL('../../../...mock-acp-server.ts', 'file://' + DSH_SNAPSHOT_FILE).pathname)`（POSIX 语义）→ win32 产出 `/D:/...` → 子进程 `Cannot find module 'C:\D:\...'`，mock-acp-server 无法启动 | **修**（APPROVED）：`fileURLToPath(new URL(...))` 替 POSIX 语义 pathname，域内机械适配 |
| F3 persistent-pwsh-tool-turn | 1 | win32 基座已原生注册 `pwsh` 工具，场景补丁 `@deepseek-ai/dsh-tool-pwsh-persistent`（注册名即 `pwsh`）再注册撞车 → boot 失败 `tool "pwsh" is already registered`；POSIX 基座注册 bash 故不撞 | **GAP 登记不修不 skip**（组长裁定 + V1.4 CONCUR）：工具注册产品语义非测试面；1 红如实保留，无 skip 标记无假绿；幂等注册/平台门控候选归后续产品链（路由 V1.4） |
| F4 read-image-attachment-path | 1 | replay.override.json fromRequest 模式 `"<path>(.+)/red\.png</path>"` authored POSIX 路径形态，win32 请求内嵌反斜杠路径 matched nothing；bext 机制不支持 override 变体 | **修**（APPROVED，不做机制扩面）：平台无关形态如 `(.+[\\/])red\.png` 容两种分隔符 |

## refresh 前 token 卫生清单（阶段②受控生成逐文件检查单）

每个 refresh 写回的变体文件（base 与变体两侧）提交前必须逐文件人工核对：

1. **首行 session 头**：`"cwd":"{{cwd}}"` token 在位（JSON 转义与裸双形态——1624f7a5a6 修补后 scaffold 已双形态，但共享包 tokenizer 泛化面同样检查）；`"createdAt"` 为稳定值（与 base 同值或既定 token，绝不留当次运行真实时间戳）；`"id":"{{session:1}}"` 家族 token 在位。
2. **事件行**：无当次运行宿主路径残留（含 basename 段，如 `dsh-web-e2e-ws-*`/`dsh-` 前缀临时目录名）；`{{message:N}}`/`{{sessionId}}` token 家族完整；无 unknown-tool 错误行固化（POSIX authored 语料纪律）。
3. **sandbox:policy 等插件文本**：cwd 以 token 形态在位（H3 类双形态 泛化落地后由机制保证，仍抽查）。
4. **互证工具**：一律 `git diff --no-index`（含 `--no-textconv`）——`git diff --stat` 对 untracked 文件恒空（bext 假阳性教训）。
5. **声明同步**：manifest 声明（sessionVariants/expectations win32）与变体文件成对落盘；清单守卫/corpus 门全量复跑。

## 批复与裁定登记

- 组长批复（阶段①后，第 15 轮）：分类认可（抽查 normalize.ts `replaceCwd`/`cwdSpellings` 单形态、sdk.snapshot.ts:311 朴素水合实锤）；阶段②顺序=机制泛化先行 → 消费缝接线 → 变体落地（共享 pin 结构优化）→ corpus 门演进；F1/F2/F4 修、F3 GAP。
- V1.4 裁定（battery-approval-request revision=2，经外部协调员保留链中转）：STAGE 2 APPROVED（扩域 packages/test-support/session-snapshot/** 正式化）；stage2Plan CONCUR（与组长批复一致）；F1/F2/F4 APPROVED、F3 GAP CONCUR；main 合并独归 V1.4；今后范围变更只向 V1.4 请求；provider 归因只认持久化 session JSON（huoshan-1 已证）。
- 目标：机制泛化+消费缝+变体落地后 **88 红 → 约 1 红（仅 F3 GAP）**，A/C 族 0 无新签名；F1 修复后增量新签名按同分类法归类上报。
