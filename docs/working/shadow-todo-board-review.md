# Shadow 任务看板设计 · 三方独立审核报告

- **待审设计**：`docs/working/shadow-todo-board-design.zh.md`
- **审核方式**：3 个独立审核员并行读设计文档 + 对照仓库源码，互不参考，2/3 多数决
- **审核日期**：2026-09-20

## 投票汇总

| 审核员 | 视角 | 结论 | 关键依据（一句话） |
|---|---|---|---|
| A | 架构与一致性 | **打回** | building→reviewing 触发信号在源码里不存在；取消 delivery 无对应 RPC；多轮回退数据模型撑不住；locale / SCHEMA_VERSION / session event 三条仓库硬约束未覆盖 |
| B | 工程与落地 | **打回** | §2.3 对 pnpm worktree 的前提判断与代码事实相反；状态机缺 integrate/merge 步骤；崩溃恢复按现有 exactly-once 机制会挂死；§2.8 intervalMs 改动理由不成立；无视仓库已有的 `dsh-worktree-registry` 与 `project-controller` |
| C | 产品与 UX | **打回** | 用户原话 5 痛点里"花超自己停"被主动划为非目标、"进度看得见"第 1 期是空架子；§2.7 给了 Shadow 一个自相矛盾的 `approveTodo` 工具；§2.6 对前端现状的描述与实际源码不符 |

**总体结论：打回（3:0）。** 概念方向（todo 正交叠加在 delivery 之上）三方均认可，但设计与现有源码的接缝、仓库硬约束、用户痛点兑现度三处都有硬伤，必须出 v2 后再审。

---

## v2 必须修改的硬伤（按优先级合并去重）

下列条目至少被一名审核员标【严重】，其中带 **【三方交叉】** 的是至少两人独立发现、可信度最高。

### P0 · 与现有源码接缝对不上（不改就无法落地）

1. **【三方交叉】§2.6 对"前端现状"的描述与源码不符** — 实际 `ShadowCard.tsx` 是侧栏 footer 里的触发按钮（icon + status dot + manage dropdown），点击打开 conversation surface，卡片本身不渲染会话、没有输入框。设计写"现状显示 shadowSessionId + 会话窗口，保留一个对话输入框"是把 conversation surface 错当成了卡片。（A、C 独立发现）
2. **【三方交叉】§2.5 / §2.6 按钮文案未走 locale dictionary** — "确认开工 / 打回 / 通过"写死中文；现有 presenter 注释明写 "No locale text is produced here; keys are data"，全部走 `t(ShadowKey)`。AGENTS.md 硬约束：Client UI copy is locale-owned。必须补 locale key 设计（含英文）。（A、C 独立发现）
3. **§2.2 / §1.4 building→reviewing 没有可监听的事件** — `shadow-routing` 只 emit `shadow/delivery-received`；`completeDelivery` 是 host-plane 调用、**没有事件**；bridge 自己声明 "registers no session events"。设计假设的"bridge 监听 delivery 完成事件推 todo 到 reviewing"在现有代码里没有信号可听。v2 必须明确：要么新增 `shadow/delivery-completed`（改 service.ts emit），要么 todo 插件轮询 `listDeliveries`。
4. **§2.2 `cancelTodo` 没有对应 RPC 动词** — router 表面只有 `stopProject`（停整个项目）和 `recoverDeliveries`（清 stale 行），没有 cancel-one-delivery。"取消关联 delivery"无处调用。
5. **§2.1 数据模型撑不住 §2.4 的多轮回退** — 记录只有单个 `deliveryMessageId` / `reviewerVerdict` / `reviewNote`，但 §2.4 允许自动回退 2 次 + 用户打回，**每次回退都发一条新 delivery**（§2.2 末行）。`ShadowTodoRecord` 里没有 `autoRejectCount` 字段、没有 delivery 轮次列表，而 §3.1 S6 明确依赖"已回退 2 次"计数。另 S8 要显示 `cancelReason`，record 里也没这字段。
6. **§3.1 P2 / §1.3 并发假设与现有架构相反** — 设计假设"同 workspace 两个 todo = 两个 controller session 并存"。实际 `shadow_router` 刻意**一个 workspace 一个 binding、一个 controllerSessionId**，重复 `openProject` 去重。两个 building todo 在同 workspace 实际挤同一个 controller 会话/agent loop；per-todo worktree 只隔离文件，不隔离执行。§3.3 的并发正确性测试建立在错误前提上。
7. **§2.3 worktree 里"node_modules 走符号链接直接解析"是错的** — 仓库 `node_modules` 被 gitignore、未被 git 跟踪，`git worktree add` 不会带过来任何 `node_modules`，pnpm 虚拟 store 根本不存在。且仓库已有 `packages/workflow/worktree-registry` 解决了 worktree 登记与依赖落点，§2.8 自己手搓 `.shadow-worktrees/<todoId>` 会造成两套真值源。v2 要么直接复用 `worktree-registry`，要么明确写"worktree 内必须 `pnpm install`（全局 content-store 硬链接）"并把成本计入。

