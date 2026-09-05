# AT2-03 · 重复打开去重与预留中断恢复（场景草案）

> 状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。
> 验收项：`AT2-03` / `R2.2`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 在每工作区创建互斥范围内读取已有关联；有效就返回，不去重失败产生第二个控制器。
- 关联不存在时先预留控制器会话 ID，并在创建会话前持久化创建中的关联；只有会话创建和必需角色设置持久化后才保存就绪状态并返回结果。
- 预留之后崩溃时围绕同一个会话 ID 核对；身份、cwd 或策略不匹配才置 `needs_attention`，不通过另建写入者兜底。

## 前置

- 单一已授权项目根 A（真实目录）。
- 并发/重复 `project_open` 调用使用不同 `requestId`（`req-open-a-1`、`req-open-a-2`），规范化输入相同。
- 中断注入点：绑定预留持久化之后、根会话就绪之前。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-03-open-dedup-recovery`，`recording: authored`。

`session.jsonl`（Shadow 主会话）两阶段骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-1","name":"project_open","arguments":"{\"path\":\"<A>\",\"requestId\":\"req-open-a-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-1"},"content":[{"type":"tool-result","toolCallId":"call-open-1","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"controllerSessionId\":\"{{session:2}}\",\"bindingRevision\":1,\"ready\":true}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-2","name":"project_open","arguments":"{\"path\":\"<A>\",\"requestId\":\"req-open-a-2\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-2"},"content":[{"type":"tool-result","toolCallId":"call-open-2","content":[{"type":"text","text":"{\"workspaceId\":\"ws-a\",\"controllerSessionId\":\"{{session:2}}\",\"bindingRevision\":1,\"ready\":true}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"step/end","data":{"turn":1,"step":1}}
{"type":"turn/end","data":{"turn":1,"reason":{"kind":"completed"}}}
```

第二次 open 返回的 `controllerSessionId` 与第一次相同：并发重复 open 全部收敛到同一预留/当前控制器。

中断恢复段（落地后以重启/恢复驱动，事件为草案）：在预留关联（`reserved` 状态、`controllerSessionId":"{{session:2}}"` 已持久化）与根会话就绪之间注入中断；恢复运行核对同一会话 ID 后完成创建，`project_open` 重试返回 `ready":true`。

错误码与状态字段为草案命名，Shadow 落地后对齐。

## 期望断言要点

- 同一获授权工作区解析出唯一控制器：两次不同 `requestId` 的 open 返回同一 `workspaceId` + `controllerSessionId` + `bindingRevision`。
- 恰好一个控制器根会话存在：A 的 `.dsh/sessions` 只有一个 `delegationDepth":0` 的控制器日志；无重复写入者、无被悄悄替换的根（第二次 open 不产生新会话 ID）。
- 预留中断后恢复：围绕同一会话 ID 核对成功并收敛为 `ready`；不另建第二个写入者兜底。
- `ready` 只在会话创建与必需角色设置持久化之后返回（就绪前 open 不返回成功结果）。
- 中断注入与恢复驱动的具体形态（重启 harness、composition patch 或 replay override）在落地时确定并回填本草案。

## 落地校准点

- headless snapshot 是单进程一次运行的收割模型；"中断—重启—恢复"需要扩展驱动或专用组合，落地时对齐 fixture 结构与 manifest 字段。
- 并发 open 的序列化由每工作区创建互斥保证；fixture 中两条 `tool/call` 的先后为录制形态，不约束真实并发调度顺序。
