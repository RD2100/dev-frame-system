# AT2-02 · Shadow 工具防护与禁止面探针（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位错误码/拒绝文案/工具参数已替换为 packages/experimental/shadow-router 已落地契约；`<raw-session-control>` 落地名不属本包，另行对齐。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；fixture 化仍待回填。
> 验收项：`AT2-02` / `R2.1`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 项目工具只暴露给 Shadow；项目开发者与审查者不获得这四个工具。
- Shadow 面向模型的允许列表只含路由工具与明确启用的用户记忆访问；不含任意文件系统/shell、原始会话控制工具、插件自我修改、无限制 MCP。
- 调用者不能提供任意目标会话 ID：工具参数面无目标会话字段，未知参数即拒（`SHADOW_INVALID_REQUEST`）；宿主从已授权关联解析目标。`project_open` 拒绝缺失目录（`SHADOW_ROOT_MISSING`）与未授权根（`SHADOW_ROOT_UNAUTHORIZED`），不悄悄创建目录；`binding_revision` 为 0 或负数在参数校验即拒（`SHADOW_INVALID_REQUEST`），正整数旧版本才是 `SHADOW_STALE_REVISION`（见 AT2-06）。
- 解析会话之前先校验工具 JSON、实际调用者（`SHADOW_CALLER_FORBIDDEN`）与工作区授权。

## 前置

- 同 AT2-01 的两个项目根 A、B；一个已打开的控制器（A，`workspaceId` 为 `ws-a`，`bindingRevision` 当前为 `1`）。
- 一个项目 worker 会话（控制器 A 的子会话）可被驱动以尝试调用项目工具。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-02-forbidden-probes`，`recording: authored`。

`session.jsonl`（Shadow 主会话）探针序列（每个探针一个 turn，只列 `tool/call` 与 `tool/result` 对；省略 chunk 流）：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-shell","name":"bash","arguments":"{\"command\":\"echo pwned\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-shell"},"content":[{"type":"tool-result","toolCallId":"call-shell","content":[{"type":"text","text":"rejected: tool not in the Shadow allow-list"}],"isError":true}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-raw","name":"<raw-session-control>","arguments":"{\"sessionId\":\"{{session:2}}\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-raw"},"content":[{"type":"tool-result","toolCallId":"call-raw","content":[{"type":"text","text":"rejected: raw session control is not exposed to Shadow"}],"isError":true}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-arb","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-arb-1\",\"mode\":\"work\",\"text\":\"x\",\"target_session_id\":\"99999999-4444-4999-8999-999999999999\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-arb"},"content":[{"type":"tool-result","toolCallId":"call-send-arb","content":[{"type":"text","text":"project tool \"project_send\" received unknown argument(s): target_session_id"}],"isError":true}],"role":"user","id":"{{message:4}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-unauth","name":"project_open","arguments":"{\"path\":\"<unauthorized>\",\"request_id\":\"req-open-unauth-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-unauth"},"content":[{"type":"tool-result","toolCallId":"call-open-unauth","content":[{"type":"text","text":"root \"<canonical>\" is not covered by any authorized root"}],"isError":true}],"role":"user","id":"{{message:5}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-stale","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":0,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-stale-1\",\"mode\":\"work\",\"text\":\"stale attempt\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-stale"},"content":[{"type":"tool-result","toolCallId":"call-send-stale","content":[{"type":"text","text":"bindingRevision must be a positive safe integer"}],"isError":true}],"role":"user","id":"{{message:6}}"}}}
```

`session.1.jsonl`（控制器 A 的 worker 子会话，`parentSession":"{{session:2}}"`）：worker 以本会话工具面尝试 `project_send` → 结果为工具不存在（实现按 scope 安装，worker 面无 `project_*`；`isError":true`）；worker 自身工具列表（`request/header` 的 `{{tools}}` token，落地后由 sidecar 固定）不含 `project_*`。

错误码与拒绝文案已对齐落地实现（`SHADOW_INVALID_REQUEST` / `SHADOW_ROOT_UNAUTHORIZED` 等，见顶部 aligned 标记）；原始会话控制工具的落地名（`<raw-session-control>` 占位）与 shell 工具拒绝文案不属 shadow-router 契约，落地后另行对齐。

## 期望断言要点

- 所有禁止请求在目标变更前失败：控制器 A 与其 worker 的日志无任何由探针产生的输入、turn 或投递事件；A 工作区无新目录（`workspace.final` 不变或与期望快照一致）。
- worker 会话的模型允许列表不含 `project_open`/`project_send`/`project_status`/`project_stop`；其调用尝试被工具缺席拒绝（服务层 `SHADOW_CALLER_FORBIDDEN` 守卫覆盖宿主直调服务方法的路径）。
- Shadow 的 `{{tools}}` 允许列表（tool-schemas sidecar）不含 shell、原始会话控制、插件自我修改、无限制 MCP 工具。
- 携带任意 `target_session_id` 字段的 `project_send` 被拒绝（`SHADOW_INVALID_REQUEST`，未知参数即拒）：工具参数面无目标会话字段，目标会话 ID 只能由宿主从已授权关联解析。
- 未授权 `path` 的 `project_open` 被拒（`SHADOW_ROOT_UNAUTHORIZED`）且不创建目录；`binding_revision: 0` 的投递被拒（`SHADOW_INVALID_REQUEST`）；正整数旧版本（如 Goal 切换/stop 递增后的旧值）才是 `SHADOW_STALE_REVISION`（见 AT2-06）。
- 所有拒绝文本只含错误类别，不含项目内容、路径内容或秘密（断言拒绝文本中无 A/B 任务文本回显）。

## 落地校准点

- worker 侧拒绝形态已按实现确定：`markShadow` 只把四工具装入 Shadow scope，worker 工具面无 `project_*`（工具缺席即拒绝）；`SHADOW_CALLER_FORBIDDEN` 是服务层守卫，宿主直调服务方法时可达。两种形态都满足"调用失败且无副作用"，断言取并集。