### P1 · 仓库硬约束未覆盖

8. **【三方交叉】"model-visible ⟺ logged"未覆盖** — 用户在卡片上 approve / reject / reviewTodo 是 Chief Shadow 可见的输入，设计通篇没定义任何注入 Chief session 的事件。§3.6 I1 把"会话日志里每步都有事件"当测试期望，但 §2 根本没有事件设计——Chief 重启后无从知道哪张卡被批了。
9. **【三方交叉】monotonic SCHEMA_VERSION 未覆盖** — §2.1 新建 `shadow_todos` 存储域，只字未提 schema migration / 版本 bump；§3.2 R4 只讲崩溃收敛，不讲老版本升级后的表迁移。按仓库 pre-release 立场，后端拒绝旧磁盘格式。
10. **§2.7 只改系统提示、没碰真正的执行面** — Shadow 的工具白名单是 `shadowSetup` 里的 `SHADOW_EXECUTION_ALLOWLIST` + `shadowAllowlistGuard`，不在白名单的工具直接被拒。新增 `planTodo/listTodos` 必须同步进 allowlist，光改 prompt 不生效。
11. **§2.8 fail-loud 边界缺失** — `reviewerProfile` 指向不存在的 profile、`worktreeRoot` 不可写时怎么失败，未写；§2.2 只对非法状态迁移 fail-loud 了。

### P1 · 状态机与恢复语义不完整

12. **§2.2 / §2.4 状态机没有 integrate/merge 步骤** — `reviewing→done` 只是"worktree 清理（可选）"，工人在短命 worktree 分支上的 commit 没有任何环节合回基线，"done"时代码从未落地。而同仓库 `project-controller` 已经有 `project_integrate`（fast-forward/merge）闸门（见 `cordis.patch.yml`）。v2 必须在 `reviewing→done` 之间加 integrate 一步（失败回 reviewing），或明确声明"done = PR 待人工合并"并保留 worktree 直到合并。
13. **§3.2 R2 崩溃后 in-flight building 的续跑策略未定义，且按现有机制会挂死** — bridge 用 `shadow_bridge` 的 `forwarded` 表做 exactly-once，崩溃前 delivery 已 `received` 且已入 `forwarded` 表 → 重启 reconcile 会跳过它，worker session 已死无人再触发，todo 永久停在 `building`。R2 只断言"delivery 行不丢"，没断言续跑。v2 必须三选一：resume worker / 回 `queued` 重投 / 置 `needs_attention`，并加一条"building 中途杀进程"用例。
14. **§2.8 `intervalMs` 60000→50000 理由不成立，建议整段删掉** — 已读 `loop.ts`：它是**进程内 `setTimeout` 安全网**，无任何网络/ALB 路径；线上 `cordis.patch.yml` 注释明写 "60s is ample because live latency does not depend on it"。改它既不提升看板刷新（看板靠 `listTodos` RPC 客户端刷新），也不存在"ALB 60s 阈值"可避。且与 §4"29 分钟心跳调参"自相矛盾（60000ms = 60s，不是 29 分钟）。要看板更实时就调前端轮询，别动 bridge 安全网。

### P1 · 用户痛点兑现度

