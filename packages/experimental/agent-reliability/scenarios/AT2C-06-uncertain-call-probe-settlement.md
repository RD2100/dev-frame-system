---
description: "AT2C-06 recorded-session 场景草案：不确定调用 probe 结算不重发——probe 先行、retry 至多一次且仅在 absent 之后，confirmed 免重发、still_uncertain 不重发返回 unresolved，四种 outcome 全部是数据不是异常。"
kind: "acceptance-scenario-draft"
---

# AT2C-06 场景草案：不确定调用 probe 结算不重发

包已在 main（agent-reliability 合并提交 `312fe9cd7c`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-06`；P22 验收矩阵 `AT4-06` 的 P06 责任面（不确定调用调和）的模型可见半边（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6b 节；[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-4-acceptance)）。

## 覆盖契约要点

- `reconcileUncertainCall` 无盲重试路径：probe（外部状态检查）先行；retry 至多一次，且仅在该 plan 的 probe 返回 `absent` 之后。
- 四种 outcome 全部以数据返回、不抛异常：`{ status: 'settled', via: 'probe' }`（confirmed，retry 未调用）；`{ status: 'settled', via: 'retry', result }`（absent + 有 retry，恰一次重发）；`{ status: 'absent' }`（absent + 无 retry）；`{ status: 'unresolved' }`（still_uncertain——即使提供了 retry 也不重发，调用方决定 unresolved 的含义）。
- reconciler 无跨调用状态：每个 plan 独立结算，operation 名仅作诊断标识。

## 前提（宿主集成）

- 组合同 AT2C-05；桥（落地名草案：`reliability_probe`）另暴露 `reconcile(operation, probeScript, withRetry)`：probe 脚本由组合 fixture 执行（返回 `confirmed`/`absent`/`still_uncertain`），retry 为计数 fixture（记录调用次数并返回合成 result）；fixture 暴露面由组合挂载波定，未定前记 `blocked`。
- operation 名全部为合成标识（`create-worktree` 仅为文档示例沿用，无真实 worktree 调用）。

## 计划录制布局

`snapshots/session/agent-reliability-uncertain-call-probe-settlement/`：`snapshot.yml`（`profile: headless`、`recording: authored`）；`session.jsonl` 单会话桥探针序列；fixture 计数通过桥结果（或逐探针读数调用）暴露，无落盘期望。

## 剧本（replay 步骤）

1. plan-1（`create-worktree`，probe → `confirmed`，有 retry）→ `{ status: 'settled', via: 'probe' }`、无 `result` 字段；retry 计数 0（不重发）。
2. plan-2（probe → `absent`，有 retry）→ `{ status: 'settled', via: 'retry', result: <合成值> }`；retry 计数恰 1。
3. plan-3（probe → `absent`，无 retry）→ `{ status: 'absent' }`。
4. plan-4（probe → `still_uncertain`，有 retry）→ `{ status: 'unresolved' }`；retry 计数 0（"不重发"契约本体）。
5. plan-5（probe → `still_uncertain`，无 retry）→ `{ status: 'unresolved' }`。
6. plan-6（同 operation 名复用，probe → `confirmed`）→ 独立结算 `{ status: 'settled', via: 'probe' }`（无跨 plan 状态）；retry 计数 0。
7. 读数探针：全序列累计 retry 调用次数恰 1（plan-2）。

## 可观察通过标准

- 全录制恰一次重发（plan-2），且发生在该 plan 的 probe 返回 `absent` 之后（probe/retry fixture 的调用次序由桥结果可证）。
- `still_uncertain` 两个变体（有/无 retry）均零重发；`confirmed` 零重发且 settle 来自 probe 本身。
- 四种 outcome 全部经桥正常返回（`isError: false` 的数据面），无 error envelope——未结算不是异常。

## 环境与安全

probe/retry 为组合内计数 fixture，零文件、零网络、零进程副作用；operation 名与 result 全为合成值。

## 开放问题

- probe/retry fixture 的桥暴露面（脚本枚举 vs 逐 plan 参数）与计数读数方式由组合挂载波定；result 透传形态首录回填。
- `settled via retry` 的 `result` 在桥结果 envelope 中的序列化形态以首录为准。
- 真实外部状态探测（进程/worktree/远端）不在本场景：probe 的可信度归调用方契约（README known limitation），录制只钉服务面的结算纪律。
