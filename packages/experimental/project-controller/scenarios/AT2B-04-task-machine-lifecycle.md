---
description: "AT2B-04 recorded-session 场景草案：任务机九态走通——planned→assigned→developing→reviewing→submitted→integrated→completed 全序加 blocked/failed 往返，developing 预算在边缘拒绝并在离开时释放，每个 move 返回更新后 record、非法 move fail loud。"
kind: "acceptance-scenario-draft"
---

# AT2B-04 场景草案：任务机九态走通

包已在 main（project-controller 合并提交 `4a515afda7`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-04`；P22 验收矩阵 `AT1-09` 的 P04 责任面（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- 九态 `TaskState` 全序：`planned → assigned → developing → reviewing → submitted → integrated → completed`，加 `blocked`/`failed`；每个 move 返回更新后 record，非法 move 抛稳定码、不改写状态。
- 并发预算数 `developing` 记录、恰在进入该态处执行；`maxActiveTasks` 是验证过的配置字段（默认 2），本场景取 `1` 使拒绝可观察，同时证明可配置。
- dispatch 类 move（`createTask`/`assign`/`startDevelopment`/`beginReview`/`submit`/merges/`resume`）要求 `admission_open`；`block`/`fail`/`complete` 为 recording move，项目未停止即可用。
- 包本身零工具、零事件、零 prompt 面：record 只经宿主桥进入会话结果；此外任何请求字段不携带任务数据。

## 前提（宿主集成）

- 组合挂载 project-contracts + session-identity + storage 栈 + `@deepseek-ai/dsh-experimental-project-controller`，config `{ maxActiveTasks: 1 }`；会话身份绑定 controller。
- 模型可见桥由组合挂载波提供（命令适配器或工具桥，落地名草案：`project_task`），把 `startProject` 与各 move 映射为会话可见调用，结果携带返回的 `TaskRecord` 或 `ProjectControllerError` 稳定码文本；桥形态未定前本条记 `blocked`，不降级为包内单测。
- 项目生命周期以 `startProject` 显式开启（`stopped → admission_open`）。

## 计划录制布局

`snapshots/session/project-controller-task-machine-lifecycle/`：`snapshot.yml`（`profile: headless`、`recording: authored`、header pin 同 `text-turn`）；`session.jsonl` 单会话驱动全部 move；`workspace.expected/` 固定 `project_tasks` 域落盘终态（t-1 `completed`、t-2 `assigned`）。

## 剧本（replay 步骤）

主弧（t-1，走满七态调度脊）：

1. `startProject` → `admission_open`；`createTask(t-1, plugin-a, 'Wire the gate')` → record `state: planned`。
2. `assign(t-1, worker-1)` → `assigned`；`startDevelopment(t-1)` → `developing`（占用预算）。
3. `createTask(t-2, plugin-a, 'Second slice')` → `planned`；`assign(t-2, worker-2)` → `assigned`；`startDevelopment(t-2)` → 拒绝：`PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED`（`the developing budget of 1 is exhausted`），t-2 record 停在 `assigned`。
4. `beginReview(t-1)` → `reviewing`（预算释放）；`submit(t-1)` → `submitted`；`requestMainTreeMerge(controller, t-1)` → marker；`integrate(t-1, marker)` → `integrated`；`complete(t-1)` → `completed`。
5. `startDevelopment(t-2)` 重试 → 成功进入 `developing`（预算在离开 `developing` 时释放的观察点）。

次弧（t-2，补齐 blocked/failed 两态，三元组取最小合法值）：

6. `block(t-2, triple)` → `blocked`；`resume(t-2)` → `assigned`；`startDevelopment(t-2)` → `developing`；`fail(t-2, triple)` → `failed`；`resume(t-2)` → `assigned`（收尾，三元组细节归 AT2B-05）。

非法 move 探针：t-2 处于 `planned` 时（步骤 3 前）调 `beginReview(t-2)` → `PROJECT_CONTROLLER_ILLEGAL_TRANSITION`（`task "t-2" cannot move planned → reviewing`），record 不变。

## 可观察通过标准

- 九态在单录制内全部出现；每个成功 move 的桥结果 record 字段（`state`、`updatedAt`、`assigneeSessionId`）与调用一致，`createdAt` 不变。
- 两次拒绝（预算、非法转移）均 fail loud：稳定码 + record 原样；无静默改写。
- 桥是唯一把 record 带入会话结果的通道；`session.jsonl` 中不含绕过桥的任务数据。

## 环境与安全

合成 taskId/pluginId/assignee；storage 用临时 JSON 后端，录制后清理。

## 开放问题

- 桥落地形态（命令面 vs 工具桥）与工具名由组合挂载波定；本文 JSONL 待首录回填。
- 冷恢复（verbatim restore）与生命周期重启不属单次 replay 的模型可见面，归重启探针/P22 `AT1-09`；本场景只钉单进程九态。
- marker 的铸造/消费在本场景为过路验证，完整门禁归 AT2B-06。
