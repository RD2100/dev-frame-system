# Shadow 任务看板（Todo Board）设计草案

状态：草案 · 待评审
日期：2026-09-20
关联：影子子系统（shadow-router / shadow-controller / shadow-bridge / client-ui-shadow-entry）
外部参考：[todos.dev](https://todos.dev/) 的六列看板形态

---

## 1. 概要设计

### 1.1 目标

把影子从"一个和人对话的主 agent + 自由文本派活"升级为"任务看板驱动的多 agent 工作台"：

- 每个工作单元（todo）有编号、有 plan、有独立 transcript、有 token 累计；
- 每个 todo 走一条明确流水线：**计划 → 等人确认 → 干活 → 评审 → 完成**；
- 用户在 Shadow 卡片上看见的不是聊天记录，而是一张看板：哪些活在计划、哪些在等他批、哪些在干、哪些在等他 review；
- 工人在独立 worktree 里干，互不踩、干完可清理；
- 保留现有三遍持久化（queued/received/completed）和重启恢复，不推翻重来。

### 1.2 非目标（本次不做）

- 跨机器 executor（`tds start` 式注册）——远期方向；
- 任务依赖 DAG（"B 等 A 的 PR 合并"）——等真出现再上；
- 预算硬顶（per-delivery token ceiling / controller 数上限）——单独一个预算议题；
- 替换 Todos.dev 或任何外部产品——只借鉴它的看板形态。

### 1.3 核心概念对照

| 概念 | 现状 | 本次之后 |
|---|---|---|
| 工作单元 | `ShadowDeliveryRecord`（一段 text 发给 controller） | **Todo**：有编号、plan、状态机、transcript 链接、token 累计；delivery 是 todo 在"开工"阶段的投递事实 |
| 主 agent | Shadow（和人对话） | Shadow = Chief：只拆任务、派活、跟踪，不写代码 |
| 工人 | 每个 workspace 一个 controller session | 工人可以是本地 controller，也可以是外部 agent（Codex/Claude Code，经 dsh-external-agents） |
| 验收 | controller 自己 `completeDelivery` | 新增 reviewer 阶段：工人报告完成 → 独立 reviewer 跑验收 → 通过才 done |
| 用户介入 | 只能事后翻聊天 | To-confirm（plan 等人批）+ To-review（结果等人看）两个明确 gate |
| 前端 | ShadowCard 显示 shadowSessionId 状态 + 会话窗口 | ShadowCard 升级为看板：六列、卡片、点卡片看 plan/diff/transcript |

### 1.4 状态机

现有 delivery 状态（`shadow-routing/src/types.ts:42`）：

```
queued → received → completed
                  ↘ cancelled
```

本次扩展为 todo 状态机（delivery 仍保留原状态，todo 状态是它的上层编排）：

```
            ┌─────────────→ cancelled
            │
planned → awaiting_approval → building → reviewing → done
   │            │              │            │
   └── 取消 ────┴── 取消 ──────┴── 取消 ────┘
```

映射到 Todos.dev 看板列：

| 看板列 | todo 状态 | 含义 |
|---|---|---|
| Backlog | （未落库） | Shadow 脑子里的候选，不持久化 |
| Planning | `planned` | Shadow 写好 plan，还没等人确认 |
| To confirm | `awaiting_approval` | plan 已提交，等用户点确认 |
| Building | `building` | 工人在独立 worktree 里干（对应 delivery `received`） |
| To review | `reviewing` | 工人报告完成，reviewer 在看 / 等人看 |
| Done | `done` | reviewer 通过 + 用户（可选）确认 |

保留 `cancelled`：任意阶段可取消，保留可见。

### 1.5 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  Shadow Card (前端)                                      │
│  ┌──────┬──────┬────────────┬──────────┬─────────┬────┐ │
│  │Plan- │To conf│ Building   │ Reviewing│ Done    │ ...│ │
│  └──┬───┴───┬──┴─────┬──────┴────┬─────┴────┬────┘  │
└─────┼───────┼────────┼───────────┼──────────┼─────────┘
      │       │        │           │          │
      └───────┴────────┴───────────┴──────────┘
                  ctx.remote.shadow/*  (RPC)
                      │
┌─────────────────────┴───────────────────────────────────┐
│  ShadowController (host)                               │
│  - listTodos()            看板聚合                      │
│  - getTodo(id)            详情（plan/diff/transcript）  │
│  - approveTodo(id)        用户批 plan                  │
│  - rejectTodo(id, note)   用户驳 plan                  │
│  - reviewTodo(id, verdict) 用户/reviewer 验收          │
│  - cancelTodo(id, reason) 取消                          │
└─────────────────────┬───────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   shadow-router  reviewer      worker controller
   (delivery 持久化)  (新)       (现有, 每 workspace 一个)
```

---

## 2. 详细设计

### 2.1 数据模型

**新增 `ShadowTodoRecord`**（存 `shadow_todos` storage domain，与现有 `shadow_router` 平级）：

```ts
interface ShadowTodoRecord {
  // 身份
  readonly todoId: string              // `T-0001` 风格自增编号
  readonly workspaceId: WorkspaceId    // 所属项目
  readonly createdAt: string          // ISO

  // 计划（planned 时写入）
  readonly title: string               // 一句话标题
  readonly goal: string                // 1-3 句交付物描述
  readonly context: string             // 基提交 / 分支 / 相关文件 / 已知失败
  readonly constraints: string[]      // 不许碰的文件 / 不许做的事
  readonly exitCriteria: string[]     // 必跑命令 + 预期结果
  readonly outputContract: string       // 完成后回什么（结构化）
  readonly assignedAgent: 'local' | 'codex' | 'claude'  // 工人选择

  // 状态机
  readonly state: ShadowTodoState      // planned | awaiting_approval | building | reviewing | done | cancelled
  readonly updatedAt: string
  readonly approvedAt?: string         // awaiting_approval → building 的时刻
  readonly reviewedAt?: string         // reviewing → done 的时刻
  readonly doneAt?: string

  // 关联
  readonly deliveryMessageId?: ShadowMessageId  // building 阶段对应的 delivery
  readonly worktreePath?: string       // 任务级 worktree 路径
  readonly reviewerVerdict?: 'passed' | 'rejected'  // reviewer 结论
  readonly reviewNote?: string         // 驳回时的结构化意见

  // 成本（聚合）
  readonly tokensIn?: number
  readonly tokensOut?: number
  readonly startedAt?: string
  readonly finishedAt?: string
}
```

**对现有 `ShadowDeliveryRecord` 的影响**：不改字段。`building` 阶段的 todo 通过 `deliveryMessageId` 关联到现有 delivery，delivery 的 `completed` 事件触发 todo 进入 `reviewing`。

### 2.2 状态机迁移规则

| 当前状态 | 事件 | 下一状态 | 谁触发 | 持久化 |
|---|---|---|---|---|
| （无） | Shadow 写完 plan | `planned` | Shadow 工具 | insert row |
| `planned` | Shadow 提交 plan 等批 | `awaiting_approval` | Shadow 工具 | update |
| `awaiting_approval` | 用户点"确认" | `building` | 用户 RPC `approveTodo` | update + 发 delivery |
| `awaiting_approval` | 用户点"打回" | `planned` | 用户 RPC `rejectTodo` | update + reviewNote |
| `building` | worker 报告完成（delivery completed） | `reviewing` | bridge 监听 delivery 事件 | update |
| `reviewing` | reviewer 通过 | `done` | reviewer RPC | update + worktree 清理（可选） |
| `reviewing` | reviewer 驳回 | `building` | reviewer RPC | update + 把意见作为新 delivery 发回 |
| 任意 | 取消 | `cancelled` | Shadow/用户 | update + 取消关联 delivery |

**非法迁移必须 fail loud**：例如从 `planned` 直接到 `done`、从 `done` 到任何状态，抛 `SHADOW_INVALID_TRANSITION`。

### 2.3 工人执行（building 阶段）

- `approveTodo` 时：
  1. 在 `authorizedRoots/<workspaceId>/.shadow-worktrees/<todoId>/` 创建短命 worktree（`git worktree add`）；
  2. 记录 `worktreePath`；
  3. 把 plan 包成一条 `work` delivery 发给对应 workspace 的 controller，`text` 里带上 worktree 路径 + 全部 plan 字段；
  4. todo 进入 `building`。
- controller 在 worktree 里干活，干完正常走 `completeDelivery`；bridge 监听 delivery 事件，把 todo 推到 `reviewing`。

**业界坑预防**：
- pnpm workspace 的 `.pnpm` 是共享 store，worktree 里 `node_modules` 走符号链接即可解析；不重复 install；
- worktree 里未提交改动在取消/完成时必须提示用户（git status），不能静默 `git worktree remove --force`。

### 2.4 reviewer 阶段

- reviewer 是一个**新 controller profile**（不是 Shadow、不是 worker）：
  - 工具集只有：read / grep / bash（跑 exitCriteria）、read_image；
  - 模型默认强模型（和 Shadow 同档）；
  - 输入：todo 的 plan + worktree 路径 + worker 的总结；
  - 输出：`{ verdict: 'passed' | 'rejected', note: string }`。
- reviewer 跑 `exitCriteria` 里每条命令：
  - 全过 → `passed` → todo `done`；
  - 任一失败 → `rejected`，note 里写哪条命令、什么错、建议改哪 → todo 回 `building`，note 作为新 delivery 发回 worker。
- **同一 todo 最多自动回退 2 次**，第 3 次 reviewer 仍 reject → todo 停在 `reviewing`，Shadow 卡片高亮，等用户介入。

### 2.5 用户 gate（awaiting_approval / reviewing）

- `awaiting_approval`：Shadow Card 的 To-confirm 列出现卡片，展示 plan 全文，两个按钮：**确认开工** / **打回**。
- `reviewing`：To-review 列出现卡片，展示 worker 总结 + reviewer 结论，按钮：**通过** / **打回**（用户可覆盖 reviewer 结论）。
- 卡片点击打开 todo 详情抽屉：plan、worktree diff、transcript 链接、token 累计。
- 两个 gate 都支持离线操作——用户 3 天后来点，状态不丢（全持久化）。

### 2.6 前端 ShadowCard 改造

现状：ShadowCard.tsx 显示 shadowSessionId + 会话窗口。
本次：
- ShadowCard 主视图改成看板（六列），每列卡片显示：编号、标题、assignedAgent、updatedAt；
- 保留一个"和 Shadow 对话"的输入框（看板顶部）；
- 点卡片打开详情抽屉；
- To-confirm / To-review 列的卡片右上角有红点提醒。

**复用现有 presenter 模式**：shadow-presenter.ts 已经做"从 host status 投影到 UI 模型"，本次加一个 `buildTodoBoard(hostState)` 投影函数。

### 2.7 Shadow 系统提示更新

在 Shadow 的系统提示（controllerProfile 的 system prompt）里加：

1. "你是 Chief，不写代码。你的工具只有：planTodo / approveTodo（内部）/ listTodos / 派发给工人。"
2. "每个 plan 必须包含：goal（一句话）、context（基提交、相关文件）、constraints（不许碰什么）、exitCriteria（必跑命令）、outputContract（回什么）。"
3. "不要把多个工作塞进一个 todo；每个 todo 一个交付物。"
4. "工人报告完成后，不要自己验收——reviewer 会做；你只看 reviewer 结论和用户是否需要介入。"

### 2.8 配置（cordis.patch.yml）

```yaml
- id: shadow-bridge
  config:
    intervalMs: 50000          # 从 60000 降到 50000，避开 ALB 60s 阈值
    followupMaxChars: 12000
- id: shadow-todo-board       # 新插件
  config:
    maxAutoRejects: 2          # reviewer 自动回退上限
    worktreeRoot: '.shadow-worktrees'  # 相对于 authorizedRoots
    reviewerProfile: 'shadow-reviewer'
```

---

## 3. 测试用例

### 3.1 状态机迁移（shadow-routing 侧单测）

| # | 用例 | 前置 | 动作 | 预期 |
|---|---|---|---|---|
| S1 | 正常全链路 | 空 | Shadow 写 plan → 提交 → 用户批准 → worker 完成 → reviewer 通过 | todo 依次 planned→awaiting_approval→building→reviewing→done，每步落库 |
| S2 | 打回 plan | awaiting_approval | 用户 rejectTodo("这个文件不许碰") | 回 planned，reviewNote 记录 |
| S3 | 非法迁移拒绝 | planned | 调 completeTodo | 抛 SHADOW_INVALID_TRANSITION |
| S4 | done 不可逆 | done | 调 rejectTodo | 抛错，状态不变 |
| S5 | reviewer 驳回回退 | reviewing | reviewer rejectTodo("test auth/ 没过") | 回 building，note 作为新 delivery 发给 worker |
| S6 | 自动回退上限 | building（已回退 2 次） | 第 3 次 reviewer reject | 停在 reviewing，不自动再回，Shadow 卡片高亮 |
| S7 | 任意阶段取消 | building | cancelTodo("不做了") | 到 cancelled，关联 delivery 一起取消 |
| S8 | 取消保留可见 | cancelled | listTodos | cancelled 的行仍列出，cancelReason 显示 |

### 3.2 持久化与恢复

| # | 用例 | 预期 |
|---|---|---|
| R1 | 进程重启时 todo 在 `awaiting_approval` | 重启后看板仍显示 To-confirm 列那张卡，用户可继续批 |
| R2 | 进程重启时 todo 在 `building` | bridge 重新 reconcile，未完成的 delivery 不丢 |
| R3 | 进程重启时 todo 在 `reviewing` | reviewer 会话恢复，继续看 |
| R4 | 半写状态崩溃 | 任意一步写入失败重启后，状态收敛到上一个合法状态，不出现半新半旧 |
| R5 | 旧 delivery 无 todo | 老版本升级后，历史 delivery 仍能列出来，不报错 |

### 3.3 并发与隔离

| # | 用例 | 预期 |
|---|---|---|
| P1 | 两个 todo 同时 building | 两个 worktree 独立，文件互不影响 |
| P2 | 同 workspace 两个 todo | 两个 controller session 并存（现状），worktree 不同目录 |
| P3 | 第三个 todo 想进 building 但 worktree 已被占 | 不允许同一 worktree 同时两个活，报错提示 |
| P4 | cancel 一个 worktree | `git worktree list` 不再显示它；未提交改动先 stash 提示 |

### 3.4 reviewer 与 gate

| # | 用例 | 预期 |
|---|---|---|
| G1 | exitCriteria 全过 | reviewer 自动 passed |
| G2 | exitCriteria 一条失败 | reviewer rejected，note 写命令+错误 |
| G3 | 用户覆盖 reviewer | reviewer rejected 后用户点"通过"，todo 直接 done |
| G4 | awaiting_approval 长时间无人点 | 不超时、不自动批；卡片一直等 |
| G5 | worker 报告"完成"但没跑 exitCriteria | reviewer 视为未过，打回 |

### 3.5 前端（client spec）

| # | 用例 | 预期 |
|---|---|---|
| U1 | 看板六列渲染 | 每列对应状态，卡片按 updatedAt 倒序 |
| U2 | To-confirm 卡片红点 | awaiting_approval 状态卡片右上角红点 |
| U3 | 点卡片开抽屉 | 显示 plan、worktree diff、token 累计 |
| U4 | 用户点"确认开工" | RPC approveTodo，卡片移到 Building 列 |
| U5 | Shadow 对话输入框 | 发消息给 Shadow，不影响看板 |
| U6 | 空状态 | 没 todo 时每列显示空态文案 |

### 3.6 集成（keyless snapshot）

| # | 用例 | 预期 |
|---|---|---|
| I1 | 跑一个完整 plan→confirm→build→review→done 循环 | 会话日志里每步都有事件，UI 看板逐列移动 |
| I2 | 取消中途 work | worktree 被清理，delivery 列 cancelled |
| I3 | 外部 agent 工人（Codex） | assignedAgent='codex' 时走 dsh-external-agents 通道 |

---

## 4. 落地分期

**第 1 期（纯增量，不动状态机）**：todo 数据模型 + Shadow 系统提示 + 看板 UI（只读，从现有 delivery 投影）。先看得见。
**第 2 期**：planning/awaiting_approval 两态 + approveTodo/rejectTodo RPC + worktree 创建。
**第 3 期**：reviewing 态 + reviewer profile + 自动回退 + worktree 清理。
**第 4 期**：token 聚合、看板细节、29 分钟心跳调参（bridge intervalMs 60→50）。

每期独立可上线、可回滚。
