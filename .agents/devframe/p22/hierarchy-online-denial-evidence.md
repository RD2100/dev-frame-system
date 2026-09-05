---
description: P22 锚点补齐交付证据——agent-hierarchy 在线拒绝探针（真实 dispatcher）的执行记录、S4 五类拒绝词表逐字符映射、缺口登记与覆盖声明。
kind: "p22-evidence"
---

# P22 交付证据：agent-hierarchy 在线拒绝探针（AT1-01/AT1-02 锚点缺口补齐）

- 交付物：[tests/online-denial.spec.ts](../../../packages/experimental/agent-hierarchy/tests/online-denial.spec.ts)（13 条新用例，真实 dispatcher `ctx.tools.execute` + 真实 Service 路径）与 [tests/helpers.ts](../../../packages/experimental/agent-hierarchy/tests/helpers.ts) 装配扩展（`PROBE_TOOLS` 增加 `team_task_update`、新增无 agent 的 `executeProbeWithoutAgent`）。
- 断言纪律（对齐 [at2b-runner-checklist](../accept/at2b-runner-checklist.md)）：每处拒绝逐字符锚定 [src/guard.ts](../../../packages/experimental/agent-hierarchy/src/guard.ts) 现役文本（`toBe` 全等，非片段），并断言探针工具体零执行、拒绝前后 `ctx.agentBindings.list()` JSON 快照不变（无副作用）；未弱化为"报了错"。
- 红线核查：全程无任何越权委派成功产生子代理（每处委派拒绝的探针体计数为 0）；未改动 `src/` 任何文件；`README`/`README.i18n.yaml` 及其他包未触碰。
- 证据采集提交：`dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd`（测试提交；本证据文档自身随后继 docs 提交落盘，sha 自引用不可能，故记录探针实际运行所在提交）。

## 1. 逐条证据记录（对齐 at2b-runner-checklist 证据格式）

```json
{"item": "AT1-01/A1-unbound-session", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["denies an unbound session fail-closed on the controlled probes with the exact missing-role text"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "缺角色 fail-closed：subagent 与新具名探针 team_task_update 逐字符拒绝，project_read 正对照 +1，绑定记录保持缺席"}
{"item": "AT1-01/A2-worker-deny-face", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["denies every creation and Team probe to the worker with the exact role-face text and keeps the reporting routes open", "denies a stale disposed identity with the exact unknown-identity text", "denies an agent-less execution with the exact no-agent text"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "worker 五探针逐字符（补 AT1-01 team_task_update 缺口）+ send_message/project_read 正对照；stale 陈旧引用与无 agent 执行各逐字符"}
{"item": "AT1-01/A2-lead-controller-faces", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["denies the Team face to the lead with the exact role-face text and lets the controller execute every probe"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "lead Team face（spawn_teammate/team_task_update）逐字符拒绝；controller 对 8 个 PROBE 工具全放行正对照（含新增 team_task_update）"}
{"item": "AT1-01/A3-depth-and-scope", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["rejects delegation at the absolute depth budget with the exact numeric text", "rejects a lead whose plugin scope is not in the approved set with the exact text, including an unlisted lead", "rejects a lead with no plugin scope binding with the exact text and allows delegation inside the approved scope"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "深度文本含预算 2 与 child depth 3（fork 探针）；三条 fail-closed scope 路径逐字符 + 已批 scope 正对照 +1"}
{"item": "AT1-01/A3-other-creation-face", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["denies the host-declared creation face to the worker and allows the controller"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "config.otherCreationToolNames=['sdk_bridge_spawn']（合成探针工具）：worker 逐字符拒绝、controller 放行（体计数 1），补 AT2B-01 宿主声明创建面包级半边"}
{"item": "AT1-02/A4-cold-recovery", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["denies a controlled tool to a role-less session after restart with the exact missing-role text", "fails loud at the durable boundary when a restored binding carries a retired role", "leaves no stale guard after disposal: the old reference is denied and a same-id successor gets its full face"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "重启后缺角色拒绝逐字符；退役角色 durable 边界 fail-loud（见 §3 接缝说明——实际拒绝点在 session-identity 持久边界，早于本包 service init）；dispose 后陈旧引用拒绝 + 同 id 后继全权限面（admin_panel 放行、worker 越权面照常拒绝）证明无陈旧守卫残留"}
{"item": "AT1-01/A5-creation-evaluator", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["mirrors the guard face on the programmatic creation evaluator with real binding records"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "service.evaluateCreation 走真实绑定记录：未列名 lead 逐字符 reason 拒绝、controller requestedRole='lead' 严格 {allowed:true}（与 guard.spec 的 toMatchObject 互补加严）"}
{"item": "AT1-01+AT1-02/package-gate", "command": "pnpm exec vitest run packages/experimental/agent-hierarchy", "exit": 0, "scenarios": ["3 files / 25 tests passed（既有 12 + 新增 13）"], "commit": "dc37f6715bfb867ee7ec9f8ffbe39d3e2de0abbd", "notes": "同状态 pnpm exec tsc -b packages/experimental/agent-hierarchy 退出码 0；连跑 3 次稳定全绿（重启/临时根面无抖动）"}
```

