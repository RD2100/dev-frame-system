# Agent Note: 专家团队运行不跨进程恢复

Status: implemented

[English](2026-09-15-expert-team-no-cross-process-resume.md) | 中文

## Problem

expert-team 的运行状态保存在内存中，并在每个提交点镜像到 `<artifactsDir>/<runId>/run-state.json`。M1 的设计明确将"跨进程恢复"列为延期项——进程重启后，进行中的运行丢失。M4 需要对该决策做出最终判断：实现恢复、显式拒绝恢复、还是保留当前行为。

## Decision

**不实现跨进程恢复。** 运行状态以内存为权威，`run-state.json` 是镜像而非恢复点。进程重启后，进行中或停在关口的运行视为终止；产物文件（artifacts）和 `run-state.json` 保留用于审计和人工重建。

理由：
1. **无当前消费者**：没有部署请求跨重启运行团队；恢复成为真实需求时再加存储接缝。
2. **内存记录 + 文件镜像足够**：`run-state.json` 记录了完整运行故事，人类可以从文件重建状态；project-memory 的 M2 记录进一步提供了跨重启的产物持久化。
3. **恢复语义复杂**：跨进程恢复需要处理部分完成的阶段、已分配但未完成的 agent 会话、gate 决策的待定状态、以及产物与 run-state 的一致性；这些问题的解决成本不匹配当前需求。
4. **与 project-memory 互补**：project-memory 的 MemoryReceiptStore 已通过会话日志持久化，提供了跨重启的产物记录；expert-team 不需要重复该能力。

## Alternatives considered

**实现跨进程恢复。** 否决：需要新增存储接缝（可能是 storage-domain 或 session-log），处理会话恢复、gate 重放、产物一致性校验；当前没有部署需要此能力，且恢复语义在无真实消费者的情况下容易设计过度。

**使用 run-state.json 作为恢复点。** 否决：run-state.json 是镜像而非检查点——它不包含足够的运行时状态（agent 会话句柄、in-flight 工具调用、gate 等待队列）来支持恢复；将其升级为恢复点需要记录更多运行时状态，与当前"内存为权威"的设计矛盾。

## Consequences

买到：运行时保持简单——一个运行只有一个生命周期拥有者，不处理恢复、重连或状态合并；`run-state.json` 保留其审计用途。成本：进程重启丢失进行中的运行；用户必须等待运行完成或手动处理停下的运行。该限制已记录在 README 的 Known Limitations 中，并在 `expert_team_status` 的响应中通过 `status` 字段体现——停下的运行在重启后不会出现在状态查询中。
