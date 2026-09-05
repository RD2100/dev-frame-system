---
description: "AT2b（agent-hierarchy + project-controller，AT2B-01…06）验收执行清单：组合挂载波 recorded-session 场景草案索引、证据格式与执行纪律。"
kind: "acceptance-scenario-draft"
---

# AT2b runner checklist（hierarchy / controller 验收执行清单）

两包已在 main（agent-hierarchy 合并提交 `9d0bea4b37`、project-controller 合并提交 `4a515afda7`；本分支基点 `4bc507e332` 交叉验证），契约即其 README 与 src。两包交付时 recorded-session 场景未建（登记为"recorded-session 场景待组合挂载波补"），本清单承接该缺口：仓库测试政策要求模型可见行为以 recorded-session 场景钉住（[docs/testing.md](../../../docs/testing.md)），正式录制归 `snapshots/session/` 属主，草案位于包内 `scenarios/`。与 P22 验收矩阵的关系：本波只补两包的模型可见半边，探针/冷恢复/重启等非模型可见面仍归 `AT1-01`/`AT1-02`/`AT1-09` 绑定的真实测试（[testAndAcceptance.md](../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 场景草案索引

| ID | 包 | 要求摘要 | 状态 | 草案 |
|---|---|---|---|---|
| AT2B-01 | agent-hierarchy | worker 全拒面：delegation seam（subagent/fork）+ Team 工具 + 宿主声明创建面逐个被 pre-execute 守卫拒绝；`send_message`/`project_read` 放行；继承 allow face 收缩 prompt 工具列表 | drafted | [AT2B-01-worker-creation-denial.md](../../../packages/experimental/agent-hierarchy/scenarios/AT2B-01-worker-creation-denial.md) |
| AT2B-02 | agent-hierarchy | 深度预算 2 双保险：三代委派走通后 depth-2 委派被本包守卫独立拒绝，seam `SubagentDepthError`（第一半）由既有 depth-two 场景持有 | drafted | [AT2B-02-depth-budget-double-guard.md](../../../packages/experimental/agent-hierarchy/scenarios/AT2B-02-depth-budget-double-guard.md) |
| AT2B-03 | agent-hierarchy | lead 范围 fail-closed：未列名 lead / 缺 pluginId 绑定 / 越集 scope 三路径拒绝，已批 scope 委派正对照，lead deny face 吞 Team 工具 | drafted | [AT2B-03-lead-scope-fail-closed.md](../../../packages/experimental/agent-hierarchy/scenarios/AT2B-03-lead-scope-fail-closed.md) |
| AT2B-04 | project-controller | 九态任务机走通：七态调度脊 + blocked/failed 往返，developing 预算边缘拒绝与离开释放，非法 move fail loud 不改写 | drafted | [AT2B-04-task-machine-lifecycle.md](../../../packages/experimental/project-controller/scenarios/AT2B-04-task-machine-lifecycle.md) |
| AT2B-05 | project-controller | blocked/failed 恢复三元组：三字段逐个强制非空 trim，落盘精确，resume 清三元组经 assigned 回调度并支持换 assignee | drafted | [AT2B-05-blocked-triple-recovery.md](../../../packages/experimental/project-controller/scenarios/AT2B-05-blocked-triple-recovery.md) |
| AT2B-06 | project-controller | controller-only 合并门：lead/未绑定会话铸造前被拒零 marker，marker 单次消费、跨任务 `MARKER_INVALID`，双任务 integrate+complete 正对照 | drafted | [AT2B-06-merge-gate-controller-only.md](../../../packages/experimental/project-controller/scenarios/AT2B-06-merge-gate-controller-only.md) |

## 执行流程（每个 AT2B-0x 一轮）

1. 读对应草案与两包 README/契约；草案与契约冲突时以契约为准并回改草案。
2. 确认组合挂载面就绪：agent-hierarchy 三条需 session-identity + hierarchy 挂载与绑定种子接缝；project-controller 三条需 storage 栈 + controller 挂载与模型可见桥（命令面或工具桥）。未就绪记 `blocked`，不降级为包内单测替代。
3. 回放：`pnpm run test:snapshot -t <scenario>`（keyless）；录制/刷新期望只由场景属主本地执行并逐 diff 评审（record 需 key）。
4. 落证据（格式见下）并回填本表状态：`passed` / `failed` / `blocked` / `skipped` + 一行原因。

## 证据格式

每条验收记录一行 JSON，追加进合并 PR 描述或运行报告（对齐 testAndAcceptance.md 的 Delivery and evidence 约定）：

```json
{"item": "AT2B-02", "command": "pnpm run test:snapshot -t agent-hierarchy-depth-budget-double-guard", "exit": 0, "scenarios": ["agent-hierarchy-depth-budget-double-guard"], "commit": "<sha>", "notes": "seam maxDepth 2 与守卫双保险并存"}
```

## 纪律与红线

- 守卫拒绝理由与 `ProjectControllerError` 稳定码是包契约：断言逐字符锚定 `src/guard.ts` / `src/controller.ts` 文本，不得弱化为"报了错"。
- 场景工作不改 `packages/experimental/agent-hierarchy/src/` 与 `packages/experimental/project-controller/src/`；契约缺口走包行为测试与修复 PR，不混进验收提交。
- 全部 agentId/pluginId/taskId 为合成值；真实秘密不入录制、不入断言。
- 只跑条目需要的场景，不整跑全库套件；部分子案通过不折算整条通过；failed/blocked 的必需条目阻止相应 delivery 声明。
- 红线（hard stop）：worker/越权委派成功产生子代理、depth-2 之下仍有存活子进程、非 controller 会话铸造或消费 marker、任务状态被静默改写、record 值绕过桥进入请求字段。
- 程序化创建面（`evaluateCreation`）与冷恢复/重启面不是模型可见面：留在包测试与 P22 探针测试，不挤进本波录制。

## 已知开放问题（录制前定案）

- 绑定种子接缝：录制前把会话绑定为指定角色/`pluginId` 的宿主手段未定（AT2B-01/02/03/06 共同前提）。
- project-controller 模型可见桥：命令适配器 vs 工具桥、落地名与 record 暴露字段面未定（AT2B-04/05/06 共同前提）；未定前这三条记 `blocked`。
- 多 lead / 无绑定会话的录制形态（多 run vs 控制器子会话）由 snapshots 属主定案后回填草案。
- 场景目录名、composition 名与 header pin 形态以 `snapshots/session/` 属主首录为准回填草案。
