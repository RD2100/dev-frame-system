---
description: "AT2C-02 recorded-session 场景草案：冷恢复重装——新进程从 session_identity.bindings 表按 (createdAt, agentId) 重建查询索引，find/byRole/list 免会话重放作答，重启后 rebind 幂等/冲突/未知 agent 三分各有探针。"
kind: "acceptance-scenario-draft"
---

# AT2C-02 场景草案：冷恢复重装

包已在 main（session-identity 合并提交 `c23e78a17a`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-02`；P22 验收矩阵 P01 责任面（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6a 执行表"冷恢复与绑定测试"；`AT1-01`/`AT1-02` 的冷恢复半边，[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- 冷恢复是 `Service.init` 的一次性重建：从 `session_identity` 域 `bindings` 表按 `(createdAt, agentId)` 排序重建整个查询索引，不重放任何会话；表是唯一持久权威，索引是 write-through 投影。
- 恢复出的记录是 detached frozen copy：查询返回值与落盘行逐字一致，`createdAt` 保持首次写入值。
- `find`/`byRole`/`list` 全部答自恢复索引：冷进程在第一次查询前无需任何会话重放动作。
- 重启后的 `bind` 三分：同内容 rebind 幂等（返回既有 record、`createdAt` 不变、不加行）；不同内容 → `SESSION_IDENTITY_ALREADY_BOUND`（`agent "<id>" is already bound with different content`），既有 record 不改写；agentId 不在 session store → `SESSION_IDENTITY_AGENT_UNKNOWN`。

## 前提（宿主集成）

- 组合同 AT2C-01；桥（落地名草案：`identity_probe`）另暴露 `bind`/`find`/`byRole`/`list` 查询面；未定前记 `blocked`。
- 两段布局：run A（种子段）经桥创建/绑定记录；run B 为全新进程、同一 storages root、无种子接缝，直接经桥查询。两段间的进程重启形态由 snapshots 属主定案（见开放问题），未定案前本条记 `blocked`。
- run B 的 session store 也冷恢复出 run A 的会话（`dsh-session` 属同一组合），rebind 探针的 live-session 前提依赖它。

## 计划录制布局

`snapshots/session/session-identity-cold-restore-rebind/`：`snapshot.yml`（`profile: headless`、`recording: authored`）；run A `session.jsonl`（种子段）+ run B `session.jsonl`（恢复段，目录形态按开放问题定案）；`workspace.expected/` 固定两段后 `bindings` 表仍为 3 行（掩码方式同 AT2C-01）。

## 剧本（replay 步骤）

1. run A：桥创建 controller-1（无父）、lead-1（父 controller-1）、worker-1（父 lead-1，`pluginId: plugin-a`）；`list()` → 三条按创建序。
2. run B（全新进程）：启动即完成恢复——桥第一次调用前无任何会话重放。
3. `list()` → 三条 record 与 run A 落盘逐字一致（含首写 `createdAt`），顺序 `(createdAt, agentId)` 稳定。
4. `byRole('lead')` → 仅 lead-1；`byRole('worker')` → 仅 worker-1；`find(lead-1)` → lead-1 record；`find("session-404")` → `undefined`。
5. 幂等 rebind：`bind({ agentId: lead-1, role: 'lead', …同字段 })` → 返回既有 record；`bindings` 表仍 3 行，`createdAt` 不变。
6. 冲突 rebind：`bind({ agentId: lead-1, role: 'worker', … })` → `SESSION_IDENTITY_ALREADY_BOUND`，表仍 3 行、record 原样。
7. 未知 agent：`bind({ agentId: "session-404", role: 'worker' })` → `SESSION_IDENTITY_AGENT_UNKNOWN`（`agent "session-404" does not exist in the session store`）。

## 可观察通过标准

- run B 全部查询在恢复索引上作答，值与 run A 落盘逐字一致；无一次会话重放（恢复不读 session 日志）。
- 幂等/冲突/未知三分各有独立探针；冲突路径零改写、零加行。
- 恢复与查询不产生任何会话事件或请求字段（零直接 token 契约在冷路径同样成立）。

## 环境与安全

合成 agentId/pluginId；storages root 为录制专用临时目录，两段共享、录制后清理。

## 开放问题

- 两 run + 共享 storages root 的录制形态：snapshot harness 目前单 run；重启探针归 recorded-session 还是 P22 真实测试由 snapshots 属主定案，未定案前本条 `blocked`。
- run B 的 `dsh-session` 冷恢复范围（哪些会话需要 live 供 `bind` 解析）由组合挂载波定。
- composition 名与 header pin 形态以首录为准回填。
