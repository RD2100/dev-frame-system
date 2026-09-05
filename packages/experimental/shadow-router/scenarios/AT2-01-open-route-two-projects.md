# AT2-01 · Shadow 打开 A/B 并分发不同工作（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位工具参数/结果字段/状态名已替换为 packages/experimental/shadow-router 已落地契约（src/tools.ts、src/service.ts、src/errors.ts）。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；fixture 化与控制器侧投递呈现仍待回填。
> 验收项：`AT2-01` / `R2.1`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)（闭式 `snapshot.yml` + 主 `session.jsonl`）；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- `project_open`：已有且获授权的 `path`、稳定 `request_id` → 返回 `workspaceId`、`controllerSessionId`、`bindingRevision`、`state`、`canonicalPath`；`state:"ready"` 为可用态。
- `project_send`：`workspace_id`、`binding_revision`、`goal_id`、`acceptance_hash`、稳定 `request_id`、`mode`（`work`/`note`）、有界文本 → 投递 `messageId`（实现派生为 `msg-<request_id>`）与 `status:"received"` 回执；回执只证明目标接受，不代表执行成功。
- 独立根会话按项目获准的 cwd 与 preset 创建，不把 Shadow 设为其 subagent 父会话；一个获授权工作区对应一个当前控制器。

## 前置

- 两个不相交的临时项目根 A、B（真实目录），任务与输出文件可区分：A 写 `out-a.txt`，B 写 `out-b.txt`。
- Shadow 主会话以 headless profile 启动；A、B 均已获用户授权（宿主侧授权，不由 Shadow 自造；`authorizedRoots` 覆盖 A、B）。

## 会话事件序列草案

`snapshot.yml` 草案：

```yaml
version: 1
scenario: at2-01-open-route-two-projects
profile: headless
composition: default
recording: authored
header:
  class: default
```

`session.jsonl`（Shadow 主会话）骨架（省略 assistant/chunk 流、runtime-context 注入行与 seq/time 信封；完整形态对齐 `snapshots/session/text-turn/session.jsonl`）：

```jsonl
{"type":"session","version":0,"id":"{{session:1}}","createdAt":0,"cwd":"{{cwd}}","delegationDepth":0}
{"type":"permission/preset","data":{"preset":"danger-full-access"}}
{"type":"sandbox/mode","data":{"mode":"danger-full-access"}}
{"type":"approval/policy","data":{"policy":"never"}}
{"type":"agent/inbox/spliced","data":{"target":"next-turn","start":0,"inserted":[{"content":[{"type":"text","text":"Open projects A and B through the project tools, send the A task to A and the B task to B, then report both delivery receipts."}],"source":{"kind":"user"},"role":"user","id":"{{message:1}}"}]}}
{"type":"turn/start","data":{"turn":1}}
{"type":"step/start","data":{"turn":1,"step":1}}
{"type":"request/header","data":{"header":{"config":{}},"system":"{{system}}","tools":"{{tools}}"},"reason":"initial"}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-a","name":"project_open","arguments":"{\"path\":\"<A>\",\"request_id\":\"req-open-a-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-a"},"content":[{"type":"tool-result","toolCallId":"call-open-a","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"controllerSessionId\":\"{{session:2}}\",\"bindingRevision\":1,\"state\":\"ready\",\"canonicalPath\":\"<A>\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-b","name":"project_open","arguments":"{\"path\":\"<B>\",\"request_id\":\"req-open-b-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-b"},"content":[{"type":"tool-result","toolCallId":"call-open-b","content":[{"type":"text","text":"{\"workspaceId\":\"ws-b\",\"controllerSessionId\":\"{{session:3}}\",\"bindingRevision\":1,\"state\":\"ready\",\"canonicalPath\":\"<B>\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-a","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-a-1\",\"mode\":\"work\",\"text\":\"Write out-a.txt containing: task A\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-a"},"content":[{"type":"tool-result","toolCallId":"call-send-a","content":[{"type":"text","text":"{\"messageId\":\"msg-req-send-a-1\",\"workspaceId\":\"ws-a\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-b","name":"project_send","arguments":"{\"workspace_id\":\"ws-b\",\"binding_revision\":1,\"goal_id\":\"goal-b-1\",\"acceptance_hash\":\"hash-b-1\",\"request_id\":\"req-send-b-1\",\"mode\":\"work\",\"text\":\"Write out-b.txt containing: task B\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-b"},"content":[{"type":"tool-result","toolCallId":"call-send-b","content":[{"type":"text","text":"{\"messageId\":\"msg-req-send-b-1\",\"workspaceId\":\"ws-b\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:5}}"}}}
{"type":"step/end","data":{"turn":1,"step":1}}
{"type":"turn/end","data":{"turn":1,"reason":{"kind":"completed"}}}
```

`session.1.jsonl`（控制器 A，根会话）：头行 `"id":"{{session:2}}","cwd":"<A>","delegationDepth":0`，无 `parentSession`；work 输入到达后安排跟进 turn。
`session.2.jsonl`（控制器 B，根会话）：头行 `"id":"{{session:3}}","cwd":"<B>","delegationDepth":0`，无 `parentSession`。
结果字段名、工具参数与状态名已按落地实现对齐（见顶部 aligned 标记）；`{{session:N}}`/`{{message:N}}`/`{{cwd}}` 为身份化 token，遵循快照语料约定。

## 期望断言要点

- 存在两个互相独立的控制器根：`{{session:2}}`、`{{session:3}}` 头部均无 `parentSession`，`cwd` 分别为 A、B。
- 控制器的 worker 子会话只挂在正确根下：`parentSession` 分别等于 `{{session:2}}` / `{{session:3}}`，无跨根父子关系。
- A/B 会话日志无任何 Team 或嵌套任务板事件（无 team 成员、team task 类事件）。
- 输出留在目标项目：`out-a.txt` 只出现在 A 的最终 workspace 期望快照，`out-b.txt` 只出现在 B。
- `project_send` 的回执是接收类状态（`status:"received"`），不是执行完成；A 的投递内容不出现在 B 的日志，反之亦然。
- fixture 不含 `input.json` / `stdout.expected.jsonl`：headless 任务的 accepted 输入来自 session JSONL（`snapshots/AGENTS.md` 约定）。

## 落地校准点

- 控制器根会话与其 worker 的日志落在 A/B 各自 cwd 的 `.dsh/sessions` 下，headless 收割只覆盖主 cwd；fixture 收集范围需在 Shadow 落地时通过组合 patch 或宿主侧记录决定。
- `project_send` 的 `work` 跟进 turn 在目标控制器中的确切事件形态（`agent/inbox/spliced` 还是专用投递事件）以实现为准（README Known Limitations：投递呈现是宿主侧职责，bare mount 收不到模型可见输入）。
