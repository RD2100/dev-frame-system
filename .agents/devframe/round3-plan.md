# DevFrame Round-3 编排规划与 Agent 注册表

项目级总控（本会话）持有的活动注册表。基线：`6cd473b470`（main）。总控 SessionID：`session-4455800dc3a5`（由运行环境持久会话分配，见本文件底部证据记录）。本文档是本轮唯一活动注册表；Round-1（`.agents/devframe-groups.md`）与 Round-2（`docs/agent-orchestration-plan.md`）作为历史记录保留，不再更新（除本文指向）。

## 一、审计结论（2026-09-05）

### 已有成果（保留，不覆盖）

| 项 | 状态 | 证据 |
| --- | --- | --- |
| Round-1 G1–G5 | 全部 merged 于 main `94820fbabc` | SessionID 行菜单+复制、worktree-registry 服务缝（branded WorktreeId，11 测试）、goal 完成回执、goal-round-driver teardown 修复、composition-smoke 包 |
| Round-2 F01–F07 | 未开始：7 个 worktree（`D:\dsh-devframe-f01..f07`）全部 clean，HEAD 停在基线 `2be4a074c2`，零代码提交 | `git status` 逐树核验 |
| 前次限流事故 | 7 个 owner 并发启动即触发 `429 AccountRateLimitExceeded`（重试耗尽），全员停摆、零损失 | Round-2 计划 changelog |
| 未跟踪用户文件 | `docs/env.md`/`docs/env.zh.md`/`docs/env.i18n.yaml` — 永不提交 | 沿用既有约定 |

### 当前能力真实状态（读码核验，非提交记录推断）

| 能力 | 状态 | 代码事实 |
| --- | --- | --- |
| 子 Agent 持久会话 | **已存在** | 每个子 Agent 是持久 Session：header 带 `parentSession`/`origin:'subagent'`/`delegationDepth`（`packages/subagent/subagent/src/child-agent.ts` L152-154） |
| 子 Agent 的 SessionID | **数据模型已存在，暴露不充分** | 后台 `subagent` 工具返回的 `subagentId` 就是持久 SessionId（`continuation.ts` L435 `childId = brandString<SessionId>(randomUUID())`；`tool-subagent/src/index.ts` L529），但以 "agentId/subagentId" 名义呈现，无 SessionID 语义标注；前台一次性模式完全不返回 id |
| Agent 树枚举 | **运行时已存在** | `listChildren`/`listDescendants` 返回真实 SessionId、parentId、depth、hasChildren、activity（`list-children.ts`） |
| 嵌套创建（组长建执行 Agent） | **机制已存在，未产品化** | 深度预算 `maxDepth`（工具默认 3）+ `SubagentDepthError` 边界测试（`depth.ts`、driver spec L259-280）；按 spawn 的 `toolFilter.deny` 可裁剪子 Agent 工具集 |
| 执行 Agent 禁建子 Agent | **可强制，未接线** | 需在组长 spawn 执行 Agent 时下发 toolFilter 禁 spawn 工具或深度收口；现有默认 maxDepth=3 允许深度 2 的 Agent 继续建到深度 3 |
| Web 左侧栏 Agent 树 | **最大缺口** | `ui-workspace/tree.ts` 的 `sessionVisible` 明确隐藏 `origin==='subagent'` 会话（仅显示 runningSubagentCount 计数）；`SessionSummary.parentSessionId/origin` 已在 list 投影中（`api/session-controller/src/list.ts` L377-383），子目录 `subagent catalog` remote 与 `lineage.ts` 已有，但侧栏不渲染树 |
| SessionID 复制菜单 | **已存在** | Round-1 G1 交付 `SessionIdDialog.tsx` + 行菜单（实机验证证据 `.agents/devframe/evidence/sessionid-check.png`） |
| Worktree 注册表 | **服务缝已存在** | `ctx.worktreeRegistry`（create/list/status/remove，真实 git 子进程测试）；模型侧工具 Consumer 与 prune 对账未做（Round-2 F06 设计位） |
| 角色权限（controller/worker/reviewer） | **仅设计** | Round-2 F01 设计（`tools.guard()` 冷恢复角色恢复），未实现 |
| 影子功能 | **仅设计，本轮按设计门禁延后** | `detailDesign-part2.md`；G5 负责核对不回归 |

