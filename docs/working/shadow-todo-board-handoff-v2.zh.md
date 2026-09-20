---
owner: shadow
status: handoff-ready
date: 2026-09-20
previous:
  - docs/working/shadow-todo-board-design.zh.md（v1，3:0 打回）
  - docs/working/shadow-todo-board-review.md（三方审核 22 条硬伤）
---

# Shadow Todo 看板 v2 交接

## 一句话状态

v1 设计 3:0 打回后，已读透关键源码，确认方向调整为**路线 3：接 project-controller 但只接核心件**。本文是给后续 agent 的交接，读完可直接开 v2。

## 用户要什么

把 DSH 影子（Shadow）从"和人对话的主 agent + 自由文本派活"升级成**任务看板驱动的多 agent 工作台**，参考 todos.dev 六列看板。用户原话 5 痛点：

1. 改完要先给工单等批（HITL gate）
2. 干完有质检（独立 reviewer）
3. 动手前问你（不要自作主张开工）
4. 花超自己停（token 预算）
5. 进度看得见（看板 UI）

## 路线决策（已拍板）

**路线 3：接 project-controller，但只接 task 状态机 + worktree + review + integrate，先不接 requiredChecks 账本和 request-budget。**

为什么不自己写：v1 被打回的 7 条 P0 都是 dsh 仓库本身的约束（worktree 没 node_modules、building→reviewing 没事件、一 workspace 一 binding、崩溃恢复挂死、integrate 冲突处理、cancelTodo 无 RPC、model-visible⟺logged），project-controller 已经把这些踩过并写了测试。

为什么不全接：requiredChecks.json 账本按 task 注册 digest、Goal binding 是 DevFrame 概念，对当前 Shadow 闭环太重。先关，v2 跑通后再补。

## 关键发现（v1 不知道、必须先记住）

### 1. 桌面端 devframeOverlay 没挂 project-controller

`apps/desktop/scripts/development-project.ts` 里的 `buildDevFrameDeploymentPatch()` 只挂了：
- shadow-router
- shadow-bridge
- shadow-controller

**没挂 project-controller 全家桶**。Shadow 把活发给 controller session 后，那个 session 只是普通 agent，不会自动 plan task / 派 worker / review / integrate。这就是为什么用户觉得影子"撒手"——不是设计缺陷，是零件没装。

### 2. shadow-loop 示例 composition 已经把闭环写好了

`apps/cli/config/examples/shadow-loop/cordis.patch.yml` 是完整的闭环配置示例，定义了：

```
Shadow session（你对话的那个）
  → shadow-router 4 工具（project_open/send/status/stop）
    → shadow-bridge 把 received delivery 转发进 project controller session
      → project-controller task 状态机
        → Worker 在 worktree-registry worktree 里干
          → project_deliver + project_commit 交付
            → Lead project_review 独立审查
              → Controller project_integrate 合回基线
```

需要挂的 row（示例里都有）：
- `project-controller`（service，maxActiveTasks=2, requestBudget=64）
- `project-controller-consumer`（project_integrate）
- `project-controller-task-consumer`（project_task plan/start）
- `project-controller-delivery-consumer`（project_deliver/commit/evidence/review）
- `project-controller-request-budget-consumer`（按项目限 LLM 发送次数）——**路线 3 先不接**

### 3. Shadow 和 project controller 是两个独立 session

- Shadow session = 你对话的那个（chat UI，标 shadowSessionId）
- project controller session = 每个 workspace 独立 root，跑 project_task
- shadow-router 会 reserve 每个项目的 controllerSessionId
- shadow-bridge 把 Shadow 的 work delivery 转发成 project controller 的 followup

### 4. project-controller 已实现的（v2 不再造）

| 能力 | 现成 API |
|---|---|
| task 生命周期 | planned → assigned → developing → reviewing → submitted |
| Worker worktree 隔离 | worktree-registry: `create/bind/commit/remove/reconcile` |
| 独立 reviewer | `project_review`（Lead 独立 session，decision + findings severity） |
| integrate 闸门 | `project_integrate`（fast-forward / merge commit，查 writer lock / source fingerprint） |
| 并发上限 | `maxActiveTasks: 2` |
| 自动回退 | `repairLimit: 3`（Lead 打回 → Worker 改 → 再 review，超了停） |
| 持久化恢复 | `reconcile` 观察 retained intent |
| Worker 交付前 checks | `project_deliver`（路线 3 先不接 checks 账本） |

### 5. ShadowCard 现状（v1 认错点）

`packages/experimental/client-ui-shadow-entry/src/client/ShadowCard.tsx` 不是会话卡片，是**侧栏 footer 触发按钮**（icon + 状态点 + manage 下拉）。点击 `onOpenConversation()` 打开指定会话。看板 UI 不能"把 ShadowCard 改成看板"，要在 conversation surface 里加视图。

## v2 要做的四块

### 块 1：composition 接线（最大头）

把 shadow-loop 示例里的 row 加进桌面端 devframeOverlay patch（`development-project.ts` 的 `buildDevFrameDeploymentPatch`）。

**必接**：
- project-controller service（maxActiveTasks=2）
- project-controller-task-consumer（project_task）
- project-controller-delivery-consumer（project_deliver/commit/evidence/review）
- project-controller-consumer（project_integrate）

**先不接**：
- request-budget-consumer（花超停以后补）
- requiredChecksByTask / commitPathsByTask（先空，reviewer 直接看 diff）
- Goal binding（DevFrame 概念，Shadow 闭环不需要）

