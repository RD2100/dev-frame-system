---
description: "AT2C-04 recorded-session 场景草案：byTask 轨迹查询——byTask 三轨各自按 recorded 序返回且跨任务隔离，bindingsByGoal 双键过滤，未知任务空轨非错误，查询全程只读零落盘。"
kind: "acceptance-scenario-draft"
---

# AT2C-04 场景草案：byTask 轨迹查询

包已在 main（agent-evidence 合并提交 `c8992f8154`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-04`；P22 验收矩阵 `AT1-05`/`AT1-06` 的 P05 责任面（evidence 拒绝矩阵的查询读面）与 `AT1-03` 证据链读半边（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6b 节；[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- `byTask(taskId)` 返回三轨（`bindings`/`submissions`/`verifications`），各轨只含该 taskId 的 receipt 且按 `recordedAt` 排序（recorded order）。
- `bindingsByGoal(controllerSessionId, goalId)` 按 controller + goal 双键过滤 binding 轨；两键任一不同即不命中。
- 跨任务隔离：t-2/t-3 的 receipt 不出现在 t-1 轨，反之亦然。
- 未知 taskId → 三空轨（是数据不是错误）；查询全程只读，不产生落盘变化。

## 前提（宿主集成）

- 组合同 AT2C-03；桥（落地名草案：`evidence_ledger`）另暴露 `byTask`/`bindingsByGoal`；未定前记 `blocked`。
- 种子（记录顺序刻意交错，走通面不做探针重点）：t-1（goal-1 binding rev 3、t-2 submission、t-1 binding rev 4、t-1 verification exit 0、t-1 verification exit 1）、t-2（goal-1 binding rev 3、t-2 verification exit 0）、t-3（goal-2 binding rev 1）。
- 三任务共用 controller-1；goal-1/goal-2 区分 `bindingsByGoal` 的键。

## 计划录制布局

`snapshots/session/agent-evidence-bytask-trail-query/`：`snapshot.yml`（`profile: headless`、`recording: authored`）；`session.jsonl` 单会话（种子段 + 查询段）；`workspace.expected/` 固定三表终态行数（bindings 3 / submissions 2 / verifications 3），掩码方式同 AT2C-03。

## 剧本（replay 步骤）

1. 种子记录按前提交错顺序走通（receipt 字段面已归 AT2C-03）。
2. `byTask('t-1')` → bindings 2（rev 3 在前、rev 4 在后）、submissions 1、verifications 2（exit 0 在前、exit 1 在后——recorded order）；无 t-2/t-3 receipt。
3. `byTask('t-2')` → bindings 1、submissions 1、verifications 1；`byTask('t-3')` → bindings 1、其余空轨。
4. `bindingsByGoal('controller-1', 'goal-1')` → t-1 两条 + t-2 一条（按 recordedAt）；`bindingsByGoal('controller-1', 'goal-2')` → 仅 t-3 一条；`bindingsByGoal('controller-2', 'goal-1')` → 空（controller 键不命中）。
5. `byTask('task-none')` → `{ bindings: [], submissions: [], verifications: [] }`（空轨数据，非 error envelope）。
6. 查询只读观察点：全部查询后三表行数与种子一致（bindings 3 / submissions 2 / verifications 3）。

## 可观察通过标准

- 各轨排序 = recorded order：同轨多 receipt 的先后与记录先后一致（步骤 2 的 rev 3→4 与 exit 0→1 两个观察点）。
- 跨任务隔离逐轨成立：任何轨都不含他任务 receipt。
- 未知任务返回空轨而非错误；查询序列零落盘变化。

## 环境与安全

合成 taskId/goalId/sessionId；种子 receipt 内容为合成 fixture；临时 JSON storage 用后清理。

## 开放问题

- 桥暴露 `byTask`/`bindingsByGoal` 的结果字段面（全 receipt vs 摘要）由组合挂载波定。
- 同毫秒 `recordedAt` 并列时的稳定序（map 插入序 + 稳定 sort）以首录实测为准；必要时种子记录间加大于 1ms 的间隔。
- `workspace.expected` 掩码方式同 AT2C-03，由 snapshots 属主定。
