# Project Bootstrap

REVIEW_RUN_ID: g0-bootstrap-skeleton-v1-20260605

## 仓库目标

DevFrame Control Plane 是 dev-frame-opencode 生态的工作流整合层。它将散落的 Agent 组件（证据构建、Guard、CDP 通信、状态机）整合成声明式流水线引擎。

## 当前阶段

**v0.1.0-rc — Released, Feature Complete**

G0-G8A (Control Plane 基础 + CDP + Handoff Protocol)、H1-H6 (产品化/治理)、T1-T3 (Context Sync Auto) 全部 accepted。项目已从初始 Bootstrap Skeleton 演进为完整的 evidence-first 工作流控制平面。

## 下一阶段

推荐后续方向（非 release blocker）：
- release documentation polish / docs sync
- optional H5 synthetic-only post-release hardening
- dev-frame-opencode real integration
- paper workflow expansion design

## 禁止事项

- 不删除、移动、重命名 evidence 文件
- 不修改 guard 逻辑或 submission guard 行为
- 不默认开启 live CDP
- 不含真实密钥、cookie、session
- 不含用户私有材料
- 不含真实论文内容

## 关键文件

| 文件 | 用途 |
|------|------|
| README.md | 项目概述 |
| QUICKSTART.md | 用户快速开始指南 |
| INSTALL.md | 安装说明 |
| PROJECT_BOOTSTRAP.md | 本文档 |
| CURRENT_STATE.yaml | 当前阶段状态 |
| NEXT_TASK.md | 下一步任务 |
| SAFETY_BOUNDARIES.md | 安全边界 |
| PHASE_LEDGER.md | 阶段记录 |
| EVIDENCE_INDEX.md | 证据索引 |
| HANDOFF.md | 跨会话交接文档 |
| RELEASE_CHECKLIST.md | 发布检查清单 |
| .gitignore | 排除规则 |
| .env.example | 环境变量模板 |

## 模板目录

| 目录 | 用途 |
|------|------|
| templates/code_project/ | 软件工程项目模板 |
| templates/paper_iteration/ | 论文迭代审查模板 |
| templates/context_handoff/ | 上下文交接模板 |
| examples/ | 示例工作流说明 |
| docs/ | 架构与概念文档 |
