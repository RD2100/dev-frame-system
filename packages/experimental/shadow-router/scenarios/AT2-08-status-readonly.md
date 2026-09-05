# AT2-08 · 只读状态反复观察（场景草案）

> 状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。
> 验收项：`AT2-08` / `R2.4`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- `project_status`：一个获授权的 `workspaceId`，或一页有数量限制的获授权项目；根据原生会话/任务、投递状态和活动后台任务计算状态，并包含观察时间与阻断原因。
- `idle`、`running`、`waiting`、`stopping`、`stopped`、`completed`、`needs_attention` 是计算得到的 UI 状态，不是竞争性持久化任务状态机。
- `completed` 必须依据第 1 部分的完成结果；队列为空或模型空闲都不够。
- 陈旧观察显示时间，且不能据此授权写入；只读状态刷新不唤醒 agent。

## 前置

- 项目根 A 已打开，并被驱动到五个可区分观察点：`idle`（队列空、无运行）、`queued`（投递已接受未开始）、`received`（目标已接受输入）、`blocked`（`waiting`/`needs_attention` 且带阻断原因）、`completed`（第 1 部分完成结果达成）。
- 每个观察点至少读取一次状态，另加一次陈旧观察（缓存/延迟读取）。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-08-status-readonly`，`recording: authored`。

`session.jsonl`（Shadow 主会话）骨架（五态 + 陈旧观察，只列 `tool/call`/`tool/result` 对）：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-1","name":"project_status","arguments":"{\"workspaceId\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-1"},"content":[{"type":"tool-result","toolCallId":"call-status-1","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"idle\",\"observedAt\":0,\"queueDepth\":0,\"blockReason\":null}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-2","name":"project_status","arguments":"{\"workspaceId\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-2"},"content":[{"type":"tool-result","toolCallId":"call-status-2","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"running\",\"observedAt\":0,\"queueDepth\":1,\"blockReason\":null}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-3","name":"project_status","arguments":"{\"workspaceId\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-3"},"content":[{"type":"tool-result","toolCallId":"call-status-3","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"waiting\",\"observedAt\":0,\"queueDepth\":0,\"blockReason\":\"review requested\"}"}],"isError":false}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-4","name":"project_status","arguments":"{\"workspaceId\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-4"},"content":[{"type":"tool-result","toolCallId":"call-status-4","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"completed\",\"observedAt\":0,\"queueDepth\":0,\"blockReason\":null}"}],"isError":false}],"role":"user","id":"{{message:5}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-5","name":"project_status","arguments":"{\"workspaceId\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-5"},"content":[{"type":"tool-result","toolCallId":"call-status-5","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"completed\",\"observedAt\":0,\"observedAge\":\"stale\",\"blockReason\":null}"}],"isError":false}],"role":"user","id":"{{message:6}}"}}}
```

`queued`/`received` 观察落在投递已被接受但目标 turn 尚未开始/已开始的时间窗内；`received` 观察结果断言其与 `completed` 的区分（`received` ≠ `completed`）。分页形态（一页获授权项目）落地后补一个带数量限制的变体观察。

错误码与状态字段为草案命名，Shadow 落地后对齐。

## 期望断言要点

- 只读：所有 `project_status` 调用在控制器 A 的日志不产生任何输入、turn 或状态变更事件。
- 不唤醒模型：状态读取不使 A 的会话出现新的 `request/header`（无模型请求）。
- 有界：单项目观察与分页观察都受数量限制；分页变体落地后断言上限生效。
- 观察时间包含在结果中：每次返回带 `observedAt`；陈旧观察显式标注观察时刻/陈旧度，且不能据此授权写入（陈旧观察后无隐式状态翻转）。
- 状态语义：`received` 与 `idle` 都不等价于 `completed`；`completed` 只在 A 的第 1 部分完成结果（`turn/end` 的 completion 依据）达成后出现，队列为空或模型空闲本身不触发 `completed`。
- `blocked` 观察带阻断原因（`blockReason` 非空）。

## 落地校准点

- 五个观察点的驱动（投递时序、阻塞注入、完成路径走第 1 部分真实验收流程）落地时确定；本草案固定的是断言面，不是驱动脚本。
- 分页 `project_status` 的输入形态（页大小字段名）以实现为准。
