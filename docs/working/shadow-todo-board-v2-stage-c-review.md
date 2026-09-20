---
title: Shadow Todo 看板 v2 — 阶段 C 子 agent 验收结论
owner: shadow
status: reviewed-pass
date: 2026-09-21
range: feat/desktop-quality-fixes, c2e966ba88..1fb1dda0e0（主体 80db24cb17，chore 1fb1dda0e0）
based-on: docs/working/shadow-todo-board-v2-stage-c-plan.md（draft-plan-r2）、docs/working/shadow-todo-board-v2-stage-c-plan-review.md（四路评审 P0×0/P1×12/P2×9）
---

# Shadow Todo 看板 v2 — 阶段 C 子 agent 验收结论

- 验收方式：只读源码保真度核对，不改任何文件、不 commit。对提交区间 `c2e966ba88..1fb1dda0e0` 逐条打开实际文件核对，每条给 file:line 证据。
- **总结论：通过（无 P0 阻断，无遗留 P1）。** 评审 12 条 P1 全部在代码层落实；范围干净（恰好 25 文件，无夹带）；阶段 B 既有用例未被删/弱化。唯一如实缺口：验收 4 的完整真实 e2e 因宿主投递链阻塞未跑通（与 readBoard 无关），已在结论中标注。

---

## A. 逐条核对表（验收点 ↔ 证据 ↔ 判定）

### 验收 1 实现存在性

