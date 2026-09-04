# Agent Note: DevFrame Slice 0 Capability Ledger and Recon Receipt

Status: proposed

Review status: review-pending

[English](2026-08-14-devframe-control-sessions.md) | 中文

## Problem

DevFrame 在安全派发智能体之前需要一个持久的 Global Controller，以及每个 DSH Workspace 一个持久的 Project Controller；随机聊天不是持久权威，另做工作台或数据库又会让权威脱离 DSH。本文是 Slice 0 的入口账本：记录固定 DSH 提交真正暴露的能力、脏工作树里仅存在的候选实现，以及在启用控制面执行前必须补齐的最小接口。

## Proposal

复用 DSH 原生 Workspace、Session、Agent、Goal、Job、Workflow、provider、tool、persistence、Profile、Bundle 和 UI 接缝。只增加一层薄的 DevFrame 控制层，把确定性的 Global 身份 `devframe-global:<profileId>` 与 Project 身份 `devframe-controller:<workspaceId>` 绑定到 DSH Session 日志，再提供 readiness 和一个原生 Global 入口。不增加第二个 Session 数据库、第二个聊天模型、第二个终端、第二个项目注册表，也不整体重写 Agent Loop。

第一条可接受切片只做身份和 readiness。它必须在模型或工具执行前写入并 flush 一个经过校验的 `controller/identity` 事件，让 Global 保持只读且不带项目工具；身份、Host 所有权、provider 就绪或策略证据缺失时必须失败关闭。派发、修订循环、论文流程、Obsidian 写回、MCP 桥和浏览器交互属于后续切片，各自有独立门槛。

这是一份有提交证据的 Recon Receipt，不是实现批准。截图、README 声明、旧 DevFrame 代码和当前候选 UI 都不是上游证据；候选证据在下文单独标注。因此状态保持 `proposed` 和 `review-pending`，绝不写成 `PASS`。

## Target

目标是在 DSH 内做出最小可用的控制面地基：用户能打开一个 Global Controller，看到它的精确 Session 身份和 readiness，选择 Workspace，并在后续把受治理任务交给 Project Controller，同时不产生第二个权威。Slice 0 不承诺自主修改项目、浏览器自动化、论文起草或多智能体完成。

## User-visible Contract

| Acceptance Delta 字段 | 冻结要求 |
|---|---|
| Source | 用户在 2026-08-15 提供的两张带批注 DSH 截图是 Slice 0 展示权威；固定 HEAD 和 Host/runtime 契约仍是技术权威。 |
| Must appear | 底部侧栏只出现一个原生机器人图标入口，标签为 `总控`；其溢出菜单展示 Host 发布的精确 Global Session ID 和复制动作。 |
| Must disappear | 普通 Workspace/Session 树不出现 `总控` 或 Global 行；普通聊天记录不出现控制器 identity/readiness 卡片。 |
| Interaction | 点击底部入口打开 readiness 发布的精确 Session；点击溢出菜单展示并复制同一个完整规范 ID；starting、blocked、stale、畸形或近似前缀身份全部失败关闭。 |
| Proof | 真实 Profile/Loader/browser 探针覆盖旧/新近似前缀 ID、精确导航、精确剪贴板输出、重启稳定性，以及重复树行和聊天卡片均不存在；只有组件测试不够。 |
| Product reviewer | 独立于实现的产品审阅者先把运行界面逐项与上述字段对照，再进行 P0-P3 技术审阅；任何一项不符都阻断接受。 |

## Recon Receipt

| Receipt field | Commit-backed observation |
|---|---|
| Source commit | 固定 DSH HEAD 是 `47f943859bef60e4160492346772ded9b24f765a`；该公共树在此提交没有 `packages/devframe` 或 DevFrame bundle。 |
| Scope | 账本映射 `D:\dev-frame-system\docs\PRD.md` Slice 0 的 DSH §5 复用候选和缺失能力；主仓库路径只是上下文，不当作 DSH 源码。 |
| Evidence rule | 复用必须有公共 symbol、源码路径和可运行探针；失败或不可用的 seam 记为 `missing` 或 `blocked`；当前脏工作树候选永远不提升为 HEAD 能力。 |
| Tree probe | `git ls-tree -r --name-only 47f943859bef60e4160492346772ded9b24f765a -- packages/devframe packages/client/ui-devframe-control-session packages/bundle/devframe` 没有返回路径。 |
| MCP and ccswitch probe | HEAD 只有 `packages/mcp/mcp-client`；`git grep -n -i ccswitch 47f943859bef60e4160492346772ded9b24f765a -- .` 没有匹配。 |
| Official MCP route recon | OpenAI 2026-08-15 的 [Secure MCP Tunnels](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) 和 [Connect ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt) 指南记录了 ChatGPT developer-mode app 通过 outbound-only tunnel 访问本地/private MCP Server 的路径。它需要 `tunnel_id`、runtime API key、Platform Tunnels Read/Use 权限、ChatGPT developer-mode permission，并在 ChatGPT Plugins 中选择 Tunnel。这只是上游路径证据，不是 DevFrame canary。 |
| License probe | 当前 checkout 的 `P-LICENSE` 通过，报告 `225 DSH package(s) checked; all declare MIT`；这只是许可证检查，不是功能证据。 |
| Test probes | 下面每个复用账行都引用逐能力探针注册表中的一个或多个 probe ID；聚合通过总数只保留为历史批次上下文，不再证明单项能力。 |
| Probe boundary | 早先批次运行在脏 checkout，而非固定提交的干净 detached 副本；其 `707 passed`、`8 failed`、`1 skipped` 总数包含 Windows symlink `EPERM`。标为 `recorded` 的路径是精确可运行目标，不表示本次修复已经重跑。 |
| Repair focused probe | 2026-08-15 覆盖 Todo、实时/持久 Subagent seam、Conversation UI/input queue/search/Node、LSP 和 event-catalog 的命令报告 34 个文件中 33 个通过：`843 passed`、`3 failed`、`2 skipped`。3 个失败全部是 LSP stdio Host symlink 用例，在 Windows `symlink()` 处被 `EPERM` 阻断；其它能力边界没有失败。 |

## Per-capability Probe Registry

每个 ID 都是矩阵使用的证据地址。`verified` 表示本收据记录了成功命令；`recorded` 表示已为下一次干净 checkout 门禁确定精确聚焦路径，不借用聚合总数。

