# Cold Start 指南

## 什么是 Cold Start

Cold Start 指一个新 Agent 或新项目从零开始接入 DevFrame Control Plane 的过程。

## Cold Start 流程

### 1. Agent 接入

新 Agent 首次接触项目时应按以下顺序阅读：

1. `README.md` — 了解项目是什么
2. `PROJECT_BOOTSTRAP.md` — 了解当前阶段和禁止事项
3. `CURRENT_STATE.yaml` — 了解当前状态
4. `NEXT_TASK.md` — 了解下一步要做什么
5. `docs/architecture.md` — 了解架构

**验收标准**：不看聊天记录，只读以上文件，就能说清项目用途和下一步。

### 2. 项目初始化

```bash
git clone https://github.com/RD2100/devframe-control-plane.git
cd devframe-control-plane
python -m control_plane init --template code_project my-project
```

### 3. 模板选择

| 使用场景 | 模板 |
|----------|------|
| 软件工程项目 | `code_project` |
| 论文迭代审查 | `paper_iteration` |

### 4. 验证

```bash
python -m control_plane doctor
```

检查项：文件完整性、状态格式、安全边界、敏感信息、依赖可用性。
