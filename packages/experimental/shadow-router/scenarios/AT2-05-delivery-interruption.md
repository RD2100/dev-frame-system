# AT2-05 · 投递链路三处中断与回执收敛（场景草案）

> 状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。
> 验收项：`AT2-05` / `R2.3`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 持久化投递顺序：Sender persist intent + flush → Target validate identity/revision + deduplicate messageId → Target persist accepted input + flush → Sender persist received receipt + flush。
- `received != started != completed`；回执恢复不得重复模型可见任务。
- 目标去重覆盖持久化收件输入，不覆盖任意外部副作用；结果未知时执行标为 `ambiguous`，查原生后台任务/进程证据。
- 两种受支持存储后端都各自验证后才可声称两者都通过。

## 前置

- 项目根 A 已打开（`workspaceId` 为 `ws-a`，`bindingRevision` 为 `1`），真实存储后端可重开。
- 一条 `work` 投递 `dl-a-1`（`messageId`/`requestId` 在首次持久化前固定，重试不变）。
- 三个中断点：目标接受前、目标 flush 后（发送者回执前）、发送者回执前。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-05-delivery-interruption`，`recording: authored`；两种存储后端落地后以两个变体 fixture 或 manifest 环境维度区分。

`session.jsonl`（Shadow 主会话）投递骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-1","name":"project_send","arguments":"{\"workspaceId\":\"ws-a\",\"bindingRevision\":1,\"goalId\":\"goal-a-1\",\"acceptanceHash\":\"hash-a-1\",\"requestId\":\"req-send-dl-a-1\",\"mode\":\"work\",\"text\":\"Write out-a.txt containing: deliver once\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-1"},"content":[{"type":"tool-result","toolCallId":"call-send-1","content":[{"type":"text","text":"{\"deliveryId\":\"dl-a-1\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"step/end","data":{"turn":1,"step":1}}
{"type":"turn/end","data":{"turn":1,"reason":{"kind":"completed"}}}
```

中断变体（落地后以重启/恢复驱动，事件为草案）：

- 变体 A — 目标接受前中断：发送意图已持久化并 flush，目标尚未接受。重放投递（同 `messageId`/`requestId`）→ 目标验证 + 去重 + 接受一次。
- 变体 B — 目标 flush 后、发送者回执前中断：目标已持久化 accepted input，发送者无回执。重开真实存储后核对：不重复安排模型可见任务，发送者补齐 received 回执。

`session.1.jsonl`（控制器 A）：恰一条该投递的模型可见输入（`agent/inbox/spliced` 或落地后的专用投递事件）与其后的单一 work turn。

错误码、`ambiguous` 标记位置与投递事件名均为草案命名，Shadow 落地后对齐。

## 期望断言要点

- 同一 message ID 收敛为一条 accepted 输入：控制器 A 日志中该投递的模型可见输入恰出现一次，不因任一中断点重放而翻倍。
- 回执恢复不重复模型可见任务：变体 B 重开后不产生第二个 work turn；不能仅因发送端缺回执就重复不可逆工作。
- 持久化顺序可从日志核对：sender intent → target accepted → sender receipt，各自有 flush 边界（落地后以存储重开验证，而非内存态）。
- 若命令可能在崩溃前已启动但结果未知，执行标为 `ambiguous` 并核对原生后台任务/进程证据；不冒充成功或失败。
- 两种受支持存储后端各跑一轮并通过后，才在结论里声称两者都覆盖；单后端通过时只声称该后端。

## 落地校准点

- 中断注入、真实存储重开与 `ambiguous` 证据检查的驱动形态（重启 harness、组合 patch 或 replay override）落地时确定并回填。
- "一条模型可见输入"的具体事件类型（`agent/inbox/spliced` vs 专用投递事件）以实现为准。