| Probe ID | 能力边界 | 固定 commit | 可完整复现的命令 | 精确结果 | 判定与限制 |
|---|---|---|---|---|---|
| `P-WORKSPACE` | Workspace 注册表/路径身份 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/workspace/workspace/tests/` | 1 个文件通过、1 个失败；45 项测试通过、2 项失败 | `BLOCKED` — 两个失败均为 Windows symlink 创建 `EPERM`；canonical alias 行为尚未完全验证。 |
| `P-SESSION` | Session 精确 ID、append、replay、flush | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/core/session/tests/` | 13 个文件通过；282 项测试通过 | `PASS`。 |
| `P-AGENT` | `ctx.agents` 实时注册表和 Agent/Session 身份 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/core/agent/tests/` | 6 个文件通过；87 项测试通过 | `PASS` — 仅证明实时注册表，不是持久 catalog 证据。 |
| `P-GOAL-PLAN` | Goal 续接和 plan-mode 组合 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/goal/goal/tests/ packages/goal/goal-round-driver/tests/ packages/plan/plan-mode/tests/` | 9 个文件通过；179 项测试通过 | `PASS`。 |
| `P-TODO` | Session 所有的 `todo_write`、回放投影和 UI 计划条 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/todo/tool-todo/tests/ packages/client/ui-conversation/tests/todo-panel.client.spec.tsx` | 6 个文件通过；50 项测试通过 | `PASS` — 单 Agent checklist，不是共享任务 authority。 |
| `P-JOBS` | Job 所有权、等待、取消 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/jobs/jobs/tests/ packages/jobs/jobs-local/tests/` | 4 个文件通过；81 项测试通过 | `PASS` — local records 仍是进程内记录。 |
| `P-WORKFLOW` | 有界 Workflow 执行 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/workflow/workflow/tests/` | 2 个文件通过；13 项测试通过 | `PASS` — 不声称具备 journaling/resume。 |
| `P-MODEL` | LLM adapter 和模型设置组合 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/llm/llm/tests/ packages/client/ui-settings-models/tests/` | 21 个文件通过；411 项测试通过 | `PASS`（仅限本地契约）— 没有真实外部模型/API 调用。 |
| `P-FS` | File provider 和 sandbox | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/fs/fs/tests/ packages/fs/fs-local/tests/ packages/fs/fs-sandbox/tests/` | 3 个文件通过、4 个失败；165 项测试通过、16 项失败、1 项跳过 | `BLOCKED` — 16 个失败均为 Windows symlink `EPERM`；跳过项覆盖 POSIX 模式，containment 尚未完全验证。 |
| `P-SHELL` | Shell executor | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/shell/shell/tests/ packages/shell/bash-local/tests/ packages/shell/pwsh-local/tests/` | 3 个文件通过、1 个失败；47 项测试通过、1 项失败、1 项跳过 | `BLOCKED` — 失败为 Windows symlink `EPERM`；跳过项为 POSIX self-signal，local shell 不是 containment。 |
| `P-TERMINAL` | PTY 所有权和 terminal tool | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/terminal/terminal/tests/ packages/terminal/tool-terminal/tests/` | 3 个文件通过、1 个跳过；43 项测试通过、1 项跳过 | `PASS` — 设计中的真实 Loader 用例只在 Linux/macOS 运行。 |
| `P-PRESENTATION` | Diff、deliverables 和工具卡投影 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/ui-deliverables/tests/ packages/core/agent-tool-presentation/tests/` | 3 个文件通过；21 项测试通过 | `PASS`。 |
| `P-WEB` | 仅 search/fetch | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/web/tool-web/tests/` | 4 个文件通过；76 项测试通过 | `PASS`（仅限 search/fetch）— 没有 DOM/browser-control 证据。 |
| `P-INTERACTION` | Permission preset、approval 和 questions | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/interaction/permission-presets/tests/ packages/interaction/user-approval/tests/ packages/interaction/tool-ask-user/tests/` | 6 个文件通过；79 项测试通过 | `PASS` — 不是 DevFrame 最终判定证据。 |
| `P-SUBAGENT-LIVE` | 通过 `ctx.agents` 的原生子 Agent 生命周期 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/subagent/subagent/tests/service.spec.ts packages/subagent/subagent/tests/continuation.spec.ts` | 2 个文件通过；138 项测试通过 | `PASS` — 仅限进程实时生命周期。 |
| `P-SUBAGENT-CATALOG` | 持久 live-preferred 子 Agent 发现和 UI 导航 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/subagent/subagent/tests/list-children.spec.ts packages/host/apiproxy/tests/api-proxy-subagents.spec.ts packages/client/ui-subagent/tests/conversation-ui.client.spec.tsx` | 3 个文件通过；93 项测试通过 | `PASS` — 是发现 catalog，不是 Controller roster/lease/verdict。 |
| `P-CONVERSATION-UI` | 常驻 chat/composer/details shell | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/ui-conversation/tests/chat-view.client.spec.tsx packages/client/ui-conversation/tests/assembly-surfaces.client.spec.tsx` | 2 个文件通过；51 项测试通过 | `PASS`。 |
| `P-INPUT-QUEUE` | Input state machine、pending queue、strict steer | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/ui-conversation/tests/input-machine.client.spec.ts packages/client/ui-conversation/tests/queue-dock.client.spec.tsx packages/client/runtime/tests/queue-store.client.spec.ts` | 3 个文件通过；108 项测试通过 | `PASS` — 是人工 composer queue，不是持久 Agent mailbox。 |
| `P-SESSION-SEARCH` | 通过侧栏 UI 的 Host 授权搜索 RPC | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/host/apiproxy/tests/api-proxy-search.spec.ts packages/client/runtime/tests/manager.client.spec.ts packages/client/ui-workspace/tests/workspace-browser.client.spec.tsx` | 3 个文件通过；124 项测试通过 | `PASS` — 搜索不产生 authority。 |
| `P-CONVERSATION-NODE` | 独立注册的 event-to-view Definition | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/runtime/tests/conversation-assembler.client.spec.ts packages/client/ui-conversation/tests/conversation-node-definitions.client.spec.ts` | 2 个文件通过；44 项测试通过 | `PASS`。 |
| `P-LSP` | 四操作语义导航 seam、stdio provider、模型工具 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/lsp/lsp/tests/ packages/lsp/lsp-stdio/tests/ packages/lsp/tool-lsp/tests/` | 11 个文件通过、1 个失败；210 项测试通过、3 项失败、2 项跳过 | `BLOCKED` — 3 个失败均为 Windows symlink `EPERM`；两个跳过项为非 Windows 条件。 |
| `P-COMPOSITION` | Plugin/Profile/Bundle/client runtime | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/boot/app-boot/tests/ packages/bundle/web-app/tests/ packages/client/runtime/tests/` | 32 个文件通过；462 项测试通过 | `PASS`（固定 HEAD）— 当前 candidate 另报 33 个文件/470 项测试，不能作为固定 commit 证据。 |
| `P-PERSISTENCE` | Session persistence 和 recovery | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/session/session-persistence/tests/ packages/session/session-persistence-jsonl/tests/ packages/session/session-persistence-sqlite/tests/` | 7 个文件通过、1 个失败；475 项测试通过、1 项失败 | `BLOCKED` — SQLite alias-symlink 用例被 Windows `EPERM` 阻断；alias recovery 尚未完全验证。 |
| `P-EVENT-CATALOG` | 声明事件词汇、生成 persistence catalog、known-event 集合 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/core/session/tests/gen-persistence-catalog.spec.ts` 然后执行 `pnpm run verify-persistence-catalog` | 1 个文件、25 项测试通过；两个生成物均报告为最新 | `PASS`。 |
| `P-TRUST` | 浏览器请求信任和 loopback 防护 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/connection/tests/` | 10 个文件通过；106 项测试通过 | `PASS` — request trust 不是 Host writer ownership。 |
| `P-READINESS` | Connection、Web startup 与可用 provider onboarding 片段 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm exec vitest run packages/client/connection/tests/ packages/client/ui-settings-models/tests/ packages/bundle/web-app/tests/startup.spec.ts` | 21 个文件通过；328 项测试通过 | `PASS`（仅限本地片段）— 没有真实外部模型/provider 调用，也没有统一 DevFrame readiness。 |
| `P-LICENSE` | Package 许可证清单 | `47f943859bef60e4160492346772ded9b24f765a` | `pnpm run verify-dsh-package-licenses` | 固定 HEAD 检查 222 个 DSH package，全部声明 MIT | `PASS`（固定 HEAD）— 当前 candidate 另报 225 个 MIT package，不能作为固定 commit 证据。 |

