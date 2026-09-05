# AT2-04 · 路径别名一致性与物理重叠根（场景草案）

> aligned: 2026-09-06 vs eff2e5b6af90e913d810bdc57c784febae809bc7 — 占位参数/结果字段/错误码已替换为已落地契约；重叠拒绝为 `SHADOW_ROOTS_OVERLAP`。
> 状态：aligned — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md)）；junction fixture 支撑仍待回填。
> 验收项：`AT2-04` / `R2.2`，定义见 [docs/testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part2)。
> fixture 形态对齐 [snapshots/session/](../../../../snapshots/session/)；本文只画事件骨架，不改任何 src。

## 覆盖契约要点

- 按原生工作区规则及实际文件系统规范化已有根目录（`fs.realpath` canon），包括 Windows 大小写和 junction 别名。
- 拒绝物理范围重叠且准备同时写入的根目录（`SHADOW_ROOTS_OVERLAP`）；实现为 segment-aware（`isWithinPath`）判定，仅靠字符串前缀检查不够。
- 不支持的别名语义要报告为未测试，不得声称已覆盖。

## 前置

- 项目根 P（真实目录）；其大小写变体路径（Windows）与指向 P 的 junction 别名 J。
- 物理重叠根对：P 与其子目录 `P/sub`，两者都准备同时写入。
- 支持别名声义的文件系统上运行；不支持的语义按平台显式标注。

## 会话事件序列草案

`snapshot.yml` 草案：同 AT2-01 形态，`scenario: at2-04-alias-overlap`，`recording: authored`。

`session.jsonl`（Shadow 主会话）探针骨架：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-case","name":"project_open","arguments":"{\"path\":\"<p-case-variant>\",\"request_id\":\"req-open-case-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-case"},"content":[{"type":"tool-result","toolCallId":"call-open-case","content":[{"type":"text","text":"{\"workspaceId\":\"ws-p\",\"controllerSessionId\":\"{{session:2}}\",\"bindingRevision\":1,\"state\":\"ready\",\"canonicalPath\":\"<P>\"}"}],"isError":false}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-junction","name":"project_open","arguments":"{\"path\":\"<J>\",\"request_id\":\"req-open-junction-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-junction"},"content":[{"type":"tool-result","toolCallId":"call-open-junction","content":[{"type":"text","text":"{\"workspaceId\":\"ws-p\",\"controllerSessionId\":\"{{session:2}}\",\"bindingRevision\":1,\"state\":\"ready\",\"canonicalPath\":\"<P>\"}"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-open-sub","name":"project_open","arguments":"{\"path\":\"<P/sub>\",\"request_id\":\"req-open-sub-1\"}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-open-sub"},"content":[{"type":"tool-result","toolCallId":"call-open-sub","content":[{"type":"text","text":"root \"<P/sub>\" physically overlaps project \"ws-p\" at \"<P>\""}],"isError":true}],"role":"user","id":"{{message:4}}"}}}
```

大小写变体与 junction 别名都解析到同一 `workspaceId` / `controllerSessionId`（规范化 `canonicalPath` 均为 `<P>`）；重叠根的 open 被显式拒绝（`SHADOW_ROOTS_OVERLAP`）。

错误码与结果字段已按落地实现对齐（见顶部 aligned 标记）；junction 创建方式（workspace setup 钩子或平台前置）落地时确定。

## 期望断言要点

- 别名一致性：大小写变体路径与 junction 别名解析出同一 `workspaceId` + `controllerSessionId` + `canonicalPath`，不产生第二条关联或第二个控制器会话。
- 重叠拒绝：对 `P/sub` 的 open（准备与 P 同时写入）被拒绝，错误显式（`SHADOW_ROOTS_OVERLAP`）；存在独立于字符串前缀的规范化/重叠判定证据（实现侧 segment-aware 判定拒绝 `D:\a` 与 `D:\ab` 混淆）。
- 不声称未测试的语义：fixture 与 manifest 只覆盖已支持平台；junction 为 Windows 语义，posix 仅断言大小写规范化，其余别名语义标注为未测试。
- 拒绝不产生副作用：`P` 的控制器状态与工作区在重叠拒绝前后不变。

## 落地校准点

- snapshot 环境里 junction 的创建与清理需要 workspace setup 支撑（`session.jsonl` 收割在 junction 目标侧，不在别名侧），落地时回填 fixture 结构。
- "物理重叠"判定的可观察证据（`SHADOW_ROOTS_OVERLAP` 错误、关联表状态）以实现为准；本草案断言拒绝发生与无副作用，不断言内部判定算法。
