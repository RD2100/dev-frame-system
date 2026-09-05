# AT2-07 · 停止隔离与幂等（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位参数/结果字段/状态名已替换为已落地契约；原草案第二次 stop（新 `requestId` + 旧 revision 直接 `stopped`）与"已接受消息取消"以实现口径改写（同 `request_id` 重放幂等、`queued` 才取消、`received` 保留）。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；`stopping → stopped` 宿主确认驱动仍待回填。
> 验收项：`AT2-07` / `R2.4`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- `project_stop`：`workspace_id`、`expected_revision`、稳定 `request_id`；只停止所选项目的接收；宿主经 `confirmProjectStopped` 确认停稳前返回 `status:"stopping"`；重复同一停止操作安全（同 `request_id` 重放先前结果）。
- 停止只关闭所选项目的接收、取消其 `queued` 投递（`cancelled` + `cancelReason:"project-stopped"`，保留可见）、递增 `bindingRevision` 并置 `stopping`；其他绑定、控制器与队列不受影响。原草案"停用目标驱动器/取消控制器与子会话"属宿主排空职责，路由器只落状态与投递行，以实现为准。
- `queued` 投递取消保留、不悄悄丢弃、不自动转给替代控制器；已接受（`received`）投递保留原状不受停止影响。原草案把"已接受消息"归入取消/待人工，实现区分 `queued`（取消）与 `received`（保留），以实现为准。

## 前置

- 两个不相交项目根 A、B 各已打开并运行真实 owned job（A 的后台任务写 `out-a.txt`，B 的写 `out-b.txt`，任务耗时可观察）。
- `project_stop A` 使用 `expected_revision: 1` 与 `request_id: "req-stop-a-1"`。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-07-stop-isolation`，`recording: authored`。

`session.jsonl`（Shadow 主会话）骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-stop-a-1","name":"project_stop","arguments":"{\"workspace_id\":\"ws-a\",\"expected_revision\":1,\"request_id\":\"req-stop-a-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-stop-a-1"},"content":[{"type":"tool-result","toolCallId":"call-stop-a-1","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"status\":\"stopping\",\"cancelledDeliveries\":0,\"bindingRevision\":2}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-stop-a-2","name":"project_stop","arguments":"{\"workspace_id\":\"ws-a\",\"expected_revision\":1,\"request_id\":\"req-stop-a-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-stop-a-2"},"content":[{"type":"tool-result","toolCallId":"call-stop-a-2","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"status\":\"stopping\",\"cancelledDeliveries\":0,\"bindingRevision\":2}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-a-stopped","name":"project_status","arguments":"{\"workspace_id\":\"ws-a\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-a-stopped"},"content":[{"type":"tool-result","toolCallId":"call-status-a-stopped","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-a\",\"canonicalPath\":\"<A>\",\"controllerSessionId\":\"{{session:2}}\",\"controllerLive\":false,\"profileKey\":\"devframe\",\"bindingRevision\":2,\"state\":\"stopped\",\"deliveries\":[],\"deliveriesTruncated\":false}],\"observedAt\":\"<t3>\"}"}],"isError":false}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-b","name":"project_status","arguments":"{\"workspace_id\":\"ws-b\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-b"},"content":[{"type":"tool-result","toolCallId":"call-status-b","content":[{"type":"text","text":"{\"projects\":[{\"workspaceId\":\"ws-b\",\"canonicalPath\":\"<B>\",\"controllerSessionId\":\"{{session:3}}\",\"controllerLive\":true,\"profileKey\":\"devframe\",\"bindingRevision\":1,\"state\":\"ready\",\"deliveries\":[],\"deliveriesTruncated\":false}],\"observedAt\":\"<t4>\"}"}],"isError":false}],"role":"user","id":"{{message:5}}"}}}
```

首次 stop 在 A 的 owned job 停稳前返回 `status:"stopping"`（`cancelledDeliveries` 计取消的 `queued` 投递；骨架窗口内 A 无 pending，故为 0；若停止时 A 有 `queued` 投递，则以 `cancelled` + `cancelReason:"project-stopped"` 保留可见）；宿主 `confirmProjectStopped` 确认排空后 `project_status` 观察到 `state:"stopped"`；第二次 stop 复用同 `request_id` 重放先前结果，幂等安全（原草案第二次 stop 用新 `requestId` + 旧 revision 直接返回 `stopped`——实现中该形态会 `SHADOW_STALE_REVISION`，以实现为准）。B 的 job 在 A 停止期间继续运行并完成。

错误码与状态字段已按落地实现对齐（见顶部 aligned 标记）。

## 期望断言要点

- A 停止幂等：同 `request_id` 的重复 `project_stop` 重放先前结果，无错误、无重复取消；`stopped` 在宿主确认后经 `project_status` 观察。原草案"第二次 stop 直接返回 stopped"以实现口径为准。
- A 停止在排空后完成：`stopping` 只出现在宿主 `confirmProjectStopped` 之前；确认后 `stopped`，A 的控制器与子会话停稳（无残留运行进程证据）。
- 已接受消息不悄悄丢弃：`queued` 投递取消为 `cancelled`（`cancelReason:"project-stopped"`）保留可见；`received` 投递保留原状；均不自动转给 B 或其他控制器。
- B 全程不受影响：A 停止期间 B 的 job 完成（`out-b.txt` 出现在 B 的最终 workspace 期望快照）、队列仍接受新输入、控制器日志无 stop 派生事件。
- 停止范围只限所选项目：`project_stop A` 不触碰 B 的队列、目标驱动器、控制器与子会话。

## 落地校准点

- `stopping` → `stopped` 的过渡由宿主 `confirmProjectStopped` 驱动并经 `project_status` 观察；fixture 中观察时点为录制形态（`controllerLive` 以录制时点为准）。
- owned job 的"真实"程度（真后台进程写文件）落地时与 sandbox/后台任务能力对齐。