## Core Concepts

- Workspace 是 DSH 持久项目注册表和规范路径所有者；DevFrame 把 Project Controller 绑定到稳定 Workspace ID，绝不绑定裸路径。
- Session 是持久事件日志和身份边界；DevFrame 必须使用精确 DSH Session ID 和 `SessionStore.flush` 屏障。
- Agent 是绑定到 Session 的实时执行者；`Agent.id === Agent.session.id` 是 DSH 不变量，不是第二个 DevFrame 身份。
- Goal、Job、Workflow 是可复用的原生执行原语，但目前作用域是进程或 Session，任何一个都不是最终控制器裁决。
- Model 和 provider 设置仍由 DSH 所有；DevFrame 只提供路由和策略元数据，不新建模型数据库或 provider 实现。
- File、Shell、Terminal、Diff、web search、web fetch 都是原生工具，但隔离和证据属性不同；`web_fetch` 不是 DOM 浏览器。
- Global Controller、Project Controller、Control Roster、Task Board、Evidence Store、Review、MemoryGateway、Paper Domain Pack 和 Host MCP bridge 是必须叠加在这些 seam 上的 DevFrame 能力。

## Core Data Models

| Object | Required identity or fields | Authority and persistence rule |
|---|---|---|
| Global Controller | `sessionId = devframe-global:<profileId>`、`profileId`、角色 `global`、schema version、规范 cwd | DSH Session 日志加 Host readiness；不带项目工具和 Project Verdict。 |
| Project Controller | `sessionId = devframe-controller:<workspaceId>`、`workspaceId`、角色 `project`、规范 Workspace cwd | DSH Workspace 和 Session 日志；每个 Workspace 一个 Project Controller。 |
| Run | `runId`、`agentSessionId`、`roleAssignmentId`、`taskId` | 只有 Controller 权威和策略门存在后才能创建。 |
| Message Envelope | `messageId`、`sessionId`、`runId`、sender、recipient、kind、payload reference、attempt、timestamp | 至少一次投递并幂等 claim；原始提示和凭据留在 API 边界之后。 |
| Evidence | `evidenceRevision`、source event IDs、diff 或 test references、reviewer decision | 证据只追加，不能被 UI 状态标签替换。 |
| Readiness | profile identity、Host lease、persistence、provider、authority、required tools、MCP 和 memory 状态 | 是显式检查的合取；证据缺失记为 `blocked`，不是 `ready`。 |

## Capability Matrix

矩阵用 `HEAD` 表示固定上游提交，用 `candidate` 表示只存在于脏工作树的代码。“Reuse”表示组合公共 seam，不表示 DevFrame 行为已经存在。

### Reuse DSH directly

