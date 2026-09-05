---
description: DevFrame 单项目试点的总控编排计划、功能登记表与 Agent 登记表。
---

# DevFrame Agent 编排计划

[English](agent-orchestration-plan.md) | 中文

## 摘要

DSH-Project-Controller 是本轮开发的唯一总控会话：它统一规划、创建、派发、监督和集成所有 Agent。其宿主生成的会话 ID 为 `session-9f2fb633-25a9-4464-8c9b-c257b0c1ab4f`，读取自 `DSH_SESSION_ID`。只有总控创建 Agent、把功能分支合并进 `main`、更新本登记表；功能负责人及其子 Agent 只向总控汇报，跨功能接口问题一律经总控转发。

用户于 2026-09-05 记录的决策：交付按[验收交付表](testAndAcceptance.zh.md#delivery)的"受控单项目试点"行执行，拆分为下文 F01–F07；每个功能拥有独立 git worktree，七个全部预先创建，负责人按最多两路并发的梯次调度激活（模型提供方的账户级请求频率限制不允许七路并发 turn；证据见变更日志）。[Shadow 路由](detailDesign-part2.zh.md)与 [Obsidian 记忆](detailDesign-part3.zh.md)保持为延后的候选扩展。本轮不推送、不部署、不使用任何凭据。

## 现状评估

上一轮并行开发（G1–G5，登记表见 [.agents/devframe-groups.md](../.agents/devframe-groups.md)）已落地基础设施：SessionID 行菜单、worktree 注册表接缝、goal 完成回执、goal-round-driver teardown 修复、组合冒烟包。全部组合并并在 `main` 的提交 `94820fbabc` 收口。

| 焦点领域 | 状态 | 本轮接手的缺口 |
| --- | --- | --- |
| SessionID / 会话持久化 | 已完成（G1 加原生日志） | 回执呈现遗留项并入 F02 |
| Agent 创建 / 恢复 / 子 Agent | 基础已完成（subagent 能力与 spike 证据） | 冷恢复时的角色守卫安装 — F01 |
| Agent Team | 部分完成（实验性 roster、任务板、邮箱） | controller/worker/reviewer 角色策略 — F01、F05 |
| Worktree 产品化 | 部分完成（G2 注册表接缝） | 模型面工具 Consumer 与 prune 对账 — F06 |
| 插件机制 | 已完成（Cordis profile 与 bundle） | DevFrame profile 最终组装 — F05 |
| 项目级总控 | 未开始（`dsh-experimental-devframe` 仅有库契约） | 项目工具、`/project` 旅程、准入、完成 — F02、F03 |
| Shadow | 仅有设计 | 被设计门控延后；不在本轮 |
| 任务状态 / 日志 / 事件 | 部分完成（devframe 包内有契约） | 投影接线与状态呈现 — F02、F05 |
| 测试 / 文档 / 发布 | 基础设施已完成 | 把每个选定的 AT 用例绑定到真实测试 — F07 |
| Windows 兼容性 | 约束已记录 | 真实进程树停止与恢复验收 — F04 |

## 功能登记表

行为细节归各功能链接的设计文档所有；本节只定范围边界、输入输出、依赖与验收锚点。七个功能全部在各自 worktree 并行开发；下表依赖标记的是集成顺序，不是启动顺序。

| ID | 功能 | 范围（仓库路径） | 依赖 | 验收锚点 |
| --- | --- | --- | --- | --- |
| F01 | 角色策略与权限执行 | `packages/experimental/devframe/src/permissions/**`、`packages/experimental/devframe/tests/permissions.spec.ts` | — | [AT1-01、AT1-02](testAndAcceptance.zh.md#part1) |
| F02 | 项目工具与证据链 | `packages/experimental/devframe/src/controller/**`、新 `src/project/**`、`src/events.ts`、`src/projection.ts`、`src/session-journal.ts` 及配套测试；`packages/goal` 内增量回执引用 | F01 | [AT1-03–AT1-06](testAndAcceptance.zh.md#part1) |
| F03 | `/project` 人工命令旅程 | 新 `devframe/src/commands/**` 及测试（规划中） | F01、F02、F04 | [AT1-10](testAndAcceptance.zh.md#part1) |
| F04 | 可靠性早期子集 | `packages/experimental/devframe/src/reliability/**`、`packages/experimental/devframe/tests/reliability/**` | F01、F02（仅集成；库工作立即启动） | [AT4-01–AT4-05、AT4-06 截止、AT4-07 flush](testAndAcceptance.zh.md#part4) |
| F05 | Profile 组装与状态呈现 | `packages/boot/app-boot/src/profile.ts` 中 DevFrame 模板行、`apps/cli/src/profile-boot.ts`、实验性 client team 状态表面 | F01–F03（脚手架立即启动） | [AT1-07、AT1-08](testAndAcceptance.zh.md#part1) |
| F06 | Worktree 工具 Consumer 与 prune 对账 | `packages/workflow/worktree-registry/**` 及其新增的 consumer 包 | — | 真实 git 子进程测试；`verify-cordis-catalog` |
| F07 | 集成、验收接线与文档 | `packages/test-support/composition-smoke/**`、`docs/**`、`.agents/devframe/**`；永不修改本文件 | 全部 | 每个选定 AT id 绑定真实测试；`test:docs` 绿 |

### F01 — 角色策略与权限执行

实现[单项目设计](detailDesign-part1.zh.md#roles)的 `R1.1`。输入：宿主拥有的角色枚举（controller、worker、reviewer）与 `src/permissions/events.ts` 中已持久化的角色和策略事件契约。输出：角色策略查找，加一个 `tools.guard()` 安装器——冷恢复时从持久化还原角色，在任何被派发工具执行前拒绝未知身份、缺失策略和模型自报角色（包括 scope 本地 Team 工具）；后置 pre-execute 放行不能推翻守卫拒绝。`tools.restrict()` 按角色限制继承工具面。非目标：不改 agent-loop、不做项目工具、不做 UI、不做命令。仅当持久化需要时才新增 `SessionEventMap` 成员；届时同一变更内履行 TypeScript 与 Python SDK 投影义务。

### F02 — 项目工具与证据链

实现 `R1.2` 与 `R1.3`。输入：F01 角色准入、原生 goal 回执（G3）、已批准的检查定义、以及对已跟踪与未跟踪输入字节做指纹的源码快照。输出：会话级 `project_verify`、`project_review`、`project_complete` 工具，含 `goalId` 与 `acceptanceHash` 绑定校验、`verificationId` 与 `snapshotId` 证据记录、对当前 `GoalRef` 的 compare-and-set 完成；G3 遗留的 devframe goal 绑定回执引用是 `packages/goal` 内的增量工作。数据：插件自有、准入前可回放的持久化事件记录；不另建验收数据库。非目标：不做 `/project` 命令、不做预算、不做 profile 组装。

### F03 — `/project` 人工命令旅程

实现 `R1.6`。输入：F02 工具服务、F04 停止与恢复语义、原生 Goal 创建顺序——先关闭准入，创建并同步解除 Goal 武装，持久化已批准的工作绑定与预算，再在同一人工启动授权下显式恢复。输出：仅人工可用的 `/project configure`、`confirm`、`start`、`stop`、`resume`、`result`、`abandon` 命令适配器，含预览校验、过期预览拒绝与静默要求。非目标：无模态 UI、无新桌面应用、无模型中介审批；组合后的 profile 持续省略原始 `/goal` 变更命令。

### F04 — 可靠性早期子集

实现交付表指定的[可靠性](detailDesign-part4.zh.md)早期子集。输入：现有 `stopProject` 库、原生 jobs/subprocess/timeout 接缝、`agent/pre-step` 准入。输出：writer 所有权租约与准入切断接线、拒绝关闭或失配工作绑定并放行合法工作的 pre-step 准入检查、以受校验 Cordis 插件配置呈现的尝试/并发/截止预算。非目标：无分布式锁、不做 AT4-06–AT4-08 全矩阵、无敌意代码隔离。库级工作立即启动；与 F01、F02 的集成在其合并后落地。

### F05 — Profile 组装与状态呈现

实现 `R1.4`。输入：F01–F03 表面、原生 preset、以实验性 team profile 为组装参照。输出：DevFrame profile 模板——角色受限的子项组合、省略原始 Goal 变更命令、并在现有 UI 中呈现任务、角色、检查与审查状态及阻断原因。非目标：不超出已文档化扩展点做大 UI 改造。脚手架立即启动；最终组合在 F01–F03 合并后落地。

### F06 — Worktree 工具 Consumer 与 prune 对账

把 G2 注册表接缝产品化。输入：`ctx.worktreeRegistry`、branded `WorktreeId`、G2 proposed Note 留下的设计位。输出：带守卫的 create/list/status/remove 模型面 worktree 工具 Consumer，加注册表与 git 状态之间的 prune 对账。非目标：不接管总控编排（总控使用原生 git worktree）；不另建会话身份体系。完全并行；不依赖 F01–F05。

### F07 — 集成、验收接线与文档

横切收口。输入：各功能交付的表面与[验收清单](../.agents/devframe/acceptance-checklist.md)。输出：新表面的组合冒烟用例、`AT*` id 到真实测试的绑定记录、双语文档同步、最终集成报告。非目标：不实现任何功能行为；永不修改总控所有的本文件。

## Agent 层级与登记表

总控会话拥有一层功能负责人；子 Agent（实现、测试、文档、审查）由总控按负责人的申请创建并向总控汇报。除总控外的任何 Agent 不得创建 Agent，任何 Agent 不得直接联系其他 Agent。

标识政策：`agentId` 是宿主 subagent 工具返回的 durable id；`SessionID` 只认宿主生成值。摘要中的总控会话 ID 读取自 `DSH_SESSION_ID`。subagent 工具不为子 Agent 返回会话 ID，因此在运行时暴露之前，其 `SessionID` 列保持 `unavailable`；绝不编造取值。`WorktreeID` 是真实 git worktree 路径加分支，由总控在负责人启动前创建。

| Agent | agentId | SessionID | Worktree（分支） | 状态 | 最后活动 | 提交 |
| --- | --- | --- | --- | --- | --- | --- |
| DSH-F01-RolePolicy-Owner | cbb87195-4eea-4eaf-aff3-438f55b7785f | unavailable | `D:\dsh-devframe-f01`（`feature/f01-role-policy`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F02-ProjectTools-Owner | eafba7de-c57a-4bb9-b652-e7dac528b960 | unavailable | `D:\dsh-devframe-f02`（`feature/f02-project-tools`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F03-ProjectCommands-Owner | 672d8085-e3bd-4a2f-ade5-36e0f6a399ea | unavailable | `D:\dsh-devframe-f03`（`feature/f03-project-commands`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F04-Reliability-Owner | 6a89b5ff-bf0c-487a-bde2-2c0846bf5742 | unavailable | `D:\dsh-devframe-f04`（`feature/f04-reliability`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F05-ProfileAssembly-Owner | f5e1ff2c-c0cc-49ee-81a5-8f939f8c53e4 | unavailable | `D:\dsh-devframe-f05`（`feature/f05-profile-assembly`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F06-WorktreeTool-Owner | b95b5bf6-63c3-4f5b-91a6-8a37fd25cff9 | unavailable | `D:\dsh-devframe-f06`（`feature/f06-worktree-tool`） | assigned | 2026-09-05 创建并派发 | — |
| DSH-F07-Integration-Owner | 571d0c3f-6497-479d-8e72-a52bc098811d | unavailable | `D:\dsh-devframe-f07`（`feature/f07-integration-qa`） | assigned | 2026-09-05 创建并派发 | — |

本文件的 `main` 副本是活登记表；worktree 副本仅作负责人入职的时点快照。

## 状态模型与监督

每个 Agent 任一时刻只处于一种状态：`planned`、`assigned`、`developing`、`reviewing`、`submitted`、`integrated`、`blocked`、`failed`。长期 idle 不是合法静止态。总控检查每个 Agent 的最后活动、当前状态、任务、真实标识、提交、测试结果与阻塞项，并把检查记入本文件变更日志。

Agent 停顿时，总控读取其最后输出与 worktree，判定为已提交完成、失败或异常退出。可恢复者收到指明最后安全位置的恢复消息。不可恢复者由总控创建接替 Agent——使用新的真实标识，继承任务、提交历史与上下文摘要；绝不覆盖已完成的代码。同一具体阻塞条件连续三个总控轮次未解除时，该 Agent 记为 `blocked` 并附该条件，随即准备接替者或提请用户决策。

## 开发与合并顺序

开发：七个 worktree 与负责人全部预先就位，但负责人按梯次激活——同时最多两路、按合并顺序优先——因为模型提供方执行账户级请求频率限制，曾终止七路并发 turn（429 证据见变更日志）。`packages/experimental/devframe` 内的共享文件——`src/index.ts`、`src/shared/types.ts`、`package.json`、`README.md` 与 tsconfig 聚合——只接受属主的增量编辑；合并时的冲突由总控解决。

合并：总控按 F01 → F02 → F04 → F03 → F05 → F06 的顺序合入 `main`，随后以 F07 收口。每次合并先跑下表该功能的针对性命令，凡改动 docs、README 或 `.agents/` 内容即加跑 `pnpm run test:docs`。最终收口跑 typecheck、build、组合冒烟、针对性矩阵并记录集成报告。只有总控合并；负责人永不触碰 `main`。

| 功能 | 针对性命令 |
| --- | --- |
| F01 | `pnpm exec vitest run packages/experimental/devframe packages/experimental/agent-team packages/core/tools/tests/scoped.spec.ts` |
| F02 | `pnpm exec vitest run packages/experimental/devframe packages/goal` |
| F03 | `pnpm exec vitest run packages/experimental/devframe` |
| F04 | `pnpm exec vitest run packages/experimental/devframe packages/goal packages/guard packages/subagent` |
| F05 | `pnpm exec vitest run packages/experimental/devframe packages/test-support/composition-smoke`；`pnpm run test:docs` |
| F06 | `pnpm exec vitest run packages/workflow/worktree-registry`；`pnpm run verify-cordis-catalog`；`pnpm run test:docs` |
| F07 | `pnpm run test:docs`；`pnpm exec vitest run packages/test-support/composition-smoke` |

## 风险、阻塞与恢复

| 风险 | 处置 |
| --- | --- |
| 五个负责人共享 `packages/experimental/devframe` | 按功能划分子目录；共享文件仅增量编辑；合并冲突由总控解决 |
| 新增 `SessionEventMap` 成员（F02、F03） | 同一变更内更新 TypeScript 与 Python SDK 投影；快照套件为 CI 信号，本地记录不运行 |
| 新增或更新文档的文档门禁 | 双语三件套加提交前 `pnpm run verify-translation-pairing --write` |
| 全量运行中既有的 Windows 红灯套件 | 负责人只跑针对性命令；全量套件保持 CI 信号并沿用已记录基线（16238 通过、10 既有红灯） |
| 七个 worktree 的磁盘占用 | 总控监控；空间不足时按上轮记录删除 `g1`–`g5` worktree |
| 各 worktree 的 `pnpm install` 交叠 | store 锁自动串行；负责人跑测试前先确认 `node_modules` |
| Agent 停顿或静默失败 | 按监督节执行检查点、恢复消息或接替 Agent；连续三个阻塞轮次强制 `blocked` 状态 |

## 环境约束

Windows 主机，仅有 `pnpm`、`pwsh`、Node 24.19 与 git 2.53；无 npm、无 bash。`pnpm run test:snapshot` 与 `pnpm run test:web` 为 POSIX 夹具的 CI 信号——本地不运行、不修复、不刷新。vitest 的 Windows 排除表自动生效。提交在针对性手工门禁（含 `git diff --cached --check` 与零 vendor 暂存）后使用 `git commit --no-verify`。未跟踪的 `docs/env.md`、`docs/env.zh.md`、`docs/env.i18n.yaml` 是用户文件，永不提交。`stash@{0}` 与既有 `g1`–`g5` worktree 保留。未经用户明确授权不推送任何远程。

## 登记表变更日志

- 2026-09-05：计划写成；F01–F07 登记为 `planned`；worktree 与负责人待创建。
- 2026-09-05：计划以 `2be4a074c2` 提交；在该提交上创建七个 worktree；七个负责人全部以宿主返回的真实 agentId 创建并派发完整任务；依赖安装在后台进行。
- 2026-09-05：F04–F07 在产生任何编辑前异常停止（已核实各 worktree 停在基线）；总控已送达恢复消息令各自续作；F01–F03 持续运行；f01–f06 依赖安装完成，f07 收尾中。
- 2026-09-05：七个负责人全部异常停止且各 worktree 零编辑，无工作丢失。会话日志证据显示 `429 AccountRateLimitExceeded` 且重试耗尽——七路并发 turn 触发提供方账户级限流。总控把执行修正为最多两路并发的梯次激活（先 F01 与 F06）；七个 worktree 的依赖安装全部完成。同时禁用 shell 递归遍历 `node_modules`（pnpm junction 环）；负责人改用限定范围的 glob 模式或 `git ls-files`。
