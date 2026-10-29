# Minimal Code Workflow Example

> 本目录为示例说明，不包含可执行代码。

## 场景

一个最小化的软件工程项目流水线：

1. **G0 Bootstrap** — 项目骨架初始化
2. **G1 Pipeline Definition** — 定义流水线 YAML
3. **Authorization** — GPT 授权代码变更
4. **Execution** — 执行变更 + 测试
5. **Closure** — 提交证据闭合包

## 对应模板

`templates/code_project/`

## 关键文件

- `PIPELINE.yaml` — 定义阶段和依赖
- `CURRENT_STATE.yaml` — 跟踪 blocked items
- `EVIDENCE_SPEC.yaml` — 定义证据要求

## 使用方式（未来）

```bash
python -m control_plane init --template code_project my-project
cd my-project
# 编辑 PIPELINE.yaml 定义自定义阶段
python -m control_plane run PIPELINE.yaml
```
