---
description: DSH 插件化开发总计划的控制器差异清单与执行登记（Round P，2026-09-05）。
---

# DSH 插件化执行登记与差异清单 — Round P

本文件是本轮项目总控的活登记表：冻结输入、经核实的现状证据、计划与现状的差异清单、Agent/任务登记和波次推进记录。基线与验收权威分别属于 [agent-orchestration-plan](../docs/agent-orchestration-plan.zh.md)、[testAndAcceptance](../docs/testAndAcceptance.zh.md) 与 [交接文档](../docs/working/dsh-pluginized-development-handoff-2026-09-05.zh.md)。

## 1. 冻结输入

| 项 | 记录值 |
| --- | --- |
| 基线提交 | `main` @ `bde71b8e308697405635b0b7c264fc7e06ce09f1`（实测 `git rev-parse HEAD` 一致） |
| 用户未提交改动 | 保留不动：`AGENTS.md`、`docs/working/devframe-qa-2026-09-04.*`、`packages/client/ui-workspace/**`（直接复制实现 + 删除 `SessionIdDialog`）、`.agents/notes/implemented/feature/2026-09-05-web-{session-id-row-menu,session-id-direct-copy,agent-tree-default-collapsed}.*`、`.agents/notes/proposed/architecture/2026-09-05-pluginized-agent-topology-and-dispatch.*` |
| 用户未跟踪文件 | `docs/env.md`、`docs/env.zh.md`、`docs/env.i18n.yaml`、`docs/working/dsh-pluginized-development-handoff-2026-09-05.*`、上述新 Agent Note、`packages/client/ui-workspace/tests/session-id-copy.client.spec.tsx`；永不提交 `docs/env*` |
| 删除待处理 | `docs/working/handoff-2026-09-03.*` 与 `SessionIdDialog.*` 为用户删除，跟随用户意图，不恢复 |
| stash | `stash@{0}`（devframe recovery snapshot 2026-09-04）保留，不应用不删除 |
| 既有 worktree | `f01`–`f07`（均在 `2be4a074c2`，零编辑零提交）、`g1`–`g5`、`r3-*`、`C:\Users\25313\.codex\worktrees\*` 全部保留 |
| 环境 | Windows、Node 24.19、pnpm；无 npm/bash；`DEEPSEEK_API_KEY` 未设置；根目录无 `.env` |

## 2. 现状证据（本轮实测）

