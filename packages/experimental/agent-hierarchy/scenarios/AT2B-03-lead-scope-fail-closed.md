---
description: "AT2B-03 recorded-session 场景草案：lead 插件范围 fail-closed——未列名 lead、缺 pluginId 绑定、越集 scope 三种拒绝路径，lead deny face 吞掉 Team 工具（reviewer 并入），一次已批 scope 委派为正对照。"
kind: "acceptance-scenario-draft"
---

# AT2B-03 场景草案：lead 范围 fail-closed

包已在 main（agent-hierarchy 合并提交 `9d0bea4b37`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-03`；P22 验收矩阵 `AT1-01` 的 P02 责任面（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- lead 经 spawn/fork 委派必须携带 `pluginId` 绑定且落在 `leadPluginScopes[<agentId>]` 内；未列名 lead（配置无该 agentId 条目）、无 pluginId 绑定、越集 scope 三者全部 fail-closed，拒绝文本分别点名缺绑定或缺批准。
- scope 检查位于深度检查之后：预算内才轮到 scope。
- lead 的 deny face 含全部 Team spawn/task-control 工具（reviewer 语义并入），与 scope 无关地拒绝 `spawn_teammate` 等。
- 程序化创建面（`evaluateCreation`，SDK 桥/host 服务）不是模型可见面：lead 只能创建 worker、intent 无 `pluginScope` 拒、越集拒——由包测试与 `AT1-01` 探针测试持有，录制不含。

## 前提（宿主集成）

- 组合同 AT2B-01；配置 `leadPluginScopes: { lead-1: ['plugin-a'], lead-2: ['plugin-c'], lead-3: ['plugin-a'] }`（lead-2 刻意越集、lead-4 刻意未列名）。
- 绑定种子接缝预置四个 lead 会话：lead-1（`pluginId: plugin-a`，正对照）、lead-2（`pluginId: plugin-b`，列名但越集）、lead-3（无 `pluginId`）、lead-4（`pluginId: plugin-b`，未列名）。
- fork 子会话为单 turn 内容 fixture 子会话，保证正对照的子会话文件可断言。

## 计划录制布局

`snapshots/session/agent-hierarchy-lead-scope-fail-closed/`：`snapshot.yml`（`profile: headless`、`recording: authored`、`composition: lead-scope-fail-closed`）；`session.jsonl`（root controller，仅作为组合入口）、`session.1..4.jsonl`（四个 lead 探针会话；录制形态按开放问题定案）、各自 `replay.override.json`。

## 剧本（replay 步骤）

1. lead-1 调用 `fork` → 成功，产生子会话（正对照：已批 scope 委派放行）。
2. lead-1 调用 `spawn_teammate` → pre-execute 拒绝：`agent-hierarchy: role "lead" cannot execute "spawn_teammate"`（reviewer 语义并入 lead face，与 scope 无关）。
3. lead-2 调用 `subagent` → `agent-hierarchy: plugin scope "plugin-b" is not in the approved set of lead "lead-2"`（列名但越集）。
4. lead-3 调用 `subagent` → `agent-hierarchy: lead "lead-3" has no plugin scope binding and cannot delegate`（缺 pluginId 绑定）。
5. lead-4 调用 `subagent` → `agent-hierarchy: plugin scope "plugin-b" is not in the approved set of lead "lead-4"`（未列名 lead 的批准集为空，fail-closed 文本与越集同形）。
6. 每次拒绝后断言：无新子会话文件、agent 注册表无新条目、拒绝先于工具体。

## 可观察通过标准

- 步骤 2–5 的拒绝文本与 guard.ts 逐字符一致；三条 fail-closed 路径（未列名/缺绑定/越集）各有独立探针。
- 唯一成功的委派来自 scope 已批的 lead-1；拒绝路径零子代理产生。

## 环境与安全

合成 agentId/pluginId（`plugin-a/b/c` 均非真实插件名）；子会话无文件副作用。

## 开放问题

- 多个 lead 会话的录制形态（多次 replay run 每次绑一个 lead，vs 控制器 spawn 的子会话由宿主绑定为 lead）由组合挂载波定；守卫按 agentId 现场解析，两种形态断言相同。
- `fork` 与 `subagent` 在 seam 侧的 provider 差异（spawn/continuable 等）只影响子会话文件命名，不影响守卫断言；录制取其一为主、另一个作可选探针。
