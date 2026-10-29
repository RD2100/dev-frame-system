# dev-frame-opencode

> Monorepo: codegraph + ai-workflow-hub + ai-workflow-hub-e2e
> Phase: M1 完成，M2 待定义
> Last updated: 2026-05-30

## Active Context

三个子项目全部绿色，13个风险已修复，OpenCode 重构完成。当前处于维护观察期。

## Projects

| 项目 | 路径 | 描述 | 测试 |
|------|------|------|------|
| codegraph | `codegraph/` | tree-sitter 代码智能库 + MCP 知识图谱服务 | tsc 0 错误 |
| ai-workflow-hub | `ai-workflow-hub/` | 4 节点 pipeline (human_gate/executor/tester/fixer) | 77 核心测试 |
| ai-workflow-hub-e2e | `ai-workflow-hub-e2e/` | E2E 证据完整性: API/模型/签名/SHA256 | 175 测试 |

## Development Plan

详见 [MVP计划](docs/mvp-plan.md) 和 [开发里程碑](docs/process.md)

## Governance

- 运行: `python smoke_test.py` 验证全项目健康
- AGENTS.md 入口: [AGENTS.md](AGENTS.md)
- RD2100 Agent Runtime: D:\agent-acceptance\
