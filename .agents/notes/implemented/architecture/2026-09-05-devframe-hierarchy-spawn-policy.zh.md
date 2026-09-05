# Agent Note：DevFrame 三层 spawn 策略固化为各档委托覆盖值

Status: implemented

[English](2026-09-05-devframe-hierarchy-spawn-policy.md) | 中文

## 问题

DevFrame 的产品规则「总控建组长，组长建执行 Agent，执行 Agent 禁建子 Agent」此前只是机制：subagent seam 已支持每次 spawn 的 `toolFilter` 与绝对 `maxDepth` 上限，但没有任何东西规定每一档的 spawn 必须携带哪些覆盖值。因此被 spawn 出来的执行 Agent 默认仍然握着可用的委托工具，三层结构始终只是编排约定，而不是有测试锚定的能力。

## 决策

[`packages/experimental/devframe/src/hierarchy/index.ts`](../../../../packages/experimental/devframe/src/hierarchy/index.ts) 中的 `devframeSpawnOverrides(tier)` 把各档策略固化为分离的委托请求覆盖值：每次 DevFrame spawn 都把 `maxDepth` 钉在树预算 `2` 上（总控 0、组长 1、执行 2），执行 Agent 的 spawn 还通过 `toolFilter.deny` 拒绝委托工具（默认名 `subagent`，改名部署可覆盖）。强制仍留在 seam 内、发生在执行器上：工具注册表在执行时以 `UNKNOWN_TOOL` 拒绝被禁工具（而非仅提示面缺席），`SubagentDepthError` 在任何子 Agent 发布前拒绝超出预算的 spawn，可继续描述符持久化 `toolFilter` 使冷恢复重新应用它。`packages/subagent` 中的测试锚定了执行器级拒绝、深度预算拒绝、父子 `sendMessage` 方向授权，以及冷恢复后的角色。

## 已考虑的替代方案

- **给 subagent seam 的 spawn 请求扩展角色概念。** 否决：两种强制机制在 seam 中都已存在，角色字段只会重复调用方用现有字段就能表达的策略，并在不新增强制的情况下拓宽 seam 契约。
- **只靠部署工具配置的深度收口。** 否决其作为唯一路径：委托工具默认 `maxDepth` 是 `3`，仅靠深度强制要求每个部署都记住一次配置变更；deny 过滤器让拒绝成为被 spawn 子 Agent 的内在属性，与工具配置无关。

## 后果

- DevFrame 父 Agent 必须在每次 spawn 时展开这些覆盖值；省略它们的 spawn 保持 seam 默认值，所以该策略是库契约，不是 seam 强加的东西。
- 执行 Agent 保留 `send_message` 与控制工具：deny 列表只点名委托工具，因此沿授权的父子路由向组长汇报仍然可用。
- 冷恢复保留角色，因为描述符携带过滤器；恢复后的执行 Agent 在执行器上仍被拒绝 spawn 工具，且仍被钉在持久深度下限上。
