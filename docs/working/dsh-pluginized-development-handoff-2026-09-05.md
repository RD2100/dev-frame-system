---
description: Compact handoff for GPT-6 Astra planning and bounded DSH plugin development.
---

# DSH Pluginized Development Handoff — 2026-09-05

English | [中文](dsh-pluginized-development-handoff-2026-09-05.zh.md)

## Summary

This working handoff gives GPT-6 Astra one short planning input and gives DSH one executable implementation brief. It keeps only the decisions that affect ownership, concurrency, SessionID, Worktree, plugin boundaries, recovery, and acceptance; detailed contracts remain in the linked owner documents.

## Table of Contents

- [1. Objective](#objective)
- [2. Current state](#current-state)
- [3. Hard rules](#hard-rules)
- [4. Plugin work packages](#plugin-work-packages)
- [5. Agent topology and waves](#agent-topology-and-waves)
- [6. Astra planning prompt](#astra-planning-prompt)
- [7. DSH execution prompt](#dsh-execution-prompt)
- [8. Acceptance and reporting](#acceptance-and-reporting)
- [Further Exploration](#further-exploration)
- [Dev Note](#dev-note)

## 1. Objective <a id="objective"></a>

GPT-6 Astra first audits the repository, current profile, design documents, tests, Agent Notes, and candidate plugin releases, then writes the authoritative dependency and execution plan. DSH then creates the first-class sessions, assigns Worktrees, delegates bounded tasks, collects evidence, and merges only reviewed paths.

The final milestone is a DSH platform that can plan, delegate, recover, review, and merge its own low-risk development work; a single successful conversation or a visible sidebar row is not enough.

## 2. Current state <a id="current-state"></a>

- Repository root: `D:\dsh-devframe`.
- Locally observed Web profile entries: `@dsh-mobile/pairing`, `dsh-codex-sidebar`, `dsh-external-agents`, `dsh-model-switch`, and `dsh-usage-monitor`.
- Still requiring explicit compatibility verification: `dsh-llm-codex`, `dsh-llm-providers-ui`, `dsh-llm-opencode-go`, `dsh-llm-ollama`, `dsh-llm-grok`, `dsh-llm-commandcode`, and `dsh-ponytail`.
- The existing user changes, Agent Notes, tests, and untracked `docs/env*` files are outside this handoff’s ownership and must remain untouched.
- The catalog at [dsh-plugins](https://github.com/NOirBRight/dsh-plugins) can lag a repository README; verify exact release, DSH/Cordis compatibility, permissions, credentials, quota, and license before activation.

## 3. Hard rules <a id="hard-rules"></a>

- Controller and Plugin Lead are the same first-class Agent/Session type; both have real durable SessionIDs and independent Worktrees.
- The logical tree has at most three levels and two creation edges: Controller → Lead → Worker.
- Only Controller creates Leads; a Lead creates Workers only inside its own plugin; a Worker cannot create any Agent.
- Every Agent/Worktree record binds `agentId`, `sessionId`, `pluginId`, `taskId`, and `worktreeId`; only Controller merges to main.
- No `idle` status: use `planned`, `assigned`, `developing`, `reviewing`, `submitted`, `integrated`, `completed`, `blocked`, or `failed`; blocked/failed records need a reason and next action.
- Model-visible facts, routing, assignments, results, and recovery state must be reconstructable from the session log.
- The UI shows a collapsed tree by default; an arrow changes only the current parent’s next level; clicking SessionID copies the complete value directly without a dialog.
- External providers use typed explicit routes such as `@codex`, `@claude`, and `@cursor`; unavailable routes fail visibly and never silently fall back.
- Shared contracts, generated events, manifests, profiles, and main-tree promotion have one owner and a serialized integration step.
- No push, PR, release, destructive cleanup, or credential-dependent live test without explicit authorization and evidence.

## 4. Plugin work packages <a id="plugin-work-packages"></a>

Each row is an independent ownership unit; P00 is a shared library and P12 is QA/integration workflow, not an installable runtime plugin.

| ID | Work package | Responsibility | Depends on |
| --- | --- | --- | --- |
| P00 | `dsh-project-contracts` | Branded IDs, typed events, task/result messages, and plugin declarations | DSH core |
| P01 | `dsh-session-identity` | Durable SessionID creation, lookup, resume, and display metadata | P00 |
| P02 | `dsh-agent-hierarchy` | Controller/Lead/Worker roles, permissions, and max-depth enforcement | P00–P01 |
| P03 | `dsh-worktree-registry` | Create, bind, lock, inspect, stop, and recover one Worktree per Agent | P00–P01 |
| P04 | `dsh-project-controller` | Project lifecycle, scheduling, bounded concurrency, and merge gate | P01–P03 |
| P05 | `dsh-agent-evidence` | Goal/task binding, commit receipt, verification snapshot, and handoff | P00, P04 |
| P06 | `dsh-agent-reliability` | Rate limits, restart, uncertain calls, corrupt logs, and process stop | P01–P05 |
| P07 | `dsh-agent-tree-ui` | Collapsed hierarchy, child discovery, status/Worktree display, and direct ID copy | P01–P06 |
| P08 | `dsh-agent-router` | Typed `@provider` routing and durable external-job metadata | P00, P09 |
| P09 | `dsh-external-agents` | Codex, Claude Code, Cursor, and other Product Worker adapters | P08 |
| P10 | `dsh-llm-codex-astra` | Codex provider plus dynamic and static/cached `gpt-6-astra` catalog paths | P11, Codex OAuth |
| P11 | `dsh-llm-providers-ui` | Shared provider settings namespace and card composition | Web UI |
| P12 | `dsh-model-switch` | Model and route selection integration | P11, provider registry |
| P13 | `dsh-codex-sidebar` | Sidebar and project/session navigation integration | P01, P07 |
| P14 | `dsh-usage-monitor` | Usage, quota, rate-limit, and retry visibility | P05, provider registry |
| P15 | `dsh-mobile-pairing` | Mobile pairing, encrypted connection, and tunnel fallback | P01, Web UI |
| P16 | `dsh-llm-opencode-go` | OpenCode Go provider installation and capability verification | P11 |
| P17 | `dsh-llm-ollama` | Ollama Cloud provider installation and capability verification | P11 |
| P18 | `dsh-llm-grok` | Grok provider installation and capability verification | P11 |
| P19 | `dsh-llm-commandcode` | Command Code provider installation and capability verification | P11 |
| P20 | `dsh-ponytail` validation | Lab-only compatibility check for modes, skills, and subagent inheritance | Current release |
| P21 | Shadow and Memory | Later cross-project routing and bounded memory extensions | P04, P06 |
| P22 | Integration and QA | Fixed-candidate assembly, read-only QA, exact-path promotion, and release evidence | Approved wave outputs |

One validation Lead owns P16–P20 in an isolated profile; `dsh-llm-providers-ui` is setup for the four providers and is not an extra validation target. Missing credentials or quota is `SKIP_AUTH` or `SKIP_QUOTA`, never a pass.

Do not add deprecated `dsh-composer-picker`, quarantined `dsh-llm-assistant`/`dsh-buddy`, or `dsh-llm-cursor` without a separate policy review.

## 5. Agent topology and waves <a id="agent-topology-and-waves"></a>

| Level | Agent | Creation right | Ownership |
| --- | --- | --- | --- |
| L0 | Project Controller | Creates L1 Leads | Project Goal, schedule, global status, and main-tree merge |
| L1 | Plugin Lead | Creates L2 Workers in its plugin | Plugin scope, Worktree set, review queue, and handoff |
| L2 | Leaf Worker | None | One bounded task and one Worktree |

| Wave | Scope | Concurrency | Exit condition |
| --- | --- | --- | --- |
| W0 | P00–P03 and P06 foundation | Serialize shared events and manifests; isolate tests | Identity, permissions, Worktree ownership, and recovery are tested |
| W1 | P04–P05 and P22 composition | One fixed candidate; Controller owns integration | Leads, evidence, stop/resume, and QA path work end to end |
| W2 | P07–P15 product integrations | One Lead per plugin; shared profile files go through the queue | UI, explicit routes, models, existing plugins, and restart behavior are visible |
| W3 | P16–P20 five-repository validation | One validation Lead, isolated profile | Each plugin is verified, blocked, or skipped with a reason |
| W4 | P21 Shadow/Memory and release trial | Only after W1 acceptance and an explicit plan | DSH completes a bounded self-development scenario |

## 6. Astra planning prompt <a id="astra-planning-prompt"></a>

Use model ID `gpt-6-astra` only after the current provider/account exposes it. The official guidance lists `low`, `medium`, `high`, `xhigh`, and `max`; verify the actual DSH provider before using any other effort. See the [official model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra).

Copy this prompt to GPT-6 Astra:

```text
你是 DSH 项目的首席架构师。请先阅读 docs/working/dsh-pluginized-development-handoff-2026-09-05.md、AGENTS.md、docs/architecture.md、设计/验收文档、当前 profile、package.json、测试和 Agent Notes，再检查候选插件的当前 README、发布版本和兼容性。
请输出一份可执行总规划，按“源码已有、profile 已安装、运行时已验证、生产已接受”区分现状；为每项能力给出插件 ID、责任边界、Service Definition/Provider/Consumer、依赖、事件/持久化影响、负责人、测试、验收和回滚。
必须保留：Controller 与 Lead 是同类一等 Session；二者都有真实 SessionID 和独立 Worktree；Controller 只能创建 Lead，Lead 只能创建本插件 Worker，Worker 不能创建 Agent；最多三层、两条创建边；只有 Controller 合并；无 idle；模型可见事实入日志；树默认折叠；SessionID 点击直接复制；外部 Agent 使用显式 @codex/@claude/@cursor 且不静默降级。
单独规划一个验证 Lead 负责 dsh-llm-opencode-go、dsh-llm-ollama、dsh-llm-grok、dsh-llm-commandcode、dsh-ponytail，使用隔离 profile；认证/配额缺失标记 SKIP_AUTH/SKIP_QUOTA。dsh-llm-providers-ui 是四个 Provider 的设置前置条件，不计入五个验证目标。
输出顺序：现状证据、插件清单、依赖与并发波次、Agent/SessionID/Worktree 创建顺序、验收、风险回滚、交给 DSH 的执行提示词。先规划，不改代码、不创建假 Agent、不创建无限层级、不推送远端。
```

## 7. DSH execution prompt <a id="dsh-execution-prompt"></a>

After Astra writes the plan, give DSH the plan and this prompt. DSH must audit the plan against the actual checkout before implementation.

```text
你是 DSH 项目级总控 Agent。请先阅读交接文档、GPT-6 Astra 总规划、实际源码、当前 profile、工作区状态、插件注册和已有 SessionID/Worktree 记录，先写执行清单并列出差异，不要把旧聊天、UI 标签或消息发送成功当成证据。
先建立正确拓扑：一个 L0 项目总控、同类的一等 L1 插件组长、每个组长可创建本插件的 L2 Worker；每个 Session 都必须有真实 SessionID、父 SessionID、独立 Worktree、pluginId、taskId、worktreeId 和持久化状态；最大三层、两条边；Worker 严禁创建 Agent。
按 W0→W4 执行，先完成 SessionID、层级、Worktree、总控、证据和可靠性，再并发低耦合插件。共享契约、事件、manifest、profile 和主树合并指定唯一负责人并串行。
为五个指定仓库创建一个隔离验证 Lead；缺少凭据或 quota 如实标记 SKIP_AUTH/SKIP_QUOTA，不污染生产 profile。
状态只能使用 planned→assigned→developing→reviewing→submitted→integrated→completed，外部等待或失败使用 blocked/failed 并写原因、唤醒条件和下一步，禁止 idle；不确定工具调用先查外部状态，禁止盲目重试。
UI 显示默认折叠的 Controller→Lead→Worker；箭头只切换当前节点的下一层；SessionID 点击直接复制；外部 Agent 使用显式 @codex/@claude/@cursor，路由、目标 SessionID、job、Worktree、结果和错误都入日志。
每轮汇报变更文件、SessionID/Worktree 映射、commit、测试命令和结果、未验证项、风险、回滚和下一动作；只有总控合并到主树，未经用户授权不得 push、PR、发布或删除文件。
```

## 8. Acceptance and reporting <a id="acceptance-and-reporting"></a>

The foundation must prove unique/persistent SessionIDs, creation/execute/cold-restore permissions, maximum depth, one Worktree writer, duplicate prevention, and exact parent records.

The product path must prove project start, Lead/Worker creation, bounded concurrency, evidence receipts, stop/resume, collapsed tree behavior, direct SessionID copy, explicit external routing, and restart persistence.

The reliability path must classify rate limits, uncertain calls, corrupt logs, service restarts, process-tree stops, and unauthorized replay; skipped live provider tests must remain visibly skipped.

Use `slice_green`, `qa_accepted`, `main_integrated`, and `release_green` as separate milestones. A local green test or completed Goal cannot replace independent QA on one fixed composition candidate.

Each lead reports: `pluginId`, Agent name, SessionID, parent SessionID, Worktree ID/path, status, exact changed files, commit, commands/results, runtime/profile evidence, known issues, rollback, and next action.

## Further Exploration

Read [Architecture](../architecture.md), [Tests and Acceptance](../testAndAcceptance.md), and the [DevFrame orchestration plan](../agent-orchestration-plan.md) for the owning contracts.

Review [dsh-llm-codex](https://github.com/NOirBRight/dsh-llm-codex), [dsh-llm-providers-ui](https://github.com/NOirBRight/dsh-llm-providers-ui), and [dsh-plugins](https://github.com/NOirBRight/dsh-plugins) before provider activation.

## Dev Note

This is a non-authoritative working handoff for the 2026-09-05 Astra planning pass. Detailed architecture, acceptance, and QA evidence stay in their owner documents; this page intentionally contains only the execution spine.
