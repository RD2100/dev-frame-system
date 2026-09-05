# AT2-05 · 投递链路三处中断与回执收敛（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位参数/结果字段/状态名已替换为已落地契约；原草案 sender/target 两方四步顺序与 `ambiguous` 标记以实现口径改写（单写者两写 + 请求重放日志）。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；中断注入与存储重开驱动仍待回填。
> 验收项：`AT2-05` / `R2.3`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 持久化投递为同一投递行两写：先 `queued`（sender intent）后 `received`（target-accepted input），均写穿 `shadow_router` domain `deliveries` 表；`completed` 是宿主经 `completeDelivery` 独立落定的状态。原草案按 sender/target 两方画 intent+flush → accepted+flush → receipt+flush 三段，实现为单写者两写 + `requests` 请求重放日志，以实现为准。
- `received` ≠ `completed`；回执恢复不得重复模型可见任务（`queued → received` 单向，已 `received` 的行不重新入队）。
- 目标去重覆盖持久化收件输入：崩溃残留行按 `assertSameDelivery` 校验 workspaceId/bindingRevision/goalId/acceptanceHash/mode/text/source 全匹配，不一致报 `SHADOW_REQUEST_CONFLICT`；结果未知由请求重放日志裁决（同 id 同输入重放先前结果，同 id 异输入 `SHADOW_REQUEST_CONFLICT`）。原草案的 `ambiguous` 标记未落地，以实现为准。
- 两种受支持存储后端都各自验证后才可声称两者都通过。

## 前置

- 项目根 A 已打开（`workspaceId` 为 `ws-a`，关联版本 1），真实存储后端可重开。
- 一条 `work` 投递：`request_id` 为 `req-send-dl-a-1`（首次持久化前固定，重试不变）；投递 `messageId` 由实现派生为 `msg-<request_id>`，即 `msg-req-send-dl-a-1`（原草案 `dl-a-1`）。
- 中断点按实现两写边界对齐：`queued` 落盘前、`queued` 已落 `received` 未落、`received` 已落但 `requests` 重放日志未记。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-05-delivery-interruption`，`recording: authored`；两种存储后端落地后以两个变体 fixture 或 manifest 环境维度区分。

`session.jsonl`（Shadow 主会话）投递骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-send-1","name":"project_send","arguments":"{\"workspace_id\":\"ws-a\",\"binding_revision\":1,\"goal_id\":\"goal-a-1\",\"acceptance_hash\":\"hash-a-1\",\"request_id\":\"req-send-dl-a-1\",\"mode\":\"work\",\"text\":\"Write out-a.txt containing: deliver once\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-send-1"},"content":[{"type":"tool-result","toolCallId":"call-send-1","content":[{"type":"text","text":"{\"messageId\":\"msg-req-send-dl-a-1\",\"workspaceId\":\"ws-a\",\"status\":\"received\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"step/end","data":{"turn":1,"step":1}}
{"type":"turn/end","data":{"turn":1,"reason":{"kind":"completed"}}}
```

中断变体（落地后以重启/恢复驱动，事件为草案）：

- 变体 A — 接受前中断（`queued` 落盘前后）：重放投递（同 `request_id` 不变）→ 崩溃残留 `queued` 行按同一 `messageId` 校验（`assertSameDelivery`）后收敛为 `received`，接受恰一次；若结果已入重放日志则直接重放先前结果，不再入队。
- 变体 B — `received` 已落、发送者回执未记中断：重开真实存储后核对：`received` 行已在，重试收敛于同一投递并补齐回执（`queued → received` 单向，不重新入队），不重复安排模型可见任务。

`session.1.jsonl`（控制器 A）：恰一条该投递的模型可见输入（`agent/inbox/spliced` 或落地后的专用投递事件；投递呈现是宿主侧职责，见 README Known Limitations）与其后的单一 work turn。

结果字段、状态名与错误码已按落地实现对齐（见顶部 aligned 标记）。

## 期望断言要点

- 同一 message ID 收敛为一条 accepted 输入：控制器 A 日志中该投递的模型可见输入恰出现一次，不因任一中断点重放而翻倍。
- 回执恢复不重复模型可见任务：变体 B 重开后不产生第二个 work turn；不能仅因发送端缺回执就重复不可逆工作。
- 持久化顺序可从存储核对：同一投递行先 `queued` 后 `received`（各一次写穿），随后结果入 `requests` 重放日志（落地后以存储重开验证，而非内存态；原草案 intent→accepted→receipt 三段 flush 实现为单行两写 + 重放日志）。
- 若命令可能在崩溃前已启动但结果未知：工具回执永远只声称 `status:"received"`，不声称已执行或成功；"是否已执行"不进入路由器状态，由宿主侧原生后台任务/进程证据承担（原草案 `ambiguous` 标记未落地，以实现为准）。
- 两种受支持存储后端各跑一轮并通过后，才在结论里声称两者都覆盖；单后端通过时只声称该后端。

## 落地校准点

- 中断注入、真实存储重开与重放日志核对的驱动形态（重启 harness、组合 patch 或 replay override）落地时确定并回填。
- "一条模型可见输入"的具体事件类型（`agent/inbox/spliced` vs 专用投递事件）以实现为准。