## 2. S4 五类拒绝词表映射（现役文本逐字符）

S4 类别口径出自 [s4-toolface-plan.md §4.2](../integration/s4-toolface-plan.md) 与交付表第 9 行（guard 拒绝词表，P02 定稿）。位点行号为 `dc37f6715b` 现役源码。

| S4 类别 | 现役拒绝文本（逐字符） | 结构化位点 | 测试用例（online-denial.spec.ts） |
| --- | --- | --- | --- |
| 未知身份（无 agent） | `agent-hierarchy: tool "subagent" requires an exact live Agent` | guard.ts：agent 缺席分支 | denies an agent-less execution with the exact no-agent text |
| 未知身份（陈旧引用） | `agent-hierarchy: stale Agent identity "worker-1" cannot execute "team_task_update"`；`agent-hierarchy: stale Agent identity "controller-1" cannot execute "subagent"`（变体） | guard.ts：exact-identity 分支 | denies a stale disposed identity…；leaves no stale guard after disposal… |
| 缺失策略（无绑定） | `agent-hierarchy: session "stray-1" has no role binding and cannot execute controlled tool "subagent" (missing role)`；`…controlled tool "team_task_update" (missing role)`（变体） | guard.ts：record 缺席 fail-closed 分支 | denies an unbound session fail-closed…；denies a controlled tool to a role-less session after restart… |
| 深度预算耗尽 | `agent-hierarchy: delegating from depth 2 would create a child at depth 3 beyond the absolute budget 2`（预算常量 2，policy.ts） | guard.ts：delegation 深度分支 | rejects delegation at the absolute depth budget… |
| lead 的 pluginScope 未批准（fail-closed） | `agent-hierarchy: plugin scope "plugin-a" is not in the approved set of lead "lead-1"`（`"lead-9"` 未列名变体同构）；`agent-hierarchy: lead "lead-2" has no plugin scope binding and cannot delegate` | guard.ts：lead scope 两分支（creation.ts 评估面同文本） | rejects a lead whose plugin scope…；rejects a lead with no plugin scope binding…；mirrors the guard face on the programmatic creation evaluator… |
| 模型自报角色 | 现役无实现路径（见 §3 缺口 1） | 无 | 无 |

现役补充断言面（S4 五类未单列，本波主断言面之一）：

| 面 | 现役拒绝文本（逐字符） | 结构化位点 | 测试用例 |
| --- | --- | --- | --- |
| 角色 deny face（worker 全拒创建面 + Team 面；lead Team 面；宿主声明创建面） | `agent-hierarchy: role "worker" cannot execute "subagent"`（`fork`/`spawn_teammate`/`team_task_create`/`team_task_update`/`sdk_bridge_spawn` 及 lead 两条同构） | guard.ts：deny-face 分支（policy.ts denyFaceFor） | denies every creation and Team probe…；denies the Team face to the lead…；denies the host-declared creation face…；leaves no stale guard after disposal… |
| 未知角色（真实组合不可达——见 §3 缺口 3） | `agent-hierarchy: session "…" carries role "…" outside the hierarchy union`；service 侧 `HIERARCHY_ROLE_UNKNOWN` | guard.ts：isAgentRole 分支；service.ts reinstallForActiveSessions | 无（持久边界先 fail-loud） |