**待确认**：shadow-loop 示例里的占位符怎么填
- `REPLACE_WITH_PROJECT_CONTROLLER_SESSION_ID`：shadow-router reserve 的 controller session id，从 binding row 读
- `REPLACE_WITH_TASK_ID` / `REPLACE_WITH_APPROVED_DIGEST`：路线 3 先空着，看 delivery-consumer 没 checks 时能不能起

### 块 2：HITL gate（唯一真要新加的状态）

project-controller 现在 `plan → start` 是 host 直接走的，没人批。要在中间加一步：

- `plan` 出 task → 状态停在 `planned`（不是直接 `assigned`）
- 等用户在看板上点"批准开工"
- 用户点 → 调 `start` 才进 `assigned → developing`

这是 v2 唯一新增的状态逻辑。设计时要回答：
- 批准动作走哪个 RPC（新加 shadow RPC？还是复用 shadow-router 的工具面？）
- 用户批准怎么注入 Shadow session（model-visible ⟺ logged）
- 超时未批怎么办（默认拒？默认放？）

### 块 3：跨 workspace task board UI

project-controller 有 task 状态，但前端没做。要在 conversation surface 里加看板视图，聚合多个 workspace 的 task board。

- 不是改 ShadowCard（它是侧栏触发按钮）
- 是在 conversation surface（点开 Shadow 后看到的聊天界面）加看板面板
- 六列映射 project-controller 现有状态：
  - Backlog = planned
  - To confirm = 等 HITL 批
  - Building = developing
  - To review = reviewing
  - Done = submitted / integrated

UI 走蓝白视觉体系，单一主 CTA（批准开工），模块聚合。

### 块 4：model-visible ⟺ logged

用户在卡片上的 approve / review 动作必须是 model-visible 的——Shadow 主 agent 要知道"哪张工单被批了"。走 shadow-bridge 的 exactly-once 前向通道（已有），payload 带 taskId + decision。

## v1 硬伤 → v2 解法对照

| v1 P0 硬伤 | v2 怎么解 |
|---|---|
| ShadowCard 现状认知错 | 已读源码确认是侧栏触发按钮，看板加在 conversation surface |
| building→reviewing 无事件 | project-controller 的 task 状态机自己管，task 持久化在 project_tasks 域，UI 直接投影，不依赖 shadow-routing emit |
| 一 workspace 一 binding 并发错 | project-controller 的 maxActiveTasks=2 服务端强制，不依赖"两 controller session"假设 |
| worktree node_modules 前提错 | 用 worktree-registry，它已经处理路径规范化和锁，node_modules 问题后续在 worker 启动脚本里解 |
| 自己手搓 worktree | 用 worktree-registry（已注册、bind、commit 限定路径） |
| cancelTodo 无 RPC | v2 先不做 cancel，task 有 blocked/failed 状态可标记 |
| intervalMs 60→50 理由错 | 沿用 60000，不编理由 |

## 后续 agent 必读文件（按顺序）

1. 本文
2. `docs/working/shadow-todo-board-review.md`（22 条硬伤全文）
3. `docs/working/shadow-todo-board-design.zh.md`（v1，看思路但别照搬）
4. `apps/cli/config/examples/shadow-loop/cordis.patch.yml`（闭环 composition 示例）
5. `packages/experimental/project-controller/README.md`（task 状态机、工具面、配置项）
6. `packages/workflow/worktree-registry/README.md`（worktree API）
7. `packages/experimental/shadow-routing/src/service.ts`（只 emit received，completeDelivery 无事件——v2 不依赖这个）
8. `packages/experimental/client-ui-shadow-entry/src/client/ShadowCard.tsx`（侧栏触发按钮现状）
9. `apps/desktop/scripts/development-project.ts`（devframeOverlay patch 构建处，要加 row 的地方）

## 环境与操作

- 仓库根：`D:\dsh-devframe`，分支 `feat/desktop-quality-fixes`
- 桌面端启动：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-launch.ps1`
- 启动命令：`corepack pnpm --dir apps/desktop run start`
- 运行日志：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-run.log`
- Web UI：127.0.0.1:3080（token 从日志 `dsh web: http://127.0.0.1:3080/?token=...` 取）
- DSH_HOME：`C:\Users\25313\.dsh`

## 已完成、不要重做

- 4 个外部插件（dsh-usage-monitor / codex-sidebar / external-agents / model-switch）已接入桌面端 `development-project.ts`，**未 commit**，用户说本地用不污染 PR。后续 agent 不要动这块，也不要 commit。

## 未决问题（v2 设计时必须回答）

1. HITL gate：plan 后停在 `planned`，用户批准走什么 RPC？
2. 跨 workspace 聚合：Shadow 怎么读多个 project-controller 的 task list？有没有现成 API，还是要新加？
3. requiredChecks 空着时 delivery-consumer 能不能起？要不要先空着 reviews 让 Lead 直接看 diff？
4. controllerSessionId 从 shadow-router 哪个 binding row 读？
5. 看板 UI 放在 conversation surface 的哪个位置（侧栏？顶部 tab？右侧面板？）

## 用户偏好（必须遵守）

- 开发流程：先出计划 → 子 agent 审核 → 执行 → 子 agent 验收，不跳步
- 完全访问模式，先落地不满意回滚
- UI 蓝白视觉体系，模块聚合、单一主 CTA、统计指标收敛
- 排障直击根因和真实报错，改完用真实界面截图验证
- 4 个外部插件是独立第三方包，不要当项目资产