15. **§1.2 把"花超自己停"主动划为非目标** — 用户原话 5 痛点里这一条 0 解决。§4 第 4 期才做"token 聚合"且只是显示不是熔断。v2 至少加一个软告警（超 N% token 时卡片黄底提醒），否则"花超自己停"这个痛点完全缺席。
16. **§2.6 "进度看得见"只解决一半** — 看板只显示 `updatedAt`，building 阶段工人当前在改哪个文件、跑了哪条命令、卡在哪一步，看板上一概不可见。用户能看到的是"状态列"，不是"进度"。v2 至少给 building 卡片加一行 live status（当前 git branch / 最近一条命令），5 秒轮询一次即可。
17. **§2.7 给了 Shadow 一个自相矛盾的 `approveTodo（内部）` 工具** — §2.5 / §2.2 明确是用户点按钮才 approve；如果 Shadow 自己能 approveTodo，awaiting_approval gate 形同虚设。v2 删掉 Shadow 的 approveTodo 工具，或明确写"Shadow 只能提交 plan，不能自己批准"。
18. **§2.7 Shadow 什么时候该派 todo、什么时候直接聊——没有触发规则** — 只说"你是 Chief，工具是 planTodo/listTodos/派发"，没说什么粒度的事开 todo、什么粒度直接在对话里答。v2 在提示词里加一条触发规则（"用户明确要求改动/交付物时才开 todo；查询、解释、浏览类直接回答"）+ 2-3 个正/反例。

### P2 · 工程与测试覆盖

19. **§3.3 并发用例缺两条关键路径**：(a) 用户 cancel 时工人 bash 正在跑——§2.2 只说"取消关联 delivery"，没说杀掉正在执行的子进程与 worktree 残留；(b) 工人 controller 在 building 中途 stop/rebind，todo 如何暴露 `blockedReason` 而不是静默挂起。
20. **§3 用例在原生 Windows 上不是真跑** — P1–P4、I2 涉及真实 `git worktree`、pnpm 符号链接、深路径，本仓 CI 的 Windows 腿是 `check:windows-wine` / `ci-windows-observational`（observational，不阻塞）。原生 Windows 建符号链接需 Developer Mode/管理员，且 `D:\...\.shadow-worktrees\<todo>\node_modules\.pnpm\<deep>` 极易撞 MAX_PATH 260。v2 加一条 windows-blocking 冒烟，并在 §2.3 写明 Developer Mode / 长路径要求。
21. **§2.4 `maxAutoRejects: 2` 无论证** — 为什么是 2 不是 1/3 没说；也不区分"exitCriteria 环境性抖动/flaky"与真·工人缺陷。第 3 次行为（停 reviewing + 高亮 + 等人）已写清，可接受；撞上限时应把"已回退次数 + 末次失败命令"显式带给用户。
22. **§4 第 1 期"进度看得见"是空架子** — 第 1 期说"看板 UI（只读，从现有 delivery 投影）"，但现有 delivery 只有 queued/received/completed/cancelled 四态，映射到六列看板时 Planning/To-confirm/To-review 三列永远是空的。用户第一期打开看板看到的就是"把现有聊天里的 delivery 重新排了四列"——没有 plan、没有 gate、没有 reviewer，痛点①②③⑤一个都没触达。v2 要么把第 2 期的 awaiting_approval gate 提前到第 1 期，要么明确写"第 1 期只是视觉预览，不解决任何痛点"。

---

## 三位审核员的独立意见摘要

### 审核员 A · 架构与一致性（打回）

概念定性上：todo 是**正交叠加**在 delivery 之上（设计自己声明"delivery 保留原状态，todo 是上层编排"），自洽，不是平层扩展也不是覆盖。问题不在定性，而在两个耦合点正好踩在缺失信号上：

- building ≈ delivery received（send 即 received，OK）
- reviewing ≈ delivery completed（**接不上**，见硬伤 #3）

额外建议（非阻塞）：
- §1.5 新 RPC（listTodos/getTodo/approveTodo/reviewTodo/cancelTodo）是新增 @Remote 动词，谁持久化 todo、是否复用现"designated Shadow caller gate"、用户卡片动作要不要 requestId/replay、cordis catalog 要不要重新生成——均未提。
- §1.3 / §3.6 I3 外部 agent 工人（`assignedAgent: 'codex'|'claude'`）走 dsh-external-agents，但 `sendToProjectForHost` 那套（goalId/acceptanceHash/bindingRevision）是为本机 provisioned controller 会话设计的，外部 agent 如何投递、如何回完成，完全没展开。
- 硬约束其余几条（ESM/strict TS、`ctx.effect/ctx.on` 注册、closed union `assertNever`、per-file 100% 覆盖门、非平凡变更带 Agent Note）设计均未显式呼应；`assignedAgent` 已是好的 closed union 样例，但 `ShadowTodoState` 没有对应的穷尽 switch/assertNever 设计。
- §4 分期：第 1 期已渲染的看板数据到第 2 期如何回填/迁移到 `shadow_todos`，未提。注：`followupMaxChars` 在现有 schema 已是 required 字段，不是新增。

