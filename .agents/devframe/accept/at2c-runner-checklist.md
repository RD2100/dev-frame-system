---
description: "AT2c（session-identity + agent-evidence + agent-reliability，AT2C-01…06）验收执行清单：recorded-session 场景草案索引、证据格式与执行纪律。"
kind: "acceptance-scenario-draft"
---

# AT2c runner checklist（identity / evidence / reliability 验收执行清单）

三包已在 main（session-identity 合并提交 `c23e78a17a`、agent-evidence 合并提交 `c8992f8154`、agent-reliability 合并提交 `312fe9cd7c`；本分支基点 `4bc507e332` 交叉验证），契约即其 README 与 src。三包都是"模型什么都看不到"的服务：无工具、无 prompt 面、无 session 事件，交付验收登记为包内测试（P01 冷恢复与绑定、P05 证据链、P06 停止/恢复，见 [pluginized-round-registry.md](../pluginized-round-registry.md) 6a 执行表），recorded-session 场景未建。本清单承接该缺口，形式沿 [at2b-runner-checklist.md](at2b-runner-checklist.md) 先例：模型可见面由组合挂载波提供的宿主桥承载，草案位于包内 `scenarios/`，正式录制归 `snapshots/session/` 属主（[docs/testing.md](../../../docs/testing.md)）。与 P22 验收矩阵（registry 6b 节）的关系：本波只补三包经桥可达的模型可见半边；探针、重启、进程树停止等非模型可见面仍归 `AT1-01…06`/`AT4-01…07` 绑定的真实测试（[testAndAcceptance.md](../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 场景草案索引

| ID | 包 | 要求摘要 | 状态 | 草案 |
|---|---|---|---|---|
| AT2C-01 | session-identity | 精确 cwd 绑定创建：header cwd 逐字、lineage（parent + 深度派生/显式）与 record 一次持久写齐；role/parent/深度/cwd 拒绝探针全部先于会话创建，零中间态行 | drafted | [AT2C-01-exact-cwd-bound-creation.md](../../../packages/experimental/session-identity/scenarios/AT2C-01-exact-cwd-bound-creation.md) |
| AT2C-02 | session-identity | 冷恢复重装：新进程从 `session_identity.bindings` 表按 (createdAt, agentId) 重建索引，find/byRole/list 免会话重放作答；重启后 rebind 幂等/冲突/未知 agent 三分各有探针 | drafted | [AT2C-02-cold-restore-rebind.md](../../../packages/experimental/session-identity/scenarios/AT2C-02-cold-restore-rebind.md) |
| AT2C-03 | agent-evidence | 证据链 append-only：goal binding（DevFrame 元组）→ submission → verification 三段回执逐字回读；非零 exit code 原样入账；畸形 receipt 逐探针 fail loud 且零落盘 | drafted | [AT2C-03-evidence-chain-append-only.md](../../../packages/experimental/agent-evidence/scenarios/AT2C-03-evidence-chain-append-only.md) |
| AT2C-04 | agent-evidence | byTask 轨迹查询：三轨按 recorded 序、跨任务隔离、bindingsByGoal 双键过滤、未知任务空轨非错误、查询全程只读零落盘 | drafted | [AT2C-04-bytask-trail-query.md](../../../packages/experimental/agent-evidence/scenarios/AT2C-04-bytask-trail-query.md) |
| AT2C-05 | agent-reliability | 准入切断 fail-closed：冷态 closed 拒、开门恰一身份、换代即旧身份失配、ADMISSION_CLOSED 与 IDENTITY_MISMATCH 两码分离；flush 失败关 admission 并扣住 writer，恢复唯显式重开 | drafted | [AT2C-05-admission-cutoff-fail-closed.md](../../../packages/experimental/agent-reliability/scenarios/AT2C-05-admission-cutoff-fail-closed.md) |
| AT2C-06 | agent-reliability | 不确定调用 probe 结算不重发：probe 先行、retry 至多一次且仅在 absent 之后；confirmed 免重发、still_uncertain 不重发返回 unresolved；四种 outcome 是数据不是异常 | drafted | [AT2C-06-uncertain-call-probe-settlement.md](../../../packages/experimental/agent-reliability/scenarios/AT2C-06-uncertain-call-probe-settlement.md) |

## 执行流程（每个 AT2C-0x 一轮）

1. 读对应草案与三包 README/契约；草案与契约冲突时以契约为准并回改草案。
2. 确认组合挂载面就绪：六条全部依赖宿主桥（identity/evidence/reliability 各一）把服务调用映射为会话可见结果；AT2C-02 另依赖两 run + 共享 storages root 的重启形态。未就绪记 `blocked`，不降级为包内单测替代。
3. 回放：`pnpm run test:snapshot -t <scenario>`（keyless）；录制/刷新期望只由场景属主本地执行并逐 diff 评审（record 需 key）。
4. 落证据（格式见下）并回填本表状态：`passed` / `failed` / `blocked` / `skipped` + 一行原因。

## 证据格式

每条验收记录一行 JSON，追加进合并 PR 描述或运行报告（对齐 testAndAcceptance.md 的 Delivery and evidence 约定）：

```json
{"item": "AT2C-05", "command": "pnpm run test:snapshot -t agent-reliability-admission-cutoff-fail-closed", "exit": 0, "scenarios": ["agent-reliability-admission-cutoff-fail-closed"], "commit": "<sha>", "notes": "flush 失败后 admission 实际关闭经 assert 探针证明"}
```

## 纪律与红线

- 稳定码与拒绝文本是包契约：断言逐字符锚定 `src/errors.ts` 与 `src/registry.ts` / `src/ledger.ts` / `src/service.ts` 文本，不得弱化为"报了错"。
- 场景工作不改三包 `packages/experimental/{session-identity,agent-evidence,agent-reliability}/src/`；契约缺口走包行为测试与修复 PR，不混进验收提交。
- 全部 taskId/goalId/sessionId/pluginId/operation 为合成值；probe/retry/flush fixture 零文件、零网络、零进程副作用；真实秘密不入录制、不入断言。
- 只跑条目需要的场景，不整跑全库套件；部分子案通过不折算整条通过；failed/blocked 的必需条目阻止相应 delivery 声明。
- 红线（hard stop）：绑定 record 或回执字段绕过桥进入请求字段、retry 在 probe 证实 absent 之前或第二次发生、flush 失败后 writer 被释放、冷恢复丢失或改写任何已落盘记录、畸形 receipt 部分落盘。
- `stopProject` 进程树停止契约不进本波录制（单实现单测试家）；冷恢复/重启的非模型可见半边仍归 P22 矩阵绑定的真实测试。

## 已知开放问题（录制前定案）

- 三包的宿主桥（落地名、参数面、结果 envelope、probe/retry/flush fixture 暴露面）未定；未定前六条记 `blocked`（同 at2b 的桥前提）。
- AT2C-02 的两 run + 共享 storages root 录制形态：snapshot harness 目前单 run；重启探针归 recorded-session 还是 P22 真实测试由 snapshots 属主定案。
- `workspace.expected` 对 receiptId（UUID）/recordedAt/session id/createdAt 的掩码方式（固定时钟 vs 正则锚）由 snapshots 属主定。
- `AGENT_EVIDENCE_PERSISTENCE` 与 `SESSION_IDENTITY_PERSISTENCE` 的中段失败需 fault 注入点，归包测试，不挤进首录（同 at3 已知缺口）。
