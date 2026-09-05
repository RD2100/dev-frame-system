---
description: "AT2B-02 recorded-session 场景草案：深度预算 2 双保险——controller→lead→worker 三代委派走通后，depth-2 会话（无论绑定角色）再委派被本包守卫独立拒绝，与 seam 的 SubagentDepthError 构成两半。"
kind: "acceptance-scenario-draft"
---

# AT2B-02 场景草案：深度预算 2 双保险

包已在 main（agent-hierarchy 合并提交 `9d0bea4b37`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2b-runner-checklist](../../../../.agents/devframe/accept/at2b-runner-checklist.md) `AT2B-02`；P22 验收矩阵 `AT1-01` 的 P02 责任面（[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- `AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET = 2` 是固定安全不变量（controller=0、lead=1、worker=2），不是配置字段。
- 双保险：seam 的 `SubagentDepthError` 是第一半（已由 `snapshots/session/subagent-depth-two-rejection/` 钉住）；本包 pre-execute 守卫是第二半、独立拒绝路径——本场景钉第二半。
- 守卫检查顺序为 deny face → depth → lead scope：深度拒绝只对 deny face 不覆盖委派工具的角色可见（depth-2 会话绑 lead 即可命中深度文本）；深度检查先于 scope，深度拒绝文本不涉 scope。
- README 契约：depth-2 会话无论绑定什么角色都不得委派；本场景以 depth-2 绑 lead 证明"独立于角色面"。

## 前提（宿主集成）

- 组合同 AT2B-01（session-identity + hierarchy + 探针工具面）；`cordis.snapshot.yml` 保留 seam `maxDepth: 2` 覆盖（照抄 `subagent-depth-two-rejection/cordis.snapshot.yml` 的 tool-subagent 段），使两半在组合中并存。
- 绑定种子接缝预置：root 会话绑 `controller`；depth-1 子会话绑 `lead`（`pluginId: plugin-a`，`leadPluginScopes: { lead-1: ['plugin-a'] }`）；depth-2 子会话绑 `lead`（同 scope）。
- 子会话由真实 seam spawn 产生（`run_in_background: false`），保证 delegationDepth 写入持久 header、`delegationDepthOf` 走真实路径。

## 计划录制布局

`snapshots/session/agent-hierarchy-depth-budget-double-guard/`：`snapshot.yml`（`profile: headless`、`recording: authored`、`composition: depth-double-guard`、header pin 同 `subagent-depth-two-rejection`）；`session.jsonl`（root controller spawn depth-1）、`session.1.jsonl`（depth-1 lead spawn depth-2）、`session.2.jsonl`（depth-2 尝试委派被拒）、每个会话一份 `replay.override.json`。

## 剧本（replay 步骤）

1. root（depth-0，controller）调用 `subagent` 生成 depth-1 子会话 → 成功（正对照：预算内第一代）。
2. depth-1（lead，scope 已批）调用 `subagent` 生成 depth-2 子会话 → 成功（正对照：预算内第二代；此步同时压 lead scope 放行路径）。
3. depth-2 会话调用 `subagent` → pre-execute 错误结果：`agent-hierarchy: delegating from depth 2 would create a child at depth 3 beyond the absolute budget 2`；无任何子会话产生（无 `session.3.jsonl`、agent 注册表无新条目）。
4. depth-2 会话改为调用 `project_read` → 正常执行（预算只拦委派，不拦受控面之外的工具）。

## 可观察通过标准

- 步骤 3 拒绝文本与 guard.ts 的深度理由逐字符一致，且先于工具体（seam 未被触达、无 `SubagentDepthError` 文本——第二半先拒绝正是双保险的观察点；第一半由既有 depth-two 场景持有）。
- depth-0/1 两次委派成功，证明预算边界恰在 2→3 而非更早。
- 组合中 seam `maxDepth: 2` 未被移除：两层拒绝路径并存、互不替代。

## 环境与安全

子会话为内容 fixture 会话，不落工作区文件；合成身份与 scope。

## 开放问题

- depth-2 绑 worker 的变体（命中 deny face 文本而非深度文本）是否加录：检查顺序已由包测试持有，录制保持单绑定形态，待 snapshots 属主定。
- 子会话绑定写入时机（spawn 前种子 vs `agent/created` 监听）不影响守卫裁决（角色每执行现场解析），录制形态由组合挂载波定。