| # | 验收点 | 证据（file:line / 摘录） | 判定 |
|---|---|---|---|
| 1 | types.ts 三类型 ShadowBoardBinding / ShadowBoardTask / ShadowBoardSnapshot | `packages/experimental/shadow-controller/src/types.ts`：Snapshot `mounted/bindings/tasks`（末段）；Binding `workspaceId/state/controllerSessionId`；Task 含 `taskId/pluginId/title/state/blockedReason?/nextAction?/wakeCondition?/createdAt/updatedAt/startReady?/branch?`（新增块全字段齐） | 符合 |
| 2 | `@Remote readBoard()` 为 async 且返回 Promise；mounted:false 降级；shadowRouter 缺失；planned startReady 派生 try/catch；assigned/developing branch | `shadow-controller/src/index.ts` readBoard：`@Remote async readBoard(): Promise<ShadowBoardSnapshot>`；`if (projectController === undefined) return { mounted:false, bindings:[], tasks:[] }`；`router === undefined ? [] : router.listBindings().map(...)`；planned 分支对每个 binding `ctx.agents.get(...).then` 后 `try { resolveTaskStartAuthority(...) ; ready=true; break } catch {}`；`(record.state==='assigned'||record.state==='developing') && worktreeRegistry!==undefined && record.worktreeId!==undefined` 才读 branch | 符合（P1-1 闭环） |
| 3 | branch 采集复用 `worktreeRegistry.status()`，非自造 execFile | index.ts readBoard：`branch = (await worktreeRegistry.status(record.worktreeId)).branch ?? null`（外层 try/catch 失败→null）。无 `execFile('git',...)` 自造调用 | 符合（P1-4 闭环） |
| 3b | 5s 缓存是否仍在 | `worktree-registry/src/git-provider.ts:215-223` `status()` 内部**无缓存**：每次跑 `rev-parse --abbrev-ref HEAD` + `status --porcelain=v1` 两个 live git 子进程；readBoard 调用点也未加显式 TTL。节流改由 client 5s 轮询兜底（BoardView `POLL_MS=5000`，每次 tick 一次 readBoard）。这是 P1-4“prefer maintained API 而非自造 5s 缓存”的预期落法 | 符合（措辞澄清，见问题 P2-1） |
| 4a | delivery-consumer Config z.object + 接口 + apply 注入；空数组 fail-loud | `project-controller/src/delivery-consumer.ts`：Config `defaultCommitPaths: z.union([z.array(z.string()), z.const(undefined)])`（刻意不用裸 `z.array` 默认 `[]`，以区分“未配置”与“显式空”）；接口 `readonly defaultCommitPaths?: readonly string[]`；apply 经 `normalizeCommitPaths(config.defaultCommitPaths)` 注入，失败抛 `Invalid host default commit path scope: ...`。commit-consumer.spec：`setup({ defaultCommitPaths: [] })` rejects `Project commit requires at least one commit path` | 符合（空数组 fail-loud、undefined 跳过，语义经测试锁定） |
| 4b | approveTask `request.commitPaths ?? registry.defaultCommitPaths` 合并点 | index.ts approveTask：`const commitPaths = request.commitPaths ?? registry.defaultCommitPaths`，再 `...(commitPaths === undefined ? {} : { commitPaths })` 展开 registerTask | 符合 |
| 4c | desktop patch config 含 defaultCommitPaths | `apps/desktop/scripts/development-project.ts`：`defaultCommitPaths: ['packages/experimental/project-controller/src/index.ts']`；`development-project.spec.ts` 新增 `expect(patch).toContain(...)` 断言 | 符合 |
| 5 | client：shadow-store / BoardView / BoardToggle / mount 两处 slots / slots BoardViewInjected / locales board.* 无硬编码中文 | `client-ui-shadow-entry/src/client/`：shadow-store.ts 新增 `ShadowBoardController`（store=`{board,error}`，refresh 用 sequence 号“最新读胜出”）；BoardView.tsx（294 行六列+triage+卡片动词）；BoardToggle.tsx；mount.ts 两处 `ctx.slots.inject('conversation.view', …id:'board'…)` 与 `ctx.slots.inject('conversation.session.header.actions', …id:'shadow-board-toggle'…)`；slots.ts `BoardViewFace{ hooks:{board,status}, onRefresh, onApprove, onReject }`；locales.ts `board.*` 与 `time.*` zh/en 双语齐。BoardView/BoardToggle 文案全部走 `t(...)`，无硬编码中文 | 符合 |
| 6 | package.json 三处依赖 ui-conversation | `client-ui-shadow-entry/package.json`：`dsh.client.inject` 数组、devDependencies、第三处（peerDependencies 区）各加 `@deepseek-ai/dsh-client-ui-conversation`；pnpm-lock.yaml 仅 +3 行（importer 段新增该 workspace link，无膨胀） | 符合（P1-3 闭环） |
| 7 | register label thunk；approve 前 find 校验 planned/blocked；blocked 卡 resume→assign→startDevelopment | mount.ts：`label: () => t('board.tab')`（thunk）。index.ts approveTask：`const task = this.ctx.projectController.find(taskId)` 后 `if (task===undefined || (task.state!=='planned' && task.state!=='blocked')) throw 'approveTask requires a planned or blocked task'`；blocked 先 `await this.ctx.projectController.resume(taskId)`；随后仅当 `authority.task.state==='planned'` 才 `assign`（blocked 已被 resume 带到 assigned，跳过重复 assign），再 `startDevelopment` | 符合（P1-6 / P1-8 闭环） |

### 评审 P1 闭环逐条

| # | P1 项 | 证据 | 判定 |
|---|---|---|---|
| 8 | ShadowApproveTaskInput.commitPaths 定义位置确在 shadow-controller/src/types.ts | `types.ts:89 readonly commitPaths?: readonly string[]`（`ShadowApproveTaskInput` 块内），未改 project-contracts | 符合 |
| 9 | shadowSessionId 自检接线落地方案 | 采用 P1-5 推荐的方案 A：`BoardViewFace.hooks.status = ShadowStatusController.store`（mount.ts `boardFace()` 内 `hooks:{ board: boardController.store, status: controller.store }`）；BoardView 用 `useStatus` 读 `presentShadowStatus(status).phase`，unmounted/issue 时渲染自检横幅（`data-shadow-board-selfcheck`）。未采用“Snapshot 带 shadowSessionId”方案 | 符合 |
| 10 | 总计划缺口：#21 repairLimit、验收 9 截图、blocked resume；计划是否 r2 | plan.md frontmatter `status: draft-plan-r2`；§3 显式记录：#21 repairLimit **deferred 到阶段 D**（building 卡以 branch+updatedAt 兑现 #16 部分）；验收 9 截图**本阶段执行不 deferred**（§4.5，桌面真实启动+截图已完成）；blocked 重新批准落地为 approveTask 接受 blocked + resume 路径 | 符合 |