### 现状 vs 目标结构差异（用户指令二/四）

| 用户目标 | 现状 | 差异动作 |
| --- | --- | --- |
| 三层：总控 → 组长 → 执行 | 数据模型支持三层；Round-1/2 从未实际运行组长→执行两层 | G2 强制接线 + 本轮实际运行验证 |
| 组长是独立持久 Agent，独立 SessionID，与总控同层可见 | 子 Agent 会话持久且 continuable，但 UI 隐藏、工具返回不标 SessionID | G1 暴露修正 + G3 树投影 |
| 执行 Agent 禁建子 Agent | maxDepth/toolFilter 机制在，无角色化装配 | G2 角色化 spawn 策略 + 测试 |
| 左侧项目 Agent 树（展开/收起/进入会话/状态/SessionID/工作树/复制） | 侧栏只有 Workspace→会话两层，subagent 被隐藏 | G3 主战场 |
| 每个 Agent 独立工作树 + 最终提交 | worktree-registry 服务缝在；per-agent 绑定与工具未做 | G4 |
| 调度/限流/状态机/合并/回归 | 教训与机制在（staggered、goal、jobs），无本轮状态机登记 | G5 + 本文件注册表 |

## 二、五功能组注册表

状态机（用户指令七选一）：`planned → developing → blocked | review → committed → merged → completed`。

并发约束：账号级 429 实证在案；**任何时刻至多 2 个组长处于 developing**，按 G2 → G1 → G3 → G4 → G5 优先级阶梯激活（G3 依赖 G1/G2 的投影先行落地）。执行 Agent 由组长在自己预算内创建，组长必须串行/小并发派工。

| 组 | 组长 Agent | SessionID | Worktree（分支） | 状态 | 最近提交 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- |
| G1 Session 与 Agent 身份 | DSH-G1-SessionIdentity-Lead | `5e7138d6-9e6a-4442-9f7a-b32c55bcb46a` | `D:\dsh-devframe-r3-g1`（`r3/g1-session-identity`） | developing | — | 身份链测试锚定 |
| G2 Agent 层级与权限 | DSH-G2-Hierarchy-Lead | `ca378724-8de0-4c17-94e0-05aa828c1366` | `D:\dsh-devframe-r3-g2`（`r3/g2-hierarchy`） | developing | — | 角色化强制 + 活体验证 |
| G3 项目 Agent 树和界面 | 待创建 | — | `D:\dsh-devframe-r3-g3`（`r3/g3-agent-tree-ui`） | planned | — | 依赖 G1/G2 投影 |
| G4 Worktree 产品化 | 待创建 | — | `D:\dsh-devframe-r3-g4`（`r3/g4-worktree`） | planned | — | 等待激活 |
| G5 调度、状态、合并与质量 | 待创建 | — | `D:\dsh-devframe-r3-g5`（`r3/g5-quality`） | planned | — | 最后激活 |

总控 SessionID：`session-52f2ff3c-52b0-4ef5-821d-d5e1b49352e2`（由子会话 header 的 `parentSession` 实证，list_agents descendants 输出）。身份约定：host 创建的会话 id 带 `session-` 前缀；agent 通过 spawn 工具创建的子会话 id 为裸 UUID（continuation manager `randomUUID()`）——两类都是真实持久 SessionID，注册表按实际返回值原样记录，不添加或去除前缀。

各组执行 Agent 由组长创建后由组长登记到自己的小节（总控汇总时同步）。

### G1 — Session 与 Agent 身份

范围：`packages/subagent/tool-subagent/**`（结果标注 SessionID）、`packages/subagent/tool-subagent-control/**`（list-agents 暴露 SessionID/parent）、`packages/session/**`、`packages/api/session-controller/**`（如投影需补字段）、`packages/client/ui-workspace/src/client/rows/SessionIdDialog.tsx`（如需配合）。验收：① 后台 `subagent` 工具结果包含名为 SessionID 的持久会话标识字段（复用 childId，不新造身份）；② `list_agents` 每行含 SessionID、parent、可继续性；③ 会话创建/恢复/查询/复制的既有能力有测试锚定（session-query、resume、SessionIdDialog 复制）；④ 双语 UI 文案走 locale 字典；⑤ 组内 vitest 全绿。禁止：改 UI 树结构（G3 范围）、改 worktree 包（G4 范围）。