| Capability | Exact HEAD source seam | Current maturity and real probe | Reuse decision | Gap | Minimum patch |
|---|---|---|---|---|---|
| Workspace and directory selection | [`WorkspaceRegistry`](../../../../packages/workspace/workspace/src/index.ts) 和 [`Workspace`](../../../../packages/workspace/workspace/src/types.ts) | 注册表 seam 成熟；`P-WORKSPACE`。 | 复用为唯一项目注册表。 | 没有 Controller 绑定或项目 readiness 记录。 | 增加薄的 `workspaceId -> Project Controller Session ID` 适配器，并校验规范 cwd。 |
| Session identity and event log | [`SessionStore`](../../../../packages/core/session/src/index.ts) 和 [`SessionEventMap`](../../../../packages/core/session/src/types.ts) | 精确 ID 和事件 seam 成熟；`P-SESSION`。 | 复用精确 ID 和事件词汇。 | 没有 DevFrame identity event 或角色校验。 | 合并声明 `controller/identity`，校验首事件，并在返回前 flush。 |
| Agent 实时注册表（`ctx.agents`） | [`AgentRegistry`](../../../../packages/core/agent/src/index.ts) | Agent/Session 进程内实时注册表成熟；`P-AGENT`。它不是持久 child catalog。 | 复用 Agent/Session 相等性和冲突检查。 | 没有 role assignment、roster、重启持久化或控制器持久映射。 | 把一个实时 Agent 绑定到每个已校验 Controller Session，角色状态放进控制器事件。 |
| Goal and Plan | [`GoalService`](../../../../packages/goal/goal/src/index.ts)、[`goal-round-driver`](../../../../packages/goal/goal-round-driver/src/index.ts) 和 [`plan-mode`](../../../../packages/plan/plan-mode/src/index.ts) | Session 内规划和有界续接成熟；`P-GOAL-PLAN`。 | 复用为投影和有界续接。 | Goal/Plan 不是 Control Board 或最终验收权威。 | 在 Goal 之上加 TaskSpec 和策略引用，不把 Goal 完成当作 Project Verdict。 |
| Todo | [`tool-todo`](../../../../packages/todo/tool-todo/src/index.ts) 和 [`TodoPanel`](../../../../packages/client/ui-conversation/src/client/skeleton/TodoPanel.tsx) | 单 Agent 全量替换的 `todo/write` 快照和 standing-plan 投影成熟；`P-TODO`。 | 复用为单个 Agent 的本地工作清单。 | 没有稳定 item ID、部分修改、共享 roster scope、依赖图或 Controller verdict。 | Todo 保持本地；项目共享工作进入只追加 TaskSpec/Task Board 事件。 |
| Jobs | [`JobRegistry`](../../../../packages/jobs/jobs/src/index.ts) 和 [`jobs-local`](../../../../packages/jobs/jobs-local/src/index.ts) | 所有者范围取消和等待成熟；`P-JOBS`；本地记录重启即消失。 | 复用为有界 worker 执行。 | 没有持久 reservation、retry ledger 或跨 Session claim。 | 开始 Job 前增加控制器事件 reservation 和幂等 claim。 |
| Workflow | [`WorkflowEngine`](../../../../packages/workflow/workflow/src/index.ts) | 有界执行成熟；`P-WORKFLOW`；README 明确没有 journaling 或 resume。 | 复用为子流程步骤。 | 没有持久嵌套流程状态或控制器策略。 | 每个 workflow 包上 TaskSpec、PolicyDecision 和 Evidence 引用。 |
| Model and provider | [`LlmRuntime`](../../../../packages/llm/llm/src/index.ts)、[`LlmAdapter`](../../../../packages/llm/llm/src/types.ts) 和 [`ui-settings-models`](../../../../packages/client/ui-settings-models/src/index.ts) | adapter seam 成熟；`P-MODEL`；没有调用真实外部 API。 | 复用 DSH provider/model 设置。 | 没有 ccswitch 只读组合或按角色路由契约。 | 增加只读 provider inventory 适配器，并把模型选择写入 Run 元数据。 |
| File system | [`FileSystem`](../../../../packages/fs/fs/src/index.ts)、[`fs-local`](../../../../packages/fs/fs-local/src/index.ts) 和 [`fs-sandbox`](../../../../packages/fs/fs-sandbox/src/index.ts) | 工具 seam 成熟；`P-FS`；local README 警告 cwd 不是 containment。 | 只在策略后复用沙箱项目工具。 | Global 需要空项目工具集；Project 需要明确 containment。 | 将工具能力绑定到角色和 PolicyDecision；沙箱不可用时失败关闭。 |
| Shell | [`ShellExecutor`](../../../../packages/shell/shell/src/index.ts)、[`bash-local`](../../../../packages/shell/bash-local/src/index.ts) 和 [`pwsh-local`](../../../../packages/shell/pwsh-local/src/index.ts) | executor seam 成熟；`P-SHELL`；local shell 不隔离。 | 只能通过项目策略和明确批准复用。 | Global 不得继承 shell；没有 DevFrame 命令审计或批准状态。 | 增加角色工具清单、命令 PolicyDecision 和执行前证据捕获。 |
| Terminal | [`TerminalSessionService`](../../../../packages/terminal/terminal/src/index.ts) 和 [`tool-terminal`](../../../../packages/terminal/tool-terminal/src/index.ts) | 所有者范围 PTY seam 成熟；`P-TERMINAL`；重启后 PTY 进程内状态不恢复。 | 复用作交互式项目执行，不承担控制器身份。 | 没有持久终端所有权或回放证据。 | 从 Run 引用终端句柄，并在 Controller Session 持久化生命周期事件。 |
| Diff, deliverables, and tool cards | [`DiffBlock`](../../../../packages/client/ui-primitives/src/DiffBlock.tsx)、[`ui-deliverables`](../../../../packages/client/ui-deliverables/src/index.ts) 和 [`agent-tool-presentation`](../../../../packages/core/agent-tool-presentation/src/index.ts) | 原生投影 seam 成熟；`P-PRESENTATION`；没有 DevFrame verdict 语义。 | 复用原生展示和 diff 渲染。 | 没有 review decision、evidence revision 或 controlled completion 卡片。 | 增加引用原生 diff 和 deliverable ID 的有界 Controller evidence card。 |
| `web_search` and `web_fetch` | [`web_search`](../../../../packages/web/tool-web/src/search.ts)、[`web_fetch`](../../../../packages/web/tool-web/src/fetch.ts) 和 [`tool-web`](../../../../packages/web/tool-web/src/index.ts) | provider 无关研究 seam 成熟；`P-WEB`；限制和超时已有文档。 | 复用 search/fetch 作为研究工具。 | 不提供 DOM、点击、浏览器 Session 或视觉证据。 | 浏览器工作必须经过独立 Recon Receipt 和独立 Browser Provider。 |
| Permission presets and human questions | [`permission-presets`](../../../../packages/interaction/permission-presets/src/index.ts)、[`user-approval`](../../../../packages/interaction/user-approval/src/index.ts) 和 [`tool-ask-user`](../../../../packages/interaction/tool-ask-user/src/index.ts) | 批准和提问原语成熟；`P-INTERACTION`；没有 DevFrame governance decision。 | 复用为人类门和一次性批准。 | 没有与 Evidence 绑定的 PolicyDecision schema 或最终人工门。 | 增加 Controller policy record，并把批准结果映射到 Task 和 Run 事件。 |
| 原生 child 生命周期 | [`SubagentRuntime`](../../../../packages/subagent/subagent/src/index.ts)、[`tool-subagent`](../../../../packages/subagent/tool-subagent/src/index.ts) 和 [`tool-subagent-control`](../../../../packages/subagent/tool-subagent-control/src/index.ts) | 基于 `ctx.agents` 的进程内生命周期和 continuation seam 成熟；`P-SUBAGENT-LIVE`。 | 复用 spawn、continuation、interrupt 和 settlement。 | 进程内 Activation 所有权不是持久 Controller roster 或 mailbox。 | 不 fork 原生 lifecycle，只持久化 DevFrame role assignment 和 settlement 事件。 |
| 持久 Subagent catalog | [`SubagentRuntime.listChildren`](../../../../packages/subagent/subagent/src/index.ts)、[`listChildren`](../../../../packages/subagent/subagent/src/list-children.ts)、`subagent` 投影和 [`SubagentCatalogAction`](../../../../packages/client/ui-subagent/src/client/SubagentCatalogAction.tsx) | live Session store 与可选 persistence 的 live-preferred 合并、projection-cache/权威 re-fold 和懒加载 UI 导航成熟；`P-SUBAGENT-CATALOG`。 | 复用为 child 发现目录。 | Catalog 状态不是 DevFrame role、lease、task owner、outcome verdict 或跨 Session mailbox。 | 用 Session ID 把 catalog 与只追加 Controller Roster 事件关联；绝不从 label 或 activity 推断权威。 |
| Conversation UI | [`ui-conversation`](../../../../packages/client/ui-conversation/src/client/apply.ts)、[`ChatView`](../../../../packages/client/ui-conversation/src/client/chat/ChatView.tsx) 和 [`ConversationRoot`](../../../../packages/client/ui-conversation/src/client/skeleton/ConversationRoot.tsx) | 常驻 chat/composer/details 表面成熟；`P-CONVERSATION-UI`。 | 复用为唯一控制器会话外壳。 | DevFrame control identity card 不属于聊天记录，且尚无 Control Board view。 | 只贡献有界原生 slot/view，并保持 Acceptance Delta。 |
| Input queue and composer state | [`InputHub`](../../../../packages/client/ui-conversation/src/client/input/hub.ts)、[`QueueDock`](../../../../packages/client/ui-conversation/src/client/queue/QueueDock.tsx) 和 [`queue-mirror`](../../../../packages/client/runtime/src/client/sessions/queue-mirror.ts) | 逐 Session draft、queue 和 strict-steer UI/runtime seam 成熟；`P-INPUT-QUEUE`。 | 复用为用户输入投递。 | 它不是 Agent-to-Agent 持久 mailbox 或 Controller task queue。 | Human composer queue 与 Message Envelope/Task Board 事件严格分开。 |
| Session search | Host [`session.search`](../../../../packages/host/apiproxy/src/api-proxy.ts)、[`SessionRuntime.search`](../../../../packages/client/runtime/src/client/sessions/service.ts) 和 [`WorkspaceBrowser`](../../../../packages/client/ui-workspace/src/client/WorkspaceBrowser.tsx) | 授权、有界、可取消搜索及侧栏展示成熟；`P-SESSION-SEARCH`。 | 复用为查找 Session transcript。 | 搜索结果不授予 Controller role 或 authority。 | 用 Host metadata 过滤/展示并打开精确 ID；绝不把文本匹配提升为 Controller。 |
| Conversation Node extension | [`ConversationNodeDefinition`](../../../../packages/client/runtime/src/client/contract/conversation.ts)、[`ConversationEventRegistry`](../../../../packages/client/runtime/src/client/conversation/event-registry.ts) 和原生 [`registerConversationNodes`](../../../../packages/client/ui-conversation/src/client/conversation-nodes/register.ts) | 独立注册的 event-to-view seam 成熟；`P-CONVERSATION-NODE`。 | 复用于 DevFrame 事件投影和渲染。 | 固定 HEAD 没有 DevFrame Controller Node Definition。 | 只为持久 DevFrame 事件增加独立 Definition/renderer；不加中央 switch，也不 fork Session fold。 |
| LSP semantic navigation | [`Lsp`](../../../../packages/lsp/lsp/src/index.ts)、[`lsp-stdio`](../../../../packages/lsp/lsp-stdio/src/index.ts) 和 [`tool-lsp`](../../../../packages/lsp/tool-lsp/src/index.ts) | definition/reference/implementation/hover 四操作 seam 成熟；`P-LSP`。 | 策略通过后复用为项目只读代码导航。 | 没有 diagnostics、rename、code action、formatting、Controller evidence 绑定或 Global grant。 | Project 角色可经策略获得只读 LSP；Global 不获得，修改类操作继续作为未来独立工具。 |
| Plugin, Profile, Bundle, and UI extension | [`app-boot/profile`](../../../../packages/boot/app-boot/src/profile.ts)、[`bundle/web-app`](../../../../packages/bundle/web-app/src/index.ts)、[`ui-settings-plugins`](../../../../packages/client/ui-settings-plugins/src/index.ts) 和 [`client/runtime`](../../../../packages/client/runtime/src/index.ts) | 组合面成熟；`P-COMPOSITION`；固定 HEAD 没有 DevFrame bundle。 | 复用原生 loader、profile、bundle、plugin 和布局组合。 | HEAD 没有规范 DevFrame profile 或单一 Global 入口。 | 只有身份/readiness 测试通过后，才增加一层薄 DevFrame Bundle 和 Profile 入口。 |
| Persistence and recovery | [`SessionPersistence`](../../../../packages/session/session-persistence/src/index.ts)、[`session-persistence-jsonl`](../../../../packages/session/session-persistence-jsonl/src/index.ts) 和 [`session-persistence-sqlite`](../../../../packages/session/session-persistence-sqlite/src/index.ts) | JSONL/SQLite seam 成熟；`P-PERSISTENCE`；JSON storage 明确没有跨进程写锁。 | 复用 DSH Session persistence 作为唯一持久存储。 | 没有 DevFrame 迁移、身份索引或多进程 writer lease。 | 增加 identity event 迁移和 Host writer fence，绝不创建第二注册表数据库。 |
| Known-event and persistence catalog tracking | 生成的 [`KNOWN_SESSION_EVENT_TYPES`](../../../../packages/core/session/src/known-event-types.ts)、[`persistence-catalog`](../../../../docs/persistence-catalog.md) 及其 generator test | 失败关闭的词汇/catalog 门成熟；`P-EVENT-CATALOG`。 | 复用为唯一持久事件兼容性清单。 | 新 DevFrame 事件在刷新生成物和双语 catalog 前属于未知事件。 | 每个 DevFrame `SessionEventMap` key 都必须重生成 catalog/known set，通过 `verify-persistence-catalog`，并有 `P-CONVERSATION-NODE` 投影决策。 |
| License | [`package.json`](../../../../package.json) 和 [`verify-dsh-package-licenses`](../../../../scripts/verify-dsh-package-licenses.ts) | 声明 MIT；`P-LICENSE` 报告全部 `225` 个 DSH package 已检查。 | 复用既有 MIT gate，并保留 vendored notices。 | 新 DevFrame 依赖和 Browser Provider 许可证尚未审阅。 | 每个新增包接受前运行许可证清单。 |
| Host request trust fence | [`api-request-trust`](../../../../packages/client/connection/src/api-request-trust.ts) 和 [`loopback-hostname`](../../../../packages/client/connection/src/loopback-hostname.ts) | 浏览器请求信任和 DNS rebinding 防护成熟；`P-TRUST`。 | 复用请求来源安全。 | 这不是单一 DSH writer 或 Profile Host lease。 | 保留 request trust，另增 Session 写入专用 Host ownership lease。 |
| Native readiness fragments | [`client/connection`](../../../../packages/client/connection/src/index.ts)、[`ui-settings-models`](../../../../packages/client/ui-settings-models/src/index.ts) 和 [`web-app/startup`](../../../../packages/bundle/web-app/src/startup.ts) | Connection、startup 和可用 provider onboarding 片段已由 `P-READINESS` 分别覆盖；HEAD 仍没有统一 DevFrame readiness 投影。 | 复用这些检查作为输入。 | 没有 profile、Host、persistence、provider、policy、MCP、memory 的合取。 | 增加只读 `DevFrameReadiness` 投影，并输出明确 `blocked` 原因。 |