---

## B. 范围核对结论

- `git diff --stat c2e966ba88..1fb1dda0e0` 恰为 **25 文件**，与声称一致；无无关文件、无临时文件、无 `pnpm-lock.yaml` 异常膨胀（仅 +3 行，纯 ui-conversation workspace link）。
- 阶段 B 既有断言：`shadow-controller.host.spec.ts` 父版 **17 条 `it()`，现 27 条**（净增 10，删除 0）。唯一被改写的既有用例是“fails loud when the task is not planned”→“neither planned nor blocked”，错误文案从 `project_task start requires a planned or assigned task` 改为 `approveTask requires a planned or blocked task`——这是配合 approveTask 新契约的**有意更新而非弱化**。
- `registerTask` 只收 digest 的断言仍在：新增 blocked 重新批准用例 `expect(registerTask).toHaveBeenCalledWith('task-1', { digest: expect.any(String) })`（未带 commitPaths，因为该用例未配 defaultCommitPaths）。
- 新增 host 用例覆盖：mounted:false、shadowRouter 缺失降级（P1-11）、全量投影+稳定序（task-2 在前、task-1 在后，断言 verbatim 不重排）、startReady 失败→false（P1-10 对应）、branch 成功/失败→null/assigned 无 worktree→undefined。
- client：presenter spec 18 条（父 6 + 净增 12，含 unmounted→disabled 展示模型 P1-10）；store spec 8 条（父 4 + 净增 4）；BoardView 组件 spec 13 条全新（六列/5s 轮询/approve/置灰/reject note/re-approve/等待黄底/live branch/triage/disabled/error+retry/自检横幅/批准后移列）。spec 归属按 P1-12：presenter/store 逻辑并入既有 spec，组件渲染另起 BoardView.client.spec.tsx（合理，非双 presenter/store 并存）。
- built bundle 一致性：`shadow-controller/lib/index.js` 含 `readBoard`（7 处引用）；`client-ui-shadow-entry/lib/client.js` 含 `BoardView`（43 处引用）——桌面 bundle 与 src 一致。

---

## C. 问题清单（按级）

### P0（阻断）
无。

### P1（重要）
无遗留。评审 12 条 P1 全部在代码层落实并经测试锁定。

### P2（收尾 / 观察）
1. **branch 采集无独立显式缓存。** `worktreeRegistry.status()`（git-provider.ts:215-223）每次调用跑两个 live git 子进程；readBoard 层未加 TTL。当前靠 client 5s 轮询把 git 调用上界压到“每 5s 一轮”，v2 单 workspace、任务数少，可接受。若后续多任务/高频轮询，可在 readBoard 层对 branch 加短 TTL，避免每任务每次轮询都 spawn git。（这是 P1-4“用 maintained API 替代自造缓存”的预期代价，非新引入缺陷。）
2. **验收 4 完整真实 e2e 未完成。** 派活→plan→看板卡片→批准 的端到端真实链路停在宿主投递链（controller 会话仅 4 条基础记录、投递未落盘、controller agent 未运行），与 readBoard 实现无关。桌面真实启动 + 截图（打开对话按钮、对话/看板/轨迹三 tab、看板六列蓝白 UI）已验证。本结论如实标注该缺口，交由宿主投递链修复后补跑。
3. ~~门结果采信提交方报告~~ **已关闭（见 E 节）**：本版 A–D 为只读源码核对；门的实测复跑（测试/构建/typecheck/oxlint 全绿）见 E 节，由第二路验收员独立执行。唯一未复跑：project-controller 全包（~210s），建议合并前 CI/owner 补跑。

---

## D. 与“关键事实”的出入澄清