### G2 — Agent 层级与权限

范围：`packages/subagent/subagent/**`（spawn 请求的角色化约束）、`packages/subagent/subagent-in-process-driver/**`、DevFrame 角色装配（controller/lead/worker 三档 preset 或 spawn 策略，落点在 `packages/experimental/devframe/**` 或 subagent 包内，组长开工前在组内小节登记落点）。验收：① 总控可建组长、组长可建执行 Agent（嵌套 spawn 实测通过）；② 执行 Agent 的 spawn 工具被拒（toolFilter 禁用或深度收口，测试断言拒绝发生在执行器而非仅 schema 缺席）；③ 消息路由：总控↔组长、组长↔执行 Agent 的 send_message 方向校验有测试；④ 冷恢复后深度预算单调不降（复用 `delegationDepthOf` 不变量）并测冷恢复角色；⑤ 组内 vitest 全绿。禁止：改 UI、改 worktree-registry。

### G3 — 项目 Agent 树和界面

范围：`packages/client/ui-workspace/src/client/**`（新 tree 投影 + 行组件 + locale）、`packages/api/session-controller/src/client/**`（如需新投影/动作）、`packages/bundle/web-app/**`（如新包注册）。验收：① 左侧呈现项目 Agent 树：项目总控为根，G1–G5 组长默认显示，展开只显示直接下级，再点收起；② 无下级不显示展开按钮；③ 点击行进入该 Agent 独立会话；④ 每行显示名称、真实状态、真实 SessionID、工作树（如有绑定）、最近进度；⑤ SessionID 菜单复制（复用/扩展 SessionIdDialog 模式）；⑥ `pnpm run test:gui` 绿 + 相关 jsdom 组件测试；⑦ 数据全部来自 session list/catalog 投影，禁止伪造状态。依赖：G1 的 SessionID 暴露先行合并（树行直接可显示）；树结构数据（parentSessionId/origin）已存在可先行开发。

### G4 — Worktree 产品化与环境可靠性

范围：`packages/workflow/worktree-registry/**`、新工具 Consumer 包（F06 设计位：guarded create/list/status/remove + prune 对账）、Windows 兼容路径（symlink/路径/权限诊断）。验收：① 模型可见的 worktree 工具注册进 catalog（`verify-cordis-catalog` 绿）；② create→bind→status→remove 全链路真实 git 子进程测试；③ prune 对账：注册表与 `git worktree list` 差异检测有测试；④ 失败路径（已存在/脏树/路径占用）有诊断与重试语义测试；⑤ README + 子系统页双语；⑥ Windows 主机实跑通过。禁止：改 UI 树（G3 范围）。

### G5 — 调度、状态、合并与质量

范围：`.agents/devframe/**`（验收清单扩展）、composition-smoke 用例、状态机与调度记录工具（如需代码落点：`packages/experimental/devframe/**`）、最终回归。验收：① 五组状态机在本文件登记并保持唯一真实来源；② 每组合并前 targeted 测试命令矩阵执行并记录实际结果；③ 影子功能核对：确认仍按设计门禁延后且无代码混入；④ 最终 `pnpm run typecheck` + `pnpm run test`（记录已知 Windows 红名单）+ composition-smoke 全绿；⑤ 汇报未完成项清单。

## 三、依赖与合并顺序

开发并行（受 429 约束阶梯激活），合并顺序：G2（层级基础）→ G1（身份暴露）→ G3（树 UI，需 G1+G2）→ G4（独立）→ G5（收口）。

| Feature | 合并时 targeted 命令 |
| --- | --- |
| G2 | `pnpm exec vitest run packages/subagent packages/experimental/devframe` |
| G1 | `pnpm exec vitest run packages/subagent packages/session packages/api/session-controller packages/client/ui-workspace` |
| G3 | `pnpm run test:gui` |
| G4 | `pnpm exec vitest run packages/workflow/worktree-registry`；`pnpm run verify-cordis-catalog`；`pnpm run test:docs` |
| G5 | `pnpm run test:docs`；`pnpm exec vitest run packages/test-support/composition-smoke` |

