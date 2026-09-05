# DevFrame Round-3 影子功能核对（detailDesign-part2 Proposed vs 实现面）

G5 产出。核对对象：`docs/detailDesign-part2.md`（Shadow 跨项目路由，Proposed 门禁项）。结论先行：**Proposed 项 100% 按设计门禁延后，零代码混入**；Round-3 五组交付均属单项目三层 Agent 编排，与跨项目 Shadow 无重叠（试点不依赖 Part 2，与设计 Summary 一致）。

## 一、Proposed 项逐条对照

| Proposed 项（Part 2） | 状态 | 核对证据 |
| --- | --- | --- |
| R2.1 工作区→控制器解析 + 禁止跨项目路由 | 按设计延后 | 无对应实现；验收锚 AT2-01/02 仍为设计文案 |
| R2.2 重复 open 去重 + 拒绝路径别名/冲突根 | 按设计延后 | 同上（AT2-03/04） |
| R2.3 跨根投递持久化 + received≠completed 区分 | 按设计延后 | 同上（AT2-05/06） |
| R2.4 单项目停止/检查不影响他项目 | 按设计延后 | 同上（AT2-07/08） |
| 四工具 `project_open`/`project_send`/`project_status`/`project_stop` | 按设计延后 | `grep project_(open\|send\|status\|stop)` 于 packages/**.{ts,tsx,yml,json} 零匹配 |
| 跨根投递消息模型（messageId/requestId/bindingRevision/goalId/acceptanceHash…） | 按设计延后 | 零匹配；`bindingRevision`/`controllerSessionId`/`needs_attention` 在 worktree-registry 等新代码亦无混入 |
| Shadow 模型面 allowlist（仅路由工具 + 显式 user-memory） | 按设计延后 | 无 Shadow 角色装配；Round-3 角色装配为 controller/lead/worker（G2），不含 Shadow |
| 多项目派生 UI 状态集（idle/running/waiting/stopping/stopped/completed/needs_attention） | 按设计延后 | ui-workspace 会话状态投影未引入该状态集（G3 仅 agent 树） |
| 绑定存储（workspaceId/reserved controllerSessionId/profileKey/bindingRevision/requestId/provisioning state） | 按设计延后 | 零实现 |

## 二、已实现面（设计引用的支撑物 + Round-3 相邻但不同界的交付）

| 已实现 | 与 Part 2 的关系 |
| --- | --- |
| 原生 workspace registry（`packages/workspace/workspace/src/index.ts`） | 设计引用的依赖物，真实存在，非 Shadow 实现 |
| 根会话控制器（`packages/api/session-controller`） | 存在；Round-3 G1/G3 扩展其投影（SessionID 暴露、parentSessionId/origin 树数据），属单项目会话面 |
| Team mailbox 持久化次序参照（`packages/experimental/agent-team/src/mailbox.ts`） | 存在且仅 intra-Team；设计明言跨根投递不得复用其成员校验方法，现无跨根调用 |
| Goal/goal-driver 显式恢复策略 | 存在（总控本轮在用）；Part 2 仅引用其恢复语义 |
| Round-3 G1–G4：SessionID 暴露、三层层级策略、Agent 树 UI、worktree 注册表与工具 | 与 Shadow 无重叠：均为单项目内编排；worktree 工具是项目内能力，不构成跨项目路由 |

## 三、设计文档自身状态

- `detailDesign-part2.md` 与 `detailDesign-part2.zh.md` 双语成对，frontmatter 仍标 Proposed，引用的 part1/part4/testAndAcceptance 均存在。
- AT2-01…08 八个验收锚在 `docs/testAndAcceptance.md` L96–103 齐全，与 R2.1–R2.4 一一对应——设计集内部一致，处于「有意延后且可随时启建」的健康状态。
- 无任何 Proposed 项被部分实现后遗留的半成品代码（grep 证据见上表）。