- 聚焦回归（本基线 + 用户改动）实测：`pnpm exec vitest run packages/experimental/devframe/tests packages/experimental/agent-team/tests packages/experimental/tool-agent-team/tests packages/experimental/agent-team-profile/tests packages/test-support/composition-smoke/tests packages/client/ui-workspace/tests` → 30 个文件 29 通过 1 失败；290 个测试 289 通过 1 失败，退出码 1。唯一失败为 `packages/test-support/composition-smoke/tests/workspace-composition.client.spec.tsx:61` 仍断言 `getByRole('dialog')`，而直接复制实现已删除对话框。
- 会话存储：全部会话位于 `C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\`（按 cwd 分桶）。F01–F07 组长会话（`cbb87195…`、`eafba7de…`、`672d8085…`、`6a89b5ff…`、`f5e1ff2c…`、`b95b5bf6…`、`571d0c3f…`）的投影缓存 `identity.cwd` 均为 `D:\dsh-devframe`，不等于各自 worktree 路径。
- 角色策略：`packages/experimental/devframe/src/permissions/index.ts` 的 `DevFrameRole = 'controller' | 'worker' | 'reviewer'`，无 `lead`；策略为内存态 `Map`，无持久化恢复，守卫只覆盖 scope-local Team 工具与继承工具 allow。
- 层级辅助：`src/hierarchy/index.ts` 提供 `devframeSpawnOverrides('lead' | 'worker')` 与深度预算 2，骑在真实 `packages/subagent/subagent` 接缝上（`SubagentStartRequest.maxDepth/toolFilter`、`SubagentDepthError` 在子 Agent 发布前拒绝，有真实测试）。
- 会话核心：`packages/core/session/src/types.ts` 的 `CreateSessionOptions.meta.cwd/parentSession/origin/delegationDepth` 均可由调用方提供并持久化进 `SessionHeader`——准确 cwd 的原生会话创建在核心层可行；宿主 subagent 工具不暴露 cwd 参数。
- profile：本机 `C:\Users\25313\.dsh\profiles\devframe` 组合为 `dsh-base + dsh-headless + dsh-experimental-agent-team-profile`，patch 为空；无任何 P00–P06 插件行。Web profile 另装 `dsh-codex-sidebar@0.5.12`、`dsh-external-agents@0.2.5`、`dsh-model-switch@0.4.6`、`dsh-usage-monitor@0.2.11`、`@dsh-mobile/pairing@0.1.15`。
- dsh-model-switch@0.4.6 导出 `./subagent-runtime`、`./subagent-route-policy`、`./adapter-registry`，确认其替换 subagent 运行时；devframe 组合当前不含它。
- `dsh-llm-codex`、`dsh-llm-providers-ui`、`dsh-llm-opencode-go`、`dsh-llm-ollama`、`dsh-llm-grok`、`dsh-llm-commandcode`、`dsh-ponytail-skills` 本机均未安装、未发现 checkout。Codex CLI 已安装（`C:\Users\25313\.codex\auth.json` 存在，未读取内容）；Ollama 未安装；无 XAI/Grok 凭据。
- 模型路由：`settings.yaml` 配有 `huoshan-1`、`huoshan-2` 两个 Provider（各自独立 `apiKeyEnv`，均含 `glm-5.3-flash`），`agent-default-model = huoshan-1 + glm-5.3-flash`。两个密钥环境变量在控制器进程环境中未设置，由 DSH 凭据存储在运行时解析。

## 3. 差异清单

| 编号 | 差异 | 归属 |
| --- | --- | --- |
| D1 | 无 Agent/Session/Worktree 绑定注册表：`agentId+sessionId+pluginId+taskId+worktreeId` 无任何持久化；F01–F07 会话 cwd 均为主工作区，不能认定独立工作树绑定 | P01、P03 |
| D2 | 角色策略三态不齐：现实现为 controller/worker/reviewer，计划要求 controller/lead/worker；无冷恢复守卫安装；不覆盖插件范围与全部创建入口 | P02 |
| D3 | Worker 创建禁令单边：仅有 spawn 工具 deny + 深度预算；fork、Team、SDK、外部适配器等创建入口未统一拦截 | P02 |
| D4 | devframe profile 为原生 Team 组合，P00–P06 无一安装；项目总控不存在 | P04、P06、profile |
| D5 | composition-smoke 仍断言 SessionID 对话框，与已实现的直接复制冲突，构成聚焦回归唯一红灯 | P07 接入面 |
| D6 | dsh-model-switch 替换 subagent 运行时；与 DevFrame 权限/恢复的最终组合未验证 | P12、组合验证 |
| D7 | 五个验证插件与 providers-ui 均未安装；dsh-llm-codex v0.3.12 的 Astra 主张无法本地复核；无在线凭据 | P16–P20，预期 SKIP_AUTH/SKIP_QUOTA |
| D8 | P04/P05/P06 产品面（会话级工具、命令旅程、profile 组装、证据回执）仅有库级碎片 | W1、W2 |
| D9 | 双路由额度（huoshan-1/2）可用但"同账号最多两路并发"尚未写入任何已验证 Config | P06、组合验证 |
| D10 | F01–F07 前轮零产出（worktree 全部干净停在 `2be4a074c2`），其分支可复用为插件组长工作树基线 | 波次规划 |

## 4. Agent 登记

| Agent | 层级 | SessionID | 父 SessionID | Worktree | 状态 |
| --- | --- | --- | --- | --- | --- |
| DSH-Project-Controller（本轮） | L0 | `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d`（取自 `DSH_SESSION_ID`，宿主生成） | — | `D:\dsh-devframe`（main，唯一合并人） | developing |

L1 组长与 L2 Worker 待创建。合规创建顺序（每个 Agent）：持久化任务/创建意图 → 校验父级与权限 → 创建并登记独立 Worktree → 用准确 cwd（worktree 路径）创建并持久化原生 Session（`meta.cwd`）→ 保存绑定并安装守卫 → 创建/恢复 Agent → 开放执行。当前宿主 subagent 工具不能指定 cwd，凡经由它创建的子项在 P01 机制落地前记录为受限合规（真实持久化 SessionID 已具备，独立工作树绑定缺失），不以 UI 标签冒充。

## 5. 并发与路由

同账号最多两路模型请求；控制器路由 `huoshan-1`，第二路（Worker/验证）路由 `huoshan-2`，均使用 `glm-5.3-flash`；两条路由各自独立配额由用户确认可用。共享契约、事件目录、manifest、profile 与主树提升由总控串行处理；每个工作树单一写入者；不把 git worktree 当权限沙箱。

## 6. 波次记录

| 波次 | 状态 | 证据 |
| --- | --- | --- |
| 差异核对与登记 | completed | 本文件第 1–5 节；聚焦回归实测记录 |
| W0/W2 并行开发 | developing | 执行表见第 6a 节；组长登记见第 4a 节 |
| W3（P16–P20 隔离验证，L-VERIFY） | developing | 独立验证组长已派发 |
| W1（P04 总控、P05 证据、P06 恢复、项目 profile） | planned | 依赖基础能力组切片交付 |
| W4（获准真实小任务、AT1-11） | planned | 用户单独决定 Shadow/Memory |

## 6a. 精简执行表

| 插件 ID | 责任边界 | 依赖 | 组长 | 允许修改路径 | 验收 | 集成序 |
| --- | --- | --- | --- | --- | --- | --- |
| P00 project-contracts | branded ID、角色/任务状态、绑定记录、持久化接缝类型 | core | L-Foundation | `packages/experimental/project-contracts/**` | 单元测试 + 导出面 | 1 |
| P01 session-identity | SessionID 创建/查找/恢复、准确 cwd 绑定注册表 | P00 | L-Foundation | `packages/experimental/session-identity/**` | 冷恢复与绑定测试 | 2 |
| P02 agent-hierarchy | controller/lead/worker 统一角色策略、创建入口守卫、冷恢复 | P00–P01 | L-Foundation | `packages/experimental/agent-hierarchy/**` | 权限探针测试（在线+冷恢复） | 2 |
| P03 worktree-registry 产品化 | 每 Agent 工作树 create/bind/lock/prune 对账 | P00–P01 | L-Foundation | `packages/workflow/worktree-registry/**`、新 consumer | 真实 git 子进程测试 | 2 |
| P04 project-controller | 项目生命周期、调度、有界并发、合并门禁 | P01–P03 | L-Foundation | `packages/experimental/project-controller/**` | 单项目端到端（mock 模型） | 3 |
| P05 agent-evidence | Goal/任务绑定、提交回执、验证快照 | P00、P04 | L-Foundation | `packages/experimental/agent-evidence/**` | 证据链测试 | 3 |
| P06 agent-reliability | 限流、重启、不确定调用、停止、准入切断 | P01–P05 | L-Foundation | `packages/experimental/agent-reliability/**`、既有 reliability | 停止/恢复测试 | 4 |
| P07 组合冒烟更新 | composition-smoke 按直接复制断言（等用户改动提交决策） | 用户 UI 改动 | L-Foundation（暂停） | `packages/test-support/composition-smoke/**` | 冒烟转绿 | 4 |
| P09/P12/P13/P14/P15 | 已装外部插件在隔离目标 profile 的组合验证 | — | L-Product | 隔离 profile 目录、验证报告 | 启动+持久化检查 | 5 |
| P11 providers-ui + P16–P20 | 五仓库隔离安装、能力与兼容验证 | — | L-Verify | 独立 DSH_HOME `C:\Users\25313\.dsh-verify` | 四态分级 + SKIP_AUTH 记录 | 5 |

四态口径：源码存在 / profile 已安装启用 / 运行时已验证 / 达到生产可用，逐插件分别报告，不得混写。

## 4a. 组长登记（W0/W2 并行）

| Agent | 层级 | SessionID | 父 SessionID | Worktree | 状态 |
| --- | --- | --- | --- | --- | --- |
| L-Foundation | L1 | `55979618-6bd7-4bc7-badc-8a3b13079158` | `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d` | `D:\dsh-devframe-p-foundation`（`p/foundation`） | developing |
| L-Verify | L1 | `f2f6d88e-b5e6-4d9f-b945-6e2491022180` | 同上 | `D:\dsh-devframe-p-verify`（`p/verify`） | developing |
| L-Product | L1 | 待创建（同上） | 同上 | `D:\dsh-devframe-p-product`（`p/product`） | planned（梯次补位） |

并发纪律：huoshan-1 同账号最多两路生成中请求；组长内部前台串行跑 Worker；组长完成即补位下一个可执行任务。

## 7. 变更日志

- 2026-09-05：Round P 登记写成；冻结输入盘点完成；差异清单 D1–D10 记录；聚焦回归实测 289/290 通过、唯一失败为 composition-smoke 对话框断言。
- 2026-09-05：经用户授权把 UI 直接复制/默认折叠实现提交 `58a82fe913`；三个组长 worktree 建立；L-Foundation（`55979618-…`）与 L-Verify（`f2f6d88e-…`）派发。
- 2026-09-05：调度缺口定位并修复——目标在续跑指令后处于 `disarmed`，自动续跑不会触发；已 `update_goal resume` 重新 arm（revision 3）。功能性缺口登记：settings.yaml 无 subagent 路由策略段，全部子 Agent 模型请求走 huoshan-1 单账号，同账号两路上限即全局上限；多账号子 Agent 车道路由归 P06/P12 修复（model-switch subagent-route-policy 接入目标 profile）。
- 2026-09-05：L-Verify 证据：隔离 home `C:\Users\25313\.dsh-verify\downloads` 已有 6 个发布包（codex 0.3.12、grok 0.3.10、ollama 0.6.17、opencode-go 0.1.20、providers-ui 0.1.9、ponytail 0.2.5），commandcode 未下载；profiles 下已建 7 项。L-Foundation 已合并 `58a82fe913`、依赖安装完成、P00 实现中。
- 2026-09-05：拆分计划：P00 交付后总控立即派发 L-Worktree（P03）；P01 交付后派发 L-Hierarchy（P02）；车道空出即补位 L-Product（P09/P12–P15）。已向 L-Foundation 下达 P00 先行纪律（绿了立即报，不等整组）。
- 2026-09-05：P00 契约冻结（L-Foundation 确认无偏离）：AgentRole = controller/lead/worker；TaskState 九态含 blocked/failed、无 idle；PluginId=Branded&lt;'PluginId'&gt;、TaskId=Branded&lt;'ProjectTaskId'&gt;（避开 devframe 的 TeamTaskId 防跨包混用）；agentId/sessionId 统一用 dsh-session SessionId 品牌（本地代理恒等、远端 provider 可能分叉）；WorktreeId 复用 dsh-worktree-registry 品牌；BindingStore/TaskStore 最小 read/write/list 接缝；ProjectContractsError{code: CONTRACTS_INVALID_ID|INVALID_RECORD|CONFLICT|STORE_UNAVAILABLE}；ID 工厂非空 trim 校验；状态穷尽用冻结元组计数+全成员遍历+局部 assertNever 三重保障。下游（L-Worktree/L-Hierarchy）以此契约为准并行。
- 2026-09-05：L-Verify 中期证据（总控抽查隔离 home）：7/7 发布包与 profile 就绪；dump-config 产物核实 dsh-llm-codex 与 dsh-llm-providers-ui 组合在 dsh-base 之上装配成功（llm-codex 行 enableSearch/enableImageTool/enableImageGeneration=false、retryPolicy normal/maxRetries 8）。此前"四个 Provider 启动失败"为写入中瞬时快照的误读，已更正。
- 2026-09-05：总控交叉核对：dsh-ponytail-0.2.5.tgz 包内真实包名为 `dsh-ponytail`，与计划约束所称 `dsh-ponytail-skills` 不一致；已转 L-Verify 专项核实（README/Releases 证据、是否存在 skills 子包、v0.2.5 是否正确目标）。P00 全部源文件与 workspace 注册已落盘、待提交；L-Verify 7 profile dump 完成进入深度验证。
- 2026-09-05：Ponytail 包名差异结案（L-Verify 三源交叉）：`dsh-ponytail-skills` 为 v0.2.2 之前旧名（v0.2.2 release note "Unify package name to dsh-ponytail"）；v0.2.5 正确目标 `dsh-ponytail`，npm unscoped 名被第三方占用故禁用 npm 发布、仅 GitHub release 分发；附带核实模式 off/lite/full(默认)/ultra、六捆绑技能与包内 skills/ 一致、子 Agent 默认继承父会话模式且可用 PONYTAIL_SUBAGENT_MATCHER 正则收窄（大小写不敏感、非锚定、对 agentPreset，非法正则加载/保存时报错）、兼容 0.1.2-alpha.4/rc.1。计划中该行约束以本次核实为准修正。