## 3. 缺口登记（fail-loud，未自行实现）

1. **"模型自报角色"类现役无实现路径。** guard 从 `exec.agent`（宿主解析）取身份、从绑定注册表取角色，模型参数不携带角色字段，因此不存在可触发"模型自报角色拒绝"的代码路径——该类目前由"调用者身份一律宿主解析"的构造性保证覆盖，而非显式拒绝文本。归属建议：S4 拒绝词表契约定稿时由 P02 组长与 P23 切片（s4-toolface-plan §6 建议的 toolface 包）裁决是保留构造性保证还是补显式词表。
2. **`AgentHierarchyError` 的 `HIERARCHY_TOOLS_UNAVAILABLE`/`HIERARCHY_BINDINGS_UNAVAILABLE` 不可达。** `AgentHierarchy` 以 `static inject = ['agentBindings', 'tools', 'agents']` 硬注入两服务，Cordis 在服务缺席时直接拒绝挂载，构造/init 永远观察不到缺席，两个码是死枚举成员。归属建议：P02/L-Hierarchy 决定删除或登记保留理由。
3. **guard 未知角色分支与 service init 的 `HIERARCHY_ROLE_UNKNOWN` 在真实组合中不可达（纵深防御层）；A4 预期接缝与实际接缝不同。** A4 用例按预期先探查了存储布局：`session_identity` 域为 single 布局单文档 `<root>/session_identity.json`（`unit`/`global`/`tables.bindings` 三层，记录键即 agentId），直接改写该记录 `role` 为退役值 `'reviewer'`（其余字段不动）完全可行；但重启的 fail-loud 落在**更早一层**——session-identity 持久边界的 zod schema（`z.enum(['controller','lead','worker'])`）在域 open 装载时拒绝该记录，`AgentBindingRegistry` init 抛 `DomainError('invalid-record')`（message 逐字符：`domain 'session_identity': stored record 'worker-1' in table 'bindings' does not match its schema`，detail `{table:'bindings', key:'worker-1'}`），本包 service 根本未挂载；`bind`/`createBoundSession` 也先经 `isAgentRole` 校验，因此 guard 的 union 分支与 `reinstallForActiveSessions` 的 `HIERARCHY_ROLE_UNKNOWN` 分支在真实组合中均不可触发。用例按实际行为钉死结构化失败（码 + message + detail）。归属建议：P02/L-Hierarchy 决定两处纵深防御层去留（建议保留并登记前提），勿在验收口径中把 `HIERARCHY_ROLE_UNKNOWN` 记为可观察面。

## 4. 用例计数与本波未覆盖面

- 计数：本波新增 13 条 `it()`（A1×1、A2×4、A3×4、A4×3、A5×1）；包内既有 12 条（guard.spec 11 + cold-recovery 1）不重复其语义，全包 3 文件 25 条全绿（`dc37f6715b` 实测，连跑 3 次稳定）。
- **recorded-session 场景仍归 AT2B 录制波**：本波全部为包级真实测试；[at2b-runner-checklist](../accept/at2b-runner-checklist.md) 既定"程序化创建面与冷恢复/重启面留在包测试与 P22 探针测试，不挤进录制"，`snapshots/session/` 无任何新录制，执行状态零回填。
- 未覆盖面（明确声明，均有既定归属）：
  - `followup_task`/`interrupt_agent` 属默认 `teamToolNames` deny 面，但 harness 未注册为探针工具，本波未具名探针（按任务边界仅 `team_task_update` 入 PROBE_TOOLS）。
  - 组合级 dispatcher 实跑与集成 profile 冷恢复仍归集成波（[anchor-matrix](anchor-matrix.md) AT1-01/02 行缺口中"组合级"半边未动）。
  - AT2B-01 的"继承 allow face 收缩 prompt 工具列表"（模型可见 schema 收缩）本波未断言；现有覆盖为 guard.spec 的 allow-face 安装语义与 AT2B 录制草案。
  - §3 三项缺口（模型自报角色词表、死错误码、不可达纵深防御层）未实现、未改 src。
