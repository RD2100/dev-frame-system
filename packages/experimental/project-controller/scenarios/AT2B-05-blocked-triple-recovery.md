---
description: "AT2B-05 recorded-session 场景草案：blocked/failed 恢复三元组——reason/nextAction/wakeCondition 逐字段强制非空 trim，缺失字段逐个报 INVALID_DETAIL，resume 清三元组经 assigned 回调度并支持换 assignee。"
kind: "acceptance-scenario-draft"
---

# AT2B-05 场景草案：blocked 三元组与恢复

包已在 main（project-controller 合并提交 `4a515afda7`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-05`；P22 验收矩阵 `AT1-09` 的 P04 责任面（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- `blocked`/`failed` move 必须携带完整恢复三元组（`blockedReason`/`nextAction`/`wakeCondition`），任一字段缺失、空串或未 trim 即 `PROJECT_CONTROLLER_INVALID_DETAIL`，文本逐字段点名（`<field> must be a non-empty trimmed string`）。
- `block`/`fail` 可从全部活动态（`planned`/`assigned`/`developing`/`reviewing`/`submitted`）进入；`resume` 只接受 `blocked`/`failed`，清空三元组并经 `assigned` 重回调度，可选替换 assignee，缺省保留原 assignee。
- 三元组是 record 的持久字段：blocked/failed 记录落盘携带三字段，resume 后读回的 record 不再含它们。

## 前提（宿主集成）

- 组合同 AT2B-04（`maxActiveTasks` 默认 2 即可，本场景单任务）；模型可见桥同 AT2B-04（落地名草案 `project_task`）。
- 绑定 controller 会话；两个合成 assignee 身份（`worker-1`、`worker-2`）供 resume 换绑断言。

## 计划录制布局

`snapshots/session/project-controller-blocked-triple-recovery/`：`snapshot.yml`（`profile: headless`、`recording: authored`）；`session.jsonl` 单会话；`workspace.expected/` 固定终态 record（`state: assigned`、`assigneeSessionId: worker-2`、无三元组字段）。

## 剧本（replay 步骤）

1. `startProject`；`createTask(t-1, plugin-a, 'Recovery probe')` → `planned`；`assign(t-1, worker-1)` → `assigned`。
2. 三元组逐字段探针（每次调用只破坏一个字段，`block(t-1, detail)`）：
   - 缺 `nextAction`（其余合法）→ `nextAction must be a non-empty trimmed string`；
   - `wakeCondition: "  "`（未 trim）→ `wakeCondition must be a non-empty trimmed string`；
   - 缺 `blockedReason` → `blockedReason must be a non-empty trimmed string`；
   全部 `PROJECT_CONTROLLER_INVALID_DETAIL`，record 停在 `assigned`。
3. 合法 `block(t-1, triple)` → record `state: blocked`，且 `blockedReason`/`nextAction`/`wakeCondition` 三字段与输入逐字一致。
4. `resume(t-1)` → `assigned`、assignee 保持 `worker-1`，读回 record 无三字段（已清除）。
5. `startDevelopment(t-1)` → `developing`；`fail(t-1, triple-2)` → `failed`（从 `developing` 源态进入，三元组落盘）。
6. `resume(t-1, worker-2)` → `assigned` 且 `assigneeSessionId: worker-2`（替换 assignee 的观察点）。
7. （可选探针）t-1 `failed` 时调 `complete(t-1)` → `PROJECT_CONTROLLER_ILLEGAL_TRANSITION`（`cannot move failed → completed`）；再 `resume` 收尾至 `assigned` 结束录制。

## 可观察通过标准

- 步骤 2 的三段拒绝文本逐字段、逐字符与 controller.ts 一致；校验先于任何状态改写。
- blocked/failed record 的三元组字段精确落盘；resume 后字段缺席是"清除"而非"残留"。
- resume 的两个形态（保留/替换 assignee）各有一次观察。

## 环境与安全

合成任务与身份；三元组内容为合成文本；临时 JSON storage 用后清理。

## 开放问题

- recording move 在 `stop_requested` 生命周期下仍可用（`requireOpenLifecycle` 面）属停止路径，不并入本场景，归 P22 `AT1-09` 停止/恢复探针。
- 桥落地名与结果 envelope 同 AT2B-04，由首录回填。