1. **“5s 缓存”措辞。** 关键事实/评审关注点问“5s 缓存是否仍在”——实际两层（worktreeRegistry.status 内部、readBoard 调用点）**都没有独立显式缓存**；节流由 client 5s 轮询承担。这是 P1-4 选择 maintained API 的预期结果，不构成缺失，但“缓存仍在”的说法不准确，应理解为“轮询周期即节流窗口”。
2. **“host.spec 17/17 类全绿”。** 实为父版 17 条 `it()` 全部原样保留并全绿、另净增 10 条（现 27 条），而非总数 17。无删减、无弱化。
3. 其余声称（readBoard async、commitPaths 三落点、package.json 三处、label thunk、branch 复用 worktreeRegistry.status、shadowSessionId 自检、approve 前 find 校验、blocked resume→assign→startDevelopment、空数组 fail-loud、defaultCommitPaths 注入 delivery-consumer、listTasks/find/排序语义、测试并入既有 spec）均与代码一致，未发现”声称做了但代码里没有”或”做了但方式不对”的项。

---

## E. 本次独立复跑记录（2026-09-21，只读复跑，补 C.3）

上一版 C.3 称”门结果采信报告、未独立复跑”。本次在仓库根对提交区间 `c2e966ba88..1fb1dda0e0` **实际重跑**了改动测试与仓库门，exit code 与通过数实测如下，结论与源码保真度版一致、并把该 caveat 关闭：

| 复跑命令 | exit | 实测结果 |
|---|---|---|
| `pnpm exec vitest run packages/experimental/shadow-controller` | 0 | 2 文件 **50 passed**：host.spec 27、agent.spec 23 |
| `pnpm exec vitest run packages/experimental/project-controller/tests/commit-consumer.spec.ts` | 0 | **29 passed**（含 :672 normalize 注入、:677 缺省 absent、:682 非法值 fail-loud 三条新用例） |
| `pnpm exec vitest run packages/experimental/client-ui-shadow-entry` | 0 | 5 文件 **61 passed**：presenter 18、mount 8、card 14、store 8、BoardView 13 |
| `pnpm run build:lib:host` | 0 | gen:typert + tsc -b tsconfig.host.json + tsdown 全通过 |
| `pnpm run typecheck:contracts-ready` | 0 | tsc -b tsconfig.client.json 通过 |
| `pnpm exec oxlint <三包 src>` | 0 | **0 warnings 0 errors**（31 文件） |

- 产物一致性实测：`shadow-controller/lib/index.js:385 async readBoard()`（@Remote 注册块 :84–192）；`client-ui-shadow-entry/lib/client.js:4266` readBoard RPC schema、`:4965 BoardView` 组件本体、`:4902 BoardView.module.css`。桌面 bundle 与 src 一致。
- 工作树 `git status --short` 干净；逐 commit 行数精确：`80db24cb17` = 25 文件 +2237/-47（与声称逐字吻合），`1fb1dda0e0` = +1/-3，区间合计 +2238/-50。
- 测试缺口 5/5 实测命中：host.spec:405（shadowRouter 缺失 mounted:true 但 bindings 空）、presenter:112 + BoardView:233（mounted:false→disabled）、BoardView:188（blocked 重新批准）、BoardView:146/259（5s 轮询 + 批准后移列，`vi.useFakeTimers` + `advanceTimersByTime(5000)`）、新用例并入既有 spec（presenter/store/host/commit-consumer 均就地增量，BoardView 专属 spec 唯一）。
- **未复跑项（如实标注）**：`project-controller` 全包（约 210s）未跑，仅精准复跑其改动点 `commit-consumer.spec.ts`；故”三包全量 278 passed”未独立复现总数，但所有改动 spec 均全绿。建议合并前由 CI / owner 复跑 project-controller 全包确认无回归。
- 结论维持 **通过（无 P0）**；唯一保留缺口仍为验收 4 完整真实 e2e（宿主投递链外部阻塞，与本次 readBoard/看板实现无关），待宿主投递链修复后补跑闭环。
