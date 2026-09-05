---
description: "AT2C-05 recorded-session 场景草案：准入切断 fail-closed——冷态 closed 拒、开门恰一身份、换代即旧身份失配，ADMISSION_CLOSED 与 IDENTITY_MISMATCH 两码分离，flush 失败关 admission 并扣住 writer，恢复唯显式重开。"
kind: "acceptance-scenario-draft"
---

# AT2C-05 场景草案：准入切断 fail-closed

包已在 main（agent-reliability 合并提交 `312fe9cd7c`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-05`；P22 验收矩阵 `AT4-06`/`AT4-07` 的 P06 责任面（准入切断 + flush 失败）的模型可见半边（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6b 节；[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-4-acceptance)）。

## 覆盖契约要点

- admission 是进程局部状态、初值 closed：新进程任何 `assertAdmitted` → `AGENT_RELIABILITY_ADMISSION_CLOSED`（`admission is closed`），先于任何模型或工具工作。
- `openAdmission` 恰为一个 work binding identity（`controllerSessionId` + `goalId`）开门；再次开门替换旧 identity（新 dispatch generation），旧身份随即失配。
- 身份不匹配 → `AGENT_RELIABILITY_IDENTITY_MISMATCH`（`work binding does not match the admitted identity; dispatch rejected`）；两稳定码分离，dispatch 可区分"从未开门"与"换代"。
- `flushBarrier`：成功 → `{ flushed: true, admissionClosed: false, writerRetained: false, failure: undefined }`；失败 → 关 admission、`writerRetained: true`、`failure` 携带原因——写入者绝不在未刷盘日志上释放。
- 失败后的恢复唯一路径是宿主显式 `openAdmission`，无隐式重开。

## 前提（宿主集成）

- 单插件挂载（`@deepseek-ai/dsh-experimental-agent-reliability`，injects nothing）。
- 模型可见桥由组合挂载波提供（工具桥，落地名草案：`reliability_probe`），暴露 `admissionState` 读、`open(identity)`、`assert(identity)`、`flush(fail?: boolean)`——flush 注错由桥内合成 fixture（注定 reject 的 flush 函数）提供，不触真实 writer；桥形态未定前本条记 `blocked`，不降级为包内单测。
- 合成 identity：identity-1 = `{ controllerSessionId: 'controller-1', goalId: 'goal-1' }`；identity-2/3 换 goal 或 controller 以制造失配。

## 计划录制布局

`snapshots/session/agent-reliability-admission-cutoff-fail-closed/`：`snapshot.yml`（`profile: headless`、`recording: authored`、header pin 同 `text-turn`）；`session.jsonl` 单会话桥探针序列。结果为纯数据 outcome，无落盘期望（服务无 durable 投影）。

## 剧本（replay 步骤）

1. 冷态：`admissionState` → `closed`；`assert(identity-1)` → `AGENT_RELIABILITY_ADMISSION_CLOSED`（`admission is closed`）。
2. `open(identity-1)` → state `open`；`assert(identity-1)` → 放行（无错）。
3. 失配双探针：`assert(identity-2)`（goalId 换 `goal-2`）→ `AGENT_RELIABILITY_IDENTITY_MISMATCH`；`assert({ controllerSessionId: 'controller-2', goalId: 'goal-1' })` → 同码（两半各自独立）。
4. 换代：`open(identity-3{controller-1, goal-3})` → `assert(identity-1)` → `IDENTITY_MISMATCH`（旧代已失效）。
5. flush 成功：`flush(fail: false)` → `{ flushed: true, admissionClosed: false, writerRetained: false, failure: undefined }`；state 仍 `open`。
6. flush 失败：`flush(fail: true)` → `{ flushed: false, admissionClosed: true, writerRetained: true, failure: <fixture 原因> }`；state → `closed`。
7. 失败后收敛：`assert(identity-3)` → `ADMISSION_CLOSED`（fail-closed 实证）；宿主重新 `open(identity-3)` → `assert` 放行（恢复是显式动作）。

## 可观察通过标准

- 两个稳定码各有独立探针，文本与 `src/service.ts`/`src/errors.ts` 逐字符一致。
- flush 失败的三个标志（`admissionClosed`/`writerRetained`/`failure`）同现，且 admission 实际关闭（步骤 7 的 assert 证明），不是只报告。
- 恢复路径唯一：失败与换代之后都只有显式 `open` 能放行。

## 环境与安全

identity 全合成；flush fixture 为组合内函数（fail 标志注入），零文件、零进程树副作用；`stopProject` 真实进程树面不在本场景。

## 开放问题

- 桥落地形态、identity 参数面与 outcome envelope 以首录回填（JSONL 待定）：
  ```jsonl
  {"type":"tool/call","data":{"turn":1,"step":1,"callId":"call-r-assert","name":"reliability_probe","arguments":"{\"op\":\"assert\",\"identity\":{\"controllerSessionId\":\"controller-1\",\"goalId\":\"goal-1\"}}"}}
  {"type":"tool/result","data":{"turn":1,"step":1,"message":{"source":{"kind":"tool","callId":"call-r-assert"},"content":[{"type":"tool-result","toolCallId":"call-r-assert","content":[{"type":"text","text":"AGENT_RELIABILITY_ADMISSION_CLOSED: admission is closed"}],"isError":true}],"role":"user","id":"{{message:2}}"}}}
  ```
- 重启丢 admission（进程局部 fail-closed 的重启半边）归重启探针/P22 真实测试，不属单次 replay。
- `stopProject` 委托面（DevFrame stop 契约，单实现单测试家）不进本波录制。
