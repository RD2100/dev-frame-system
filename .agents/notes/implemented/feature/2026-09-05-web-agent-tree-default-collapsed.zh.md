# Agent Note: 项目 Agent 树默认收起

Status: implemented

[English](2026-09-05-web-agent-tree-default-collapsed.md) | 中文

## 问题

分组侧边栏可能包含一个总控、多个委派组长以及更深层的执行 Agent。挂载时展开每条 Agent 行会让大型项目树在用户选择分支前就占满侧边栏。

## 决策

`dsh-client-ui-workspace` 让所有带有直接下级的 Agent 行默认收起。浏览器在临时状态中保存用户打开的行 id，现有箭头继续切换一层直接下级。Workspace 分组的展开状态保持独立，因此打开 Workspace 只显示顶层 Agent 行，不会自动显示它们的后代。

同一规则适用于每个 Agent 层级。用户可以先打开总控，再打开其一个委派组长，而无关分支保持收起。只有已经打开的行才会公布 catalog 成员，因此默认投影不会订阅后代 catalog。

## 已考虑的替代方案

**让每条 Agent 行默认展开。** 拒绝：拥有大量委派 Agent 的项目会立即变得嘈杂，用户必须先收起分支才能找到目标。

**只收起最顶层总控。** 拒绝：带有执行 Agent 的嵌套组长仍会意外展开，同一棵树在不同层级会有不同表现。

**把 Agent 展开状态持久化到 Workspace 视图 store。** 拒绝：本次需求是紧凑的初始投影，现有浏览器本地状态已经能在树挂载期间保留活动分支，无需增加持久化视图字段。

## 后果

初始侧边栏显示 Workspace 的顶层 Agent 行及其状态，不显示后代。用户需要点击箭头查看每一层；点击行仍会打开该 Agent 的 Session，并切换该行的直接下级。Agent 展开状态在浏览器树卸载时重置；Workspace 分组的展开状态保持现有持久化行为。

## 验证

`pnpm exec vitest run packages/client/ui-workspace/tests/workspace-browser.client.spec.tsx packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx` 覆盖默认收起的树和手动一层展开。浏览器验证前使用 `pnpm --filter @deepseek-ai/dsh-client-ui-workspace bundle` 重新构建客户端 bundle。
