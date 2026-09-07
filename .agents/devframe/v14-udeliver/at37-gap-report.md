# AT3-07 — project-controller 编码任务旅程 × memory_unavailable：契约缺口报告（判定：gap）

判定：**gap**。`packages/experimental/project-controller` 现有产品面不存在 A1–A3 所需的任何 memory / warning 契约。按任务硬规则：不臆造测试、不改产品代码（本片 test-only），只报告缺口。以下现状全部在 worktree `D:\dsh-udeliver-at37`（branch `codex/v14-udeliver-at37`，tip `ec27a5c6ce`）逐文件核实。

## 观察到的现状（逐文件，含行号）

1. `packages/experimental/project-controller/src/controller.ts` — 任务机 `createTask / assign / startDevelopment / beginReview / submit / requestMainTreeMerge / integrate / complete / block / fail / resume`。
   - completion 面：`complete(taskId)`（controller.ts:410–417）只收 `taskId`，返回 `TaskRecord`。无 warning 参数、无 completion 事件（全 src 无 `ctx.emit` / 事件声明合并）、无工具面（本包不注册任何 tool）。
   - 大小写不敏感 grep `memory|warn|receipt|unavailable` 全 src **仅 1 处命中**：controller.ts:64 `MainTreeMergeMarker` 的 JSDoc "The receipt minted by the controller-only main-tree merge gate" —— 是 merge marker，与 memory receipt 无关。
2. `packages/experimental/project-controller/src/errors.ts:4–26` — `ProjectControllerErrorCode` 共 10 个码（ILLEGAL_TRANSITION / CONCURRENCY_EXCEEDED / TASK_UNKNOWN / TASK_EXISTS / NOT_CONTROLLER / INVALID_DETAIL / INVALID_CONFIG / ADMISSION_CLOSED / MARKER_INVALID / QUIESCENCE_INCOMPLETE / PERSISTENCE），无一与 memory 或 warning 相关。
3. `packages/experimental/project-controller/src/spec.ts:35–47` — `taskRecordSchema` 字段：`taskId / pluginId / title / state / blockedReason? / nextAction? / wakeCondition? / assigneeSessionId? / worktreeId? / createdAt / updatedAt`。无 `warnings`、无任何 memory 字段；`project_tasks` domain（spec.ts:55–59）只有一张 `tasks` 表。
4. `packages/experimental/project-contracts/src/types.ts:84–107` — 共享契约 `TaskRecord` 与 schema 同构，同样无 `warnings` / memory-outcome 字段；`TaskState`（types.ts:33–43）九态无 journey 概念。
5. `packages/experimental/project-controller/package.json` — dependencies / peerDependencies / devDependencies 均无 `@deepseek-ai/dsh-experimental-project-memory`。旅程 spec 在本包内连挂载 memory 插件都做不到，除非改 manifest（产品变更，越权）。
6. `packages/experimental/project-controller/tests/helpers.ts:39–44` — 测试组合为 session / storage / storage-json / storage-domain / agent-bindings / project-controller，无 memory 插件可挂。
7. 只读参照 `packages/experimental/project-memory`：失败码 `MEMORY_UNAVAILABLE / MEMORY_WRITE_FAILED / MEMORY_APPEND_DISABLED / MEMORY_CONTENT_REJECTED / MEMORY_INVALID_NOTE`（tests/failure.spec.ts:23,40,79,105,133）。receipt 诚实语义**在包内已成立**：成功 append 才在调用 agent 的 session log 记 `memory/receipt`（tests/agent-rehydration.spec.ts:139–143），失败 append 不落 receipt（tests/failure.spec.ts:52–53，`committedReceipts` 为 0）。但 controller 旅程从未调用 memory，本包内不存在可断言的旅程面。

## 防误判排除项

- `packages/experimental/devframe` 的 `GoalBindingController`（src/controller/goal-binding.ts）是另一个 controller 缝（goal 绑定/完成准入），无 memory 关联。
- 全 `packages/experimental` 组 grep `projectMemory|project-memory`：命中仅在 project-memory 包自身（52 处全部在其 src/tests 内）。memory 与任务机的旅程联动在整个 experimental 组都不存在。

## 缺口 → A1–A3 最小契约提案

**A1（编码任务遇 memory_unavailable 仍完成，完成面带类型化可观察 warning）**
- 缺口：completion 面没有任何 warning 载体（TaskRecord 无字段、complete() 无参数、service 无事件面）。
- 最小契约：`project-contracts/src/types.ts` 的 `TaskRecord` 增加可选字段 `readonly warnings?: readonly TaskWarning[]`，`TaskWarning` 为封闭联合 `{ code: 'memory_unavailable' | …; detail: string }`（code 词表与 project-memory 的 `MEMORY_UNAVAILABLE` 对齐并在契约处钉死）；`controller.ts` 的 `complete(taskId)` 扩为 `complete(taskId, outcome?)`，把 warning 冻结进持久记录，`spec.ts` 的 `taskRecordSchema` 同步加 optional 字段（durable boundary 一起改）。备选面（completion 事件）需先给这个目前完全没有事件管线的 service 接 session/emit，改动更大；记录字段是最小路径。

**A2（失败的 memory save 不得产生成功 receipt）**
- 缺口：旅程面不存在——controller 既不执行也不观察 memory save，因此无旅程级 receipt 断言面；包级诚实语义已由 project-memory 自身成立（见现状第 7 条）。
- 最小契约：A1 的 outcome/warning 里区分 save 结果（`memory_saved: false` + code `MEMORY_WRITE_FAILED | MEMORY_UNAVAILABLE`）；旅程断言规则：completion 记录携带 failed save 时不得出现任何成功 receipt 声明——controller 目前不 mint 任何 receipt，契约只需"不新增成功声明面"，切勿把失败 save 折叠成 success。

**A3（memory-only 任务必须仍然 fail，不得被静默吸收为成功）**
- 缺口：没有"memory-only 任务"概念，`complete()` 也无交付校验。
- 最小契约：`createTask`（controller.ts:258）或 `TaskRecord` 增加交付类型（如 `deliverable?: 'code' | 'memory'`）；`complete()` 在 memory 交付不可用时拒绝 completed（新增 `PROJECT_CONTROLLER_*` 码或显式拒绝路径），任务须走 `fail()` 带完整 recovery triple（controller.ts:446–459 已强制 triple 校验，可直接承载）。

## 命令证据（workdir=D:\dsh-udeliver-at37）

| 命令 | 退出码 |
| --- | --- |
| `git status/branch/log` 核对 + `Test-Path node_modules` | 0（树干净，node_modules 缺失） |
| `pnpm install --prefer-offline` | 0 |
| `pnpm exec vitest run packages/experimental/project-controller/tests`（邻居回归，4 文件 18 用例） | 0 |

未落 spec 的原因：A1–A3 的每一个断言目标（warning 载体、旅程 receipt 面、memory-only 交付校验）在当前产品面均不存在，任何"测试"都只能对不存在的契约编程。本片按硬规则止于缺口报告，未改任何包代码。