### Add above DSH seams

| Capability | Exact HEAD seam or absence | Current maturity and real probe | Reuse decision | Gap | Minimum patch |
|---|---|---|---|---|---|
| Global and Project Controller identity | 组合 [`SessionStore`](../../../../packages/core/session/src/index.ts) 与 [`WorkspaceRegistry`](../../../../packages/workspace/workspace/src/index.ts)；固定 HEAD 没有 DevFrame identity symbol。 | HEAD 缺失；tree probe 没找到 DevFrame package。 | 增加薄身份适配器，不加第二存储。 | 没有确定性 ID、首事件 schema、角色绑定或恢复契约。 | 实现精确 Global/Project ID，校验唯一首个 `controller/identity`，返回前 flush。 |
| Single Global entry and ordinary-tree contract | 组合 [`app-boot/profile`](../../../../packages/boot/app-boot/src/profile.ts) 与原生 client runtime；固定 HEAD 没有 Global entry。 | HEAD 缺失；脏候选不是上游证据。 | 只扩展原生 tree 和 menu。 | 没有 Host 发布的精确 ID、按角色去重和聊天身份卡规则。 | 增加一个 Host readiness 入口、服务端角色元数据、精确 ID 复制和近似前缀负例。 |
| Cross-Agent and cross-Session communication | 使用 [`SessionStore`](../../../../packages/core/session/src/index.ts) 事件和 [`subagent`](../../../../packages/subagent/subagent/src/index.ts)；没有 DevFrame mailbox 或 envelope。 | HEAD 缺失；没有真实跨 Session 探针。 | 在原生事件之上增加 Message Envelope 和 Mailbox。 | 没有 recipient、幂等 claim、重试或投递证据。 | 持久化 envelope 引用，实现至少一次 claim，并拒绝未知 Session recipient。 |
| Control Roster and Task Board | 从实时 [`AgentRegistry`](../../../../packages/core/agent/src/index.ts)、持久 [`SubagentRuntime.listChildren`](../../../../packages/subagent/subagent/src/index.ts)、[`GoalService`](../../../../packages/goal/goal/src/index.ts) 和 [`jobs`](../../../../packages/jobs/jobs/src/index.ts) 投影；没有 Controller Roster/Board symbol。 | HEAD 缺失；`P-AGENT` 和 `P-SUBAGENT-CATALOG` 证明的是不同生命周期来源，任何一个都不是 board。 | 用精确 Session ID 连接成新投影；不 fork Agent、Subagent catalog 或 Goal。 | 没有 DevFrame role assignment、dependency、owner、lease、task 状态机或持久 verdict。 | 增加只追加 Roster/TaskSpec 事件和派生 Task Board；实时状态只当作 liveness。 |
| Automatic dispatch and revision loop | 原生 [`goal-round-driver`](../../../../packages/goal/goal-round-driver/src/index.ts) 只是同 Session 续接；没有受治理 Controller loop。 | HEAD 缺失；round-driver 通过不等于 governance 证明。 | 只在 gated RunLoop 内复用有界续接。 | 没有任务分解、策略门、context packet、重试预算或 reviewer 触发。 | 增加 ControllerAgent proposal、PolicyDecision、RunLoop 和明确停止条件。 |
| Controlled completion and independent review | 复用 [`ui-deliverables`](../../../../packages/client/ui-deliverables/src/index.ts) 和原生 diff 卡；没有 FinalVerdict 或 EvidenceStore。 | HEAD 缺失；没有独立 review 探针。 | 在原生 deliverable 之上增加 review record。 | 没有 evidence revision、审阅独立性或人工验收门。 | 必须有 EvidenceStore、独立 Reviewer 和 HumanGate 才能 Project Verdict。 |
| Comparable evaluation and feedback | 复用 [`SessionStore`](../../../../packages/core/session/src/index.ts) 的原生工具/Session 事件；没有 Scorecard 或 Feedback symbol。 | HEAD 缺失；没有评估数据集或 score 探针。 | 增加小型 Scorecard 投影，不加第二 analytics DB。 | 没有可重复 rubric、baseline 或 feedback-to-policy loop。 | 定义 task-level rubric，并把 score/feedback 事件追加到 Controller Session。 |
| Obsidian and cross-Session MemoryGateway | 主仓库契约位于 `D:/dev-frame-system/packages/control-plane/control_plane/obsidian_memory.py`、`memory_stdio.py` 和 `packages/devframe-memory/README.md`；DSH HEAD 没有 Obsidian 或 DevFrame memory package。 | DSH HEAD 缺失；主仓库 create-only 与人工发布探针位于 `packages/control-plane/tests/test_obsidian_project_plan.py` 和 `test_memory_stdio.py`。 | 通过无状态 adapter 复用隐私、项目绑定、create-only 与人工发布契约；不迁移 Python store，也不创建第二 memory DB。 | DSH 没有 checkpoint/lesson adapter 或规范 Session 投影。 | 通过项目隔离且需明确人工发布批准的无状态 adapter 接入既有 gateway 契约。 |
| Paper Domain Pack | DSH HEAD 没有 `packages/paper` 或 paper workflow 源码；复用同一个 Controller 和 evidence seam。 | HEAD 缺失；没有论文探针。 | 增加 domain pack，不增加独立 agent runtime。 | 没有论文项目模型、source ledger、claims/evidence review 或导出契约。 | 实现 paper TaskSpec、引文/来源证据、审阅清单和有界导出。 |
| External-brain MCP Server、tunnel 和 stdio bridge | DSH HEAD 只有 [`mcp-client`](../../../../packages/mcp/mcp-client/src/index.ts)。主仓库已有 `D:/dev-frame-system/packages/control-plane/control_plane/mcp_server.py` 的 Streamable HTTP 契约和 `memory_stdio.py` 的项目绑定 stdio 契约；OpenAI 官方 Secure MCP Tunnel 路径在上游可用。 | DSH 实现缺失；主仓库探针是 `packages/control-plane/tests/test_mcp_server.py` 与 `test_memory_stdio.py`，但没有 DevFrame DSH MCP Server、tunnel 配置、账户权限证明或真实 ChatGPT canary。 | 复用有界响应、认证、项目绑定、consent 和 stdio framing 契约，并把它们重宿主为 canonical DSH Host 的无状态 adapter；不把 Python 进程或 store 当作第二权威，也不把官方 tunnel 候选当作证明。 | 没有规范 DSH Host server、outbound tunnel binding、无状态转发或经过身份验证的 ChatGPT canary。 | 增加一个 Host 所有的 server 和无状态 bridge，配置文档要求的 tunnel 前提，再执行真实 developer-mode ChatGPT canary，同时让 Session 权威留在 DSH。 |
| ccswitch read-only composition | 没有精确 HEAD symbol；`git grep -n -i ccswitch 47f943859bef60e4160492346772ded9b24f765a -- .` 没有匹配。 | HEAD 缺失；没有 provider switch 探针。 | 只有记录来源和许可证后才增加只读 adapter。 | 没有 provider inventory、fallback 策略或 model identity 记录。 | 把 provider/model 选择作为不可变 Run 元数据，secret 不进入事件。 |
| Browser Provider and controlled interaction | [`web_fetch`](../../../../packages/web/tool-web/src/fetch.ts) 和 [`web_search`](../../../../packages/web/tool-web/src/search.ts) 是研究工具；固定 HEAD 没有 DOM/browser provider。 | 缺失并明确 Recon-blocked；Web 测试通过不等于浏览器控制。 | 实现前先做独立 Browser Provider Recon。 | 没有 browser Session、导航策略、视觉证据或安全动作门。 | 增加成熟 provider 及 Task、Policy、Evidence、HumanGate 契约，绝不把 fetch 改名 browser。 |
| Single Host writer and Profile fence | [`api-request-trust`](../../../../packages/client/connection/src/api-request-trust.ts) 保护请求；`storage-json` 说明没有跨进程写锁；固定 HEAD 没有 DSH writer lease。 | HEAD 缺失；request trust 不是 writer ownership。 | 增加一个规范 DSH Host lease，不加第二数据库。 | desktop web/devframe 启动路由可能分裂 profile 或 writer 身份。 | 统一 launcher/profile，获得持久 Host fence，重复 writer 时失败关闭。 |
| Unified DevFrame readiness | 组合 [`client/connection`](../../../../packages/client/connection/src/index.ts)、[`SessionPersistence`](../../../../packages/session/session-persistence/src/index.ts) 和 provider settings；固定 HEAD 没有 DevFrame readiness schema。 | HEAD 缺失；当前候选 readiness 不是 HEAD 证据。 | 在现有检查上增加只读投影。 | 没有 identity、Host、persistence、model、policy、MCP、memory、browser 的稳定状态模型。 | 定义 check ID 与 `ready`/`blocked` 状态，只有 Slice 0 检查全通过才发布精确 Global ID。 |

