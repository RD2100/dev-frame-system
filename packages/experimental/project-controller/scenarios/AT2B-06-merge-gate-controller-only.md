---
description: "AT2B-06 recorded-session 场景草案：controller-only 合并门——lead 绑定与未绑定会话均被 NOT_CONTROLLER 拒绝且零 marker 产生，controller 铸造的 marker 单次消费、跨任务即 MARKER_INVALID，双任务正对照走满 integrate+complete。"
kind: "acceptance-scenario-draft"
---

# AT2B-06 场景草案：合并门非总控拒绝

包已在 main（project-controller 合并提交 `4a515afda7`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-06`；P22 验收矩阵 `AT1-09` 的 P04 责任面（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- 只有绑定角色为 `controller` 的会话能经 `requestMainTreeMerge` 铸造合并 marker；角色检查先于任务状态检查：非 controller 的调用无论任务处于何态都在铸造前被拒，零 marker 产生。
- 拒绝分两形：无绑定 → `session "<id>" has no agent binding`；绑定非 controller → `session "<id>" carries role "<role>", not "controller"`；稳定码同为 `PROJECT_CONTROLLER_NOT_CONTROLLER`。
- marker 单次消费、进程局部、不持久不恢复；`integrate` 先验 marker 后验状态：已消费 marker 再用报 `PROJECT_CONTROLLER_MARKER_INVALID`（`does not name a pending merge`），即使任务已前进；marker 点名其他任务同码。

## 前提（宿主集成）

- 组合同 AT2B-04；桥暴露合并两 move（落地名草案：`project_merge` / `project_integrate`），调用者身份取执行该调用的会话绑定。
- 绑定种子：controller 会话（主会话）+ 一个 lead 绑定子会话 + 一个未绑定 live 会话（形态归 AT2B-01 同一开放问题；未就绪则未绑定子案记 `blocked`）。
- 预置两个任务 t-1、t-2 推进至 `submitted`（`assign`/`startDevelopment`/`beginReview`/`submit` 各两次，属走通面，不做探针重点）。

## 计划录制布局

`snapshots/session/project-controller-merge-gate-controller-only/`：`snapshot.yml`（`profile: headless`、`recording: authored`）；`session.jsonl`（controller 主会话：预置 + 门禁探针 + 正对照）、`session.1.jsonl`（lead 子会话的越权探针）；`workspace.expected/` 固定终态（t-1/t-2 均 `completed`）。

## 剧本（replay 步骤）

1. lead 子会话调用 `project_merge(t-1)` → `PROJECT_CONTROLLER_NOT_CONTROLLER`（`session "<lead-id>" carries role "lead", not "controller"`）；断言 controller 侧 marker 集为空、t-1 停在 `submitted`。
2. 未绑定会话调用 `project_merge(t-1)` → `session "<id>" has no agent binding`（同码）。
3. controller 调用 `project_merge(t-1)` → 铸造 marker-1（含 `mergeId`/`taskId`/`callerSessionId`/`createdAt`）；再对 t-2 铸造 marker-2。
4. controller 调用 `project_integrate(t-2, marker-1)` → `PROJECT_CONTROLLER_MARKER_INVALID`（marker 不点名 t-2），t-2 停在 `submitted`。
5. `project_integrate(t-1, marker-1)` → t-1 `integrated`；同 marker 重放 `project_integrate(t-1, marker-1)` → `PROJECT_CONTROLLER_MARKER_INVALID`（已消费；marker 检查先于状态检查——此时任务已 `integrated`，拒绝码仍是 marker 无效而非非法转移）。
6. `complete(t-1)` → `completed`；`project_integrate(t-2, marker-2)` → `integrated`；`complete(t-2)` → `completed`（双任务正对照收尾）。

## 可观察通过标准

- 步骤 1–2 的拒绝先于铸造：全录制恰铸造两个 marker（controller 各一），非 controller 调用零产出。
- marker 单次消费与跨任务拒绝各有独立探针；步骤 5 的重放钉住"marker 检查先于状态检查"的次序契约。
- 任务从 `submitted` 到 `completed` 的路径只经 marker；无 marker 的 `integrate` 尝试不存在于成功路径。

## 环境与安全

marker 为进程内 UUID，录制断言只看存在性与消费行为、不固化具体 `mergeId`；合成身份与任务。

## 开放问题

- 桥把 marker 暴露给模型请求的字段面（完整 marker vs 不透明 handle）由组合挂载波定；断言锚定拒绝码与状态，不锚定 marker 序列化形态。
- marker 不跨进程恢复（重启后 `MARKER_INVALID`）不属单次 replay，归 P22 `AT1-09` 重启探针。