只有总控执行合并；合并一律 `--no-verify` 并手工执行等价门禁（`git diff --cached --check`、零 vendor 暂存、双语配对如动 docs）。`test:snapshot`/`test:web` 为 CI 信号（POSIX 夹具），本地不跑。

## 四、汇报模板（每次阶段汇报必含）

Agent 名称 / Agent 类型 / SessionID / 工作树路径 / 当前状态 / 已完成内容 / 当前阻塞 / 最近一次提交 / 下一步动作 / 是否可以合并。

## 五、环境约束与本轮事故记录

- Windows 主机：Node 24.19、pnpm 11.19、git 2.53；无 npm/bash。pnpm junction 循环：禁止 shell 递归进 `node_modules`。
- 本轮新增：会话初段文件沙箱 `grantWrite` 报 Win32 5 错误，用户已授权 danger-full-access 解决；后续命令不再申请沙箱提权（审批策略 never）。
- 429 防复发：≤2 组长并发；组长派工串行优先；遇限流记录原因、降并发、按最后安全位置恢复。
- 历史工作树 `D:\dsh-devframe-g1..g5`、`f01..f07` 与 `stash@{0}` 保留不动；不推送任何远程。

## 六、值班交接（自动续期轮次耗尽时，恢复回合按此执行）

1. `list_agents`（scope descendants）核对 G1/G2 组长状态；`git -C D:\dsh-devframe-r3-g1 log --oneline -3` 与 `git -C D:\dsh-devframe-r3-g2 log --oneline -3` 核对提交。
2. 若组长已提交：按 §三 targeted 命令跑该组测试 → 人工审 diff（边界遵守：G1 不碰 G2/G3/G4 范围，G2 不碰 UI/worktree）→ 合并入 main → 本表登记 → 激活下一组长（顺序 G4 → G3 → G5）。
3. 若组长已 settle 且无提交：发恢复信标（按 §四 模板，指明最后安全位置）。
4. 若仍在运行：继续等待，勿打扰。
5. 全组合并后：G5 收口（typecheck、test、composition-smoke、已知 Windows 红名单记录）+ 最终汇报（含未完成项）。

## 七、注册表 changelog

- 2026-09-05：审计完成（git/worktree/Agent/能力四线核验）；本文档创建；G1–G5 登记 planned；worktree 待创建。
- 2026-09-05：六个 r3 工作树建成（foundation + g1–g5）；总控完成基础能力修复 `1ed2c783d4`（subagent 工具与 list_agents 显式暴露持久 SessionID，rename subagentId/id → sessionId；Agent Note 三元组；769 subagent 测试绿；tool-catalog 再生；双语配对 1136 对绿；test:docs 15/15），已 ff 合并入 main；五个组工作树快进至新基线；组工作树依赖安装进行中。
- 2026-09-05：五组工作树依赖安装全部完成（pnpm -C 逐树，store 锁串行）；G1、G2 组长已创建（后台 continuable，SessionID 见注册表），按 ≤2 并发阶梯激活；G3–G5 待前组合并后激活。工作树策略：执行 Agent 由组长按需建独立 worktree（r3-gX-eN 分支 r3/gX-eN），审核后由组长并回组分支。
- 2026-09-05：组长信标回报。G2：设计选型完成——组长 spawn 执行 Agent 时下发 `toolFilter.deny`（执行器级拒绝）+ 深度收口；首个提交将含 devframe 角色装配 + 四类测试（深度边界/执行器拒绝/消息路由/冷恢复深度）+ 双语文档 + Agent Note，随后活体验证。G1：覆盖勘察完成，锁定三处真实缺口（跨 Context 冷恢复身份链 e2e 缺失、generic resume 未锚定 origin、SessionIdDialog 复制反馈回 idle 分支未测）；**发现快照基线债务**：snapshots/* 40+ 文件仍期望旧 subagentId/agent id 文案（CI 快照信号，本地不跑不修，登记为合并后 CI 义务）。无阻塞。
