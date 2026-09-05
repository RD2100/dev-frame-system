# AT2-07 · 停止隔离与幂等（场景草案）

> 状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。
> 验收项：`AT2-07` / `R2.4`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- `project_stop`：`workspaceId`、预期版本、稳定 `requestId`；只停止所选项目的接收与执行工作；所属工作停稳前返回 `stopping`；重复同一停止操作是安全的。
- 停止只关闭所选项目的队列、停用其目标驱动器、取消其控制器与子会话，等待所属进程停稳。
- 已接受消息保留为取消或待人工处理，不悄悄丢弃，也不自动转给替代控制器。

## 前置

- 两个不相交项目根 A、B 各已打开并运行真实 owned job（A 的后台任务写 `out-a.txt`，B 的写 `out-b.txt`，任务耗时可观察）。
- `project_stop A` 使用预期版本与 `requestId` 为 `req-stop-a-1`。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-07-stop-isolation`，`recording: authored`。

`session.jsonl`（Shadow 主会话）骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-stop-a-1","name":"project_stop","arguments":"{\"workspaceId\":\"ws-a\",\"expectedRevision\":1,\"requestId\":\"req-stop-a-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-stop-a-1"},"content":[{"type":"tool-result","toolCallId":"call-stop-a-1","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"stopping\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-stop-a-2","name":"project_stop","arguments":"{\"workspaceId\":\"ws-a\",\"expectedRevision\":1,\"requestId\":\"req-stop-a-2\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-stop-a-2"},"content":[{"type":"tool-result","toolCallId":"call-stop-a-2","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"state\":\"stopped\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-status-b","name":"project_status","arguments":"{\"workspaceId\":\"ws-b\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-status-b"},"content":[{"type":"tool-result","toolCallId":"call-status-b","content":[{"type":"text","text":"{\"workspaceId\":\"ws-b\",\"state\":\"running\",\"observedAt\":0,\"blockReason\":null}"}],"isError":false}],"role":"user","id":"{{message:4}}"}}}
```

首次 stop 在 A 的 owned job 停稳前返回 `stopping`；A 排空后到达 `stopped`；第二次 stop 幂等安全。B 的 job 在 A 停止期间继续运行并完成。

错误码与状态字段为草案命名，Shadow 落地后对齐。

## 期望断言要点

- A 停止幂等：两次 `project_stop` 都成功，最终状态一致为 `stopped`；无重复取消、无错误。
- A 停止在排空后完成：`stopping` 只出现在所属工作停稳之前；A 的控制器与子会话停稳（无残留运行进程证据）。
- 已接受消息不悄悄丢弃：A 队列中已接受的投递保留为取消/待人工状态，不自动转给 B 或其他控制器。
- B 全程不受影响：A 停止期间 B 的 job 完成（`out-b.txt` 出现在 B 的最终 workspace 期望快照）、队列仍接受新输入、控制器日志无 stop 派生事件。
- 停止范围只限所选项目：`project_stop A` 不触碰 B 的队列、目标驱动器、控制器与子会话。

## 落地校准点

- `stopping` → `stopped` 的过渡观察方式（状态轮询 vs stop 返回即排空完成）以实现为准；fixture 中两次 stop 的间隔为录制形态。
- owned job 的"真实"程度（真后台进程写文件）落地时与 sandbox/后台任务能力对齐。
