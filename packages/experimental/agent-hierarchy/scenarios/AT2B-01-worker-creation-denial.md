---
description: "AT2B-01 recorded-session 场景草案：worker 全拒面——delegation seam（subagent/fork）、Team 工具、宿主声明创建面逐个被 pre-execute 守卫拒绝，send_message 保留为汇报通道，继承 allow face 收缩 worker 工具列表。"
kind: "acceptance-scenario-draft"
---

# AT2B-01 场景草案：worker 全拒面

包已在 main（agent-hierarchy 合并提交 `9d0bea4b37`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-01`（组合挂载波 recorded-session 缺口）；P22 验收矩阵 `AT1-01`/`AT1-02` 的 P02 责任面的模型可见半边（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- worker 的 deny face = `delegationToolNames` + `teamToolNames` + `otherCreationToolNames` + 宿主 extras；reviewer 的 deny 语义已并入（worker 失去全部 Team spawn/task-control 工具）。
- `send_message` 对 worker 刻意放行：它是 worker 向 lead 汇报的授权通道；`project_read` 同样放行。
- 拒绝是 pre-execute 错误结果，理由文本点名角色与工具；工具体永不执行，post-execute 监听无法翻案。
- 继承 allow face 独立于 deny face 生效：不在 worker `inheritedTools` 里的受控工具从 prompt 消失，读作未知工具。

## 前提（宿主集成）

- 组合按 README 顺序挂载：session-identity → agent registry → tool registry → `@deepseek-ai/dsh-experimental-agent-hierarchy`；组合需提供绑定种子接缝，在录制会话启动前把目标会话绑定为 `role: worker`（接缝形态属组合挂载波，见开放问题）。
- 全局工具面含探针工具：`project_read`、`send_message`、`subagent`、`fork`、`spawn_teammate`、`team_task_create`、`team_task_update`、`followup_task`、`interrupt_agent`；组合另声明 `otherCreationToolNames: ['sdk_bridge_create']` 并注册同名探针工具，证明宿主声明的后续创建面被同一 deny face 覆盖。
- 两个组合变体：变体 A（guard face）把受控工具留在 worker `inheritedTools` 里，使模型可见并可发起调用、由守卫拒绝；变体 B（allow face）用 README 默认配置（worker 仅 `project_read`/`send_message`），钉 prompt 收缩面。

## 计划录制布局

`snapshots/session/agent-hierarchy-worker-creation-denial/`：`snapshot.yml`（`profile: headless`、`recording: authored`、`header` pin 同 `subagent-depth-two-rejection`、`composition: worker-guard-face`）；`cordis.snapshot.yml` 挂 experimental 两插件并禁用真实适配器、换 `llm-replay`；`session.jsonl` 为 worker 会话探针序列；`replay.override.json` 提供 authored chunks。变体 B 目录 `agent-hierarchy-worker-allow-face/` 只含 `session.jsonl` + `tool-schemas.expected.json`（sidecar 断言工具列表）。

## 剧本（replay 步骤）

worker 会话逐探针一个 turn，每探针一对 `tool/call` → `tool/result`（省略 chunk 流）：

```jsonl
{"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-w-spawn","name":"subagent","arguments":"{\"description\":\"probe\",\"prompt\":\"x\",\"run_in_background\":false}"}}
{"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-w-spawn"},"content":[{"type":"tool-result","toolCallId":"call-w-spawn","content":[{"type":"text","text":"agent-hierarchy: role \"worker\" cannot execute \"subagent\""}],"isError":true}],"role":"user","id":"{{message:2}}"}}}
{"type":"tool/call","data":{"turn":1,"step":2,"callId":"call-w-report","name":"send_message","arguments":"{}"}}
{"type":"tool/result","data":{"turn":1,"step":2,"message":{"source":{"kind":"tool","callId":"call-w-report"},"content":[{"type":"tool-result","toolCallId":"call-w-report","content":[{"type":"text","text":"WORKER_REPORT_OK"}],"isError":false}],"role":"user","id":"{{message:3}}"}}}
```

1. worker 依次调用 `subagent`、`fork`、`spawn_teammate`、`team_task_create`、`team_task_update`、`followup_task`、`interrupt_agent`、`sdk_bridge_create` → 全部 `isError: true`，文本逐一为 `agent-hierarchy: role "worker" cannot execute "<tool>"`。
2. worker 调用 `send_message` 与 `project_read` → 正常结果（`isError: false`），工具体确实执行。
3. （可选，形态见开放问题）一个无绑定 live 会话调用 `subagent` → `agent-hierarchy: session "<id>" has no role binding and cannot execute controlled tool "subagent" (missing role)`；同一会话调用 `project_read`（非受控工具）→ 放行。
4. 变体 B：worker 的 `request/header` `{{tools}}` sidecar 断言不含任何受控工具，且 `project_read`/`send_message` 在列。

## 可观察通过标准

- 步骤 1 每个拒绝文本与 guard.ts 的 deny-face 理由逐字符一致；拒绝先于工具体（探针工具体无副作用、无成功文本）。
- 步骤 2 证明拒绝对象是"创建面"而非 worker 的全部工具面；`send_message` 保留是契约而非遗漏。
- 变体 B 的工具列表收缩与守卫拒绝互补：两层各自独立成立。

## 环境与安全

全部身份与 pluginId 为合成值；探针工具为内容 fixture，无文件、无网络、无子进程。

## 开放问题

- 绑定种子接缝（录制前写入 `ctx.agentBindings` 的宿主手段）未定；未就绪则本条记 `blocked`，不以包内单测替代。
- 无绑定会话探针取决于组合能否安排未绑定的 live 会话；否则该子案留在 `AT1-01`/`AT1-02` 探针测试持有。
- pre-execute 拒绝在 session log 中的精确事件形态（错误结果的 envelope 字段）以首录为准回填本文 JSONL。
