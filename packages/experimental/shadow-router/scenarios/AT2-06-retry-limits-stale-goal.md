# AT2-06 · 重试去重、限额与旧 Goal 消息隔离（场景草案）

> 状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。
> 验收项：`AT2-06` / `R2.3`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 相同 `requestId` 配相同规范化输入返回先前结果；配不同输入返回 `request_conflict`。
- 投递重试次数有界并复用同一 ID；队列与消息大小限制在接受新输入之前应用；次数耗尽后保留可见的待投递/失败操作，由人工决定。
- 消息的 Goal/验收归属在首次持久化前固定；前一个 Goal 的消息不能转给控制器的当前 Goal，重试不重置限额。
- 发送消息不创建或替换 Goal；重试崩溃前的投递不授权旧工作重启。

## 前置

- 项目根 A 已打开（`ws-a`、`bindingRevision":"1`）；控制器先运行 Goal `goal-a-1`（验收哈希 `hash-a-1`），后开始 Goal `goal-a-2`（哈希 `hash-a-2`）。
- 队列与消息大小限制取第 4 部分统一默认值（`docs/detailDesign-part4.zh.md` limits）。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-06-retry-limits-stale-goal`，`recording: authored`。

`session.jsonl`（Shadow 主会话）探针骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-idem","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Task payload one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-idem"},"content":[{"type":"tool-result","toolCallId":"call-send-idem","content":[{"type":"text","text":"{\"deliveryId\":\"dl-r1\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-idem-2","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Task payload one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-idem-2"},"content":[{"type":"tool-result","toolCallId":"call-send-idem-2","content":[{"type":"text","text":"{\"deliveryId\":\"dl-r1\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-conflict","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Different payload same requestId\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-conflict"},"content":[{"type":"tool-result","toolCallId":"call-send-conflict","content":[{"type":"text","text":"rejected: request_conflict"}],"isError":true}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-oversize","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-big\",\"mode\":\"work\",\"text\":\"<bounded-limit-exceeding text>\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-oversize"},"content":[{"type":"tool-result","toolCallId":"call-send-oversize","content":[{"type":"text","text":"rejected: message exceeds the size limit"}],"isError":true}],"role":"user","id":"{{message:5}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-stale-goal","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-old-goal\",\"mode\":\"work\",\"text\":\"Late message for goal one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-stale-goal"},"content":[{"type":"tool-result","toolCallId":"call-send-stale-goal","content":[{"type":"text","text":"rejected: acceptance binding no longer matches the current goal"}],"isError":true}],"role":"user","id":"{{message:6}}"}}}
```

旧 Goal 消息送达时控制器已在 `goal-a-2` 上：对 `goal-a-1`/`hash-a-1` 的投递被拒绝或保留为待人工，不进入 `goal-a-2` 的输入。队列满（`queue_full`）探针以受控填充实现，落地时确定驱动方式。

错误码与状态字段为草案命名，Shadow 落地后对齐。

## 期望断言要点

- 稳定重试去重：相同 `requestId` + 相同规范化输入的第二次投递返回先前结果，控制器日志不出现第二条该投递的模型可见输入。
- `request_conflict`：相同 `requestId` + 不同输入被拒绝，无副作用。
- 限额接受前生效：超限消息与队满投递被拒绝，控制器日志无对应 accepted 输入；拒绝后保留可见的待投递/失败操作（或等价持久化痕迹）。
- 旧 Goal 隔离：`goal-a-1` 的迟到消息永不成为 `goal-a-2` 的输入；`goal-a-2` 的输入里无 `goal-a-1` 内容。
- 重试限额不因 Goal 切换重置：`goal-a-1` 投递的已用重试次数在 `goal-a-2` 开始后继续有效。
- 发送消息不创建/不替换 Goal：所有 `project_send` 调用前后控制器的当前 Goal 归属只经人工授权路径变化。

## 落地校准点

- 队满探针需要受控填充队列；具体驱动（多条合法投递到限值 vs 直接注入）落地时确定。
- "保留可见的待投递/失败操作"的可观察形态（状态查询结果或持久化行）以实现为准。
