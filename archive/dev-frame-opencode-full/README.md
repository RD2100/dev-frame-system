# Dev-Frame OpenCode

**Agent Runtime 治理 Monorepo** — 证据优先、GPT 审查、fail-closed 的 AI 辅助软件工程流水线。

## 当前状态

[![Smoke](https://img.shields.io/badge/smoke-5%2F5%20PASS-brightgreen)](smoke_report.txt)
[![Tests](https://img.shields.io/badge/tests-748%20passed-brightgreen)](smoke_report.txt)
[![Production](https://img.shields.io/badge/production-%E5%B7%B2%E6%99%8B%E5%8D%87-blue)](CURRENT_ROUTE.json)

```
production_promotion_approved: true          # 生产晋升已完成
broader_real_chain_testing_unblocked: true   # 广域真实链路已解锁
hardcoded_driver_replacement_approved: true  # 硬编码驱动替换已授权
Smoke: 5/5 PASS | 748 测试通过 (532 核心 + 216 端到端)
```

## 子项目

| 项目 | 路径 | 说明 |
|------|------|------|
| **codegraph** | `codegraph/` | 本地优先的代码智能库（tree-sitter），提供 CLI 和 MCP 服务端，为 AI Agent 暴露知识图谱 |
| **ai-workflow-hub** | `ai-workflow-hub/` | OpenCode 驱动的编码自动化 — 4 节点流水线（human_gate / executor / tester / fixer），支持 SADP TaskSpec |
| **ai-workflow-hub-e2e** | `ai-workflow-hub-e2e/` | 端到端证据完整性与门禁测试 — API 集成、完整性看门狗、模型验证、SHA256 签名 |

## 架构

```
codegraph (MCP 就绪) → ai-workflow-hub (核心状态机) → ai-workflow-hub-e2e (证据完整性)
```

## 快速开始

```bash
# 一键验证所有项目
python smoke_test.py

# 单独检查
cd codegraph && npx tsc --noEmit           # TypeScript 类型检查
cd ai-workflow-hub && pytest tests/ -v     # 532 核心测试
cd ai-workflow-hub-e2e && pytest tests/ -v # 216 端到端测试
```

## 治理模型

- **证据优先**：所有声明必须有 ZIP 证据包中的可验证证据
- **Fail-Closed**：review_unverified / RID 不匹配 / CDP 不可用 → 立即停止
- **GPT 为最终审查权威**：所有授权必须通过 GPT 审查的证据包
- **证据只追加**：历史证据不可删除、移动、重命名
- **分阶段解锁**：blocked items 通过 P0-P15 顺序流水线逐步解锁

## Guard 系统

10/10 提交脚本通过 `tools/submission_guard.py` 受保护：

| 函数 | 用途 |
|------|------|
| `pre_submit_gate()` | 提交前去重检查（30s 冷却，最多 3 次重试） |
| `record_submission_result()` | 提交后追加日志记录，fail-closed |
| `check_before_submit()` | 飞行前提交校验 |
| `record_submission()` | 底层日志写入 |
| `get_submission_summary()` | 诊断聚合查询 |

## 环境要求

- Python >= 3.10
- Node.js >= 20.0.0
- `codegraph/node_modules/` 已安装（`npm ci`）
- `ai-workflow-hub` 依赖已安装（`pip install -e ".[dev]"`）
- `ai-workflow-hub-e2e` 依赖已安装（`pip install -e .`）

## 许可证

MIT