## Current P0 findings in the working-tree candidate

以下都是当前脏工作树发现，不是固定提交能力。它们说明第一条实现切片必须先关闭权威漏洞并在项目写入前失败关闭。

| P0 finding | Candidate source and observation | Impact | Minimum patch | Review gate |
|---|---|---|---|---|
| Launcher 双入口验收仍未关闭 | 候选 [`scripts/launch-devframe.mjs`](../../../../scripts/launch-devframe.mjs) 现在包含正式 `--profile devframe` 启动修复，而 [`scripts/devframe-web.patch.yml`](../../../../scripts/devframe-web.patch.yml) 仍是可调用兼容入口。这是修复候选，不是固定 HEAD 已接受能力。 | 规范入口已经明确，但正式入口与兼容入口的等价性尚未证明；它们仍可能在 profile、Host ownership、readiness 或精确 Global ID 上分裂。 | 保持 `--profile devframe` 为规范入口，并证明两入口解析为同一身份；否则在后续经人工批准的切片中让兼容入口失败关闭或退役。 | 两入口真实 Loader/Profile 重启探针必须发布同一个精确 Global Session ID 且只保留一个 Host writer；产品和技术审阅仍待完成。 |
| Client prefix guessing | 候选 [`tree.ts`](../../../../packages/client/ui-workspace/src/client/tree.ts) 用 `startsWith('devframe-global:')` 决定可见性；候选 [`GlobalControllerAction.tsx`](../../../../packages/client/ui-devframe-control-session/src/client/GlobalControllerAction.tsx) 虽有精确 readiness ID 路径，但 tree 仍用前缀推断权威。 | 客户端可以在没有 Host 角色元数据时隐藏或分类近似前缀或伪造 Session。 | 所有投影改用 Host 发布的精确角色和入口元数据，并添加畸形/近似前缀负例。 | 对普通 tree、Global 入口、聊天和菜单契约做产品审阅，并执行真实浏览器探针。 |
| Task tracer bypasses 1A/1C | 候选 [`control-session/src/index.ts`](../../../../packages/devframe/control-session/src/index.ts) 暴露 `dispatchProjectGoal` 并直接调用 Goal/Agent Loop；路径上没有已证明的 Authority、PolicyDecision、ContextPacket、Evidence、Reviewer 或 FinalVerdict 门。 | 在 Controller 和治理切片存在前，项目写入可能直接运行。 | 在 Slice 1A/1C 门存在前，项目写派发硬性失败关闭，或只允许身份/只读 dry-run。 | 负向生产路径派发探针必须证明不会执行项目工具或模型。 |

