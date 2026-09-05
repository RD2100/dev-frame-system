# AT2-08 · 只读状态反复观察（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位参数/结果字段已替换为已落地契约；原草案 UI 计算态（`idle`/`running`/`waiting`/`completed`）、`observedAge:"stale"` 与 `queueDepth`/`blockReason` 以实现口径改写（绑定 `state` 枚举 + 投递 `state` + `blockedReason` + `observedAt`）。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；观察点驱动仍待回填。
> 验收项：`AT2-08` / `R2.4`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- `project_status`：可选 `workspace_id`（单个）或有界分页（`cursor` 零基偏移、`limit` 1..`statusPageSize` 默认 20，更多项目时返回 `nextCursor`）；返回绑定 `state`、`bindingRevision`、`controllerLive`、投递行（`state`/`createdAt`/`receivedAt`/`completedAt`/`cancelReason`）、`blockedReason` 与 `observedAt`。
- 实现无 UI 计算态：返回的是绑定持久化 `state` 枚举（`reserving`/`provisioning`/`ready`/`stopping`/`stopped`/`needs_attention`/`failed`）与投递 `state`（`queued`/`received`/`completed`/`cancelled`）。原草案的 `idle`/`running`/`waiting`/`completed` UI 状态不在本包范围（README Known Limitations：UI state set 未落地），以实现为准。
- 投递层 `completed` 由宿主 `completeDelivery` 独立落定（controller-side durable fact）；队列空或模型空闲都不产生 `completed`。绑定层无 `completed`。
- 每次读取返回新 `observedAt`；实现无陈旧度标记（原草案 `observedAge:"stale"` 未落地，以实现为准）；只读状态刷新不唤醒 agent、不产生模型请求。

## 前置

- 项目根 A 已打开（`state:"ready"`），并被驱动到五个可区分观察点：无投递（原草案 `idle`）、投递 `queued`/`received`（投递已被接受但目标 turn 尚未开始/已开始的时间窗）、阻断（`needs_attention` 带 `blockedReason`，或 `stopping`）、投递 `completed`（宿主 `completeDelivery` 落定）。
- 每个观察点至少读取一次状态，另加一次重读（原草案"陈旧观察"；实现每次返回新 `observedAt`）。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-08-status-readonly`，`recording: authored`。

`session.jsonl`（Shadow 主会话）骨架（观察点 + 重读，只列 `tool/call`/`tool/result` 对）：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-1","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-1"},"content":[{"type":"tool-result","toolCallId":"call-status-1","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"canonicalPath\":\"<A>\",\"controllerSessionId\":\"{{session:2}}\",\"controllerLive\":true,\"profileKey\":\"devframe\",\"bindingRevision\":1,\"state\":\"ready\",\"deliveries\":[],\"deliveriesTruncated\":false}],\"observedAt\":\"<t1>\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-2","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-2"},"content":[{"type":"tool-result","toolCallId":"call-status-2","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"state\":\"ready\",\"deliveries\":[{\"messageId\":\"msg-req-send-s1\",\"mode\":\"work\",\"goalId\":\"goal-a-1\",\"state\":\"received\",\"createdAt\":\"<t>\",\"receivedAt\":\"<t>\"}],\"deliveriesTruncated\":false}],\"observedAt\":\"<t2>\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-3","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-3"},"content":[{"type":"tool-result","toolCallId":"call-status-3","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"state\":\"needs_attention\",\"failureReason\":\"<durable failure reason>\",\"blockedReason\":\"<durable failure reason>\",\"deliveries\":[],\"deliveriesTruncated\":false}],\"observedAt\":\"<t3>\"}"}],"isError":false}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-4","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-4"},"content":[{"type":"tool-result","toolCallId":"call-status-4","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"state\":\"ready\",\"deliveries\":[{\"messageId\":\"msg-req-send-s1\",\"mode\":\"work\",\"goalId\":\"goal-a-1\",\"state\":\"completed\",\"createdAt\":\"<t>\",\"receivedAt\":\"<t>\",\"completedAt\":\"<t>\"}],\"deliveriesTruncated\":false}],\"observedAt\":\"<t4>\"}"}],"isError":false}],"role":"user","id":"{{message:5}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-5","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-5"},"content":[{"type":"tool-result","toolCallId":"call-status-5","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"state\":\"ready\",\"deliveries\":[{\"messageId\":\"msg-req-send-s1\",\"mode\":\"work\",\"goalId\":\"goal-a-1\",\"state\":\"completed\",\"createdAt\":\"<t>\",\"receivedAt\":\"<t>\",\"completedAt\":\"<t>\"}],\"deliveriesTruncated\":false}],\"observedAt\":\"<t5>\"}"}],"isError":false}],"role":"user","id":"{{message:6}}"}}}
```

`queued`/`received` 观察落在投递已被接受但目标 turn 尚未开始/已开始的时间窗内（骨架第 2 对展示 `received` 窗口）；`received` 观察结果断言其与 `completed` 的区分（投递 `received` ≠ `completed`）。第 5 对为重读：同持久化状态、新 `observedAt`（实现无 `observedAge:"stale"` 标记）。分页变体落地后补一个带数量限制的观察：`{"workspace_id":"ws-a"}` 之外还有 `cursor`/`limit`（1..`statusPageSize` 默认 20，超出上限报 `SHADOW_INVALID_REQUEST`，更多项目时返回 `nextCursor`）。

结果字段、状态枚举与分页参数已按落地实现对齐（见顶部 aligned 标记）。

## 期望断言要点

- 只读：所有 `project_status` 调用在控制器 A 的日志不产生任何输入、turn 或状态变更事件。
- 不唤醒模型：状态读取不使 A 的会话出现新的 `request/header`（无模型请求）。
- 有界：单项目观察与分页观察都受数量限制（`limit` ≤ `statusPageSize`，超出返回 `SHADOW_INVALID_REQUEST`）；分页变体落地后断言上限与 `nextCursor` 生效。
- 观察时间包含在结果中：每次返回带 `observedAt`；重读返回同持久化状态与新 `observedAt`（原草案 `observedAge:"stale"` 以实现口径为准），且不能据此授权写入（工具面无写路径）。
- 状态语义：投递 `received` 与绑定 `ready` 都不等价于投递 `completed`；`completed` 只在宿主 `completeDelivery` 落定后出现，队列空或模型空闲不触发（原草案 `idle`/`completed` UI 态以实现口径为准）。
- 阻断观察带非空 `blockedReason`（`needs_attention` 取 `failureReason`，`stopping` 为"stop requested; quiescence confirmation is pending"）。

## 落地校准点

- 五个观察点的驱动（投递时序、`needs_attention` 注入、完成路径走宿主 `completeDelivery`）落地时确定；本草案固定的是断言面，不是驱动脚本。
- 分页输入形态已落地：`cursor`（零基）/`limit`（1..`statusPageSize`，默认 20），超出上限返回 `SHADOW_INVALID_REQUEST`，更多项目时返回 `nextCursor`。
