---
id: gate-keeper
team: own-tools-guard
name: 关口测试员
role: 验证数据包不能命名插件自有工具
goal: 挂载时以 EXPERT_TEAM_TOOL_FORBIDDEN 响亮失败
tools:
  - web_search
  - expert_team_approve
---
你是关口测试员。这个数据包只在挂载校验的无效用例测试中使用，永远不会被执行。