## Integration Risk Table

| Risk | Why it matters | Control |
|---|---|---|
| Authority split | 第二注册表、profile 或 Session store 可能与 DSH 恢复结果不一致。 | DSH Session 日志和 Workspace registry 保持唯一权威；adapter 只能是投影。 |
| Identity spoofing | 客户端前缀判断或猜测 ID 会暴露错误控制器。 | Host 发布精确 ID 和角色元数据；服务端校验全部 identity event。 |
| Premature writes | 正向 tracer 可能绕过 Authority、Policy、Evidence 和 Review。 | Slice 1A/1C 治理门实现并在真实路径测试前，项目写入必须失败关闭。 |
| Browser overclaim | Search/fetch 可能被误认为受控 DOM 交互。 | 浏览器 Provider 单独做 Recon Receipt，并明确 Task、Policy、Evidence 和 HumanGate。 |
| Restart and multi-process drift | Job 和 PTY 是进程内的，JSON storage 没有跨进程锁，第二启动路由还可能竞争。 | Host writer lease、flush 屏障、重启探针和唯一 canonical launcher。 |
| Provider and secret leakage | provider 切换和 MCP adapter 可能意外持久化凭据或原始提示。 | 只记录 provider/model ID；payload 留在 API 边界后，并执行 secret/license 检查。 |

## Reuse Candidate List

| Candidate | Source | Decision |
|---|---|---|
| DSH native workbench | [`bundle/web-app`](../../../../packages/bundle/web-app)、[`client/runtime`](../../../../packages/client/runtime) 和 Profile 组合 | 作为唯一产品外壳复用，只增加薄原生入口。 |
| DSH native Agent Loop | [`agent-loop`](../../../../packages/core/agent-loop/src/index.ts) | 作为 Controller 策略后的执行器保留，不 fork 或重写私有 restore helper。 |
| Main DevFrame memory contract | `D:/dev-frame-system/packages/control-plane/control_plane/obsidian_memory.py`、`memory_stdio.py` 和 `packages/devframe-memory/README.md` | 通过无状态 adapter 复用项目绑定、create-only、隐私与人工发布契约；不把 Python store 用作 DSH 权威。 |
| Main DevFrame MCP contracts | `D:/dev-frame-system/packages/control-plane/control_plane/mcp_server.py`、`memory_stdio.py` 及其聚焦测试 | 复用认证、consent、有界投影、项目绑定与 stdio framing；在 canonical DSH Host 下重宿主，而不是运行第二个 control-plane 权威。 |
| Browser capability | DSH `web_search` 和 `web_fetch` seam | 只复用 search/fetch 研究工具；Browser Provider 仍 Recon-blocked。 |
| Dirty-tree DevFrame candidates | [`packages/devframe`](../../../../packages/devframe) 和候选 UI/scripts | 只作为实现线索；每个 seam 都要和 HEAD 对齐，绝不作为验收证据。 |

## Build-vs-Buy Decision