### 审核员 B · 工程与落地（打回）

对六个必答问题的直答：

1. **worktree 路径安全吗？** 不安全。未提交改动有提示（可接受）；pnpm 符号链接前提错误（严重）；Windows MAX_PATH/符号链接特权无对策；未推送/未合并分支的清理未写。
2. **§3.3 / §3.2 用例够吗？** 不够。缺：运行中任务的中途取消（子进程回收）、building 期间 controller 重连/rebind；且 R2 不验证真正的续跑/回滚，只验证行不丢。
3. **reviewer 2 次上限合理吗？** 第 3 次行为已讲清（停 reviewing 高亮），可接受；但"为何是 2"无论证，且未处理 flaky 命令误判，属建议级。
4. **intervalMs 现状/必要性？** 现状确为 60000（`cordis.patch.yml:78`、README）。改它**没必要**：它是本地兜底定时器，与看板刷新、与任何 ALB 无关，理由是编的，且与 §4 矛盾。
5. **持久化恢复 in-flight building？** 没写清——既非续跑、也非回滚/重队列；按现有 exactly-once 前向表，实际会**挂死在 building**。
6. **§3 用例能在 Windows 真跑吗？** 不能算真跑。worktree/符号链接/路径用例落在 observational/wine 腿上，原生 Windows 行为（符号链接权限、MAX_PATH）无阻塞性覆盖。

额外发现（重要）：仓库已有 `packages/workflow/worktree-registry` 和 `project-controller`（含独立 review lead + `project_integrate` merge 闸门）两套现成体系，新设计完全没引用，存在重复造轮子。

### 审核员 C · 产品与 UX（打回）

对用户原话 5 痛点的兑现度：

- ①"改完要先给工单" — 解决到位，但 §1.1 / §2.2 措辞有歧义：用户原话"改完要先给工单"更像"做完一件事先出工单再继续下一件"，设计实际做的是"开工前审批"。建议 §1.1 明确写"开工前先出 plan 等批"。
- ②"干完有质检" — §2.4 reviewer 自动回退设计扎实，不展开。
- ③"动手前问你" — §2.5 gate 设计方向对，但"要求修改"这个动作在 UI 上不存在：状态机有 `rejectTodo(note)` 带 reviewNote，UI 只说两个按钮"确认开工/打回"——点"打回"后用户能输入修改意见吗？还是打回就完事了？v2 明确"打回"按钮点击后弹出 note 输入框。
- ④"花超自己停" — **0 解决**（见硬伤 #15）。
- ⑤"进度看得见" — **只解决一半**（见硬伤 #16）。

额外 UX 意见：
- §2.6 老用户从聊天切看板的过渡完全没讲：现在用户点 Shadow 按钮看到的是完整聊天窗口；改成看板后，点按钮看到什么？看板是全屏、侧栏、还是新 tab？原来的聊天历史在哪里看？建议加一节"视图迁移"，明确看板和对话是两个 tab 还是左右分栏、历史对话怎么回溯、第一次打开看板有没有引导。
- gate 提醒的触达方式没讲：用户不打开看板时怎么知道 To-confirm 列有东西？现有 sidebar trigger 有 status dot，会不会因为有待批 gate 而变红/加 badge？
- §3.5 / §3.6 UX 测试缺：用户 rejectTodo 后 Shadow 重提 plan，UI 怎么体现"这是第二版 plan"？用户 3 天没看打开看板有没有汇总提示？同列 5 个 building todo 怎么排序？点"确认开工"RPC 往返期间按钮 disabled 吗？失败了 toast 还是原地重试？

---

## v2 再审建议

不必等所有 P2 都改完才送审，但 P0（硬伤 1–7）和 P1（硬伤 8–18）必须在 v2 里出现明确回应。其中三处"认知错误"建议作者在送 v2 前亲自 Read 一遍对应源码确认：

1. `packages/experimental/client-ui-shadow-entry/src/client/ShadowCard.tsx` —— 现状描述
2. `packages/experimental/shadow-routing/src/service.ts` —— 事件 emit 点
3. `packages/workflow/worktree-registry` 与 `project-controller` —— 已有轮子

v2 送审时建议附一个"变更点对照表"：每条 v1 硬伤编号 → v2 落在哪一节。
