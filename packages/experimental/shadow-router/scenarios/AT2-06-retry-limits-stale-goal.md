# AT2-06 · 重试去重、限额与旧 Goal 消息隔离（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位错误码/参数/限额默认值已替换为已落地契约（`SHADOW_REQUEST_CONFLICT`/`SHADOW_MESSAGE_TOO_LARGE`/`SHADOW_GOAL_STALE`/`SHADOW_QUEUE_FULL`，限额取服务 Config 默认值）；原草案投递级重试计数与旧 Goal 探针 `bindingRevision:1` 以实现口径改写。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；队满探针驱动仍待回填。
> 验收项：`AT2-06` / `R2.3`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 相同 `request_id` 配相同规范化输入返回先前结果（请求重放日志）；配不同输入返回 `SHADOW_REQUEST_CONFLICT`。
- 重试复用同一 `request_id`；实现无投递级重试计数，重试有界性由请求重放日志承载（同 id 异输入拒绝）。队列（`maxPendingDeliveries`，默认 16）与消息大小（`maxMessageChars`，默认 20000）限制在接受新输入之前应用；崩溃残留行保留可见（`queued`/`cancelled`+reason），拒绝本身不留行。原草案"次数耗尽后保留可见的待投递/失败操作"以实现口径为准。
- 消息的 Goal/验收归属在首次持久化前固定；前一个 Goal 的消息被 `SHADOW_GOAL_STALE` 拒绝，不转给控制器的当前 Goal；Goal 切换不重置请求重放去重。
- 发送消息不创建或替换 Goal（`setActiveGoal` 为宿主专用 seam）；重试崩溃前的投递不授权旧工作重启。

## 前置

- 项目根 A 已打开（`ws-a`、`bindingRevision":"1`）；控制器先运行 Goal `goal-a-1`（验收哈希 `hash-a-1`，宿主 `setActiveGoal` 授权），后切 Goal `goal-a-2`（哈希 `hash-a-2`；切换经 `setActiveGoal`，`bindingRevision` 递增至 2）。
- 限额取服务 Config 默认值：`maxPendingDeliveries: 16`、`maxMessageChars: 20000`（原草案引 part4 统一默认值，以实现 Config 为准）。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-06-retry-limits-stale-goal`，`recording: authored`。

`session.jsonl`（Shadow 主会话）探针骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-idem","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Task payload one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-idem"},"content":[{"type":"tool-result","toolCallId":"call-send-idem","content":[{"type":"text","text":"{\"messageId\":\"msg-req-send-r1\",\"workspaceId\":\"ws-a\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-idem-2","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Task payload one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-idem-2"},"content":[{"type":"tool-result","toolCallId":"call-send-idem-2","content":[{"type":"text","text":"{\"messageId\":\"msg-req-send-r1\",\"workspaceId\":\"ws-a\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-conflict","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-r1\",\"mode\":\"work\",\"text\":\"Different payload same requestId\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-conflict"},"content":[{"type":"tool-result","toolCallId":"call-send-conflict","content":[{"type":"text","text":"requestId \"req-send-r1\" was already used with different input"}],"isError":true}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-oversize","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-big\",\"mode\":\"work\",\"text\":\"<bounded-limit-exceeding text>\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-oversize"},"content":[{"type":"tool-result","toolCallId":"call-send-oversize","content":[{"type":"text","text":"text is <n> chars; the limit is 20000"}],"isError":true}],"role":"user","id":"{{message:5}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-stale-goal","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":2,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-old-goal\",\"mode\":\"work\",\"text\":\"Late message for goal one\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-stale-goal"},"content":[{"type":"tool-result","toolCallId":"call-send-stale-goal","content":[{"type":"text","text":"the message's Goal/acceptance association does not match workspace \"ws-a\"'s authorized open run; a previous Goal's message is never forwarded to the current Goal"}],"isError":true}],"role":"user","id":"{{message:6}}"}}}
```

旧 Goal 消息送达时控制器已在 `goal-a-2` 上（宿主 `setActiveGoal` 已递增 `bindingRevision` 至 2，故探针断言 `binding_revision: 2`；原草案仍用 1，会先触发 `SHADOW_STALE_REVISION`，以实现为准）：对 `goal-a-1`/`hash-a-1` 的新投递被 `SHADOW_GOAL_STALE` 拒绝；崩溃残留的 `queued` 旧行由宿主 `recoverDeliveries` 以 `goal-no-longer-authorized` 取消并保留可见。队满（`SHADOW_QUEUE_FULL`）探针以受控填充实现（`maxPendingDeliveries` 默认 16），落地时确定驱动方式。

错误码、状态字段与限额默认值已按落地实现对齐（见顶部 aligned 标记）。

## 期望断言要点

- 稳定重试去重：相同 `request_id` + 相同规范化输入的第二次投递重放先前结果，控制器日志不出现第二条该投递的模型可见输入。
- `SHADOW_REQUEST_CONFLICT`：相同 `request_id` + 不同输入被拒绝，无副作用。
- 限额接受前生效：超限（`SHADOW_MESSAGE_TOO_LARGE`）与队满（`SHADOW_QUEUE_FULL`）投递被拒绝，控制器日志无对应 accepted 输入；拒绝本身不留投递行（限额在接受前应用），可见痕迹为拒绝错误与 `requests` 重放日志；崩溃残留行保留可见（`queued`/`cancelled`+reason）。原草案"拒绝后保留可见的待投递/失败操作"以实现口径为准。
- 旧 Goal 隔离：`goal-a-1` 的迟到消息被 `SHADOW_GOAL_STALE` 拒绝，永不成为 `goal-a-2` 的输入；`goal-a-2` 的输入里无 `goal-a-1` 内容。
- Goal 切换不重置重放去重：`req-send-r1` 的重放语义在 `goal-a-2` 开始后继续生效（同 id 异输入仍拒绝）。原草案"已用重试次数继续有效"以实现口径为准（实现无投递级重试计数）。
- 发送消息不创建/不替换 Goal：所有 `project_send` 调用前后控制器的当前 Goal 归属只经宿主 `setActiveGoal`（人工授权路径）变化。

## 落地校准点

- 队满探针需受控填满 `maxPendingDeliveries`（默认 16）；具体驱动（多条合法投递到限值 vs 直接注入存储）落地时确定。
- "保留可见的待投递/失败操作"的可观察形态：`project_status` 的 deliveries 行（含 `state`/`cancelReason`）或存储重开后的 deliveries 表行。