- 复用 DSH 的 Workspace、Session、Agent、Goal、Job、Workflow、model settings、tools、persistence、permission prompts、diff、deliverables、Profile、Bundle、Plugin 和 UI 组合。
- 因为 DSH HEAD 没有精确 Global/Project Controller seam，所以只构建小型 DevFrame identity 和 readiness adapter。
- 通过无状态 adapter 复用主仓库的 Obsidian working-plan/checkpoint/lesson 契约，不创建第二个 memory authority。
- 先 Recon 再复用成熟 Browser Provider；不手写浏览器 UI，也不把 `web_fetch` 改成浏览器。
- 在规范 DSH Host 增加 external-brain MCP Server 和无状态 stdio bridge；不增加第二个 Session writer。

## Recommended Next Slice

1. 以固定提交冻结 Capability Ledger，并独立审阅三个 P0 发现。
2. 关闭 launcher/profile 歧义，增加单一 Host writer fence，以及重启和重复 writer 探针。
3. 实现 Slice 0 identity/readiness：精确 Global/Project ID、首 identity event、flush 屏障和 blocked 原因。
4. 增加单一 Global 入口、按 Host 角色元数据抑制普通 tree、聊天契约和精确 Session-ID 复制菜单。
5. 增加只读 Project Controller 选择和 Workspace 绑定；继续禁用项目写入。
6. 在任何 Goal 或 Agent Loop 项目 tracer 前实现 Slice 1A authority 对象和 Slice 1C policy/context/evidence 门。
7. 以 DSH 事件的只追加投影增加 Message Envelope、Control Roster、Task Board、有界 RunLoop、独立 Reviewer、Scorecard 和 HumanGate。
8. 只有各自完成明确 recon 和许可证门后，才增加 Paper Domain Pack、MemoryGateway、MCP server/bridge、ccswitch 只读 adapter 和 Browser Provider。

## Alternatives considered

**用随机 DSH chat 充当 controller。** 拒绝，因为 fresh start、重启或不同启动路径都可能改变身份和路由。

**新建 DevFrame SQLite registry 或 JSON sidecar。** 拒绝，因为它会成为与 DSH Session log 和 persistence recovery 竞争的第二权威。

**重写 Agent Loop 或复制其私有 restore helper。** 拒绝，因为 loop 是高风险执行核心；只组合公共服务并增加窄身份 seam。

**另做 DevFrame dashboard。** 拒绝，因为 DSH 已经拥有 workbench、chat、model、tool、diff、layout 和 settings 表面。

**把当前候选代码或截图当作证明。** 拒绝，因为只有固定提交源码和真实探针能进入账本；候选代码在对齐前只能作为线索。

## Acceptance criteria

1. 从空临时 home 经真实 DSH Profile/Bundle 启动原生 client，出现一个 DevFrame Global 入口，不需要第二条服务命令。
2. 从 cwd A 启动、退出，再从 cwd B 重启后恢复同一个 Global Session ID；重新打开 Workspace 后恢复同一个 Project Controller ID。
3. 每个控制器 Session 恰好有一个合法首个 `controller/identity` 事件，创建返回前已经 await persistence flush。
4. 单 Host 并发打开只发布一个实时 Agent 和一个 Session log；损坏或不匹配身份在不替换权威的情况下失败关闭。
5. 普通 tree 没有重复 Global 行，聊天没有身份卡，菜单复制 Host 发布的精确 Session ID。
6. Global 有效工具集合不包含项目 File、Shell、Terminal 或 Browser 能力。
7. Authority、PolicyDecision、ContextPacket、Evidence、Reviewer 和 HumanGate 存在前，项目写派发必须被阻断。
8. 跨 Agent、跨 Session 消息有稳定 ID、至少一次 claim、幂等性和持久证据引用。
9. 在干净 checkout 上，逐能力 focused probe、`SessionEventMap`/known-event/persistence-catalog 生成、对应 Conversation Node 投影决策、package invariants、typecheck、真实 Loader/Profile composition、重启、重复 writer 和身份负例探针全部通过。
10. 许可证、secret、隐私、Browser Provider、MCP 和 Obsidian 发布门在各自切片接受前都有记录。

## Risks

公共 Agent API 没有原子跨进程 restore-or-create helper；身份 adapter 必须保持串行范围窄，并证明重复 writer 行为。

Job、Workflow 和 PTY 有进程内生命周期限制；重启状态必须用 Controller 事件表达，不能从实时对象猜测。

Local Shell 和 File provider 本身不等于 containment；项目写入前必须有角色工具和 sandbox 策略。

DSH event data 可经 Host API 到浏览器；identity event 必须有界，绝不能放凭据、提示或额外路径。

provider switch 或 MCP bridge 可能泄漏 secret 或制造第二 writer；只记录非敏感 ID，并保持 canonical Host 为 writer。

Profile UUID 不能从 telemetry anonymous ID、cwd 或临时值推导；显式 profile identity 缺失或无效时必须阻断 readiness。

Browser 和 Obsidian 属于独立风险域，在独立 Recon、许可证、隐私和人工门证据前保持阻断。

## Reviewer Index

| Review item | Exact verification target |
|---|---|
| Changed files | 只允许 `.agents/notes/proposed/architecture/2026-08-14-devframe-control-sessions.md`、其 `.zh.md` pair 和 `.i18n.yaml` sidecar。 |
| Critical code paths | Capability Matrix 中的 Workspace、Session、实时 `ctx.agents`、持久 Subagent catalog、Goal/Plan、Todo、Job、Workflow、Conversation UI/input queue/search/Node、LSP、provider、tools、persistence/event catalog 和 Profile/Bundle 链接；P0 候选路径已明确标记。 |
| Tests and probes | Per-capability Probe Registry 为每个账行列出精确路径。修复聚焦批次报告 34 个文件中 33 个通过（`843 passed`、`3 failed`、`2 skipped`）；3 个失败是已记录的 Windows `EPERM` LSP symlink 阻断。`P-LICENSE` 和 `P-EVENT-CATALOG` freshness 已 verified；不声称 clean full-suite 通过。 |
| Generated artifacts | 没有代码、测试、manifest、catalog、构建产物或归档；唯一看似生成的更新是 pair 校验后的双语 hash sidecar。 |
| Known gaps | 固定 HEAD 缺少 DevFrame identity、Global entry、Host writer lease、统一 readiness、跨 Session mailbox、Paper、MemoryGateway adapter、MCP Server、ccswitch 和 Browser Provider；当前候选不算验收证据。 |
| Review focus | 核对精确源码链接、实时 Agent 与持久 catalog 边界、Todo/LSP 限制、known-event/persistence/Conversation-Node 追踪、HEAD 与候选证据区分、三个 P0 失败关闭要求、全部六项 Acceptance Delta 字段、双语结构一致性，以及 `proposed` 加 `review-pending` 状态。 |
